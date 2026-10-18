"""[P9 · DOKÜMAN YENİLEME] README'nin SAYILARI kodla aynı olmalı.

README "herkesin anlayabileceği bir dilde" yazıldı; ama düz dil, **yalan** demek
değildir. Bu dosya README'de geçen sayıları (ajan, yetenek, motor, API ucu,
envanter) **canlı koddan ölçer** ve eşleştirir:

  * Kod değişirse (yeni ajan/yetenek/uç eklenirse) bu test KIRMIZIYA döner →
    README sessizce geride kalamaz.
  * README'deki iddia uydurulursa test KIRMIZIYA döner.

Ölçüm kaynakları:
  * ajanlar      → `agent_core/task_executor.py` (`self.agents` sözlüğü)
  * yetenekler   → `agent_core.capabilities.registry.bootstrap()`
  * motorlar     → `agent_core/engines/*_engine.py` (7 dalga motoru)
  * API uçları   → `backend.api.app.routes`
  * envanter     → `scripts/generate_inventory_page.build_entries()` (haritanın
                   kendi dosya sayımı — README ile aynı kaynak)
"""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"

#: README'de sayıların geçtiği KİLİTLİ biçimler (metin değişirse test kırılır).
_AGENT_MARK = r"\*\*(\d+)\s+görev ajanı\*\*"
_CAPABILITY_MARK = r"\*\*(\d+)\s+yetenek\*\*"
_ENGINE_MARK = r"\*\*(\d+)\s+dalga motoru\*\*"
_ENDPOINT_MARK = r"\((\d+)\s+HTTP ucu"


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def _readme_number(pattern: str) -> int:
    match = re.search(pattern, _readme())
    assert match, (
        f"README'de beklenen sayı ifadesi yok: {pattern!r} — "
        "doküman yenilemesinde sayı biçimi bozulmuş olabilir"
    )
    return int(match.group(1))


def _inventory_entries() -> list:
    """Envanter üretecinden dosya listesini al (haritanın KENDİ ölçümü)."""
    spec = importlib.util.spec_from_file_location(
        "_inventory_generator", REPO_ROOT / "scripts" / "generate_inventory_page.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_entries()


# ─────────────────────────────────────────────────────────────────────────────
# 1. AJAN SAYISI
# ─────────────────────────────────────────────────────────────────────────────
def _registered_agents() -> list[str]:
    """Yürütücünün kaydettiği ajan adları (`self.agents = {...}` sözlüğü)."""
    source = (REPO_ROOT / "agent_core" / "task_executor.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        attrs = [t.attr for t in node.targets if isinstance(t, ast.Attribute)]
        if ("agents" in targets or "agents" in attrs) and isinstance(node.value, ast.Dict):
            for key in node.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    names.append(key.value)
    return names


def test_readme_agent_count_matches_the_executor():
    """README'nin ajan sayısı = yürütücünün kaydettiği ajan sayısı."""
    count = len(_registered_agents())
    claimed = _readme_number(_AGENT_MARK)
    assert claimed == count, (
        f"README {claimed} görev ajanı diyor, yürütücü {count} kaydediyor"
    )


def test_readme_lists_every_registered_agent():
    """Her kayıtlı ajanın adı README'de geçmeli (yoksa "13 ajan" eksik anlatır)."""
    names = _registered_agents()
    assert names, "yürütücüden ajan okunamadı — test kendi ölçümünü kaybetti"
    readme = _readme()
    missing = [n for n in names if n not in readme]
    assert not missing, f"README'de geçmeyen ajanlar: {missing}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. YETENEK SAYISI
# ─────────────────────────────────────────────────────────────────────────────
def test_readme_capability_count_matches_the_registry():
    """README'nin yetenek sayısı = kayıtlı yetenek sayısı."""
    from agent_core.capabilities.registry import bootstrap

    count = len(bootstrap())
    claimed = _readme_number(_CAPABILITY_MARK)
    assert claimed == count, (
        f"README {claimed} yetenek diyor, kayıt defteri {count} yetenek içeriyor"
    )


def test_readme_lists_every_capability_id():
    """Her yetenek kimliği README'de geçmeli."""
    from agent_core.capabilities.registry import bootstrap

    readme = _readme()
    missing = [cap for cap in bootstrap().ids() if cap not in readme]
    assert not missing, f"README'de geçmeyen yetenekler: {missing}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. DALGA MOTORLARI
# ─────────────────────────────────────────────────────────────────────────────
def test_readme_engine_count_matches_the_code():
    """README'nin motor sayısı = `agent_core/engines` altındaki motor dosyaları."""
    engines = sorted(
        p.name for p in (REPO_ROOT / "agent_core" / "engines").glob("*_engine.py")
    )
    claimed = _readme_number(_ENGINE_MARK)
    assert claimed == len(engines), (
        f"README {claimed} dalga motoru diyor, kodda {len(engines)} motor var: {engines}"
    )


def test_readme_lists_every_engine():
    """Her motorun dosya adı README'de geçmeli."""
    readme = _readme()
    missing = [
        p.name
        for p in sorted((REPO_ROOT / "agent_core" / "engines").glob("*_engine.py"))
        if p.name not in readme
    ]
    assert not missing, f"README'de geçmeyen motorlar: {missing}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. API YÜZEYİ
# ─────────────────────────────────────────────────────────────────────────────
def test_readme_endpoint_count_matches_the_app():
    """README'nin uç sayısı = uygulamanın GERÇEKTEN kayıtlı uç sayısı."""
    from backend.api import app

    paths = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api") or path.startswith("/v1") or path == "/health":
            paths.append((path, tuple(sorted(getattr(route, "methods", ())))))
    claimed = _readme_number(_ENDPOINT_MARK)
    assert claimed == len(paths), (
        f"README {claimed} HTTP ucu diyor, uygulama {len(paths)} uç kaydediyor"
    )


def test_readme_mentions_the_websocket_route():
    """Canlı akış (WS) README'de adıyla geçmeli."""
    assert "/ws/{client_id}" in _readme(), "WebSocket ucu README'de yazılı değil"


# ─────────────────────────────────────────────────────────────────────────────
# 5. ENVANTER (SİSTEMİN YENİ HARİTASI) — README ile aynı sayım
# ─────────────────────────────────────────────────────────────────────────────
def test_readme_inventory_count_matches_the_map():
    """README'deki dosya sayısı = haritanın (envanter) kendi ölçümü."""
    readme = _readme()
    match = re.search(r"(\d+)\s+dosya,\s+klasör klasör", readme)
    assert match, "README'de envanter dosya sayısı yazılı değil"
    claimed = int(match.group(1))
    actual = len(_inventory_entries())
    assert claimed == actual, (
        f"README {claimed} dosya diyor, harita {actual} dosya sayıyor — "
        "harita `python scripts/generate_inventory_page.py` ile yenilenmeli"
    )


def test_readme_points_to_the_map():
    """README, sistemin haritasına (docs/envanter.html) bağlanmalı."""
    assert "docs/envanter.html" in _readme(), "README haritayı bağlamıyor"
