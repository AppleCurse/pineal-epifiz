"""P6 · ÖLÜ KOD / "ÇALIŞIR GİBİ YAPAN" BEKÇİSİ.

Bu test, `scripts/dead_code_audit.py` dedektörünü çalıştırır ve şu
SONUCU kilitler:

  * `agent_core/` ve `backend/` içinde hiç import edilmemiş modül YOK
  * hiçbir modül YALNIZ testler tarafından import edilmiyor
  * hiçbir ≥12 satırlık fonksiyon çağrılmaz durumda değil
  * executor'da kayıtlı 13 ajanın TAMAMI gerçekten çağrılabilir
  * kayıt defterindeki 26 yeteneğin TAMAMI düşürülebilir (dispatch var)
  * frontend'de giriş noktalarından ulaşılamayan bileşen YOK

Kilit, 2026-10-18'de ölçülen gerçek bulgulara göre yazıldı:
  · `DeepScanResult.summary_row` (ölü P0 kopyası) → SİLİNDİ
  · 12 ölü frontend bileşeni (4653 satır) → SİLİNDİ
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DETECTOR = ROOT / "scripts" / "dead_code_audit.py"


def _load_detector():
    spec = importlib.util.spec_from_file_location("dead_code_audit", DETECTOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def audit():
    return _load_detector()


# ── C1 · modül ──────────────────────────────────────────────────────────────
def test_no_dead_modules(audit):
    """Canlı kodda hiç import edilmemiş modül olmamalı."""
    dead, _ = audit.dead_modules()
    assert dead == [], f"ölü modül: {dead}"


def test_no_test_only_modules(audit):
    """Yalnız testlerden import edilen (üretimde kullanılmayan) modül olmamalı."""
    _, test_only = audit.dead_modules()
    assert test_only == [], f"yalnız testten import edilen modül: {test_only}"


# ── C2 · fonksiyon ──────────────────────────────────────────────────────────
def test_no_dead_functions(audit):
    """Hiç çağrılmayan ≥12 satırlık fonksiyon olmamalı."""
    dead = audit.dead_functions()
    assert dead == [], f"ölü fonksiyon: {dead}"


# ── C3 · ajan ───────────────────────────────────────────────────────────────
def test_all_registered_agents_are_callable(audit):
    """Executor'da kayıtlı her ajan gerçekten çağrılabilir olmalı.

    2026-10-18 ölçümü: 13 ajan kayıtlı, 13'ü de çağrılabilir
    (10'u router üzerinden dinamik, 3'ü doğrudan: osint_investigator,
    shadow_executor, depth_analyst).
    """
    dead = audit.dead_agents()
    assert dead == [], f"kayıtlı ama çağrılmayan ajan: {dead}"


def test_registered_agent_count_is_13(audit):
    """Kayıt sayısı 13; bu kilit, bir ajanın kaydı silinirse kırılır."""
    exec_path = ROOT / "agent_core/task_executor.py"
    tree = audit.parse(exec_path)
    registered = []
    for node in audit.ast.walk(tree):
        if isinstance(node, (audit.ast.Assign, audit.ast.AnnAssign)):
            raw = node.targets if isinstance(node, audit.ast.Assign) else [node.target]
            names = [t.id for t in raw if isinstance(t, audit.ast.Name)]
            attrs = [t.attr for t in raw if isinstance(t, audit.ast.Attribute)]
            if ("agents" in names or "agents" in attrs) and isinstance(node.value, audit.ast.Dict):
                for k in node.value.keys:
                    if isinstance(k, audit.ast.Constant) and isinstance(k.value, str):
                        registered.append(k.value)
    assert len(registered) == 13, f"beklenen 13 ajan, bulunan {len(registered)}: {registered}"


# ── C4 · yetenek ────────────────────────────────────────────────────────────
def test_all_registered_capabilities_are_dispatchable(audit):
    """Kayıt defterindeki her yetenek gerçekten düşürülebilir olmalı."""
    dead, source = audit.dead_capabilities()
    assert dead == [], f"düşürülemeyen yetenek: {dead}"
    assert source.startswith("kayıt defteri"), f"yetenek listesi varsayımdan gelmemeli: {source}"


def test_registered_capability_count_is_27(audit):
    """Kayıt defteri 27 yetenek; bu kilit, bir yetenek kaydı silinirse kırılır.

    [2026-10-23] 26 → 27: `sensor.identity.handle_probe` (native çapraz
    platform kullanıcı-adı yoklaması) eklendi.
    """
    ids, _ = audit.registered_capability_ids()
    assert len(ids) == 27, f"beklenen 27 yetenek, bulunan {len(ids)}"


# ── C5 · frontend ───────────────────────────────────────────────────────────
def test_no_orphan_frontend_components(audit):
    """Giriş noktalarından (main.ts → App.svelte) ulaşılamayan frontend dosyası olmamalı."""
    dead = audit.dead_frontend()
    assert dead == [], f"ölü frontend bileşeni: {dead}"


# ── geri-alma doğrulaması (revert) ──────────────────────────────────────────
def test_detector_flags_a_planted_dead_module(audit, tmp_path):
    """Dedektör GERÇEKTEN ölü dosyayı görür: sahte yeşil yok.

    Geçici bir ölü modül yazılır → dedektör onu listelemeli; sonra silinir.
    """
    victim = ROOT / "agent_core" / "_dead_probe_tmp.py"
    victim.write_text("x = 1\n", encoding="utf-8")
    try:
        audit.refresh_scope()
        dead, _ = audit.dead_modules()
        assert any(m["path"] == "agent_core/_dead_probe_tmp.py" for m in dead), (
            "dedektör ölü modülü görmedi — ölçüm yalan söylüyor"
        )
    finally:
        victim.unlink(missing_ok=True)
        audit.refresh_scope()
    dead, _ = audit.dead_modules()
    assert not any(m["path"] == "agent_core/_dead_probe_tmp.py" for m in dead)


def test_detector_flags_a_restored_orphan_frontend_component(audit):
    """[P6] Silinen ölü frontend bileşeni geri konursa dedektör KIRMIZIya döner.

    Revert-doğrulama: `UnifiedCompactPanel.svelte` (1990 satır) 2026-10-18'de
    silindi. Bu test onu geçici olarak geri koyar → C5 onu listelemeli.
    """
    victim = ROOT / "frontend" / "src" / "components" / "_dead_probe_tmp.svelte"
    victim.write_text("<script lang='ts'>const x = 1;</script>\n", encoding="utf-8")
    try:
        dead = audit.dead_frontend()
        assert any(m["path"] == "frontend/src/components/_dead_probe_tmp.svelte" for m in dead), (
            "dedektör geri konan ölü frontend bileşenini görmedi"
        )
    finally:
        victim.unlink(missing_ok=True)


def test_removed_orphan_components_are_absent_from_repo(audit):
    """[P6] 2026-10-18'de silinen 12 ölü frontend bileşeni depoda OLMAMALI.

    Revert-doğrulamanın kalıcı yarısı: biri geri gelirse bu test kırmızı.
    """
    removed = (
        "frontend/src/components/CockpitEntry.svelte",
        "frontend/src/components/OrganikIrisCanvas.svelte",
        "frontend/src/components/UnifiedCompactPanel.svelte",
        "frontend/src/components/PillarFeed.svelte",
        "frontend/src/components/PinealEye.svelte",
        "frontend/src/components/diesel/AnalogGauge.svelte",
        "frontend/src/components/diesel/EmergencyStop.svelte",
        "frontend/src/components/diesel/KeyLock.svelte",
        "frontend/src/components/diesel/LcdLogin.svelte",
        "frontend/src/components/diesel/SplitFlap.svelte",
        "frontend/src/components/diesel/ToggleSwitch.svelte",
        "frontend/src/lib/irisRenderer.ts",
    )
    present = [rel for rel in removed if (ROOT / rel).exists()]
    assert present == [], f"silinen ölü bileşen geri geldi: {present}"
