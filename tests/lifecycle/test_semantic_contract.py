"""Sözleşme kilidi — model etiketi ölçüm sayılmaz, ritüel sözlüğünü BESLEMEZ.

Kilitlenen iddialar:
    * rapora ``epistemic_type != "inference"`` taşıyan satır GİREMEZ,
    * ``counts_toward_cluster`` ``False`` değilse satır düşürülür (modele güvenilmez),
    * etiketler ``ritual.*`` sinyali ÜRETMEZ: ritüel sözlüğü yalnız ÖLÇÜLMÜŞ
      kare etiketlerinden çıkar, model cümlesinden değil,
    * etiketler küme/bağımsızlık sayımına girmez,
    * raporda "bunlar çıkarım" yazılıdır (sessiz boşluk yok),
    * kimlik deterministik; farklı kanıt farklı kimlik.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from agent_core.lifecycle.pipeline import analyze_life_rupture
from agent_core.lifecycle.report import LifeRuptureReport
from agent_core.services.frame_semantics import SemanticInference, slug_label

BASE = datetime(2022, 1, 1, tzinfo=timezone.utc)


def _profile(count: int = 18) -> dict:
    return {
        "posts": ["kelime " * (5 + index % 4) for index in range(count)],
        "post_times": [(BASE + timedelta(days=14 * index)).isoformat() for index in range(count)],
    }


def _frames(count: int = 8) -> list[dict]:
    frames = []
    for index in range(count):
        frames.append(
            {
                "frame_id": f"fr_{index:04d}",
                "observed_at": (BASE + timedelta(days=14 * index)).isoformat(),
                "capture_class": "unknown",
                "has_measurable_background": index % 2 == 0,
                "detected_objects": [],
                "environment_and_places": [],
                "lighting": "unknown",
                "visual_stats": {
                    "brightness": 0.2 + index * 0.05,
                    "saturation": 0.3,
                    "contrast": 0.4 + index * 0.02,
                    "edge_density": 0.1 + index * 0.01,
                    "colorfulness": 0.2,
                },
                "data_confidence": True,
            }
        )
    return frames


def _inference(index: int, label: str = "kitchen table", kind: str = "object") -> dict:
    return SemanticInference(
        inference_id=f"si_{index:020x}",
        frame_id=f"fr_{index:04d}",
        observed_at=(BASE + timedelta(days=14 * index)).isoformat(),
        label=label,
        label_slug=slug_label(label),
        kind=kind,
    ).to_dict()


def _report(**kwargs):
    return analyze_life_rupture(_profile(), visual_evidence={"frames": _frames()}, **kwargs)


def test_inferences_reach_the_report_as_inferences() -> None:
    rows = [_inference(0), _inference(1, "studio", "place")]
    report = _report(semantic_inferences=rows)

    assert report.semantic_inference_count == 2
    assert [row["label"] for row in report.semantic_inferences] == ["kitchen table", "studio"]
    assert all(row["epistemic_type"] == "inference" for row in report.semantic_inferences)
    assert report.semantic_inferences_count_toward_cluster is False
    assert report.diagnostics["semantic_inferences_count_toward_cluster"] is False
    assert any("model çıkarımıdır" in unknown for unknown in report.unknowns)


def test_mislabelled_rows_never_enter_the_report() -> None:
    rogue = dict(_inference(0), epistemic_type="observation")
    report = _report(semantic_inferences=[rogue])

    assert report.semantic_inference_count == 0
    assert report.semantic_inferences == []


def test_rows_without_explicit_false_are_dropped() -> None:
    rogue = dict(_inference(0))
    rogue.pop("counts_toward_cluster")
    assert _report(semantic_inferences=[rogue]).semantic_inference_count == 0


def test_report_model_rejects_tampered_rows() -> None:
    """Model düzeyinde kilit: ``observation`` etiketiyle satır kurulamaz."""
    with pytest.raises(ValidationError):
        LifeRuptureReport(
            subject_id="x",
            status="NO_RUPTURE",
            semantic_inferences=[dict(_inference(0), epistemic_type="observation")],
        )
    with pytest.raises(ValidationError):
        LifeRuptureReport(
            subject_id="x",
            status="NO_RUPTURE",
            semantic_inferences=[dict(_inference(0), counts_toward_cluster=True)],
        )


def test_inferences_do_not_create_ritual_signals() -> None:
    """Etiket ``detected_objects``e yazılsaydı ritüel sözlüğü kirlenirdi."""
    rows = [_inference(index, "kitchen table") for index in range(6)]
    report = _report(semantic_inferences=rows)

    assert "ritual" not in report.families
    coverage = {row["signal_id"] for row in report.data_coverage}
    assert not [signal for signal in coverage if signal.startswith("ritual.")]


def test_inferences_do_not_create_candidate_signals() -> None:
    rows = [_inference(index, "kitchen table") for index in range(6)]
    with_rows = _report(semantic_inferences=rows)
    without = _report()

    assert with_rows.candidate_signal_count == without.candidate_signal_count
    assert with_rows.confirmed_independent_signal_count == without.confirmed_independent_signal_count
    assert with_rows.status == without.status
    assert with_rows.cluster_state == without.cluster_state


def test_identity_is_deterministic_and_evidence_sensitive() -> None:
    rows = [_inference(0)]
    first = _report(semantic_inferences=rows)
    second = _report(semantic_inferences=rows)
    plain = _report()

    assert first.report_id == second.report_id
    assert first.report_id != plain.report_id


def test_malformed_inference_payload_is_ignored() -> None:
    assert _report(semantic_inferences="bozuk").semantic_inference_count == 0
    assert _report(semantic_inferences=[None, 3, "x"]).semantic_inference_count == 0


def test_collection_object_is_accepted() -> None:
    class _Collection:
        def to_dict(self):
            return {"semantic_inferences": [_inference(0)]}

    assert _report(semantic_inferences=_Collection()).semantic_inference_count == 1


def test_inference_rows_are_sorted_deterministically() -> None:
    rows = [_inference(3), _inference(1), _inference(2)]
    report = _report(semantic_inferences=rows)
    ordered = [row["frame_id"] for row in report.semantic_inferences]
    assert ordered == sorted(ordered)
