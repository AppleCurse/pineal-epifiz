"""Soruşturma döngüsü — kapatılamayan boşluk AÇIK kalır, uydurulmaz.

Kilitlenen iddialar:
    * sorular rapordan türetilir, deterministiktir ve ``subject_id``den bağımsızdır,
    * sonda yoksa soru "cevaplandı" sayılmaz (``no_probe_registered``),
    * sonda kanıt getirmezse ``no_new_evidence`` — başarı sayılmaz,
    * sonda hatası/timeout'u döngüyü patlatmaz, ``failed`` olarak kaydedilir,
    * sınırlar sert: tur/soru/süre tavanı; yeni kare yoksa döngü durur,
    * getirilen kareler tekilleştirilir ve deterministik sıralanır,
    * soru metinlerinde yorum kelimesi yok (teşhis yok).
"""

from __future__ import annotations

import asyncio

import pytest

from agent_core.lifecycle.investigation import (
    FRAME_SIGNAL_PREFIX,
    InvestigationConfig,
    InvestigationQuestion,
    ProbeOutcome,
    plan_questions,
    run_investigation,
)
from agent_core.lifecycle.pipeline import FORBIDDEN_INTERPRETATION_ROOTS


def _frame(**overrides) -> dict:
    frame = {
        "frame_id": "fr_0123456789abcdef0123",
        "observed_at": "2022-03-01T00:00:00+00:00",
        "capture_class": "unknown",
        "visual_stats": {"brightness": 0.5},
    }
    frame.update(overrides)
    return frame


def _report(**overrides) -> dict:
    payload = {
        "subject_id": "task_a",
        "status": "INSUFFICIENT_DATA",
        "baseline_window_start": "2021-01-01T00:00:00+00:00",
        "baseline_window_end": "2021-12-31T00:00:00+00:00",
        "data_coverage": [
            {"signal_id": FRAME_SIGNAL_PREFIX + "brightness", "baseline_observations": 20, "comparison_observations": 0},
            {"signal_id": FRAME_SIGNAL_PREFIX + "contrast", "baseline_observations": 2, "comparison_observations": 4},
            {"signal_id": "text.volume", "baseline_observations": 20, "comparison_observations": 0},
        ],
        "axes": [
            {"axis": "habitat", "state": "suppressed", "reason": "kare provenance unknown"},
            {"axis": "media", "state": "measured"},
        ],
        "excluded_evidence": [{"source": "instagram_post", "reason": "timestamp mismatch"}],
        "unknowns": ["bağımsızlık: ölçülmemiş korelasyon", "üretim biçimi: örnek az"],
    }
    payload.update(overrides)
    return payload


# --- Planlama ---------------------------------------------------------------


def test_plan_questions_covers_frame_gaps_and_sparse_baseline() -> None:
    questions = plan_questions(_report())
    kinds = {question.kind for question in questions}

    assert {"frame_coverage_gap", "frame_baseline_sparse", "visual_axis_suppressed"} <= kinds
    gap = next(question for question in questions if question.kind == "frame_coverage_gap")
    assert gap.subject == FRAME_SIGNAL_PREFIX + "brightness"
    assert gap.probe == "frame_window"
    assert gap.window == ("2021-01-01T00:00:00+00:00", "2021-12-31T00:00:00+00:00")


def test_non_frame_signals_are_not_our_questions() -> None:
    questions = plan_questions(_report())
    assert all(question.subject != "text.volume" for question in questions)


def test_suppressed_axis_has_no_probe() -> None:
    questions = plan_questions(_report())
    axis_question = next(question for question in questions if question.kind == "visual_axis_suppressed")
    assert axis_question.probe is None


def test_timestamp_conflict_is_planned() -> None:
    questions = plan_questions(_report())
    assert "timestamp_conflict" in {question.kind for question in questions}


def test_unknowns_become_open_questions() -> None:
    kinds = {question.kind for question in plan_questions(_report())}
    assert {"independence_unresolved", "medium_change_unknown"} <= kinds


def test_plan_is_deterministic_and_subject_independent() -> None:
    first = plan_questions(_report(subject_id="task_a"))
    second = plan_questions(_report(subject_id="task_a"))
    other = plan_questions(_report(subject_id="anon_başka"))

    assert [q.to_dict() for q in first] == [q.to_dict() for q in second]
    assert [q.question_id for q in first] == [q.question_id for q in other]
    assert all(q.question_id.startswith("q_") and len(q.question_id) == 14 for q in first)


def test_severity_ordering_is_stable() -> None:
    questions = plan_questions(_report())
    severities = [question.severity for question in questions]
    assert severities == sorted(severities, reverse=True)


def test_question_budget_truncates_plan() -> None:
    assert len(plan_questions(_report(), max_questions=2)) == 2


def test_plan_has_no_interpretive_language() -> None:
    texts = " ".join(
        f"{question.reason} {question.subject}" for question in plan_questions(_report())
    ).lower()
    leaked = [root for root in FORBIDDEN_INTERPRETATION_ROOTS if root in texts]
    assert leaked == []


def test_empty_report_yields_no_questions() -> None:
    assert plan_questions({"subject_id": "x"}) == []


# --- Döngü ------------------------------------------------------------------


def _probe_returning(outcome_factory):
    calls: list[str] = []

    async def _probe(question: InvestigationQuestion, *, budget_seconds: float) -> ProbeOutcome:
        calls.append(question.question_id)
        return outcome_factory(question)

    _probe.calls = calls  # type: ignore[attr-defined]
    return _probe


def test_without_probe_gaps_stay_open() -> None:
    result = asyncio.run(run_investigation(_report(), probes={}))

    assert result.resolved == []
    assert result.rounds == []
    assert result.still_unknown
    assert result.diagnostics["stop_reason"] == "no_probe_registered"
    assert all("sonda" in line for line in result.still_unknown)
    assert not result.closed


def test_unregistered_kind_is_not_silently_closed() -> None:
    # Sonda kayıtlı ama bu tür için değil: kare sorusu açık kalır.
    async def _other(question, *, budget_seconds):
        return ProbeOutcome(status="resolved")

    result = asyncio.run(run_investigation(_report(), probes={"timestamp_crosscheck": _other}))
    gap_questions = [q for q in result.questions if q.kind == "frame_coverage_gap"]
    assert gap_questions
    assert all(q.question_id in " ".join(result.still_unknown) for q in gap_questions)


def test_probe_that_finds_nothing_is_not_success() -> None:
    probe = _probe_returning(lambda question: ProbeOutcome(status="no_new_evidence", detail="yeni kare yok"))
    result = asyncio.run(run_investigation(_report(), probes={"frame_window": probe}))

    assert result.resolved == []
    assert result.diagnostics["stop_reason"] == "no_new_evidence"
    assert result.diagnostics["rounds_run"] == 1
    assert any("yeni kare yok" in line for line in result.still_unknown)


def test_probe_evidence_closes_question_and_sorts_frames() -> None:
    frames = [
        _frame(frame_id="fr_b", observed_at="2022-05-01T00:00:00+00:00"),
        _frame(frame_id="fr_a", observed_at="2022-03-01T00:00:00+00:00"),
    ]
    probe = _probe_returning(
        lambda question: ProbeOutcome(status="resolved", observations_added=2, frames=frames)
    )
    result = asyncio.run(run_investigation(_report(), probes={"frame_window": probe}))

    assert result.resolved
    assert [frame["frame_id"] for frame in result.extra_frames] == ["fr_a", "fr_b"]
    assert result.diagnostics["extra_frame_count"] == 2


def test_duplicate_frames_are_not_double_counted() -> None:
    same = [_frame(frame_id="fr_x"), _frame(frame_id="fr_x")]
    probe = _probe_returning(lambda question: ProbeOutcome(status="failed", frames=same))
    result = asyncio.run(run_investigation(_report(), probes={"frame_window": probe}, config=InvestigationConfig(max_rounds=1)))

    assert len(result.extra_frames) == 1
    assert result.diagnostics["rounds_run"] == 1


def test_probe_exception_is_contained() -> None:
    async def _boom(question, *, budget_seconds):
        raise RuntimeError("indirme çöktü")

    result = asyncio.run(run_investigation(_report(), probes={"frame_window": _boom}))

    assert result.resolved == []
    assert any("indirme çöktü" in line for line in result.still_unknown)
    assert result.rounds[0].outcomes  # tur kaydı yine de yazılır


def test_probe_timeout_is_contained() -> None:
    async def _slow(question, *, budget_seconds):
        await asyncio.sleep(5)
        return ProbeOutcome(status="resolved")

    result = asyncio.run(
        run_investigation(
            _report(),
            probes={"frame_window": _slow},
            config=InvestigationConfig(question_timeout_seconds=0.05),
        )
    )

    assert result.resolved == []
    assert any("question_timeout" in line for line in result.still_unknown)


def test_invalid_probe_output_is_failed_not_resolved() -> None:
    async def _bad(question, *, budget_seconds):
        return {"status": "resolved"}

    result = asyncio.run(run_investigation(_report(), probes={"frame_window": _bad}))
    assert result.resolved == []
    assert any("geçersiz" in line for line in result.still_unknown)


def test_unknown_status_is_failed() -> None:
    probe = _probe_returning(lambda question: ProbeOutcome(status="tamam"))
    result = asyncio.run(run_investigation(_report(), probes={"frame_window": probe}))
    assert result.resolved == []
    assert any("bilinmeyen durum" in line for line in result.still_unknown)


def test_round_budget_is_enforced() -> None:
    counter = {"n": 0}

    def _factory(question):
        counter["n"] += 1
        return ProbeOutcome(
            status="failed",
            frames=[_frame(frame_id=f"fr_{counter['n']:04d}", observed_at=f"2022-0{counter['n']}-01T00:00:00+00:00")],
        )

    probe = _probe_returning(_factory)
    first_gap = plan_questions(_report())[0]
    result = asyncio.run(
        run_investigation(
            _report(),
            probes={"frame_window": probe},
            config=InvestigationConfig(max_rounds=2, max_questions=1),
            questions=[first_gap],
        )
    )

    assert result.diagnostics["rounds_run"] == 2
    assert result.diagnostics["stop_reason"] == "round_budget_exhausted"
    assert len(probe.calls) == 2  # type: ignore[attr-defined]
    assert result.resolved == []


def test_zero_rounds_asks_nothing() -> None:
    probe = _probe_returning(lambda question: ProbeOutcome(status="resolved"))
    result = asyncio.run(
        run_investigation(
            _report(),
            probes={"frame_window": probe},
            config=InvestigationConfig(max_rounds=0),
        )
    )
    assert probe.calls == []  # type: ignore[attr-defined]
    assert result.resolved == []
    assert result.still_unknown


def test_result_is_json_friendly_and_deterministic() -> None:
    probe = _probe_returning(lambda question: ProbeOutcome(status="no_new_evidence"))
    first = asyncio.run(run_investigation(_report(), probes={"frame_window": probe})).to_dict()
    second = asyncio.run(run_investigation(_report(), probes={"frame_window": probe})).to_dict()

    assert first == second
    assert isinstance(first["questions"][0], dict)
    assert "still_unknown" in first and "rounds" in first


def test_config_rejects_negative_budget() -> None:
    with pytest.raises(ValueError):
        InvestigationConfig(max_rounds=-1)
    with pytest.raises(ValueError):
        InvestigationConfig(question_timeout_seconds=0)


# --- Rapora yansıma ---------------------------------------------------------


def _profile() -> dict:
    """Küçük ama tarihli bir profil: rapor üretilebilsin."""
    from datetime import datetime, timedelta, timezone

    base = datetime(2022, 1, 1, tzinfo=timezone.utc)
    count = 16
    return {
        "posts": ["kelime " * (5 + index % 4) for index in range(count)],
        "post_times": [(base + timedelta(days=14 * index)).isoformat() for index in range(count)],
    }


def _report_with(investigation) -> "object":
    from agent_core.lifecycle.pipeline import analyze_life_rupture

    return analyze_life_rupture(_profile(), investigation=investigation)


def test_open_questions_reach_the_report() -> None:
    result = asyncio.run(run_investigation(_report(), probes={}))
    report = _report_with(result)

    assert report.unknowns
    assert any(unknown.startswith("soruşturma açık: ") for unknown in report.unknowns)
    assert report.diagnostics.get("investigation", {}).get("stop_reason") == "no_probe_registered"
    assert report.diagnostics["investigation"]["still_unknown_count"] == len(result.still_unknown)


def test_report_without_investigation_is_unchanged() -> None:
    from agent_core.lifecycle.pipeline import analyze_life_rupture

    baseline = analyze_life_rupture(_profile())
    explicit_none = analyze_life_rupture(_profile(), investigation=None)

    assert explicit_none.report_id == baseline.report_id
    assert explicit_none.unknowns == baseline.unknowns
    assert "investigation" not in explicit_none.diagnostics


def test_digest_is_deterministic_and_subject_independent() -> None:
    result = asyncio.run(run_investigation(_report(), probes={}))
    first = _report_with(result)
    second = _report_with(result)

    assert first.report_id == second.report_id
    assert first.unknowns == second.unknowns


def test_extra_evidence_changes_the_report_identity() -> None:
    empty = asyncio.run(run_investigation(_report(), probes={}))
    richer = asyncio.run(
        run_investigation(
            _report(),
            probes={"frame_window": _probe_returning(lambda q: ProbeOutcome(status="no_new_evidence"))},
        )
    )

    assert _report_with(empty).report_id != _report_with(richer).report_id


def test_digest_accepts_object_and_dict_forms() -> None:
    result = asyncio.run(run_investigation(_report(), probes={}))
    assert _report_with(result).report_id == _report_with(result.to_dict()).report_id


def test_malformed_investigation_payload_is_ignored_not_trusted() -> None:
    report = _report_with({"still_unknown": "bozuk"})
    assert report.diagnostics.get("investigation", {}).get("still_unknown_count") == 0
