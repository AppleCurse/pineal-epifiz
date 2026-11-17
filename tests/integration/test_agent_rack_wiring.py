"""Adım 3 kilidi: 12 ajan GERÇEKTEN koşuyor mu ve Agent Rack'e 1:1 mi bağlı?

[RÖNTGEN 2026-09-23] Ölçülen kusur — ÖDÜNÇ SLOT eşlemesi:

    _AGENT_RACK_MAP = {
        ...
        "shadow_executor": "depth_analyst",      # shadow -> depth slotu
        "pineal_7pillar":  "pattern_interrupt",  # motor -> ajan slotu
        "vision_analyzer": "pattern_interrupt",  # görsel -> ajan slotu
    }

Deterministik 7-sütun motoru koştuğunda ekranda PATTERN INTERRUPT slotu
READY yanıyor, görsel analizi AYNI slotu boyuyor, shadow_executor ise DEPTH
ANALYST slotunu kendi durumuyla değiştiriyordu. Yani Agent Rack'te görünen
durum, adını taşıdığı ajana İZLENEMİYORDU — kullanıcının "her UI durumunu
backend kaynağına kadar izle" talebinin doğrudan ihlali.

Yeni sözleşme (bu dosya kilitler):
  * 12 rack slotu ↔ görev ajanı BİRE-BİR (enjekte/örtüşme yok, kapsama tam).
  * Slotu olmayan adımlar (7pillar motoru, vision, shadow) HİÇBİR slotu
    boyamaz; gerçek durumları olay akışında ve `runs` kayıtlarında yaşar.
  * Router'ın planladığı her ajan gerçekten `await` edilir (çağrı zinciri
    dosyada değil, koşuda bağlı).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from agent_core.agents.depth_analyst import DepthReport
from agent_core.domain.memory_models import TaskSnapshot
from agent_core.services.agent_status_tracker import AGENT_DEFINITIONS
from agent_core.task_executor import PinealExecutor

REPO_ROOT = Path(__file__).resolve().parents[2]
RACK_IDS = [a["id"] for a in AGENT_DEFINITIONS]


class DummyResult(BaseModel):
    compatibility_score: float = 0.9


class DummyCheck(BaseModel):
    confidence: float
    is_suspicious: bool
    reason: str = ""


class _FakeTracker:
    """Rack'e yazılan her durumu (slot, durum, kaynak görev ajanı) kaydeder."""

    def __init__(self):
        self.calls: list[tuple[str, str, str | None]] = []

    async def update_status(self, agent_id: str, status: str, metadata=None):
        self.calls.append((agent_id, status, (metadata or {}).get("task_agent")))
        return {"agent_id": agent_id, "status": status}


def _ok_depth_report() -> DepthReport:
    return DepthReport(
        reality_index=0.9,
        reality_rationale="test",
        essence_one_liner="test",
        reality_findings=[],
        quote_guard={"kept": 0, "checked": 0, "dropped_fake_quote": 0},
    )


def _executor_with_mocks(monkeypatch) -> tuple[PinealExecutor, _FakeTracker]:
    executor = PinealExecutor()

    tracker = _FakeTracker()
    executor._agent_tracker = tracker

    routed = [
        "osint_investigator",
        "mirror_truth",
        "autonomous_verifier",
        "human_behavior",
        "passion_mapper",
        "friction_detector",
        "cognitive_profiler",
        "resonance_calc",
        "pattern_interrupt",
        "authenticity_auditor",
        "resonance_synthesizer",
        "shadow_executor",
    ]

    router = MagicMock()
    route = MagicMock()
    route.agents = list(routed)
    router.analyze = AsyncMock(return_value=route)
    executor.router = router

    uncertainty = MagicMock()
    uncertainty.evaluate.return_value = DummyCheck(confidence=0.9, is_suspicious=False)
    executor.uncertainty = uncertainty

    memory = MagicMock()
    memory.merge_evidence = AsyncMock()
    executor.memory = memory

    llm = MagicMock()
    llm.query = AsyncMock(return_value="kanıt metni")
    executor.llm_gateway = llm

    injector = MagicMock()
    injector.fetch_active_rules.return_value = {}
    executor.injector = injector

    for name in executor.agents:
        agent = MagicMock()
        agent.execute = AsyncMock(return_value=DummyResult())
        executor.agents[name] = agent
    executor.agents["depth_analyst"].analyze = AsyncMock(return_value=_ok_depth_report())

    executor._download_images = AsyncMock(return_value=[])
    return executor, tracker


# --------------------------------------------------------------------------- #
# 1) Eşleme sözleşmesi: bire-bir, tam kapsama
# --------------------------------------------------------------------------- #
def test_rack_map_is_one_to_one_and_covers_every_slot():
    mapping = PinealExecutor._AGENT_RACK_MAP
    slotted = {task: slot for task, slot in mapping.items() if slot is not None}

    # Kapsama: 12 slotun her biri en az bir görev ajanına bağlı.
    assert set(slotted.values()) == set(RACK_IDS), (
        f"kapsanmayan slotlar: {sorted(set(RACK_IDS) - set(slotted.values()))}"
    )
    # Enjektivite: iki görev ajanı aynı slotu PAYLAŞAMAZ (ödünç slot yasağı).
    duplicates = [slot for slot in set(slotted.values()) if list(slotted.values()).count(slot) > 1]
    assert not duplicates, f"slot paylaşan görev ajanları var: {duplicates}"


def test_slotless_steps_are_explicitly_unslotted():
    """7-sütun motoru, görsel analizi ve shadow hiçbir slotu boyayamaz."""
    mapping = PinealExecutor._AGENT_RACK_MAP
    for step in ("pineal_7pillar", "vision_analyzer", "shadow_executor"):
        assert step in mapping, f"{step} eşlemede açıkça None'a bağlanmalı"
        assert mapping[step] is None, (
            f"{step} başka bir ajanın slotunu ödünç alıyor: {mapping[step]}"
        )


def test_no_loop_context_does_not_fake_a_write():
    """Senkron bağlamda (event loop yok) rack'e yazılamaz — uydurma yazım yok.

    Eski `_rack_update` bu durumda `tracker.statuses[...]` alanına yazmayı
    deniyordu; tracker'da böyle bir alan YOK (`_statuses`), yani yedek dal ölü
    koddu ve hata sessizce yutuluyordu.
    """
    executor, tracker = PinealExecutor(), _FakeTracker()
    executor._agent_tracker = tracker
    logs: list[tuple[str, str]] = []
    executor._log = lambda level, msg: logs.append((level, msg))

    executor._rack_update("mirror_truth", "active")  # döngü yok

    assert tracker.calls == []
    assert any("event loop yok" in msg for _lvl, msg in logs), (
        "yazılamayan durum dürüstçe loglanmalı"
    )
    source = (REPO_ROOT / "agent_core" / "task_executor.py").read_text(encoding="utf-8")
    assert "_agent_tracker.statuses[" not in source, "ölü senkron yazım yedeği geri gelmiş"


def test_every_slotted_task_agent_is_a_real_executor_agent():
    """Slotu olan her görev ajanı executor kaydında GERÇEKTEN var (dosya değil, kablolama)."""
    executor = PinealExecutor()
    mapping = PinealExecutor._AGENT_RACK_MAP
    missing = [
        task for task, slot in mapping.items()
        if slot is not None and task not in executor.agents
    ]
    assert not missing, f"rack'e bağlanan ama executor'da olmayan ajanlar: {missing}"


# --------------------------------------------------------------------------- #
# 2) Koşu zamanı: durumlar gerçek geçişlerden gelir
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_slotless_step_does_not_paint_another_agents_slot():
    executor, tracker = PinealExecutor(), _FakeTracker()
    executor._agent_tracker = tracker

    executor._rack_update("pineal_7pillar", "ready")
    executor._rack_update("vision_analyzer", "active")
    executor._rack_update("shadow_executor", "done")
    await asyncio.sleep(0.01)

    assert tracker.calls == [], (
        f"slotu olmayan adımlar rack'e yazdı: {tracker.calls}"
    )


@pytest.mark.asyncio
async def test_real_agent_paints_only_its_own_slot():
    executor, tracker = PinealExecutor(), _FakeTracker()
    executor._agent_tracker = tracker

    executor._rack_update("mirror_truth", "active")
    executor._rack_update("resonance_calc", "ready")
    await asyncio.sleep(0.01)  # create_task ile zamanlanan yazımlar tamamlansın

    assert ("mirror_truth", "active", "mirror_truth") in tracker.calls
    # resonance_calc görev adı -> resonance_calculator slotu (bire-bir eşleme).
    assert ("resonance_calculator", "ready", "resonance_calc") in tracker.calls
    painted = {slot for slot, _status, _src in tracker.calls}
    assert painted == {"mirror_truth", "resonance_calculator"}


@pytest.mark.asyncio
async def test_full_mission_runs_every_routed_agent(monkeypatch):
    """Router'ın planladığı her ajan gerçekten await edilir ve rack'e yazılır."""
    executor, tracker = _executor_with_mocks(monkeypatch)
    routed = [name for name in PinealExecutor._AGENT_RACK_MAP]

    status = await executor.execute_task({"target_profile": {"bio": "", "posts": []}}, "task-wire")
    await asyncio.sleep(0.05)  # _rack_update create_task'leri tamamlansın

    assert isinstance(status, TaskSnapshot)
    assert set(status.planned_agents) >= {
        "mirror_truth", "passion_mapper", "resonance_calc", "pattern_interrupt"
    }

    executed = {
        name for name, agent in executor.agents.items()
        if (isinstance(getattr(agent.execute, "await_count", None), int) and agent.execute.await_count > 0) or (isinstance(getattr(agent.analyze, "await_count", None), int) and agent.analyze.await_count > 0)
    }
    # Planlanan ajanların tamamı koşuldu (çağrı zinciri bağlı).
    planned = set(status.planned_agents)
    assert planned <= executed | {"depth_analyst"}, (
        f"planlandı ama koşmadı: {sorted(planned - executed)}"
    )

    # Rack kayıtları: her yazım, slotun adını taşıdığı ajandan geldi.
    borrowed = [
        (slot, src) for slot, _state, src in tracker.calls
        if src is not None and PinealExecutor._AGENT_RACK_MAP.get(src) not in (None, slot)
    ]
    assert not borrowed, f"ödünç slot yazımı: {borrowed}"

    sources = {src for _slot, _state, src in tracker.calls}
    for agent_name in ("mirror_truth", "passion_mapper", "pattern_interrupt"):
        assert agent_name in sources, f"{agent_name} rack'e hiç yazılmadı"
    for step in ("pineal_7pillar", "vision_analyzer", "shadow_executor"):
        assert step not in sources, f"{step} rack'e yazdı (slotu yok)"
    assert routed  # dokümantasyon amaçlı: eşleme tablosu boş değil
