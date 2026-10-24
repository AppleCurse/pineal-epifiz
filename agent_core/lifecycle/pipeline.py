"""Boylamsal hattın orkestratörü — veriden mühürlü rapora tek çağrı.

Akış (her adım bir öncekine bağlı, hiçbir modül orphan değil):

    target_profile + visual_evidence + frequency_map
        ↓ observation_adapter        (tarihli sinyal serisi + teşhis defteri)
    list[SignalObservation]
        ↓ baseline_builder           (KİŞİNİN KENDİ normali; sabit eşik yok)
    BaselineProfile
        ↓ deviation_detector         (sapma + yapısal confound kaydı)
    list[DeviationFinding] → EvidenceTimeline
        ↓ cluster_analyzer           (3+ bağımsız eksen, kalıcı, rebound yok)
    RuptureCluster
        ↓ report                     (teşhis YOK, kök neden UNKNOWN)

Kişiye özel kod YOKTUR: burada hiçbir hesap adı, şehir, cinsiyet, nesne veya
tarih aralığı sabit değildir. Kişiye özel olan tek şey, kişinin kendi
verisinden çıkan baseline'dır.

Tüketici: ``agent_core.task_executor`` (``status.life_rupture``).
Test: ``tests/lifecycle/test_lifecycle_pipeline.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from agent_core.domain.evidence_models import EvidenceItem, EvidenceTimeline, EvidenceTimelineEntry
from agent_core.lifecycle.baseline_builder import (
    DEFAULT_BASELINE_DAYS,
    BaselineProfile,
    SignalObservation,
    build_baseline,
    ensure_utc,
)
from agent_core.lifecycle.cluster_analyzer import (
    DEFAULT_CLUSTER_WINDOW_DAYS,
    DEFAULT_MIN_FAMILIES,
    DEFAULT_MIN_PERSISTENCE_DAYS,
    ClusterAnalysis,
    analyze_clusters,
)
from agent_core.lifecycle.default_specs import default_registry
from agent_core.lifecycle.deviation_detector import (
    MEDIUM_SIGNAL,
    DeviationFinding,
    build_evidence_timeline,
    detect_deviations,
    make_evidence_id,
)
from agent_core.lifecycle.families import FAMILY_ORDER, signal_family
from agent_core.lifecycle.observation_adapter import AdapterDiagnostics, ObservationAdapter
from agent_core.lifecycle.report import AxisReport, LifeRuptureReport
from agent_core.lifecycle.strata_bridge import StrataDrift, extract_strata_drifts
from agent_core.services.evidence_timeline import build_evidence_timeline as _canonical_timeline

__all__ = ["FORBIDDEN_INTERPRETATION_ROOTS", "analyze_life_rupture"]

#: "Yorum" sayılan kökler: rapor metninde GEÇMEMELİ (testle kilitli).
#: Liste, teşhis iddiası taşıyan Türkçe köklerdir; ölçüm adları (sapma, eksen,
#: pencere) burada değildir.
FORBIDDEN_INTERPRETATION_ROOTS = (
    "depres",
    "mutsuz",
    "mutlu",
    "üzgün",
    "kaygı",
    "anksiyete",
    "travma",
    "yalnız",
    "tükenmiş",
    "kişilik bozukluğu",
)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _axis_reports(
    baseline: BaselineProfile,
    findings: list[DeviationFinding],
    diagnostics: AdapterDiagnostics,
    observations: list[SignalObservation],
) -> list[AxisReport]:
    """Her eksen için dürüst durum: ölçüldü / bastırıldı / kullanılamıyor."""
    deviating_by_family: dict[str, set[str]] = {}
    for finding in findings:
        deviating_by_family.setdefault(finding.family, set()).add(finding.signal_id)

    signals_by_family: dict[str, list[str]] = {}
    for signal_id, signal_baseline in baseline.baselines.items():
        family = signal_family(signal_id)
        if signal_baseline.is_reliable:
            signals_by_family.setdefault(family, []).append(signal_id)

    suppressed_reasons = {
        "habitat": (
            diagnostics.habitat_suppressed_frame_count,
            "gerçek çekim + ölçülebilir arka plan koşulunu sağlayan kare yok",
        ),
        "gaze": (
            diagnostics.gaze_suppressed_frame_count,
            "kurgu/montaj kare ya da yüz ölçümü yok; bakış sinyali üretilmedi",
        ),
        "ritual": (0, "tarihli görsel kare yok; ritüel sözlüğü çıkarılamadı"),
        "media": (0, "tarihli görsel kare yok; üretim biçimi ölçülemedi"),
    }

    axis_reports: list[AxisReport] = []
    for family in FAMILY_ORDER:
        if family == "strata":
            continue  # pillar kanıtı ayrı alanda raporlanır (bağımsız sayılmaz)
        measured = signals_by_family.get(family, [])
        deviating = sorted(deviating_by_family.get(family, set()))
        if measured:
            axis_reports.append(
                AxisReport(
                    axis=family,
                    state="measured",
                    reason=f"{len(measured)} sinyal kişisel baseline'da güvenilir",
                    baseline_signal_count=len(measured),
                    deviating_signals=deviating,
                )
            )
            continue

        suppressed_count, suppressed_reason = suppressed_reasons.get(family, (0, "sinyal üretilmedi"))
        has_any = any(signal_family(obs.signal_id) == family for obs in observations)
        axis_reports.append(
            AxisReport(
                axis=family,
                state="suppressed" if (family in suppressed_reasons and not has_any) else "unavailable",
                reason=(
                    f"{suppressed_reason} (bastırılan kare: {suppressed_count})"
                    if family in suppressed_reasons
                    else "bu eksende baseline penceresinde yeterli gözlem yok"
                ),
                baseline_signal_count=0,
                deviating_signals=deviating,
            )
        )
    return axis_reports


def _strata_timeline_entries(drifts: list[StrataDrift]) -> list[EvidenceItem]:
    """Pillar Strata kayıtlarını kanonik kanıt öğelerine çevirir (kaynak etiketli).

    Fosil = erken dönemde var olup geç dönemde görülmeyen tema → ``absence``;
    kayma = tarih taşımayan erken/geç karşılaştırması → ``inference`` +
    ``temporal_basis="undated"``. Sahte tarih YAZILMAZ.
    """
    items: list[EvidenceItem] = []
    for drift in drifts:
        if not drift.is_significant:
            continue
        basis = "observed_at" if (drift.is_fossil and drift.last_seen) else "undated"
        key = f"{drift.signal_id}|{_iso(drift.last_seen) or 'undated'}"
        if drift.is_fossil:
            content = (
                f"strata fosili: {drift.label} erken {drift.early_value:.4g} → "
                f"geç {drift.late_value:.4g}"
            )
            kind = "absence"
        else:
            content = (
                f"strata kayması: {drift.label} erken {drift.early_value:.4g} → "
                f"geç {drift.late_value:.4g} (oran {drift.drift_ratio:.4g})"
            )
            kind = "inference"
        items.append(
            EvidenceItem(
                evidence_id=make_evidence_id("pillar_strata", basis, key),
                epistemic_type=kind,
                source_engine="pillar_strata",
                content=content,
                provenance_refs=list(drift.evidence_refs),
                scope={
                    "signal_id": drift.signal_id,
                    "is_fossil": drift.is_fossil,
                    "prior_pillar": "strata",
                },
                observed_at=drift.last_seen if drift.is_fossil else None,
                source_metrics={
                    "signal_id": drift.signal_id,
                    "early_value": drift.early_value,
                    "late_value": drift.late_value,
                    "drift_ratio": drift.drift_ratio,
                    "is_significant": drift.is_significant,
                },
            )
        )
    return items


def _summary(
    status: str,
    cluster: Optional[Any],
    baseline: Optional[BaselineProfile],
    findings: list[DeviationFinding],
    diagnostics: AdapterDiagnostics,
    drifts: list[StrataDrift],
) -> list[str]:
    lines: list[str] = []
    if baseline is not None:
        start, end = baseline.baseline_window
        lines.append(
            f"Baseline penceresi {start.date()} → {end.date()}; "
            f"{len(baseline.reliable_signals())} güvenilir sinyal (kişinin kendi normali)."
        )
        if baseline.unspecified_signals:
            lines.append(
                f"Semantiği beyan edilmeyen {len(baseline.unspecified_signals)} sinyal baseline dışında bırakıldı."
            )
    lines.append(f"Hedef pencerede {len(findings)} sapma kaydı üretildi.")

    if cluster is not None:
        families = ", ".join(sorted(cluster.families))
        lines.append(
            f"{cluster.family_count} bağımsız eksende ({families}) kalıcı sapma aynı pencerede: "
            f"{cluster.window_start.date()} → {cluster.window_end.date()}, "
            f"kalıcılık {cluster.persistence_days:.0f} gün."
        )
        if cluster.dropped:
            lines.append(f"Küme dışında bırakılan {len(cluster.dropped)} kayıt: geri sıçrama/kalıcılık eşiği.")
    if status == "RUPTURE_CONFOUNDED_BY_MEDIUM_CHANGE":
        lines.append(
            "Aynı pencerede üretim biçimi de değişti (kurgu/stüdyo oranı yükseldi); "
            "mekân ve bakış sapmaları yaşam koşulu değişimi olarak OKUNAMAZ."
        )
    if diagnostics.undated_visual_summary_skipped:
        lines.append("Tarihsiz görsel özet zaman serisine alınmadı (sahte tarih yazılmadı).")
    if diagnostics.shortcode_mismatch_refs:
        lines.append(
            f"{len(diagnostics.shortcode_mismatch_refs)} kare shortcode zamanıyla uyuşmadığı için reddedildi."
        )
    if drifts:
        significant = [drift for drift in drifts if drift.is_significant]
        lines.append(
            f"Pillar Strata {len(significant)} anlamlı erken/geç kaydı bildirdi "
            "(bağımsız eksen sayılmaz; aynı metin korpusundan türetilir)."
        )
    lines.append("Kök neden: BİLİNMİYOR. Bu rapor teşhis değil, gözlenen değişimin kaydıdır.")
    return lines


def analyze_life_rupture(
    target_profile: Optional[Mapping[str, Any]],
    *,
    visual_evidence: Any = None,
    frequency_map: Any = None,
    strata_map: Any = None,
    subject_id: str = "subject",
    baseline_start: Optional[datetime] = None,
    baseline_end: Optional[datetime] = None,
    target_start: Optional[datetime] = None,
    target_end: Optional[datetime] = None,
    now: Optional[datetime] = None,
    window_days: int = DEFAULT_CLUSTER_WINDOW_DAYS,
    min_families: int = DEFAULT_MIN_FAMILIES,
    min_persistence_days: int = DEFAULT_MIN_PERSISTENCE_DAYS,
    include_timeline: bool = True,
) -> LifeRuptureReport:
    """Tek çağrıda boylamsal analiz. Hata fırlatmaz; durumu raporlar."""
    diagnostics = AdapterDiagnostics()
    observations = ObservationAdapter().transform(
        target_profile,
        visual_evidence=visual_evidence,
        frequency_map=frequency_map,
        diagnostics=diagnostics,
        now=now,
    )

    if not observations:
        return LifeRuptureReport(
            subject_id=subject_id,
            status="INSUFFICIENT_DATA",
            diagnostics=diagnostics.to_dict(),
            summary=[
                "Tarihli gözlem üretilemedi; sapma iddiası kurulmadı.",
                "Kök neden: BİLİNMİYOR. Bu rapor teşhis değil, gözlenen değişimin kaydıdır.",
            ],
            machine_note="no_dated_observation",
        )

    first_seen = observations[0].timestamp
    last_seen = observations[-1].timestamp
    window_start = ensure_utc(baseline_start) if baseline_start else first_seen
    window_end = ensure_utc(baseline_end) if baseline_end else window_start + timedelta(days=DEFAULT_BASELINE_DAYS)
    report_target_start = ensure_utc(target_start) if target_start else window_end + timedelta(seconds=1)
    report_target_end = ensure_utc(target_end) if target_end else last_seen

    profile = build_baseline(subject_id, observations, window_start, window_end, registry=default_registry())
    if report_target_start > report_target_end:
        return LifeRuptureReport(
            subject_id=subject_id,
            status="INSUFFICIENT_DATA",
            baseline_window_start=window_start,
            baseline_window_end=window_end,
            target_window_start=report_target_start,
            target_window_end=report_target_end,
            diagnostics=diagnostics.to_dict(),
            axes=_axis_reports(profile, [], diagnostics, observations),
            summary=[
                "Hedef pencerede gözlem yok: baseline penceresi tüm seriyi kapsıyor.",
                "Kök neden: BİLİNMİYOR. Bu rapor teşhis değil, gözlenen değişimin kaydıdır.",
            ],
            machine_note="target_window_empty",
        )

    if not profile.reliable_signals():
        return LifeRuptureReport(
            subject_id=subject_id,
            status="INSUFFICIENT_BASELINE",
            baseline_window_start=window_start,
            baseline_window_end=window_end,
            target_window_start=report_target_start,
            target_window_end=report_target_end,
            diagnostics=diagnostics.to_dict(),
            axes=_axis_reports(profile, [], diagnostics, observations),
            summary=[
                "Baseline penceresinde güvenilir sinyal yok; sapma iddiası ÜRETİLMEDİ.",
                "Kök neden: BİLİNMİYOR. Bu rapor teşhis değil, gözlenen değişimin kaydıdır.",
            ],
            machine_note="insufficient_baseline",
        )

    findings = detect_deviations(profile, observations, report_target_start, report_target_end)
    analysis: ClusterAnalysis = analyze_clusters(
        findings,
        observations,
        profile,
        window_days=window_days,
        min_families=min_families,
        min_persistence_days=min_persistence_days,
    )
    drifts, strata_problems = extract_strata_drifts(strata_map)
    for problem in strata_problems:
        diagnostics.warn(problem)

    cluster = analysis.best
    if cluster is None:
        status = "NO_RUPTURE"
    elif cluster.is_confounded:
        status = "RUPTURE_CONFOUNDED_BY_MEDIUM_CHANGE"
    else:
        status = "RUPTURE_CONFIRMED"

    timeline: Optional[EvidenceTimeline] = None
    entry_count = 0
    if include_timeline:
        timeline = _merge_timeline(
            build_evidence_timeline(findings),
            _canonical_timeline(_strata_timeline_entries(drifts)),
        )
        entry_count = len(timeline.entries)

    medium_rate = cluster.medium_shift_rate if cluster else _medium_rate(observations, report_target_start, report_target_end)
    falsification = [
        "uç-nokta karşılaştırması YAPILMADI: tüm seri kaydırmalı pencereyle tarandı",
        f"medium_shift denetimi: kurgu/stüdyo oranı {('%.2f' % medium_rate) if medium_rate is not None else 'ölçülmedi'}",
        "bağımsızlık denetimi: aile içi sinyaller tek eksen; korelasyon eşiği 0.80",
        (
            f"geri sıçrama denetimi: {len(cluster.dropped)} kayıt düşürüldü"
            if cluster
            else "geri söndürme denetimi: küme adayı yok"
        ),
        f"shortcode zaman doğrulaması: {diagnostics.visual_frame_count} kare tarandı, "
        f"{len(diagnostics.shortcode_mismatch_refs)} uyuşmazlık",
    ]

    report = LifeRuptureReport(
        subject_id=subject_id,
        status=status,
        baseline_window_start=window_start,
        baseline_window_end=window_end,
        target_window_start=report_target_start,
        target_window_end=report_target_end,
        cluster_window_start=cluster.window_start if cluster else None,
        cluster_window_end=cluster.window_end if cluster else None,
        family_count=cluster.family_count if cluster else 0,
        families={family: list(signals) for family, signals in (cluster.families if cluster else {}).items()},
        persistence_days=cluster.persistence_days if cluster else 0.0,
        deviation_count=len(findings),
        medium_shift_rate=medium_rate,
        confounded_axes=list(cluster.confounded_axes) if cluster else [],
        falsification_checks=falsification,
        axes=_axis_reports(profile, findings, diagnostics, observations),
        summary=_summary(status, cluster, profile, findings, diagnostics, drifts),
        prior_pillar_evidence=[
            {
                "signal_id": drift.signal_id,
                "label": drift.label,
                "early_value": drift.early_value,
                "late_value": drift.late_value,
                "drift_ratio": drift.drift_ratio,
                "is_significant": drift.is_significant,
                "last_seen": _iso(drift.last_seen),
                "source": drift.source,
            }
            for drift in drifts
        ],
        evidence_timeline=timeline,
        evidence_entry_count=entry_count,
        diagnostics=diagnostics.to_dict(),
        machine_note=(
            f"cluster_families={cluster.family_count}" if cluster else "; ".join(analysis.reasons[:3]) or "no_cluster"
        ),
    )
    return report


def _medium_rate(
    observations: list[SignalObservation], start: datetime, end: datetime
) -> Optional[float]:
    values = [obs.value for obs in observations if obs.signal_id == MEDIUM_SIGNAL and start <= obs.timestamp <= end]
    if not values:
        return None
    return sum(values) / len(values)


def _merge_timeline(*sources: EvidenceTimeline) -> EvidenceTimeline:
    """Birden çok kaynağı tek, kronolojik zaman çizelgesinde birleştirir.

    Reddedilen/elenen sayaçları da toplanır: birleştirme, doğrulamanın
    üstünü ÖRTEMEZ.
    """
    entries: list[EvidenceTimelineEntry] = []
    rejected = 0
    excluded = 0
    for source in sources:
        entries.extend(source.entries)
        rejected += source.rejected_item_count
        excluded += source.excluded_strategy_count
    entries.sort(
        key=lambda entry: (
            entry.timeline_at or datetime.min.replace(tzinfo=timezone.utc),
            entry.evidence_id,
        )
    )
    return EvidenceTimeline(
        entries=entries,
        rejected_item_count=rejected,
        excluded_strategy_count=excluded,
    )
