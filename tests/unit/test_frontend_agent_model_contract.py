"""
UI model-etiketi sözleşmesi — [P6 · 2026-10-18] SONRAKİ HALİ.

Geçmiş: kontrat, `UnifiedCompactPanel.svelte` içindeki 13 ajan kartının
statik `primaryModel/backupModel` etiketlerini gateway SoT'sine kilitliyordu.
ÖLÇÜLDÜ: o bileşen PR #143'te yenilen arayüzde kullanılmaz hâle geldi
(ölü kod denetimi: giriş noktalarından ulaşılamayan frontend bileşeni) ve
2026-10-18'de silindi. Yani kontrat, ÜRETİME HİÇ GİRMEYEN bir dosyayı
kılıfını da göstererek "yeşil" tutuyordu — testin kendisi "çalışır gibi
yapan" bir yere dönüşmüştü.

Yeni sözleşme (canlı yüzeylerde):
  1. Canlı arayüzde statik ajan-model tablosu YOKTUR; model/via bilgisi
     koşunun provenance'ından (canlı `run.model`) gelir. Statik tablo
     geri gelirse sözleşme kırılır.
  2. Etiket SoT'si hâlâ belgede yaşar: RUNBOOK'un ÜRETİLEN gölge bloğu
     gateway zinciriyle birebir aynı olmalıdır (gölge bayatlarsa CI kırılır).

Not: `primaryModel`/`backupModel` gibi statik alanlar yeniden gelirse
UI, canlı koşunun gerçek modelini değil sabit bir etiketi gösterecek ve
"çalışır gibi" davranacaktır — bu yüzden 1. madde bir KİLİTTİR.
"""

from pathlib import Path

from agent_core.services.llm_gateway import LLMGateway
from agent_core.services.task_routing_resolver import resolve_task_chain

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend/src"
RUNBOOK = ROOT / "RUNBOOK.md"
WAR_ROOM = FRONTEND_SRC / "components/TacticalWarRoom.svelte"

#: Canlı arayüzde model etiketi taşıyan bileşenler (canlı olmalı).
LIVE_COMPONENTS = (
    FRONTEND_SRC / "App.svelte",
    FRONTEND_SRC / "components/AtlasPinealCockpit.svelte",
    FRONTEND_SRC / "components/TacticalWarRoom.svelte",
    FRONTEND_SRC / "components/AgentRack.svelte",
)


def _short(model_id: str) -> str:
    """Registry tam model-id'sinden UI kısa adını üretir (display SoT kuralı)."""
    return model_id.rsplit("/", 1)[-1]


def _effective_chain(agent_id: str) -> list[str]:
    """gateway.get_agent_chain'in env-override'siz SoT hali (task_routing > AGENT_CHAINS)."""
    valid_keys = frozenset(LLMGateway.MODEL_REGISTRY.keys())
    routed = resolve_task_chain(agent_id, task="depth", valid_keys=valid_keys)
    if routed is not None:
        return [LLMGateway.MODEL_REGISTRY[key] for key in routed]
    if agent_id in LLMGateway.AGENT_CHAINS:
        return list(LLMGateway.AGENT_CHAINS[agent_id])
    return []


def test_no_static_model_label_table_in_live_frontend():
    """Canlı arayüzde statik ajan→model tablosu olmamalı (ölü panelin mirası).

    Statik tablo, koşunun gerçek modelini değil sabit bir etiketi gösterir;
    bu, "çalışır gibi yapan" arayüzdür.
    """
    offenders = []
    for path in sorted(FRONTEND_SRC.rglob("*.svelte")):
        text = path.read_text(encoding="utf-8")
        if "primaryModel:" in text or "backupModel:" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"statik model etiketi tablosu geri geldi: {offenders}"


def test_live_ui_shows_model_from_live_run_payload():
    """War-room model bilgisini koşunun canlı verisinden okumalı."""
    source = WAR_ROOM.read_text(encoding="utf-8")
    assert "run.model" in source, "canlı model alanı okunmuyor"
    assert "ÇALIŞMA MODELİ" in source


def test_live_components_exist():
    """Sözleşmenin bağlandığı canlı dosyalar depoda olmalı."""
    missing = [str(p.relative_to(ROOT)) for p in LIVE_COMPONENTS if not p.exists()]
    assert missing == [], f"canlı bileşen eksik: {missing}"


def test_runbook_shadow_matches_gateway_source_of_truth():
    """RUNBOOK'un üretilen gölge bloğu gateway SoT'siyle birebir aynı olmalı.

    Bu, eski paneldeki statik tablonun canlı karşılığıdır: etiket SoT'si
    belgede yaşar ve ÜRETİCİ tarafından yazılır (elle kopyalanmaz).
    """
    import importlib.util

    script = ROOT / "scripts" / "generate_routing_shadows.py"
    spec = importlib.util.spec_from_file_location("gen_shadows_contract", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    runbook = RUNBOOK.read_text(encoding="utf-8")
    block = runbook.split(module.RUNBOOK_START)[1].split(module.RUNBOOK_END)[0]

    snapshot = LLMGateway().effective_routing_snapshot()
    for agent, entry in sorted(snapshot["agents"].items()):
        row = [ln for ln in block.splitlines() if ln.startswith(f"| {agent} |")]
        assert row, f"RUNBOOK gölgesinde ajan satırı yok: {agent}"
        rendered_chain = row[0].split("|")[3].strip()
        expected = " → ".join(_short(m) for m in entry["chain"])
        assert rendered_chain == expected, (
            f"{agent}: RUNBOOK zinciri {rendered_chain!r} != SoT {expected!r}"
        )


def test_router_canonical_map_is_derived_not_handwritten():
    """9Router kanonik etiket tablosu KODDAN türetilir (elle kurgu değil)."""
    import importlib.util

    script = ROOT / "scripts" / "generate_routing_shadows.py"
    spec = importlib.util.spec_from_file_location("gen_shadows_canon", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    seats = [seat.replace("pineal_juror_", "") for seat in LLMGateway.JURY_PANEL_AGENTS]
    primary, backup, via = module.ROUTER_9_CANONICAL_MAP["autonomous_verifier"]
    assert primary == "pineal-verifier-panel"
    assert f"({len(seats)} jüri: {'+'.join(seats)})" == backup
    assert via == "9router"
