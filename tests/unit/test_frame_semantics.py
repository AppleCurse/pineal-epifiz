"""Kare semantiği — model İDDİASI ölçüm sayılmaz, teşhis sızmaz.

Kilitlenen iddialar:
    * yalnız DEĞİŞİM NOKTALARINDAKİ kareler analiz edilir (maliyet duvarı),
    * değişim noktası yoksa hiçbir kare gönderilmez (uydurma seçim yok),
    * model etiketi ``observation`` olarak DEĞİL ``inference`` olarak kaydedilir,
    * ``counts_toward_cluster`` daima ``False`` — çıkarım küme kanıtı değildir,
    * yorum kökü taşıyan etiket reddedilir, kayda geçmez,
    * hatada/boş cevapta kayıt üretilmez (yokluk ile bakılmamışlık karışmaz),
    * kimlik ``si_<20hex>`` ve deterministik; bütçe/tavan uygulanır.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from agent_core.lifecycle.pipeline import FORBIDDEN_INTERPRETATION_ROOTS
from agent_core.services.frame_semantics import (
    EPISTEMIC_TYPE,
    FRAME_SEMANTIC_PROMPT,
    MAX_LABELS_PER_FRAME,
    collect_semantic_inferences,
    select_inference_frames,
    slug_label,
)

INFERENCE_ID_RE = re.compile(r"^si_[0-9a-f]{20}$")


def _frame(frame_id: str, observed_at: str, **overrides) -> dict:
    payload = {"frame_id": frame_id, "observed_at": observed_at, "source_sha256": f"sha_{frame_id}"}
    payload.update(overrides)
    return payload


def _frames(count: int = 3) -> list[dict]:
    return [_frame(f"fr_{index:04d}", f"2022-0{index + 1}-01T00:00:00+00:00") for index in range(count)]


def _ask_returning(labels_by_frame: dict[str, list[dict]]):
    calls: list[str] = []

    async def _ask(frame, prompt) -> dict:
        calls.append(str(frame.get("frame_id")))
        assert prompt == FRAME_SEMANTIC_PROMPT
        return {"labels": labels_by_frame.get(str(frame.get("frame_id")), [])}

    _ask.calls = calls  # type: ignore[attr-defined]
    return _ask


# --- Seçim ------------------------------------------------------------------


def test_only_change_points_are_sent_to_the_model() -> None:
    frames = _frames(4)
    selected, problems = select_inference_frames(frames, change_point_ids=["fr_0001", "fr_0003"])

    assert [frame["frame_id"] for frame in selected] == ["fr_0001", "fr_0003"]
    assert problems == []


def test_without_change_points_nothing_is_sent() -> None:
    selected, problems = select_inference_frames(_frames(3))
    assert selected == []
    assert "change_points_missing" in problems


def test_unmatched_change_points_are_reported() -> None:
    selected, problems = select_inference_frames(_frames(2), change_point_ids=["fr_9999"])
    assert selected == []
    assert "change_points_unmatched" in problems


def test_selection_is_deterministic_and_time_ordered() -> None:
    frames = [_frame("fr_b", "2022-05-01T00:00:00+00:00"), _frame("fr_a", "2022-01-01T00:00:00+00:00")]
    first, _ = select_inference_frames(frames, change_point_ids=["fr_b", "fr_a"])
    second, _ = select_inference_frames(frames, change_point_ids=["fr_b", "fr_a"])

    assert [frame["frame_id"] for frame in first] == ["fr_a", "fr_b"]
    assert [frame["frame_id"] for frame in first] == [frame["frame_id"] for frame in second]


def test_frame_budget_is_enforced_deterministically() -> None:
    frames = _frames(10)
    ids = [frame["frame_id"] for frame in frames]

    selected, problems = select_inference_frames(frames, change_point_ids=ids, max_frames=4)
    again, _ = select_inference_frames(frames, change_point_ids=ids, max_frames=4)

    assert len(selected) == 4
    assert [frame["frame_id"] for frame in selected] == [frame["frame_id"] for frame in again]
    assert any("inference_budget_applied" in problem for problem in problems)


def test_zero_budget_sends_nothing() -> None:
    selected, problems = select_inference_frames(_frames(2), change_point_ids=["fr_0000"], max_frames=0)
    assert selected == []
    assert "inference_budget_zero" in problems


# --- Toplama ----------------------------------------------------------------


def test_inference_is_never_an_observation() -> None:
    ask = _ask_returning({"fr_0000": [{"label": "kitchen table", "kind": "object"}]})
    collection = asyncio.run(
        collect_semantic_inferences(_frames(1), ask=ask, change_point_ids=["fr_0000"])
    )

    assert len(collection.inferences) == 1
    row = collection.inferences[0]
    assert row["epistemic_type"] == EPISTEMIC_TYPE == "inference"
    assert row["counts_toward_cluster"] is False
    assert row["method"] == "vision_llm"
    assert row["prompt_version"] == "frame-semantics-v1"
    assert INFERENCE_ID_RE.match(row["inference_id"])
    assert row["label_slug"] == "kitchen_table"
    assert row["source_sha256"] == "sha_fr_0000"
    assert collection.diagnostics["epistemic_type"] == "inference"
    assert collection.diagnostics["counts_toward_cluster"] is False


def test_identity_is_deterministic() -> None:
    ask = _ask_returning({"fr_0000": [{"label": "kitchen table", "kind": "object"}]})
    first = asyncio.run(collect_semantic_inferences(_frames(1), ask=ask, change_point_ids=["fr_0000"]))
    second = asyncio.run(collect_semantic_inferences(_frames(1), ask=ask, change_point_ids=["fr_0000"]))

    assert first.to_dict() == second.to_dict()
    assert first.inferences[0]["inference_id"] == second.inferences[0]["inference_id"]


def test_duplicate_labels_collapse() -> None:
    ask = _ask_returning(
        {
            "fr_0000": [
                {"label": "kitchen table", "kind": "object"},
                {"label": "Kitchen  Table", "kind": "object"},
            ]
        }
    )
    collection = asyncio.run(collect_semantic_inferences(_frames(1), ask=ask, change_point_ids=["fr_0000"]))
    assert len(collection.inferences) == 1


def test_inference_labels_cannot_carry_diagnosis() -> None:
    ask = _ask_returning(
        {
            "fr_0000": [
                {"label": "kitchen table", "kind": "object"},
                {"label": "yalnız adam", "kind": "object"},
                {"label": "depresif oda", "kind": "place"},
                {"label": "kaygılı", "kind": "object"},
            ]
        }
    )
    collection = asyncio.run(collect_semantic_inferences(_frames(1), ask=ask, change_point_ids=["fr_0000"]))

    accepted = [row["label"] for row in collection.inferences]
    assert accepted == ["kitchen table"]
    assert any("rejected_interpretation" in problem for problem in collection.problems)
    for root in FORBIDDEN_INTERPRETATION_ROOTS:
        assert root not in " ".join(accepted).lower()


def test_disallowed_kind_is_rejected() -> None:
    ask = _ask_returning(
        {"fr_0000": [{"label": "walking", "kind": "activity"}, {"label": "kitchen table", "kind": "object"}]}
    )
    collection = asyncio.run(collect_semantic_inferences(_frames(1), ask=ask, change_point_ids=["fr_0000"]))

    assert [row["label"] for row in collection.inferences] == ["kitchen table"]
    assert any("kind_not_allowed" in problem for problem in collection.problems)


def test_numeric_and_unusable_labels_are_rejected() -> None:
    ask = _ask_returning({"fr_0000": [{"label": "42", "kind": "object"}, {"label": "   ", "kind": "object"}]})
    collection = asyncio.run(collect_semantic_inferences(_frames(1), ask=ask, change_point_ids=["fr_0000"]))

    assert collection.inferences == []
    assert any("label_numeric" in problem or "label_empty" in problem for problem in collection.problems)


def test_empty_answer_is_not_a_clean_frame() -> None:
    ask = _ask_returning({"fr_0000": []})
    collection = asyncio.run(collect_semantic_inferences(_frames(1), ask=ask, change_point_ids=["fr_0000"]))

    assert collection.inferences == []
    assert any(problem.startswith("semantic_empty:") for problem in collection.problems)
    assert "no_semantic_inference" in collection.problems


def test_malformed_payload_produces_no_record() -> None:
    async def _ask(frame, prompt):
        return "etiketler: masa"

    collection = asyncio.run(collect_semantic_inferences(_frames(1), ask=_ask, change_point_ids=["fr_0000"]))

    assert collection.inferences == []
    assert any("payload_not_mapping" in problem for problem in collection.problems)


def test_failed_payload_is_reported_not_swallowed() -> None:
    async def _ask(frame, prompt):
        return {"status": "failed", "reason": "llm_unavailable"}

    collection = asyncio.run(collect_semantic_inferences(_frames(1), ask=_ask, change_point_ids=["fr_0000"]))

    assert collection.inferences == []
    assert any("llm_unavailable" in problem for problem in collection.problems)


def test_model_exception_is_contained() -> None:
    async def _boom(frame, prompt):
        raise RuntimeError("provider down")

    collection = asyncio.run(collect_semantic_inferences(_frames(1), ask=_boom, change_point_ids=["fr_0000"]))

    assert collection.inferences == []
    assert any("semantic_call_failed" in problem and "RuntimeError" in problem for problem in collection.problems)


def test_budget_timeout_is_reported() -> None:
    async def _slow(frame, prompt):
        await asyncio.sleep(5)
        return {"labels": [{"label": "kitchen table", "kind": "object"}]}

    collection = asyncio.run(
        collect_semantic_inferences(
            _frames(2), ask=_slow, change_point_ids=["fr_0000", "fr_0001"], budget_seconds=0.05
        )
    )

    assert collection.inferences == []
    assert collection.diagnostics["budget_exceeded"] is True
    assert "semantic_budget_exceeded" in collection.problems


def test_only_selected_frames_are_asked() -> None:
    ask = _ask_returning({"fr_0001": [{"label": "kitchen table", "kind": "object"}]})
    asyncio.run(collect_semantic_inferences(_frames(3), ask=ask, change_point_ids=["fr_0001"]))

    assert ask.calls == ["fr_0001"]  # type: ignore[attr-defined]


def test_no_change_points_means_no_model_call() -> None:
    ask = _ask_returning({})
    collection = asyncio.run(collect_semantic_inferences(_frames(3), ask=ask))

    assert ask.calls == []  # type: ignore[attr-defined]
    assert "change_points_missing" in collection.problems
    assert collection.diagnostics["candidate_frame_count"] == 0


def test_label_budget_is_enforced() -> None:
    labels = [{"label": f"item {index}", "kind": "object"} for index in range(MAX_LABELS_PER_FRAME + 5)]
    ask = _ask_returning({"fr_0000": labels})
    collection = asyncio.run(collect_semantic_inferences(_frames(1), ask=ask, change_point_ids=["fr_0000"]))

    assert len(collection.inferences) == MAX_LABELS_PER_FRAME
    assert any("label_budget_applied" in problem for problem in collection.problems)


# --- Prompt ve sözlük -------------------------------------------------------


def test_prompt_gives_no_example_objects() -> None:
    """Örnek nesne listesi, kişiye/olaya bağlı "aranan şeyler" listesine dönüşür."""
    lowered = FRAME_SEMANTIC_PROMPT.lower()
    assert "ör:" not in lowered
    assert "örnek" not in lowered
    for word in ("kahve", "bira", "bardak", "kamera", "kitap"):
        assert word not in lowered


def test_prompt_forbids_interpretation() -> None:
    lowered = FRAME_SEMANTIC_PROMPT.lower()
    assert "duygu" in lowered and "psikolojik" in lowered


def test_slug_normalisation_is_stable() -> None:
    assert slug_label("  Kitchen   Table ") == "kitchen_table"
    assert slug_label("Türkçe Etiket") == "türkçe_etiket"
    assert slug_label(None) == ""
    assert slug_label(42) == ""


def test_bad_frame_arguments_are_not_fatal() -> None:
    collection = asyncio.run(collect_semantic_inferences(None, ask=_ask_returning({})))
    assert collection.inferences == []
    assert "frames_not_list" in collection.problems


def test_semantic_budget_is_positive() -> None:
    from agent_core.services.frame_semantics import DEFAULT_SEMANTIC_BUDGET_SECONDS

    assert DEFAULT_SEMANTIC_BUDGET_SECONDS > 0


@pytest.mark.parametrize("kind", ["object", "place"])
def test_both_label_kinds_are_accepted(kind: str) -> None:
    ask = _ask_returning({"fr_0000": [{"label": "kitchen table", "kind": kind}]})
    collection = asyncio.run(collect_semantic_inferences(_frames(1), ask=ask, change_point_ids=["fr_0000"]))
    assert collection.inferences[0]["kind"] == kind
