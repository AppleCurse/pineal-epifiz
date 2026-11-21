"""KABLO BEKÇİSİ (Permanent Wiring Guard) — kopuk modül / ölü buton engelleyici.

Bu test dosyası, önceki turlarda defalarca yaşanan "motor yazıldı ama beyne veya
ekrana bağlanmadı / sonraki turda fişi çekildi" kusurunu yapısal olarak imkânsız
kılar. Herhangi bir kablo koparsa CI doğrudan kırmızı yakar.
"""

from __future__ import annotations

from pathlib import Path

from agent_core.capabilities.policy import (
    CONSENT_ONLY_FLAGS,
    EXTERNAL_KEYED_FLAGS,
    LOCAL_CORE_FLAGS,
    MANAGED_GATE_FLAGS,
)
from agent_core.capabilities.state import (
    capability_profile_summary,
    enabled_flags,
    flag_enabled,
)
from agent_core.domain.memory_models import TaskSnapshot
from agent_core.task_executor import PinealExecutor

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_capability_two_profile_partition_has_no_orphans():
    """17 ENABLE_* bayrağı eksiksiz ve çakışmasız bölünür (local_core + external_keyed + consent_only)."""
    local_set = set(LOCAL_CORE_FLAGS)
    ext_set = set(EXTERNAL_KEYED_FLAGS)
    consent_set = set(CONSENT_ONLY_FLAGS)
    managed_set = set(MANAGED_GATE_FLAGS)

    assert local_set.isdisjoint(ext_set), f"Çakışan bayraklar: {local_set & ext_set}"
    assert local_set.isdisjoint(consent_set), f"Çakışan bayraklar: {local_set & consent_set}"
    assert ext_set.isdisjoint(consent_set), f"Çakışan bayraklar: {ext_set & consent_set}"
    assert (local_set | ext_set | consent_set) == managed_set, (
        f"Yetim/eksik bayraklar: {managed_set ^ (local_set | ext_set | consent_set)}"
    )


def test_capability_consent_only_flag_not_opened_by_local_core_profile():
    """ENABLE_CROSS_PLATFORM yerel-çekirdek profiliyle AÇILAMAZ; yalnız açık onay/env açar."""
    profiled = enabled_flags({"PINEAL_CAPABILITY_PROFILE": "local_core"})
    assert profiled["ENABLE_CROSS_PLATFORM"] is False, (
        "çapraz platform kapısı profil tarafından açıldı — rıza kapısı delindi"
    )
    explicit = enabled_flags({"PINEAL_CAPABILITY_PROFILE": "local_core", "ENABLE_CROSS_PLATFORM": "true"})
    assert explicit["ENABLE_CROSS_PLATFORM"] is True, "açık env hâlâ kazanmalı"


def test_capability_local_core_profile_enables_local_only_and_respects_explicit_false():
    """PINEAL_CAPABILITY_PROFILE=local_core yalnız yerel çekirdeği açar; elle false baskındır."""
    strict = enabled_flags({})
    assert all(v is False for v in strict.values())

    local = enabled_flags({"PINEAL_CAPABILITY_PROFILE": "local_core"})
    for f in LOCAL_CORE_FLAGS:
        assert local[f] is True, f"{f} local_core profilinde açık olmalı"
    for f in EXTERNAL_KEYED_FLAGS:
        assert local[f] is False, f"{f} harici/hesap profilinde varsayılan kapalı kalmalı"

    override = enabled_flags(
        {"PINEAL_CAPABILITY_PROFILE": "local_core", "ENABLE_MAIGRET": "false"}
    )
    assert override["ENABLE_MAIGRET"] is False
    assert flag_enabled("ENABLE_COMPANY_TARGETING", {"PINEAL_CAPABILITY_PROFILE": "local_core"}) is True

    summary = capability_profile_summary({"PINEAL_CAPABILITY_PROFILE": "local_core"})
    assert summary["profile"] == "local_core"
    assert summary["local_core"]["active_count"] == len(LOCAL_CORE_FLAGS)
    assert summary["external_keyed"]["active_count"] == 0


def test_deterministic_7_pillar_engines_wired_to_orchestrator_and_executor():
    """Tüm deterministik 7-sütun motorları + spectrum orkestratöre ve yürütücüye bağlı olmalı."""
    orch_src = (REPO_ROOT / "agent_core" / "engines" / "pillar_orchestrator.py").read_text(encoding="utf-8")
    exec_src = (REPO_ROOT / "agent_core" / "task_executor.py").read_text(encoding="utf-8")
    freq_src = (REPO_ROOT / "agent_core" / "engines" / "frequency_engine.py").read_text(encoding="utf-8")

    for eng in (
        "frequency_engine",
        "gravity_engine",
        "key_engine",
        "pulse_engine",
        "seismos_engine",
        "strata_engine",
        "void_engine",
    ):
        assert eng in orch_src, f"{eng} pillar_orchestrator.py içinde bağlı değil"

    assert "spectrum" in freq_src, "spectrum FFT motoru frequency_engine.py içinde bağlı değil"
    assert "PillarOrchestrator" in exec_src, "PillarOrchestrator task_executor.py içinde bağlı değil"
    assert "cross_profiler" in exec_src, "cross_profiler task_executor.py içinde bağlı değil"
    assert "psychodynamic_depth" in exec_src, "psychodynamic_depth task_executor.py içinde bağlı değil"
    assert "timing_forensics" in exec_src, "timing_forensics task_executor.py içinde bağlı değil"
    assert "follower_audit" in exec_src, "follower_audit task_executor.py içinde bağlı değil"


def test_lilith_permanently_wired_into_executor_snapshot_and_aspasia():
    """LilithGrowthAgent yürütücüde kayıtlı, TaskSnapshot'ta alanlı ve Aspasia özetinde görünür olmalı."""
    executor = PinealExecutor()
    assert "lilith_growth" in executor.agents, "lilith_growth PinealExecutor.agents içinde değil!"
    assert "lilith_report" in TaskSnapshot.model_fields, "TaskSnapshot.lilith_report alanı eksik!"

    exec_src = (REPO_ROOT / "agent_core" / "task_executor.py").read_text(encoding="utf-8")
    assert 'self.agents["lilith_growth"].execute(' in exec_src
    assert "status.lilith_report =" in exec_src

    aspasia_src = (REPO_ROOT / "agent_core" / "aspasia" / "aspasia_chief.py").read_text(encoding="utf-8")
    assert "lilith_report" in aspasia_src, "Aspasia build_telemetry_summary lilith_report'u okumuyor!"

    lilith_route_src = (REPO_ROOT / "backend" / "routes" / "lilith.py").read_text(encoding="utf-8")
    assert "generate_hook_package" in lilith_route_src, (
        "backend/routes/lilith.py gerçek hook_studio motoruna (generate_hook_package) bağlı değil!"
    )
    assert "memory_crystal.crystallize(" in exec_src, (
        "task_executor.py görev sonunda memory_crystal.crystallize çağırmıyor!"
    )


def test_backend_app_exposes_all_permanent_brain_and_lilith_routes():
    """FastAPI uygulamasında tüm birleşik Lilith, Brain Hub ve hazır motor uçları kayıtlı olmalı."""
    from backend import api as backend_api

    paths = {getattr(r, "path", "") for r in backend_api.app.routes}
    required = {
        "/api/lilith/strategy",
        "/api/brain/route",
        "/api/brain/capabilities",
        "/api/hook/generate",
        "/api/company/scan",
        "/api/memory/{target}/recall",
        "/api/tasks/{task_id}/graph",
        "/api/aspasia/chat",
        "/api/aspasia/command",
        "/api/initiate",
    }
    missing = required - paths
    assert not missing, f"Backend FastAPI app'te eksik kritik uçlar: {sorted(missing)}"

    api_src = (REPO_ROOT / "backend" / "api.py").read_text(encoding="utf-8")
    cmd_start = api_src.index("async def aspasia_command(")
    cmd_end = api_src.index("@app.get(\"/api/aspasia/state\")", cmd_start)
    cmd_body = api_src[cmd_start:cmd_end]
    assert "_require_minor_clearance(" in cmd_body, "/api/aspasia/command çocuk koruma kapısını çağırmıyor!"
    assert "_require_vault_open(" in cmd_body, "/api/aspasia/command kasa kilidi kapısını çağırmıyor!"


def test_frontend_cockpit_wires_lilith_and_brain_hub_directly():
    """Ön yüz Lilith tıklamasını Aspasia sohbetine düşürmemeli; gerçek uçlara bağlanmalı."""
    cockpit_src = (
        REPO_ROOT / "frontend" / "src" / "components" / "UnifiedPinealCockpit.svelte"
    ).read_text(encoding="utf-8")

    assert "/api/lilith/strategy" in cockpit_src, (
        "UnifiedPinealCockpit.svelte /api/lilith/strategy ucunu çağırmıyor!"
    )
    assert "/api/brain/route" in cockpit_src, (
        "UnifiedPinealCockpit.svelte /api/brain/route ucunu çağırmıyor!"
    )
    assert "selectedAgentId === 'lilith'" in cockpit_src, (
        "Lilith seçimi doğrudan Lilith hattına yönlendirilmiyor!"
    )
