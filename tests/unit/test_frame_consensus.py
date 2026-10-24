"""Mutabakat kuralı — tekrar ≠ bağımsızlık.

Kilitlenen iddialar:
    * iki geçiş AYNI modele gittiyse terfi YOK (``same_model_repeat``),
    * model kimliği bilinmiyorsa bağımsızlık SAYILMAZ (``unknown``),
    * aynı soru (prompt sürümü) sorulmadan karşılaştırma yapılmaz,
    * iki FARKLI model aynı etiketi verirse ``corroborated`` satır doğar,
    * tek görünüm asla terfi ettirmez,
    * kimlik deterministik: ``cl_<20hex>``,
    * etiketler kareye ``{objects, places}`` olarak deterministik dağıtılır.
"""

from __future__ import annotations

import re

from agent_core.services.frame_consensus import (
    CORROBORATED_GRADE,
    LabelView,
    build_consensus,
    labels_by_frame,
    model_id_or_unknown,
)

ID_RE = re.compile(r"^cl_[0-9a-f]{20}$")


def _row(label: str = "kitchen table", kind: str = "object", frame: str = "fr_0001") -> dict:
    return {
        "frame_id": frame,
        "observed_at": "2022-03-01T00:00:00+00:00",
        "label": label,
        "label_slug": label.replace(" ", "_"),
        "kind": kind,
        "epistemic_type": "inference",
    }


def _view(view_id: str, model: str, rows: list[dict], version: str = "frame-semantics-v1") -> LabelView:
    return LabelView(view_id=view_id, model_id=model, prompt_version=version, labels=tuple(rows))


def test_two_distinct_models_promote_the_label() -> None:
    result = build_consensus(
        [_view("view_0", "model_a", [_row()]), _view("view_1", "model_b", [_row()])]
    )

    assert len(result.corroborated) == 1
    row = result.corroborated[0]
    assert row["observation_grade"] == CORROBORATED_GRADE
    assert row["epistemic_type"] == "observation"
    assert row["agreement_count"] == 2
    assert row["models"] == ["model_a", "model_b"]
    assert row["counts_toward_cluster"] is True
    assert ID_RE.match(row["corroboration_id"])


def test_same_model_twice_is_a_repeat_not_consensus() -> None:
    result = build_consensus(
        [_view("view_0", "model_a", [_row()]), _view("view_1", "model_a", [_row()])]
    )

    assert result.corroborated == []
    assert any(problem.startswith("same_model_repeat") for problem in result.rejected)
    assert "no_corroborated_label" in result.rejected


def test_unknown_model_never_counts_as_independent() -> None:
    result = build_consensus(
        [_view("view_0", "unknown", [_row()]), _view("view_1", "model_b", [_row()])]
    )

    assert result.corroborated == []
    assert result.diagnostics["independent_view_count"] == 1
    assert any("independence_unverified" in problem for problem in result.rejected)


def test_all_unknown_models_promote_nothing() -> None:
    result = build_consensus(
        [_view("view_0", "", [_row()]), _view("view_1", "  ", [_row()])]
    )
    assert result.corroborated == []
    assert result.diagnostics["independent_view_count"] == 0


def test_single_view_never_promotes() -> None:
    result = build_consensus([_view("view_0", "model_a", [_row()])])
    assert result.corroborated == []
    assert any("insufficient_independent_views" in problem for problem in result.rejected)


def test_prompt_mismatch_blocks_comparison() -> None:
    result = build_consensus(
        [
            _view("view_0", "model_a", [_row()], version="v1"),
            _view("view_1", "model_b", [_row()], version="v2"),
        ]
    )

    assert result.corroborated == []
    assert any(problem.startswith("prompt_mismatch") for problem in result.rejected)


def test_one_model_agreeing_is_not_enough() -> None:
    only_a = [_row("kitchen table")]
    other = [_row("wooden crate")]
    result = build_consensus(
        [_view("view_0", "model_a", only_a + other), _view("view_1", "model_b", only_a)]
    )

    assert [row["label_slug"] for row in result.corroborated] == ["kitchen_table"]
    assert result.diagnostics["inference_only_count"] >= 1


def test_three_views_require_three_distinct_models() -> None:
    views = [
        _view("view_0", "model_a", [_row()]),
        _view("view_1", "model_b", [_row()]),
        _view("view_2", "model_b", [_row()]),  # aynı model tekrar sayılmaz
    ]
    strict = build_consensus(views, min_views=3)
    loose = build_consensus(views)

    assert strict.corroborated == []
    assert loose.corroborated[0]["agreement_count"] == 2


def test_place_and_object_labels_are_separate() -> None:
    rows = [_row("kitchen table", "object"), _row("dark room", "place")]
    result = build_consensus(
        [_view("view_0", "model_a", rows), _view("view_1", "model_b", rows)]
    )

    assert {row["kind"] for row in result.corroborated} == {"object", "place"}


def test_identity_is_deterministic_and_ordered() -> None:
    views = [
        _view("view_0", "model_a", [_row("b item"), _row("a item")]),
        _view("view_1", "model_b", [_row("a item"), _row("b item")]),
    ]
    first = build_consensus(views)
    second = build_consensus(views)

    assert [row["label_slug"] for row in first.corroborated] == ["a_item", "b_item"]
    assert first.to_dict() == second.to_dict()


def test_incomplete_rows_are_rejected_not_guessed() -> None:
    result = build_consensus(
        [
            _view("view_0", "model_a", [{"frame_id": "", "kind": "object", "label_slug": "x"}]),
            _view("view_1", "model_b", [{"frame_id": "", "kind": "object", "label_slug": "x"}]),
        ]
    )
    assert result.corroborated == []
    assert any("label_incomplete" in problem for problem in result.rejected)


def test_empty_and_bad_inputs_are_not_fatal() -> None:
    assert build_consensus([]).rejected == ["no_views"]
    assert build_consensus(None).rejected == ["no_views"]
    assert build_consensus([None, "x"]).corroborated == []


def test_labels_by_frame_groups_and_sorts() -> None:
    rows = [
        {"frame_id": "fr_a", "kind": "object", "label": "table"},
        {"frame_id": "fr_a", "kind": "object", "label": "chair"},
        {"frame_id": "fr_a", "kind": "place", "label": "studio"},
        {"frame_id": "fr_b", "kind": "activity", "label": "walking"},  # tür yok sayılır
        {"frame_id": "", "kind": "object", "label": "orphan"},
    ]
    grouped = labels_by_frame(rows)

    assert grouped["fr_a"] == {"objects": ["chair", "table"], "places": ["studio"]}
    assert "fr_b" not in grouped


def test_model_id_normalisation() -> None:
    assert model_id_or_unknown(None) == "unknown"
    assert model_id_or_unknown("  ") == "unknown"
    assert model_id_or_unknown("unknown") == "unknown"
    assert model_id_or_unknown("gpt-4o") == "gpt-4o"
    assert LabelView("v", "none", "p").is_independent_source() is False
