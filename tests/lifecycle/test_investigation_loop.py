from datetime import datetime, timedelta, timezone
import pytest

from agent_core.lifecycle.baseline_builder import (
    SignalObservation,
    build_baseline,
)
from agent_core.lifecycle.investigation_loop import (
    InvestigationLoop,
    LeadInquirer,
    InvestigationLedger,
    QuestionStatus,
    TargetedTask,
    TurnStage,
)

T0 = datetime(2022, 1, 1, tzinfo=timezone.utc)


def _obs(sid: str, day: int, val: float, ref: str = "") -> SignalObservation:
    return SignalObservation(
        signal_id=sid,
        timestamp=T0 + timedelta(days=day),
        value=float(val),
        source_ref=ref or f"{sid}:{day}",
    )


def _make_baseline():
    base_obs = []
    for d in range(30):
        base_obs.append(_obs("timing.is_night_post", d, 0.0 if d % 2 == 0 else 0.2))
        base_obs.append(_obs("visual.is_daylight", d, 1.0 if d % 3 == 0 else 0.8))
        base_obs.append(_obs("visual.is_isolated", d, 0.0 if d % 5 == 0 else 0.2))
        base_obs.append(_obs("media.is_authored_or_staged", d, 0.0))

    return build_baseline(
        subject_id="subject_investigation",
        observations=base_obs,
        baseline_start=T0,
        baseline_end=T0 + timedelta(days=50),
        min_samples=3,
    )


def test_investigation_loop_runs_minimum_two_turns():
    """Kural 1: İlk turda asla iş bitmez. En az iki tur zorunludur."""
    baseline = _make_baseline()
    initial_obs = [
        _obs("timing.is_night_post", 0, 0.0),
        _obs("visual.habitat_object_dog", 5, 1.0),
        _obs("visual.is_daylight", 300, 0.0),
    ]

    dispatcher_calls = []

    def mock_dispatcher(turn: int, tasks: list[TargetedTask]):
        dispatcher_calls.append(turn)
        # Tur 2'de hedefli görev yanıtı döner
        return [
            _obs("visual.habitat_object_dog", 20, 0.0, ref=f"{tasks[0].question_id}:verify")
            if tasks else _obs("dummy", 10, 0.0)
        ]

    loop = InvestigationLoop(inquirer=LeadInquirer(min_turns=2, max_turns=4))
    report, ledger = loop.execute_inquest(
        subject_id="subject_investigation",
        initial_observations=initial_obs,
        baseline=baseline,
        agent_dispatcher_callable=mock_dispatcher,
        target_start=T0 + timedelta(days=100),
        target_end=T0 + timedelta(days=400),
    )

    # En az 2 tur koşulmuş olmalı
    assert len(ledger.turns) >= 2
    assert 1 in dispatcher_calls or 2 in dispatcher_calls


def test_turn1_findings_spawn_targeted_tasks():
    """Kural 2: 1. turun bulguları 2. tur için koordinatlı (tarih ve soru kimlikli) görev üretir."""
    baseline = _make_baseline()
    initial_obs = [
        # Köpek 10. günde görüldü, ama 350. güne kadar bir daha hiç yok (ani kesilme)
        _obs("visual.habitat_object_dog", 10, 1.0),
        _obs("timing.is_night_post", 300, 1.0),
        _obs("timing.is_night_post", 350, 1.0),
    ]

    captured_tasks = []

    def mock_dispatcher(turn: int, tasks: list[TargetedTask]):
        captured_tasks.extend(tasks)
        return []

    loop = InvestigationLoop(inquirer=LeadInquirer(min_turns=2, max_turns=4))
    report, ledger = loop.execute_inquest(
        subject_id="subject_investigation",
        initial_observations=initial_obs,
        baseline=baseline,
        agent_dispatcher_callable=mock_dispatcher,
        target_start=T0 + timedelta(days=100),
        target_end=T0 + timedelta(days=400),
    )

    # 1. turdan sonra köpek kesilmesi için dinamik soru üretilmiş olmalı
    question_ids = [t.question_id for t in captured_tasks]
    assert any("disappearance_visual_habitat_object_dog" in q for q in question_ids)

    # Görev hedef ajan ve zaman aralığı koordinatını taşımalı
    task = next(t for t in captured_tasks if "disappearance_visual_habitat_object_dog" in t.question_id)
    assert task.target_agent == "vision_analyzer"
    assert task.target_time_window is not None


def test_falsification_counter_hypothesis_generated():
    """Kural 3: Beyin kendi hipotezini çürütmek için karşıt hipotez (confounding / kurgu) sorusu üretir."""
    baseline = _make_baseline()
    initial_obs = [
        _obs("visual.habitat_object_dog", 10, 1.0),
        _obs("timing.is_night_post", 300, 1.0),
    ]

    all_tasks = []

    def mock_dispatcher(turn: int, tasks: list[TargetedTask]):
        all_tasks.extend(tasks)
        # Yeni gözlem döndürerek döngünün 2. ve 3. tura devamını sağla
        return [_obs("media.is_authored_or_staged", 300 + turn, 0.0)]

    loop = InvestigationLoop(inquirer=LeadInquirer(min_turns=2, max_turns=4))
    report, ledger = loop.execute_inquest(
        subject_id="subject_investigation",
        initial_observations=initial_obs,
        baseline=baseline,
        agent_dispatcher_callable=mock_dispatcher,
        target_start=T0 + timedelta(days=100),
        target_end=T0 + timedelta(days=400),
    )

    # 2. turda karşı-hipotez (q_counter_) üretilmiş olmalı
    question_ids = [t.question_id for t in all_tasks]
    assert any(q.startswith("q_counter_") for q in question_ids)


def test_investigation_loop_stops_at_maximum_four_turns():
    """Kural 4: Döngü asla sonsuza gitmez. Azami 4 tur emniyet kilidi vardır."""
    baseline = _make_baseline()
    initial_obs = [_obs("timing.is_night_post", 300, 1.0)]

    def infinite_dispatcher(turn: int, tasks: list[TargetedTask]):
        # Sürekli yeni gözlem üreten bir ajan olsa bile
        return [_obs("timing.is_night_post", 300 + turn, 1.0)]

    loop = InvestigationLoop(inquirer=LeadInquirer(min_turns=2, max_turns=4))
    report, ledger = loop.execute_inquest(
        subject_id="subject_investigation",
        initial_observations=initial_obs,
        baseline=baseline,
        agent_dispatcher_callable=infinite_dispatcher,
        target_start=T0 + timedelta(days=100),
        target_end=T0 + timedelta(days=400),
    )

    # Kesinlikle 4 turda durmalı
    assert len(ledger.turns) <= 4


def test_ledger_permanently_retains_all_turns():
    """Kural 5: Tüm turların hafızası kalıcıdır. 1. turun gözlemi 3. turda silinmez."""
    baseline = _make_baseline()
    initial_obs = [_obs("timing.is_night_post", 10, 0.0, ref="t1_obs")]

    def mock_dispatcher(turn: int, tasks: list[TargetedTask]):
        return [_obs("timing.is_night_post", 300 + turn, 1.0, ref=f"t{turn}_obs")]

    loop = InvestigationLoop(inquirer=LeadInquirer(min_turns=2, max_turns=4))
    report, ledger = loop.execute_inquest(
        subject_id="subject_investigation",
        initial_observations=initial_obs,
        baseline=baseline,
        agent_dispatcher_callable=mock_dispatcher,
        target_start=T0 + timedelta(days=100),
        target_end=T0 + timedelta(days=400),
    )

    all_refs = [o.source_ref for o in ledger.all_observations]
    assert "t1_obs" in all_refs
    assert any("t2_obs" in r for r in all_refs)
