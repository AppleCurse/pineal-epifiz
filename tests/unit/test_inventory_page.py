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
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

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
    page = PAGE.read_text(encoding="utf-8")
    #: [DENETİM 2026-10-14 · B12] Sihirli sayı (eskiden 98) KALDIRILDI: sayı
    #: kaynaktan sayılır ve sayfanın KENDİ başlığındaki sayıyla karşılaştırılır.
    #: Böylece `.env.example`'a ayar eklemek testi elle güncellemeyi gerektirmez;
    #: sayfa bayatlarsa yine kırmızıya döner (uydurma sayı yasağı korunur).
    stated = {int(s) for s in re.findall(r"(\d+)\s*ayarın tek tek anlamı", page)}
    assert stated, "sayfa başlığında ayar sayısı yazmıyor (üretici metni değişmiş olabilir)"
    assert stated == {len(settings)}, (
        f"sayfa {sorted(stated)} diyor, kaynakta {len(settings)} ayar var — "
        "ayar eklerken sayfayı da üret: python scripts/generate_inventory_page.py"
    )
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


# --------------------------------------------------------------------------- #
# DENETİM 2026-10-14 düzeltmelerinin kilitleri (bulgular 2 ve 3)
# --------------------------------------------------------------------------- #

def _gercek_tarama() -> list[str]:
    """BAĞIMSIZ tarama: `tests/` altındaki test modülleri — takip edilen + edilmeyen.

    Test kendi taramasını yapar (üreticinin fonksiyonunu çağırmaz); böylece
    sayı gerçekten repo durumuna karşı doğrulanır. Kapsam: `git ls-files`
    (izlenen) + `ls-files --others --exclude-standard` (yeni eklenmiş, henüz
    commit edilmemiş dosyalar) — üreticiyle aynı evren.
    """
    def _git(*args: str) -> list[str]:
        proc = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout.splitlines()

    yollar = _git("ls-files") + _git("ls-files", "--others", "--exclude-standard")
    return [
        y
        for y in yollar
        if y.startswith("tests/") and y.endswith(".py") and y.rsplit("/", 1)[-1].startswith("test_")
    ]


def test_page_test_count_is_the_canonical_measure():
    """[Bulgu 2] Sayfadaki 'test modülü' sayısı GERÇEK taramayla aynı olmalı."""
    kanonik = len(_gercek_tarama())
    page = PAGE.read_text(encoding="utf-8")
    eslesme = re.search(r'<div class="stat"><b>(\d+)</b><span title="tanım: tests/ altındaki', page)
    assert eslesme, "sayfada tanımlı 'test modülü' istatistiği bulunamadı"
    assert int(eslesme.group(1)) == kanonik, (
        f"sayfa {eslesme.group(1)} diyor, gerçek tarama {kanonik}: test sayısı ölçümden sapıyor"
    )
    # Sayfadaki stat, tanımı satır içinde taşımalı (okuyucu hangi ölçü olduğunu görsün).
    assert "tests/ ağacında toplam" in page


def test_generator_owns_the_single_definition():
    """[Bulgu 2] Kanonik tanım üreticide TEK yerde yaşar; ölçüm ondan gelir."""
    gen = _load_generator()
    entries = gen.build_entries()
    kanonik = gen.canonical_test_modules(entries)
    assert len(kanonik) == len(_gercek_tarama()), "üretici ölçümü ile gerçek tarama ayrıştı"
    # `tests/` ağacı ölçüsü AYRI etiketlenir; ikisi karıştırılmamalı.
    assert len(gen.tests_tree(entries)) > len(kanonik), "ağaç ölçüsü modül ölçüsünden büyük olmalı"


def test_notes_file_carries_no_hand_written_test_count():
    """[Bulgu 2] ``inventory_notes.json`` elle sayı taşıyamaz: yer tutucu kullanır."""
    notes = json.loads((REPO_ROOT / "docs" / "inventory_notes.json").read_text(encoding="utf-8"))
    tests_desc = notes["folder_descriptions"]["tests"]
    assert "{test_modulu}" in tests_desc, (
        f"not dosyası yer tutucu yerine elle sayı taşıyor: {tests_desc!r}"
    )
    assert not re.search(r"\b\d+(?:\.\d{3})? test dosyas", tests_desc), (
        "not dosyasında elle yazılmış test sayısı var"
    )
    page = PAGE.read_text(encoding="utf-8")
    assert "{test_modulu}" not in page, "doldurulmamış yer tutucu sayfaya sızmış"
    kanonik = len(_gercek_tarama())
    assert f"{kanonik} test modülü" in page, f"kanonik sayı ({kanonik}) sayfada görünmeli"


def test_changelog_uses_the_same_definition():
    """[Bulgu 2] CHANGELOG deyimi de kanonik ölçüyü kullanmalı — üçüncü sayı yasak.

    CHANGELOG'da 'N test' geçen her satır, ya kanonik test modülü sayısını ya da
    açıkça başka tanımı (ör. 'N test dosyası: tests/ ağacı') yazmak zorundadır.
    """
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    kanonik = len(_gercek_tarama())
    # Yalnız REPO ÖLÇEKLİ dosya iddiaları ("234 test modülü" / "N test dosyası")
    # kapsamdadır. "(25 test)" gibi dosya adına bağlı ifadeler o dosyanın test
    # fonksiyonu sayısıdır — ayrı ölçü, karışıklık yaratmaz.
    for eslesme in re.finditer(r"(\d[\d.]*)\s+test (?:modülü|dosyas[ıi])", changelog):
        sayi = int(eslesme.group(1).replace(".", ""))
        baglam = changelog[max(0, eslesme.start() - 120) : eslesme.end() + 120]
        if sayi < 100:
            continue  # küçük sayılar dosya/alt-küme kapsamlıdır ("+3 test dosyası" gibi)
        if "ağac" in baglam or "tüm dosya" in baglam:
            continue  # açıkça tanımlanmış AĞAÇ ölçüsü (ikinci ölçü, karışıklık yok)
        assert sayi == kanonik, (
            f"CHANGELOG'da repo ölçekli test dosyası sayısı {sayi}; kanonik ölçü {kanonik}. "
            "Ya düzelt ya da tanımı açıkça yaz."
        )


def test_git_raises_instead_of_returning_empty_on_failure():
    """[Bulgu 3] `git` başarısız olursa BOŞ çıktı değil, AÇIK hata döner."""
    gen = _load_generator()
    with pytest.raises(gen.GitError):
        gen.git("rev-parse", "--verify", "refs/heads/kesinlikle-yok-boyle-bir-dal")


def test_main_returns_2_and_writes_nothing_when_git_fails(monkeypatch, tmp_path):
    """[Bulgu 3] git hatasında sayfa HİÇ yazılmaz — eksik veriyle 'geçerli' sayfa yok."""
    gen = _load_generator()
    hedef = tmp_path / "envanter.html"
    monkeypatch.setattr(gen, "OUT", hedef)
    monkeypatch.setattr(sys, "argv", ["generate_inventory_page.py"])
    monkeypatch.setattr(gen, "build_entries", lambda: (_ for _ in ()).throw(gen.GitError("test")))
    assert gen.main() == 2
    assert not hedef.exists(), "git hatasına rağmen sayfa yazıldı"


def test_page_lists_exactly_the_repo_universe():
    """Sayfanın dosya evreni = izlenen + izlenmeyen (yok sayılmayan) dosyalar.

    [CI KIRMIZI KÖK NEDENİ · 2026-10-14] `docs/pineal_envanter.zip` `.gitignore`
    kapsamındayken üretilen sayfa onu LİSTELEMİYORDU; `git add -f` ile izlenir
    olunca dosya evrene girdi ve sayfa bayatladı — CI `--check` adımı kırmızı oldu.
    Bu test o sınıfı kapatır: sayfa, üretildiği andaki evreni BİREBİR yansıtmalı.
    """
    gen = _load_generator()
    evren = {
        yol
        for yol in gen.git("ls-files").splitlines()
        + gen.git("ls-files", "--others", "--exclude-standard").splitlines()
        if yol
    }
    evren.discard("docs/envanter.html")  # öz-referans kilidi: sayfa kendini saymaz
    sayfa = set(re.findall(r'<td class="pth"><span class="mono">([^<]+)</span>', PAGE.read_text(encoding="utf-8")))
    assert sayfa == evren, (
        f"sayfada olmayan dosyalar: {sorted(evren - sayfa)[:10]} · "
        f"evrende olmayan satırlar: {sorted(sayfa - evren)[:10]}"
    )


def test_binary_files_carry_no_fake_line_count():
    """İkili/arşiv dosya 'satır' taşımaz; sayfada `ikili` yazar.

    [2026-10-14] 4 MB'lık arşiv "14.965 satır" görünüyordu: sayı, okuyucuya sahte
    bir metin izlenimi veriyor ve `toplam satır` istatistiğini şişiriyordu.
    """
    gen = _load_generator()
    assert gen.is_binary_path("docs/pineal_envanter.zip") is True
    assert gen.loc_of(REPO_ROOT / "docs" / "pineal_envanter.zip") == 0
    assert gen.is_binary_path("backend/routes/language.py") is False

    page = PAGE.read_text(encoding="utf-8")
    for arsiv in ("docs/pineal_envanter.zip",):
        eslesme = re.search(
            re.escape(f'<span class="mono">{arsiv}</span>') + r'.*?<td class="loc">([^<]*)</td>',
            page,
            re.S,
        )
        assert eslesme, f"{arsiv} sayfada listelenmeli (izlenen dosya)"
        assert eslesme.group(1) == "ikili", (
            f"{arsiv} hâlâ sayı gösteriyor: {eslesme.group(1)!r}"
        )


def test_entry_order_is_independent_of_tracking_state(monkeypatch):
    """[DENETİM 2026-10-14 · B16] Sayfa sırası `git add`'e bağlı OLAMAZ.

    Eskiden liste `tracked + untracked` idi: yeni bir dosya commit'lendiği anda
    alfabetik yerine SONA düşüyor, sayfa yalnız bu yüzden değişiyor ve
    `--check` "bayat" diyordu (kirli ağaçta üret → temiz ağaçta doğrula =
    CI kırmızısı). Sıra artık izleme durumundan bağımsız, yalnız yola göre.
    """
    module = _load_generator()
    seen: list[tuple[str, ...]] = []

    def _fake_git(*args: str) -> str:
        # İkinci çağrı (untracked) bilinçli olarak ters sırada verilir.
        seen.append(tuple(args))
        if "--others" in args:
            return "docs/reports/KAPASITE_ACIGI_RAPORU_2026-10-14.md\n"
        return "scripts/kapasite_denetimi_probe.py\nbackend/api.py\n"

    monkeypatch.setattr(module, "git", _fake_git)
    entries = module.build_entries()
    paths = [e["path"] for e in entries]
    assert paths == sorted(paths), f"sıra determinist değil: {paths[:5]}"
    assert seen, "üretici git çağırmadı"
