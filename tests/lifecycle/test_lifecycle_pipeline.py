"""Uçtan uca hat — veriden mühürlü rapora, teşhis iddiası olmadan.

Kilitlenen iddialar:
    * aynı veri farklı ``subject_id`` ile AYNI sonucu verir (kişiye özel kod yok),
    * kurguya kayış (üretim biçimi) yaşam ekseniyle karışırsa rapor
      ``RUPTURE_CONFOUNDED_BY_MEDIUM_CHANGE`` der,
    * rapor metninde yorum kökü GEÇMEZ, ``root_cause`` yalnız ``UNKNOWN``,
    * kanıt kimlikleri ``^ev_[0-9a-f]{20}$`` ve tekrar üretilebilir,
    * veri yoksa "kırılma yok" değil "kanıt yetersiz" denir.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from agent_core.lifecycle.pipeline import FORBIDDEN_INTERPRETATION_ROOTS, analyze_life_rupture
from agent_core.lifecycle.report import LifeRuptureReport

EVIDENCE_ID_RE = re.compile(r"^ev_[0-9a-f]{20}$")
BASE = datetime(2022, 1, 10, 10, tzinfo=timezone.utc)
TARGET = datetime(2024, 1, 10, 23, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _series(
    posts_per_period: int = 13,
    *,
    target_authored: bool = False,
    target_objects: list[str] | None = None,
) -> dict:
    posts: list[str] = []
    times: list[str] = []
    frames: list[dict] = []

    for index in range(posts_per_period):
        ts = BASE + timedelta(days=7 * index)
        posts.append("Yarın yeni parça üzerinde çalışacağım, hedefim bitirmek")
        times.append(_iso(ts))
        frames.append(
            {
                "frame_id": f"base{index}",
                "observed_at": _iso(ts),
                "capture_class": "camera_incidental",
                "has_measurable_background": True,
                "detected_objects": ["kitchen_table", "cup"],
                "environment_and_places": ["home_living_room"],
                "lighting": "daylight",
                "person_count": 2,
            }
        )

    for index in range(posts_per_period):
        ts = TARGET + timedelta(days=7 * index)
        posts.append("keşke artık hiçbir şey olmasa, yoruldum")
        times.append(_iso(ts))
        frames.append(
            {
                "frame_id": f"target{index}",
                "observed_at": _iso(ts),
                "capture_class": "edited_composite" if target_authored else "camera_incidental",
                "has_measurable_background": not target_authored,
                "detected_objects": target_objects or ["mirror"],
                "environment_and_places": ["dark_studio"],
                "lighting": "low_key_dark",
                "person_count": 1,
            }
        )

    return {
        "target_profile": {
            "posts": posts,
            "post_times": times,
            "post_evidence_types": ["platform_post"] * len(posts),
        },
        "visual_evidence": {"frames": frames},
    }


# --- Durum makinesi ---------------------------------------------------------


def test_no_dated_observation_is_insufficient_data() -> None:
    report = analyze_life_rupture({"posts": ["metin"], "post_times": [""]})

    assert isinstance(report, LifeRuptureReport)
    assert report.status == "INSUFFICIENT_DATA"
    assert report.evidence_entry_count == 0
    assert report.diagnostics["undated_post_count"] == 1


def test_too_few_points_never_produce_rupture() -> None:
    posts = ["yarın başlayacağım"] * 3
    times = [_iso(BASE + timedelta(days=7 * index)) for index in range(3)]
    report = analyze_life_rupture({"posts": posts, "post_times": times})

    assert report.status in ("INSUFFICIENT_BASELINE", "INSUFFICIENT_DATA")
    assert report.root_cause == "UNKNOWN"
    assert report.evidence_entry_count == 0  # sapma iddiası ÜRETİLMEDİ


# --- Kırılma tespiti --------------------------------------------------------


def test_sustained_multi_axis_change_is_confirmed() -> None:
    data = _series()
    report = analyze_life_rupture(
        data["target_profile"], visual_evidence=data["visual_evidence"], subject_id="synthetic_alpha"
    )

    assert report.status == "RUPTURE_CONFIRMED"
    assert report.family_count >= 3
    assert {"timing", "text", "ritual"} <= set(report.families)
    assert report.persistence_days >= 60
    assert report.cluster_window_start is not None and report.cluster_window_end is not None
    assert report.root_cause == "UNKNOWN"
    assert report.evidence_entry_count > 0


def test_authored_shift_confounds_life_axes() -> None:
    data = _series(target_authored=True)
    report = analyze_life_rupture(
        data["target_profile"], visual_evidence=data["visual_evidence"], subject_id="synthetic_beta"
    )

    assert report.status == "RUPTURE_CONFOUNDED_BY_MEDIUM_CHANGE"
    assert report.medium_shift_rate is not None and report.medium_shift_rate > 0.5
    assert "ritual" in report.confounded_axes
    assert any("OKUNAMAZ" in line for line in report.summary)


def test_stable_incidental_series_has_no_rupture() -> None:
    """Aynı davranış sürüyorsa küme çıkmaz (yanlış pozitif kilidi)."""
    posts, times, frames = [], [], []
    # 52 hafta: baseline varsayılan 180 günü aşan bir seri (hedef penceresi dolu).
    for index in range(52):
        ts = BASE + timedelta(days=7 * index)
        posts.append("Bugün sakin bir gün")
        times.append(_iso(ts))
        frames.append(
            {
                "frame_id": f"f{index}",
                "observed_at": _iso(ts),
                "capture_class": "camera_incidental",
                "has_measurable_background": True,
                "detected_objects": ["kitchen_table"],
                "environment_and_places": ["home_living_room"],
                "lighting": "daylight",
                "person_count": 2,
            }
        )

    report = analyze_life_rupture(
        {"posts": posts, "post_times": times},
        visual_evidence={"frames": frames},
    )

    assert report.status == "NO_RUPTURE"
    assert report.family_count == 0


# --- Yorum yasağı ve determinizm -------------------------------------------


def test_report_text_contains_no_interpretation_roots() -> None:
    data = _series(target_authored=True)
    report = analyze_life_rupture(data["target_profile"], visual_evidence=data["visual_evidence"])
    haystack = " ".join([*report.summary, *report.falsification_checks, report.machine_note]).lower()

    for root in FORBIDDEN_INTERPRETATION_ROOTS:
        assert root not in haystack, f"yorum kökü rapora sızdı: {root}"
    assert report.root_cause == "UNKNOWN"


def test_result_does_not_depend_on_subject_id() -> None:
    """Aynı veri + farklı ad → aynı ölçüm. Kişiye özel kod olmadığının kilidi."""
    data = _series()
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
    data = _series()
    first = analyze_life_rupture(data["target_profile"], visual_evidence=data["visual_evidence"])
    second = analyze_life_rupture(data["target_profile"], visual_evidence=data["visual_evidence"])

    assert first.model_dump(mode="json", exclude={"computed_at"}) == second.model_dump(
        mode="json", exclude={"computed_at"}
    )
    timeline = first.evidence_timeline
    assert timeline is not None
    for entry in timeline.entries:
        assert EVIDENCE_ID_RE.match(entry.evidence_id)


# --- Ölçülemeyen eksen dürüstlüğü -----------------------------------------


def test_unmeasurable_axes_are_reported_with_reason() -> None:
    data = _series()
    report = analyze_life_rupture(data["target_profile"])  # görsel kanıt YOK
    axes = {axis.axis: axis for axis in report.axes}

    assert axes["media"].state in ("unavailable", "suppressed")
    assert axes["habitat"].state in ("unavailable", "suppressed")
    assert axes["gaze"].state in ("unavailable", "suppressed")
    assert all(axis.reason for axis in report.axes if axis.state != "measured")
    assert report.diagnostics["visual_frame_count"] == 0


def test_pillar_strata_evidence_is_carried_but_not_counted() -> None:
    data = _series()
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
