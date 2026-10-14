"""Envanter sayfası sözleşmeleri — ``docs/envanter.html`` kaynaktan sapamaz.

Bu test dosyası, "eksik envanter" kusurunun SESSİZCE geri gelmesini engeller:

1. **Güncellik:** sayfa, ``scripts/generate_inventory_page.py --check`` ile
   bayat sayılmaz (yani docstring/kod değişip sayfa unutulursa test düşer).
2. **A listesi (30 dosya) açıklamasız kalamaz:** envanterde adı olup açıklaması
   olmayan dosyaların HER BİRİNDE modül docstring'i olmak zorundadır.
3. **B listesi (31 dosya) sayfada görünmek zorundadır:** çekirdek dosyalar
   (``agent_core/task_executor.py``, ``backend/api.py``) dâhil.
4. **Sayılar kaynaktan gelir:** ``.env.example`` ayar sayısı ve dekoratörle
   tanımlı uç nokta sayısı sayfadaki satır sayısıyla BİREBİR aynı olmalı;
   sayfa elle yazılmış sayı taşıyamaz.
5. **Her dosya tam bir kez:** sayfa tek listeleme ilkesini korur (mükerrer satır
   aramayı ve sayacı bozar).

Üretici modülü içe aktarılır (``importlib``), böylece A/B listelerinin TEK
kaynağı korunur: liste değişirse testler de aynı yerden okur.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE = REPO_ROOT / "docs" / "envanter.html"
GENERATOR = REPO_ROOT / "scripts" / "generate_inventory_page.py"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
API = REPO_ROOT / "backend" / "api.py"
LANGUAGE_ROUTES = REPO_ROOT / "backend" / "routes" / "language.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("pineal_inventory_generator", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_generator_exists_and_page_is_not_stale():
    """Sayfa kaynaktan üretilmiş olmalı; bayatsa bu test DÜŞER."""
    assert GENERATOR.is_file(), "envanter üreticisi yok: scripts/generate_inventory_page.py"
    proc = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        "docs/envanter.html kaynakla uyuşmuyor (bayat). "
        "Yeniden üret: python scripts/generate_inventory_page.py\n"
        f"stdout: {proc.stdout[-400:]}\nstderr: {proc.stderr[-400:]}"
    )


def test_every_category_a_file_has_a_module_docstring():
    """A listesindeki 30 dosya yeniden 'açıklamasız' hâle düşemez."""
    gen = _load_generator()
    assert len(gen.CATEGORY_A) == 30, (
        f"A listesi 30 dosyaydı, şimdi {len(gen.CATEGORY_A)}: liste daralıyorsa "
        "gerekçesi burada görünmeli"
    )
    missing = []
    for rel in gen.CATEGORY_A:
        path = REPO_ROOT / rel
        assert path.is_file(), f"A listesindeki dosya yok: {rel}"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if not ast.get_docstring(tree):
            missing.append(rel)
    assert not missing, f"modül docstring'i eksik (envanterde açıklamasız kalır): {missing}"


def test_category_b_paths_are_visible_in_the_page():
    """B listesindeki dosyalar sayfada GERÇEKTEN listelenir (ad + satır)."""
    gen = _load_generator()
    page = PAGE.read_text(encoding="utf-8")
    assert len(gen.CATEGORY_B) >= 31, (
        f"B listesi 31 dosyaydı, şimdi {len(gen.CATEGORY_B)}"
    )
    absent = [rel for rel in gen.CATEGORY_B if rel not in page]
    assert not absent, f"sayfada görünmeyen B dosyaları: {absent}"

    # Çekirdek iddiası: bu ikisi envanterin en kritik satırlarıdır.
    for critical in ("agent_core/task_executor.py", "backend/api.py"):
        assert critical in page, f"çekirdek dosya sayfada yok: {critical}"


def test_env_settings_are_counted_from_the_file_not_by_hand():
    """.env.example'daki her ayar sayfada bir satır olmalı (uydurma sayı yasak)."""
    settings = [
        line.split("=", 1)[0].strip()
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if re.match(r"^[A-Z][A-Z0-9_]*=", line)
    ]
    assert len(settings) == 98, (
        f".env.example ayar sayısı {len(settings)}; sayfa/başlık metinleri 98 diyor — "
        "ayar eklerken sayfayı da üret"
    )
    page = PAGE.read_text(encoding="utf-8")
    rows = re.findall(r'data-flags="env"', page)
    assert len(rows) == len(settings), (
        f"sayfada {len(rows)} ayar satırı var, dosyada {len(settings)} ayar"
    )
    absent = [name for name in settings if f'>{name}</td>' not in page]
    assert not absent, f"sayfada açıklanmayan ayarlar: {absent[:10]}"


def test_endpoint_rows_match_real_decorators():
    """Uç nokta sayısı dekoratörlerden sayılır; sayfa şişemez/eksilemez."""
    decorators = re.findall(r'@app\.(?:get|post|put|delete|patch|websocket)\("', API.read_text(encoding="utf-8"))
    decorators += re.findall(
        r'^\s*@app\.(?:get|post|put|delete|patch)\("', LANGUAGE_ROUTES.read_text(encoding="utf-8"), re.M
    )
    page = PAGE.read_text(encoding="utf-8")
    rows = re.findall(r'data-flags="endpoint"', page)
    assert len(rows) == len(decorators), (
        f"sayfada {len(rows)} uç satırı, kodda {len(decorators)} dekoratör"
    )


def test_each_file_is_listed_exactly_once():
    """Tek listeleme ilkesi: mükerrer satır aramayı ve sayacı bozar."""
    page = PAGE.read_text(encoding="utf-8")
    paths = re.findall(r'<td class="pth"><span class="mono">([^<]+)</span>', page)
    dupes = [p for p, n in Counter(paths).items() if n > 1]
    assert not dupes, f"sayfada birden çok kez listelenen dosyalar: {dupes[:10]}"


def test_page_documents_the_api_split_it_triggered():
    """Tavan çakışması ve çözümü sayfada yazılı olmalı (denetim izi)."""
    page = PAGE.read_text(encoding="utf-8")
    assert "backend/routes/language.py" in page
    assert "API-BÖLME 2" in page
    assert "5.916" in page, "tavana düşürme kararı sayfada yazılı olmalı"
