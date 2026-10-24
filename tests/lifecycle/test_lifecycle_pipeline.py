"""Uçtan uca hat — veriden mühürlü rapora, teşhis iddiası olmadan.

Kilitlenen iddialar:
    * aynı veri farklı ``subject_id`` ile AYNI sonucu verir (kişiye özel kod yok),
    * kurguya kayış yaşam ekseniyle karışırsa rapor CONFOUNDED der; oran YÜKSEK
      ama SABİT ise confound demez,
    * korelasyon ölçülemiyorsa küme "doğrulandı" sayılmaz → CANDIDATE,
    * rapor metninde yorum kökü GEÇMEZ, ``root_cause`` yalnız ``UNKNOWN``,
    * kanıt kimlikleri ``^ev_[0-9a-f]{20}$`` ve tekrar üretilebilir; ``report_id``
      aynı kanıtta aynıdır,
    * her bulgu denetlenebilir alanlar taşır,
    * veri yoksa "kırılma yok" değil "kanıt yetersiz" denir.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from agent_core.lifecycle.pipeline import FORBIDDEN_INTERPRETATION_ROOTS, analyze_life_rupture
from agent_core.lifecycle.report import Finding, LifeRuptureReport

EVIDENCE_ID_RE = re.compile(r"^ev_[0-9a-f]{20}$")
REPORT_ID_RE = re.compile(r"^lr_[0-9a-f]{20}$")

BASE = datetime(2022, 1, 10, 14, tzinfo=timezone.utc)
TARGET = datetime(2024, 1, 10, 23, tzinfo=timezone.utc)
WEEKS = 13


def _words(count: int) -> str:
    return " ".join(["kelime"] * count)


def _frame(frame_id: str, observed_at: str, **overrides) -> dict:
    payload = {
        "frame_id": frame_id,
        "observed_at": observed_at,
        "capture_class": "camera_incidental",
        "has_measurable_background": True,
        "detected_objects": ["kitchen_table"],
        "environment_and_places": ["home_living_room"],
        "lighting": "daylight",
        "person_count": 2,
    }
    payload.update(overrides)
    return payload


def _varying_series(*, target_authored: bool = False) -> dict:
    """Baseline'da GERÇEK varyans var → bağımsızlık ölçülebilir.

    Sabit bir baseline'da Pearson tanımsızdır; o durum ayrı testte (CANDIDATE)
    kilitlenir.
    """
    posts: list[str] = []
    times: list[str] = []
    frames: list[dict] = []

    for index in range(WEEKS):
        moment = BASE + timedelta(days=7 * index, hours=(index % 3) - 1)
        posts.append("Yarın yeni parça üzerinde çalışacağım " + _words(10 + (index * 3) % 7))
        times.append(moment.isoformat())
        frames.append(
            _frame(
                f"base{index}",
                moment.isoformat(),
                detected_objects=["kitchen_table"] if index % 4 != 3 else ["cup"],
                lighting="daylight" if index % 3 != 2 else "indoor",
                person_count=2 if index % 5 else 1,
            )
        )

    for index in range(WEEKS):
        moment = TARGET + timedelta(days=7 * index)
        posts.append(_words(60 + (index % 4)))
        times.append(moment.isoformat())
        frames.append(
            _frame(
                f"target{index}",
                moment.isoformat(),
                capture_class="edited_composite" if target_authored else "camera_incidental",
                has_measurable_background=not target_authored,
                detected_objects=["mirror"],
                environment_and_places=["dark_studio"],
                lighting="low_key_dark",
                person_count=1,
            )
        )

    return {
        "target_profile": {
            "posts": posts,
            "post_times": times,
            "post_evidence_types": ["platform_post"] * len(posts),
        },
        "visual_evidence": {"frames": frames},
    }


def _constant_series(authored: bool = False) -> dict:
    """Baseline tamamen sabit: korelasyon tanımsız → bağımsızlık BİLİNMİYOR."""
    posts: list[str] = []
    times: list[str] = []
    frames: list[dict] = []
    for index in range(WEEKS):
        moment = BASE + timedelta(days=7 * index)
        posts.append("Yarın yeni parça üzerinde çalışacağım, hedefim bitirmek")
        times.append(moment.isoformat())
        frames.append(_frame(f"base{index}", moment.isoformat(), detected_objects=["kitchen_table"]))
    for index in range(WEEKS):
        moment = TARGET + timedelta(days=7 * index)
        posts.append("keşke artık hiçbir şey olmasa, yoruldum")
        times.append(moment.isoformat())
        frames.append(
            _frame(
                f"target{index}",
                moment.isoformat(),
                capture_class="edited_composite" if authored else "camera_incidental",
                has_measurable_background=not authored,
                detected_objects=["mirror"],
                environment_and_places=["dark_studio"],
                lighting="low_key_dark",
                person_count=1,
            )
        )
    return {
        "target_profile": {"posts": posts, "post_times": times},
        "visual_evidence": {"frames": frames},
    }


# --- Durum makinesi ---------------------------------------------------------


def test_no_dated_observation_is_insufficient_data() -> None:
    report = analyze_life_rupture({"posts": ["metin"], "post_times": [""]})

    assert isinstance(report, LifeRuptureReport)
    assert report.status == "INSUFFICIENT_DATA"
    assert report.cluster_state == "INSUFFICIENT_EVIDENCE"
    assert report.evidence_entry_count == 0
    assert report.diagnostics["undated_post_count"] == 1
    assert report.unknowns  # ne bilinmiyor: yazılı


def test_insufficient_data_differs_from_no_change() -> None:
    """Sözleşme #14: "veri yok" ile "değişim yok" AYNI statü değildir."""
    posts = ["yarın başlayacağım"] * 3
    times = [(BASE + timedelta(days=7 * index)).isoformat() for index in range(3)]
    report = analyze_life_rupture({"posts": posts, "post_times": times})

    assert report.status in ("INSUFFICIENT_BASELINE", "INSUFFICIENT_DATA")
    assert report.status != "NO_RUPTURE"
    assert report.root_cause == "UNKNOWN"
    assert report.evidence_entry_count == 0  # sapma iddiası ÜRETİLMEDİ


# --- Kırılma tespiti --------------------------------------------------------


def test_sustained_multi_axis_change_is_confirmed() -> None:
    data = _varying_series()
    report = analyze_life_rupture(
        data["target_profile"], visual_evidence=data["visual_evidence"], subject_id="synthetic_alpha"
    )

    assert report.status == "RUPTURE_CONFIRMED"
    assert report.cluster_state == "DETECTED"
    assert report.family_count >= 3
    assert {"timing", "text", "ritual"} <= set(report.families)
    assert report.persistence_days >= 60
    assert report.independence_assessment["status"] == "confirmed"
    assert report.confirmed_independent_signal_count >= 3
    assert report.root_cause == "UNKNOWN"
    assert report.evidence_entry_count > 0
    assert report.decision_summary


def test_constant_baseline_cannot_confirm_independence() -> None:
    """Sabit baseline'da korelasyon tanımsız → "3 bağımsız sinyal" İDDİA EDİLEMEZ."""
    data = _constant_series()
    report = analyze_life_rupture(data["target_profile"], visual_evidence=data["visual_evidence"])

    assert report.status == "RUPTURE_CANDIDATE"
    assert report.cluster_state == "CANDIDATE"
    assert report.independence_assessment["status"] == "unknown"
    assert report.confirmed_independent_signal_count == 0
    assert any("bağımsızlık" in unknown for unknown in report.unknowns)


def test_authored_shift_confounds_life_axes() -> None:
    data = _varying_series(target_authored=True)
    report = analyze_life_rupture(
        data["target_profile"], visual_evidence=data["visual_evidence"], subject_id="synthetic_beta"
    )

    assert report.status == "RUPTURE_CONFOUNDED_BY_MEDIUM_CHANGE"
    assert report.cluster_state == "CONFOUNDED"
    assessment = report.medium_change_assessment
    assert assessment["status"] == "changed"
    assert assessment["baseline_rate"] == 0.0
    assert assessment["comparison_rate"] == 1.0
    assert "ritual" in report.confounded_axes
    assert any("OKUNAMAZ" in line for line in report.summary)


def test_stable_incidental_series_has_no_rupture() -> None:
    """Aynı davranış sürüyorsa küme çıkmaz (yanlış pozitif kilidi)."""
    posts, times, frames = [], [], []
    for index in range(52):
        moment = BASE + timedelta(days=7 * index)
        posts.append("Bugün sakin bir gün")
        times.append(moment.isoformat())
        frames.append(_frame(f"f{index}", moment.isoformat(), detected_objects=["kitchen_table"]))

    report = analyze_life_rupture({"posts": posts, "post_times": times}, visual_evidence={"frames": frames})

    assert report.status == "NO_RUPTURE"
    assert report.cluster_state == "NO_SIGNIFICANT_CLUSTER"
    assert report.family_count == 0
    assert report.medium_change_assessment["status"] == "stable"


# --- Yorum yasağı, determinizm, denetlenebilirlik ---------------------------


def test_report_text_contains_no_interpretation_roots() -> None:
    data = _varying_series(target_authored=True)
    report = analyze_life_rupture(data["target_profile"], visual_evidence=data["visual_evidence"])
    haystack = " ".join(
        [
            *report.summary,
            *report.falsification_checks,
            *report.unknowns,
            report.machine_note,
            report.decision_summary,
            *(finding.direction for finding in report.findings),
        ]
    ).lower()

    for root in FORBIDDEN_INTERPRETATION_ROOTS:
        assert root not in haystack, f"yorum kökü rapora sızdı: {root}"
    assert report.root_cause == "UNKNOWN"


def test_result_does_not_depend_on_subject_id() -> None:
    """Aynı veri + farklı ad → aynı ölçüm. Kişiye özel kod olmadığının kilidi."""
    data = _varying_series()
    first = analyze_life_rupture(
        data["target_profile"], visual_evidence=data["visual_evidence"], subject_id="alpha"
    )
    second = analyze_life_rupture(
        data["target_profile"], visual_evidence=data["visual_evidence"], subject_id="beta"
    )

    first_dump = first.model_dump(mode="json", exclude={"subject_id", "computed_at"})
    second_dump = second.model_dump(mode="json", exclude={"subject_id", "computed_at"})
    assert first_dump == second_dump


def test_report_is_reproducible_and_serializable() -> None:
    data = _varying_series()
    first = analyze_life_rupture(data["target_profile"], visual_evidence=data["visual_evidence"])
    second = analyze_life_rupture(data["target_profile"], visual_evidence=data["visual_evidence"])

    assert first.model_dump(mode="json", exclude={"computed_at"}) == second.model_dump(
        mode="json", exclude={"computed_at"}
    )
    assert REPORT_ID_RE.match(first.report_id)
    timeline = first.evidence_timeline
    assert timeline is not None
    for entry in timeline.entries:
        assert EVIDENCE_ID_RE.match(entry.evidence_id)


def test_report_id_changes_when_evidence_changes() -> None:
    first = analyze_life_rupture(**_kwargs(_varying_series()))
    other = _varying_series()
    other["target_profile"]["posts"] = other["target_profile"]["posts"][:-1]
    other["target_profile"]["post_times"] = other["target_profile"]["post_times"][:-1]
    second = analyze_life_rupture(**_kwargs(other))

    assert first.report_id != second.report_id


def _kwargs(data: dict) -> dict:
    return {"target_profile": data["target_profile"], "visual_evidence": data["visual_evidence"]}


def test_every_finding_is_auditable() -> None:
    """Sözleşme §11.1: tek cümle değil, denetlenebilir kayıt."""
    data = _varying_series()
    report = analyze_life_rupture(data["target_profile"], visual_evidence=data["visual_evidence"])

    assert report.findings
    for finding in report.findings:
        assert isinstance(finding, Finding)
        assert finding.finding_id.startswith("fi_")
        assert finding.signal_id and finding.signal_family
        assert finding.baseline_period["start"] and finding.comparison_period["end"]
        assert finding.baseline_value is not None and finding.observed_value is not None
        assert finding.delta is not None
        assert finding.direction in (
            "increased", "decreased", "appeared", "disappeared", "changed", "stable", "unknown"
        )
        assert finding.deviation_method in ("z_score", "constant_break")
        assert finding.threshold_or_tolerance is not None
        assert finding.persistence["status"]
        assert finding.independence_status in ("confirmed", "unknown", "dependent", "not_applicable")
        assert finding.measurement_status in (
            "measured", "partial", "not_measurable", "insufficient_data", "confounded"
        )
        assert finding.source_refs


def test_contradicting_findings_are_preserved() -> None:
    """Sözleşme #17: karşıt yönlü bulgu silinmez, çelişki olarak görünür."""
    data = _varying_series()
    report = analyze_life_rupture(data["target_profile"], visual_evidence=data["visual_evidence"])

    directions = {finding.signal_id: finding.direction for finding in report.findings}
    assert len(directions) == len(report.findings)  # hiçbiri düşürülmedi
    text_directions = {
        finding.direction for finding in report.findings if finding.signal_family == "text"
    }
    if {"increased", "decreased"} <= text_directions:
        assert report.contradictions  # aynı ailede karşıt yön varsa yazılır
    assert all("note" in item for item in report.contradictions)


# --- Ölçülemeyen eksen dürüstlüğü -----------------------------------------


def test_unmeasurable_axes_are_reported_with_reason() -> None:
    data = _varying_series()
    report = analyze_life_rupture(data["target_profile"])  # görsel kanıt YOK
    axes = {axis.axis: axis for axis in report.axes}

    assert axes["media"].state in ("unavailable", "suppressed")
    assert axes["habitat"].state in ("unavailable", "suppressed")
    assert axes["gaze"].state in ("unavailable", "suppressed")
    assert all(axis.reason for axis in report.axes if axis.state != "measured")
    assert report.diagnostics["visual_frame_count"] == 0
    assert any("görsel kare yok" in unknown for unknown in report.unknowns)


def test_excluded_evidence_is_counted_not_dropped_silently() -> None:
    posts = ["gerçek gönderi"] * WEEKS
    times = [(BASE + timedelta(days=7 * index)).isoformat() for index in range(WEEKS)]
    types = ["platform_post"] * (WEEKS - 2) + ["search_snippet", "search_snippet"]

    report = analyze_life_rupture(
        {"posts": posts, "post_times": times, "post_evidence_types": types}
    )

    excluded = {item["reason"]: item["count"] for item in report.excluded_evidence}
    assert excluded["non_platform_text"] == 2


def test_pillar_strata_evidence_is_carried_but_not_counted() -> None:
    data = _varying_series()
    strata_map = {
        "fossils": [
            {
                "topic": "kitchen_table",
                "last_seen_iso": "2022-03-01T00:00:00+00:00",
                "extinction_confidence": 0.9,
                "early_presence": 0.8,
                "late_presence": 0.0,
            }
        ],
        "drifts": [
            {
                "metric": "solitude_ratio",
                "early_value": 0.2,
                "late_value": 0.9,
                "drift_ratio": 3.5,
                "is_significant": True,
            }
        ],
    }
    report = analyze_life_rupture(
        data["target_profile"], visual_evidence=data["visual_evidence"], strata_map=strata_map
    )

    assert report.prior_pillar_counts_toward_cluster is False
    labels = {item["label"] for item in report.prior_pillar_evidence}
    assert {"kitchen_table", "solitude_ratio"} <= labels
    assert any("Pillar Strata" in line for line in report.summary)
