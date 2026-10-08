"""Deterministic adapter from the real 7-Pillar bundle to EvidenceItems.

This module performs classification and faithful field transfer only. It does
not infer causes, convert source scores to confidence, or make strategy items
available to message-generation agents.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from agent_core.domain.evidence_models import EvidenceItem, EpistemicType
from agent_core.domain.pillar_models import EvidenceStatus
from agent_core.domain.pillar_wave2_models import FullPillarBundle
from agent_core.engines.frequency_engine import parse_timestamp


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return str(value.value)
    raise TypeError(f"Unsupported evidence value: {type(value).__name__}")


def _as_status(value: EvidenceStatus | str) -> EvidenceStatus:
    return value if isinstance(value, EvidenceStatus) else EvidenceStatus(value)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _profile_scope(target_profile: dict[str, Any] | None) -> dict[str, Any]:
    """Return metadata about the supplied corpus without copying its contents."""
    if not isinstance(target_profile, dict):
        return {
            "platform": "unknown",
            "source_count": None,
            "source_count_unit": "non-empty bio/post text segments",
            "post_count": None,
            "timestamped_post_count": None,
            "time_window": None,
            "time_window_note": "No target_profile supplied; corpus count/window unavailable.",
            "provenance_note": "Only source-provided references are carried; no missing source IDs are synthesized.",
        }

    profile = target_profile
    raw_posts = profile.get("posts")
    posts = raw_posts if isinstance(raw_posts, list) else []
    bio = _text(profile.get("bio"))

    nonempty_posts = 0
    for post in posts:
        if isinstance(post, str):
            post_text = post
        elif isinstance(post, dict):
            post_text = str(post.get("text") or post.get("caption") or "")
        else:
            post_text = ""
        nonempty_posts += bool(post_text.strip())

    # Align dates only to non-empty post text actually included by VoidEngine.
    # Undated text remains in the corpus and is disclosed in the scope note.
    raw_times = profile.get("post_times")
    post_times = raw_times if isinstance(raw_times, list) else []
    raw_meta = profile.get("posts_meta")
    posts_meta = raw_meta if isinstance(raw_meta, list) else []
    timestamps: list[datetime] = []
    for index, post in enumerate(posts):
        if isinstance(post, str):
            post_text = post
        elif isinstance(post, dict):
            post_text = str(post.get("text") or post.get("caption") or "")
        else:
            post_text = ""
        if not post_text.strip():
            continue
        raw_timestamp = post_times[index] if index < len(post_times) else None
        if raw_timestamp is None and isinstance(post, dict):
            raw_timestamp = post.get("created_at") or post.get("timestamp")
        if raw_timestamp is None and index < len(posts_meta) and isinstance(posts_meta[index], dict):
            raw_timestamp = posts_meta[index].get("created_at") or posts_meta[index].get("timestamp")
        parsed = parse_timestamp(raw_timestamp)
        if parsed is not None:
            timestamps.append(parsed)
    window = (
        {"start": min(timestamps).isoformat(), "end": max(timestamps).isoformat()}
        if timestamps
        else None
    )
    return {
        "platform": str(profile.get("platform") or "unknown"),
        "source_count": int(bool(bio)) + nonempty_posts,
        "source_count_unit": "non-empty bio/post text segments",
        "post_count": len(posts),
        "timestamped_post_count": len(timestamps),
        "time_window": window,
        "time_window_note": "Non-empty posts with aligned timestamps only; undated text may also be in the corpus.",
        "provenance_note": "Only source-provided references are carried; no missing source IDs are synthesized.",
    }


def _range_bounds(value: str) -> tuple[datetime | None, datetime | None]:
    parts = [part.strip() for part in (value or "").split("→") if part.strip()]
    parsed = [parse_timestamp(part) for part in parts]
    dates = [item for item in parsed if item is not None]
    if not dates:
        return None, None
    return min(dates), max(dates)


def _canonicalize(value: Any) -> Any:
    """Normalize equivalent Pydantic/default values before hashing."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.isoformat()
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _canonicalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if type(value) is float and value.is_integer():
        # Pydantic can retain a numeric default as int on model construction,
        # but serialize it as float after parsing; equal values need equal IDs.
        return int(value)
    return value


def _stable_id(source_key: str, fields: dict[str, Any]) -> str:
    canonical = json.dumps(
        _canonicalize({"source_key": source_key, **fields}),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return "ev_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def adapt_pillar_bundle(
    bundle: FullPillarBundle | dict[str, Any] | None,
    *,
    target_profile: dict[str, Any] | None = None,
) -> list[EvidenceItem]:
    """Adapt a ``FullPillarBundle`` without adding interpretation.

    The resulting list is stable for identical inputs. ``computed_at`` is not
    part of evidence identity, so rerunning the same deterministic analysis does
    not create new IDs solely because the wall clock changed.
    """
    if bundle is None:
        return []
    if isinstance(bundle, FullPillarBundle):
        typed = bundle
    elif isinstance(bundle, dict):
        typed = FullPillarBundle.model_validate(bundle)
    else:
        raise TypeError("bundle must be FullPillarBundle, dict, or None")

    profile_scope = _profile_scope(target_profile)
    items: list[EvidenceItem] = []

    def add(
        *,
        source_key: str,
        epistemic_type: EpistemicType,
        source_engine: str,
        source_status: EvidenceStatus | str,
        content: str,
        provenance_refs: list[str] | None = None,
        scope: dict[str, Any] | None = None,
        observed_at: datetime | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        source_metrics: dict[str, Any] | None = None,
    ) -> None:
        clean_content = _text(content)
        if not clean_content:
            return
        refs = sorted({str(ref) for ref in (provenance_refs or []) if str(ref).strip()})
        status = _as_status(source_status)
        fields: dict[str, Any] = {
            "epistemic_type": epistemic_type,
            "source_engine": source_engine,
            "source_status": status,
            "content": clean_content,
            "provenance_refs": refs,
            "scope": scope,
            "observed_at": observed_at,
            "window_start": window_start,
            "window_end": window_end,
            # Current pillar scores are heuristic/source metrics, not calibrated
            # probabilities. Leave the canonical confidence explicitly unknown.
            "confidence": None,
            "source_metrics": source_metrics,
        }
        items.append(EvidenceItem(evidence_id=_stable_id(source_key, fields), **fields))

    # FREQUENCY: preserve measured report/window values, not a psychological
    # reading of posting rhythm.
    frequency = typed.frequency
    has_frequency_measurements = bool(
        frequency.samples
        or frequency.flow_windows
        or frequency.friction_collapses
        or frequency.phase_shifts
    )
    if has_frequency_measurements:
        sample_times = [sample.t for sample in frequency.samples]
        add(
            source_key="frequency:summary",
            epistemic_type="observation",
            source_engine="frequency_engine",
            source_status=frequency.status,
            content=frequency.machine_note
            or f"Frequency summary from {len(frequency.samples)} activity bucket(s).",
            provenance_refs=frequency.evidence_refs,
            scope={**profile_scope, "measurement": "post activity buckets"},
            window_start=min(sample_times) if sample_times else None,
            window_end=max(sample_times) if sample_times else None,
            source_metrics={
                "sample_count": len(frequency.samples),
                "energy_mean": frequency.energy_mean,
                "energy_std": frequency.energy_std,
                "night_energy_share": frequency.night_energy_share,
                "dominant_period_days": frequency.dominant_period_days,
            },
        )
        for sample in frequency.samples:
            add(
                source_key=f"frequency:sample:{sample.platform}:{sample.t.isoformat()}",
                epistemic_type="observation",
                source_engine="frequency_engine",
                source_status=frequency.status,
                content=(
                    f"Activity bucket at {sample.t.isoformat()}: "
                    f"{sample.post_count} post(s)."
                ),
                scope={
                    **profile_scope,
                    "measurement": "time-bucketed post activity sample",
                    "timestamp_semantics": "WaveSample.t as emitted; bucket timestamp, not each post's exact time",
                },
                observed_at=sample.t,
                source_metrics={
                    "energy": sample.energy,
                    "post_count": sample.post_count,
                    "mean_text_len": sample.mean_text_len,
                    "engagement": sample.engagement,
                    "platform": sample.platform,
                },
            )
        for window in frequency.flow_windows + frequency.friction_collapses:
            add(
                source_key=f"frequency:window:{window.label}:{window.start.isoformat()}",
                epistemic_type="observation",
                source_engine="frequency_engine",
                source_status=frequency.status,
                content=f"Frequency window label={window.label}; sample_count={window.sample_count}.",
                provenance_refs=frequency.evidence_refs,
                scope={
                    **profile_scope,
                    "measurement": "within-corpus energy window",
                    "provenance_granularity": "frequency-report references; not one-to-one window linkage",
                },
                window_start=window.start,
                window_end=window.end,
                source_metrics={
                    "label": window.label,
                    "peak_energy": window.peak_energy,
                    "mean_energy": window.mean_energy,
                    "sample_count": window.sample_count,
                },
            )
        for shift in frequency.phase_shifts:
            add(
                source_key=f"frequency:phase:{shift.platform_a}:{shift.platform_b}",
                epistemic_type="observation",
                source_engine="frequency_engine",
                source_status=shift.status,
                content=(
                    f"Phase-shift measurement between {shift.platform_a} and "
                    f"{shift.platform_b}; no causal interpretation attached."
                ),
                provenance_refs=frequency.evidence_refs,
                scope={
                    **profile_scope,
                    "measurement": "cross-platform timing correlation",
                    "provenance_granularity": "frequency-report references; not phase-shift-specific IDs",
                },
                source_metrics={"lag_hours": shift.lag_hours, "correlation": shift.correlation},
            )

    # SEISMOS: separate observed event fields from engine-generated hypotheses.
    for event in typed.seismos.events:
        event_kind = event.kind.value
        add(
            source_key=f"seismos:{event.event_id}:observation",
            epistemic_type="observation",
            source_engine="seismos_engine",
            source_status=event.status,
            content=" ".join(event.observables) or f"Event kind={event_kind}.",
            provenance_refs=event.evidence_refs,
            scope={
                **profile_scope,
                "event_kind": event_kind,
                "statement_scope": "event only; cause unknown",
                "timestamp_semantics": "SeismicEvent.timestamp as emitted by the engine",
            },
            observed_at=event.timestamp,
            window_start=event.window_start,
            window_end=event.window_end,
            source_metrics={"event_kind": event_kind, "intensity": event.intensity, **event.metrics},
        )
        for hypothesis in event.hypotheses:
            add(
                source_key=f"seismos:{event.event_id}:hypothesis:{hypothesis}",
                epistemic_type="inference",
                source_engine="seismos_engine",
                source_status=event.status,
                content=hypothesis,
                provenance_refs=event.evidence_refs,
                scope={
                    **profile_scope,
                    "parent_event_id": event.event_id,
                    "interpretation": "engine-generated, unverified hypothesis; not an observed cause",
                    "source_status_semantics": "copied from parent event; does not validate this hypothesis",
                    "timestamp_semantics": "parent SeismicEvent.timestamp; not a hypothesis creation time",
                },
                observed_at=event.timestamp,
                window_start=event.window_start,
                window_end=event.window_end,
                source_metrics={"event_kind": event_kind},
            )

    # VOID: an absence is scoped to the analyzed corpus and the engine prior,
    # which may use supplied interest metadata. It is not a motive/life claim.
    void = typed.void
    profile_input = target_profile if isinstance(target_profile, dict) else {}
    has_interest_metadata = bool(
        profile_input.get("interests") or profile_input.get("following_topics")
    )
    void_scope = {
        **profile_scope,
        "corpus_basis": "target_profile.bio + target_profile.posts",
        "comparison_basis": (
            "CATEGORY_LEXICON engine prior, optionally boosted by "
            "target_profile.interests/following_topics; not a personal historical baseline"
        ),
        "interest_metadata_available": has_interest_metadata,
        "provenance_granularity": "category/cue count; not post-level quotations",
    }
    for signal in void.signals:
        scope = {**void_scope, "category": signal.category, "topic": signal.topic}
        add(
            source_key=f"void:{signal.category}:absence",
            epistemic_type="absence",
            source_engine="void_engine",
            source_status=signal.status,
            content=" ".join(signal.observables)
            or f"Category {signal.category!r} has a lower observed presence in this corpus than the engine prior.",
            provenance_refs=signal.evidence_refs,
            scope=scope,
            source_metrics={
                "expected_presence": signal.expected_presence,
                "actual_presence": signal.actual_presence,
                "absence_delta": signal.absence_delta,
                "absence_score": signal.absence_score,
            },
        )
        for hypothesis in signal.hypotheses:
            add(
                source_key=f"void:{signal.category}:hypothesis:{hypothesis.value}",
                epistemic_type="inference",
                source_engine="void_engine",
                source_status=signal.status,
                content=f"Engine hypothesis: {hypothesis.value} (not independently established).",
                provenance_refs=signal.evidence_refs,
                scope={
                    **scope,
                    "interpretation": "hypothesis only; absence does not establish motive",
                    "source_status_semantics": "copied from VoidSignal; does not validate this hypothesis",
                },
                source_metrics={"absence_score": signal.absence_score},
            )

    # STRATA: lexical/engagement deltas and topic drop-offs stay source-scoped.
    strata = typed.strata
    early_start, early_end = _range_bounds(strata.early_range)
    late_start, late_end = _range_bounds(strata.late_range)
    strata_start = early_start or early_end
    strata_end = late_end or late_start
    strata_scope = {
        **profile_scope,
        "early_range": strata.early_range or None,
        "late_range": strata.late_range or None,
        "comparison_method": "first and last thirds of the available post series",
        "archaeological_depth_days": strata.archaeological_depth_days,
        "layer_count": strata.layer_count,
        "significance_note": "is_significant is an engine threshold flag, not a statistical p-value",
        "provenance_granularity": "report-level range/topic references; not post-level IDs",
    }
    for drift in strata.drifts:
        add(
            source_key=f"strata:drift:{drift.metric}",
            epistemic_type="observation",
            source_engine="strata_engine",
            source_status=strata.status,
            content=drift.observable or f"Metric {drift.metric} changed between early and late samples.",
            provenance_refs=strata.evidence_refs,
            scope=strata_scope,
            window_start=strata_start,
            window_end=strata_end,
            source_metrics={
                "metric": drift.metric,
                "early_value": drift.early_value,
                "late_value": drift.late_value,
                "drift_ratio": drift.drift_ratio,
                "is_significant_threshold_flag": drift.is_significant,
            },
        )
    for fossil in strata.fossils:
        last_seen = parse_timestamp(fossil.last_seen_iso)
        add(
            source_key=f"strata:fossil:{fossil.topic}",
            epistemic_type="absence",
            source_engine="strata_engine",
            source_status=strata.status,
            content=" ".join(fossil.observables)
            or f"Topic {fossil.topic!r} was present in the early subset and not observed in the late subset.",
            provenance_refs=fossil.evidence_refs,
            scope={
                **strata_scope,
                "absence_scope": "late subset only",
                "topic": fossil.topic,
                "timestamp_semantics": "FossilRecord.last_seen_iso",
            },
            observed_at=last_seen,
            window_start=strata_start,
            window_end=strata_end,
            source_metrics={
                "topic": fossil.topic,
                "last_seen_iso": fossil.last_seen_iso,
                "early_presence": fossil.early_presence,
                "late_presence": fossil.late_presence,
                # Preserve the engine field as a source metric; do not promote it
                # to canonical calibrated confidence.
                "source_extinction_confidence": fossil.extinction_confidence,
                "last_seen_timestamp_parsed": last_seen.isoformat() if last_seen else None,
            },
        )

    # GRAVITY: record recurring term/engagement measurements, not a claim of
    # actual personal preference or psychological attraction.
    gravity = typed.gravity
    for well in gravity.wells:
        add(
            source_key=f"gravity:well:{well.anchor}",
            epistemic_type="observation",
            source_engine="gravity_engine",
            source_status=gravity.status,
            content=" ".join(well.observables)
            or f"Anchor {well.anchor!r} was emitted by the frequency/engagement ranking engine.",
            provenance_refs=well.evidence_refs,
            scope={
                **profile_scope,
                "measurement": "text recurrence and engagement ranking; not stated preference",
                "provenance_granularity": "anchor/count-level source reference; not post-level IDs",
            },
            source_metrics={
                "anchor": well.anchor,
                "mass": well.mass,
                "density": well.density,
                "pull": well.pull,
                "recurrence": well.recurrence,
                "is_black_hole_threshold_flag": well.is_black_hole,
            },
        )

    # PULSE: these are textual post-pattern metrics (despite the legacy model
    # name BiometricSignal); the fixed engine baselines are not personal history.
    pulse = typed.pulse
    for signal in pulse.signals:
        add(
            source_key=f"pulse:signal:{signal.signal_type}",
            epistemic_type="observation",
            source_engine="pulse_engine",
            source_status=pulse.status,
            content=(
                f"Text metric {signal.signal_type} ({signal.label}): "
                f"value={signal.value}, z_score={signal.z_score}."
            ),
            provenance_refs=pulse.evidence_refs,
            scope={
                **profile_scope,
                "measurement_domain": "textual posts only",
                "baseline_basis": "engine threshold; not personal longitudinal baseline",
                "rhythm_signature_semantics": "rule-derived textual-pattern label; not a physiological reading",
                "provenance_granularity": "report-level corpus count; not per-post linkage",
            },
            source_metrics={
                "signal_type": signal.signal_type,
                "value": signal.value,
                "z_score": signal.z_score,
                "source_baseline": signal.baseline,
                "source_interpretation": signal.interpretation,
                "report_baseline_volatility": pulse.baseline_volatility,
                "source_rhythm_signature": pulse.rhythm_signature,
            },
        )

    # KEY output is a recommendation layer. It is carried as STRATEGY for audit
    # completeness, but callers must not inject these items into forensic or
    # message-generation prompts. core_tension is a synthesized hypothesis.
    key = typed.key
    key_scope = {
        **profile_scope,
        "heuristic_only": True,
        "reported_confidence_semantics": "KeyEngine active-report coverage ratio (active/6), not calibrated probability",
        "provenance_granularity": "key-report-level synthesis; not direct source-post references",
    }
    key_metrics = {
        "source_key_report_confidence": key.confidence,
        "frequency_night_energy_share": typed.frequency.night_energy_share,
        "pulse_baseline_volatility": typed.pulse.baseline_volatility,
    }
    if key.frequency_signature:
        add(
            source_key="key:frequency_signature",
            epistemic_type="inference",
            source_engine="key_engine",
            source_status=key.status,
            content=key.frequency_signature,
            provenance_refs=key.evidence_refs,
            scope={
                **key_scope,
                "summary_of": "frequency report",
                "classification_semantics": "engine-generated label from source frequency metrics",
            },
            source_metrics=key_metrics,
        )
    if key.core_tension:
        add(
            source_key="key:core_tension",
            epistemic_type="inference",
            source_engine="key_engine",
            source_status=key.status,
            content=key.core_tension,
            provenance_refs=key.evidence_refs,
            scope={**key_scope, "interpretation": "cross-pillar synthesis; not a direct observation"},
            source_metrics=key_metrics,
        )
    for name, value in (
        ("gate_key", key.gate_key),
        ("timing_window", key.timing_window),
        ("channel_recommendation", key.channel_recommendation),
    ):
        add(
            source_key=f"key:{name}",
            epistemic_type="strategy",
            source_engine="key_engine",
            source_status=key.status,
            content=value,
            provenance_refs=key.evidence_refs,
            scope={**key_scope, "strategy_field": name, "not_evidence": True},
            source_metrics=key_metrics,
        )
    for wall in key.walls:
        add(
            source_key=f"key:wall:{wall}",
            epistemic_type="strategy",
            source_engine="key_engine",
            source_status=key.status,
            content=wall,
            provenance_refs=key.evidence_refs,
            scope={**key_scope, "strategy_field": "walls", "not_an_established_personal_boundary": True},
            source_metrics=key_metrics,
        )
    if key.rhythm_note:
        add(
            source_key="key:rhythm_note",
            epistemic_type="inference",
            source_engine="key_engine",
            source_status=key.status,
            content=key.rhythm_note,
            provenance_refs=key.evidence_refs,
            scope={**key_scope, "summary_of": "pulse report; non-biological heuristic"},
            source_metrics=key_metrics,
        )
    for vector in key.vectors:
        add(
            source_key=f"key:vector:{vector.dimension}",
            epistemic_type="strategy",
            source_engine="key_engine",
            source_status=key.status,
            content=f"{vector.dimension}: approach={vector.approach}; avoid={vector.avoid}",
            provenance_refs=key.evidence_refs,
            scope={
                **key_scope,
                "strategy_field": "vectors",
                "source_pillars": vector.source_pillars,
                "reported_vector_confidence_semantics": "source heuristic score; not calibrated probability",
            },
            source_metrics={**key_metrics, "source_vector_confidence": vector.confidence},
        )

    # IDs are content-derived, but duplicate occurrences in one bundle should
    # not duplicate the canonical ledger. Sorting makes list order stable too.
    unique = {item.evidence_id: item for item in items}
    return [unique[evidence_id] for evidence_id in sorted(unique)]
