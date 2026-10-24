"""Boylamsal hattın orkestratörü — veriden mühürlü rapora tek çağrı.

Akış (her adım bir öncekine bağlı, hiçbir modül orphan değil):

    target_profile + visual_evidence + frequency_map
        ↓ observation_adapter        (tarihli sinyal serisi + teşhis defteri)
    list[SignalObservation]
        ↓ baseline_builder           (KİŞİNİN KENDİ normali; sabit eşik yok)
    BaselineProfile
        ↓ medium_change              (üretim biçimi BASELINE'A göre değişti mi?)
    MediumChangeAssessment
        ↓ deviation_detector         (sapma + yapısal confound kaydı)
    list[DeviationFinding]
        ↓ persistence                (dilim bazlı kalıcılık: iki uç nokta yetmez)
        ↓ cluster_analyzer           (3+ BAĞIMSIZ eksen, kalıcı, rebound yok)
    RuptureCluster (veya aday/bilinmiyor)
        ↓ report                     (teşhis YOK, kök neden UNKNOWN)

Kişiye özel kod YOKTUR: burada hiçbir hesap adı, şehir, cinsiyet, nesne veya
tarih aralığı sabit değildir. Kişiye özel olan tek şey, kişinin kendi
verisinden çıkan baseline'dır. Aynı gözlemler farklı ``subject_id`` ile
işlendiğinde ölçüm AYNIDIR.

Üç hüküm birbirine karıştırılmaz: **değişim**, **kalıcılık** ve **neden**.
Birini ölçmek diğerini kanıtlamaz.

Tüketici: ``agent_core.task_executor`` (``status.life_rupture``).
Test: ``tests/lifecycle/test_lifecycle_pipeline.py``.
"""

from __future__ import annotations

import hashlib
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
    RuptureCluster,
    analyze_clusters,
)
from agent_core.lifecycle.default_specs import default_registry
from agent_core.lifecycle.deviation_detector import (
    DeviationFinding,
    build_evidence_timeline,
    detect_deviations,
    make_evidence_id,
)
from agent_core.lifecycle.families import FAMILY_ORDER, signal_family
from agent_core.lifecycle.medium_change import (
    DEFAULT_MEDIUM_THRESHOLD,
    MediumChangeAssessment,
    assess_medium_change,
)
from agent_core.lifecycle.observation_adapter import AdapterDiagnostics, ObservationAdapter
from agent_core.lifecycle.persistence import (
    DEFAULT_PERSISTENCE_CONFIG,
    PersistenceRecord,
    measure_persistence,
)
from agent_core.lifecycle.report import AxisReport, Finding, LifeRuptureReport, compute_report_id
from agent_core.lifecycle.strata_bridge import StrataDrift, extract_strata_drifts
from agent_core.services.evidence_timeline import build_evidence_timeline as _canonical_timeline

__all__ = ["FORBIDDEN_INTERPRETATION_ROOTS", "analyze_life_rupture", "resolve_cluster_state"]

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


def _finalize(report: LifeRuptureReport) -> LifeRuptureReport:
    """Kanıttan deterministik ``report_id`` üretir.

    Kimlik ``subject_id`` ve ``computed_at`` alanlarına BAĞLI DEĞİLDİR: aynı
    gözlemler farklı bir etiketle işlendiğinde kimlik değişmemeli, yoksa
    "kişiye özel kod yok" iddiası kimliğin kendisinde çürür.
    """
    payload = report.model_dump(
        mode="json", exclude={"computed_at", "report_id", "subject_id"}
    )
    return report.model_copy(update={"report_id": compute_report_id(payload)})


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


def _direction(center: float, observed: float, kind: str, delta: float) -> str:
    """Ölçülen yön — yorum değil, işaret."""
    if kind == "circular":
        return "changed" if abs(delta) > 0 else "stable"
    epsilon = 1e-9
    if observed <= epsilon and center > epsilon:
        return "disappeared"
    if center <= epsilon and observed > epsilon:
        return "appeared"
    if abs(delta) <= epsilon:
        return "stable"
    return "increased" if delta > 0 else "decreased"


def _excluded_evidence(diagnostics: AdapterDiagnostics) -> list[dict[str, Any]]:
    """Dışarıda bırakılan kanıt: sessizce yutulmaz, sayılır."""
    entries: list[dict[str, Any]] = []
    if diagnostics.filtered_non_platform_count:
        entries.append(
            {
                "reason": "non_platform_text",
                "count": diagnostics.filtered_non_platform_count,
                "note": "üçüncü şahıs arama özeti kişinin kendi dil baseline'ına alınmadı",
            }
        )
    if diagnostics.undated_post_count:
        entries.append(
            {
                "reason": "undated_post",
                "count": diagnostics.undated_post_count,
                "note": "tarih çözülemedi; gözlem üretilmedi (tarih uydurulmadı)",
            }
        )
    if diagnostics.rejected_future_timestamp_count:
        entries.append(
            {
                "reason": "future_timestamp",
                "count": diagnostics.rejected_future_timestamp_count,
                "note": "gelecek tarihli kayıt analiz kapsamına alınmadı",
            }
        )
    if diagnostics.rejected_frame_count:
        entries.append(
            {
                "reason": "rejected_visual_frame",
                "count": diagnostics.rejected_frame_count,
                "note": "ölçüm güveni yok ya da shortcode zamanı uyuşmadı",
            }
        )
    if diagnostics.shortcode_mismatch_refs:
        entries.append(
            {
                "reason": "shortcode_timestamp_mismatch",
                "count": len(diagnostics.shortcode_mismatch_refs),
                "note": "medya kimliğinin çözünürlüğü beyan edilen tarihle çelişti",
                "refs": list(diagnostics.shortcode_mismatch_refs),
            }
        )
    if diagnostics.undated_visual_summary_skipped:
        entries.append(
            {
                "reason": "undated_visual_summary",
                "count": 1,
                "note": "havuzlanmış görsel özet tarih taşımadığı için seriye çevrilmedi",
            }
        )
    return entries


def _unknowns(
    baseline: BaselineProfile,
    analysis: ClusterAnalysis,
    medium: MediumChangeAssessment,
    diagnostics: AdapterDiagnostics,
    cluster: Optional[RuptureCluster],
) -> list[str]:
    """Ne BİLİNMİYOR — yazılı cevap (sessiz boşluk yok)."""
    unknowns: list[str] = []
    if baseline.unspecified_signals:
        unknowns.append(
            "semantiği beyan edilmemiş sinyaller baseline dışında: "
            + ", ".join(baseline.unspecified_signals[:8])
        )
    unknowns.extend(analysis.unknowns)
    if medium.status == "unknown":
        unknowns.extend(f"üretim biçimi: {reason}" for reason in medium.reasons)
    if cluster is not None and not cluster.independence.is_confirmed:
        unknowns.extend(f"bağımsızlık: {reason}" for reason in cluster.independence.reasons)
    for warning in diagnostics.warnings:
        if "unverified" in warning or "unknown" in warning:
            unknowns.append(f"doğrulanamadı: {warning}")
    if not diagnostics.visual_frame_count:
        unknowns.append("görsel kare yok: habitat/bakış/ritüel eksenleri ölçülemedi (sıfır sayılmadı)")
    # Aynı metni tekrar etme.
    return list(dict.fromkeys(unknowns))


def resolve_cluster_state(
    cluster: Optional[RuptureCluster], analysis: ClusterAnalysis
) -> str:
    """Sözleşme §10: küme durumu ile "veri yok" birbirine karışmaz."""
    if cluster is not None:
        if cluster.is_confounded:
            return "CONFOUNDED"
        if cluster.is_verified:
            return "DETECTED"
        return "CANDIDATE"
    insufficient = any("insufficient_coverage" in reason for reason in analysis.reasons) or (
        any("insufficient_coverage" in unknown for unknown in analysis.unknowns)
    )
    return "INSUFFICIENT_EVIDENCE" if insufficient else "NO_SIGNIFICANT_CLUSTER"


def _status_for(cluster_state: str) -> str:
    return {
        "DETECTED": "RUPTURE_CONFIRMED",
        "CANDIDATE": "RUPTURE_CANDIDATE",
        "CONFOUNDED": "RUPTURE_CONFOUNDED_BY_MEDIUM_CHANGE",
        "INSUFFICIENT_EVIDENCE": "INSUFFICIENT_DATA",
        "NO_SIGNIFICANT_CLUSTER": "NO_RUPTURE",
    }[cluster_state]


def _signal_findings(
    findings: list[DeviationFinding],
    baseline: BaselineProfile,
    observations: list[SignalObservation],
    cluster: Optional[RuptureCluster],
    medium: MediumChangeAssessment,
    baseline_window: tuple[datetime, datetime],
    target_window: tuple[datetime, datetime],
    persistence_config,
) -> list[Finding]:
    """Her sapmış sinyal için denetlenebilir bulgu kaydı üretir."""
    grouped: dict[str, list[DeviationFinding]] = {}
    for finding in findings:
        grouped.setdefault(finding.signal_id, []).append(finding)

    records: list[Finding] = []
    for signal_id, items in sorted(grouped.items()):
        first = items[0]
        signal_baseline = baseline.get(signal_id)
        center = signal_baseline.center if signal_baseline else first.result.baseline_center
        kind = signal_baseline.kind if signal_baseline else "continuous"
        values = [item.observation.value for item in items]
        observed = sum(values) / len(values) if values else None
        delta = (observed - center) if observed is not None and center is not None else None

        record: PersistenceRecord = (
            cluster.persistence_records.get(signal_id)
            if cluster is not None and signal_id in cluster.persistence_records
            else measure_persistence(
                [obs for obs in observations if obs.signal_id == signal_id],
                [item.timestamp for item in items],
                config=persistence_config,
            )
        )

        confounded = any(item.confounded_by_medium_change for item in items)
        if confounded:
            measurement_status = "confounded"
        elif record.status == "insufficient_coverage":
            measurement_status = "partial"
        else:
            measurement_status = "measured"

        alternatives: list[dict[str, Any]] = []
        if medium.status == "changed" and first.family in ("habitat", "gaze", "ritual"):
            alternatives.append(
                {
                    "hypothesis": "medium_change",
                    "status": "supported",
                    "note": (
                        "üretim biçimi bu dönemde değişti; bu eksendeki ölçüm "
                        "yaşam koşulu değişimi olarak okunamaz"
                    ),
                    "source": "media.is_authored_or_staged",
                }
            )
        if medium.status == "unknown":
            alternatives.append(
                {
                    "hypothesis": "medium_change",
                    "status": "unknown",
                    "note": "üretim biçimi karşılaştırması için yeterli örneklem yok",
                    "source": "media.is_authored_or_staged",
                }
            )
        if record.status in ("intermittent", "transient"):
            alternatives.append(
                {
                    "hypothesis": "one_off_event",
                    "status": "weakened",
                    "note": "sapma sürekli değil; kalıcılık koşulu karşılanmadı",
                    "source": "persistence",
                }
            )

        limitations: list[str] = []
        if record.status == "insufficient_coverage":
            limitations.append("kapsama yetersiz: gözlenmeyen dilimler 'sapma yok' sayılmadı")
        if signal_baseline is None:
            limitations.append("baseline'da bu sinyal yok; yalnız gözlem kaydı")
        if confounded:
            limitations.append("confound: aynı pencerede üretim biçimi değişti")

        finding_id = "fi_" + hashlib.sha256(
            f"{signal_id}|{first.timestamp.isoformat()}|{record.status}".encode("utf-8")
        ).hexdigest()[:20]

        records.append(
            Finding(
                finding_id=finding_id,
                signal_id=signal_id,
                signal_family=first.family,
                baseline_period={
                    "start": _iso(baseline_window[0]),
                    "end": _iso(baseline_window[1]),
                    "measured_count": signal_baseline.n if signal_baseline else 0,
                    "eligible_count": signal_baseline.n if signal_baseline else 0,
                },
                comparison_period={
                    "start": _iso(target_window[0]),
                    "end": _iso(target_window[1]),
                    "measured_count": len(items),
                },
                baseline_value=center,
                observed_value=observed,
                delta=delta,
                direction=_direction(center, observed if observed is not None else center, kind, delta or 0.0),
                deviation_method=first.result.method,
                threshold_or_tolerance=signal_baseline.min_meaningful_delta if signal_baseline else None,
                persistence=record.to_dict(),
                independence_status=(
                    cluster.independence.status if cluster is not None else "not_applicable"
                ),
                measurement_status=measurement_status,
                deviation_count=len(items),
                source_refs=sorted({item.observation.source_ref for item in items}),
                contradictions=[],
                alternative_explanations=alternatives,
                limitations=limitations,
            )
        )
    return records


def _contradictions(findings: list[Finding]) -> list[dict[str, Any]]:
    """Aynı ailede karşıt yönlü sinyaller SİLİNMEZ; çelişki olarak yazılır."""
    positive = {"increased", "appeared"}
    negative = {"decreased", "disappeared"}
    by_family: dict[str, list[Finding]] = {}
    for finding in findings:
        by_family.setdefault(finding.signal_family, []).append(finding)

    contradictions: list[dict[str, Any]] = []
    for family, items in sorted(by_family.items()):
        ups = [item.signal_id for item in items if item.direction in positive]
        downs = [item.signal_id for item in items if item.direction in negative]
        if ups and downs:
            contradictions.append(
                {
                    "family": family,
                    "increased_or_appeared": ups,
                    "decreased_or_disappeared": downs,
                    "note": "karşıt yönlü kayıtlar korunur; biri diğerini iptal etmez",
                }
            )
    return contradictions


def _data_coverage(
    baseline: BaselineProfile,
    observations: list[SignalObservation],
    target_window: tuple[datetime, datetime],
) -> list[dict[str, Any]]:
    """Hangi sinyalde ne kadar gözlem var — sayı, tahmin değil."""
    start, end = target_window
    comparison_counts: dict[str, int] = {}
    for observation in observations:
        if start <= observation.timestamp <= end:
            comparison_counts[observation.signal_id] = comparison_counts.get(observation.signal_id, 0) + 1

    coverage: list[dict[str, Any]] = []
    for signal_id in sorted(set(baseline.baselines) | set(comparison_counts)):
        signal_baseline = baseline.get(signal_id)
        coverage.append(
            {
                "signal_id": signal_id,
                "family": signal_family(signal_id),
                "baseline_observations": baseline.observation_counts.get(signal_id, 0),
                "baseline_reliable": bool(signal_baseline and signal_baseline.is_reliable),
                "comparison_observations": comparison_counts.get(signal_id, 0),
            }
        )
    return coverage


def _summary(
    status: str,
    cluster: Optional[RuptureCluster],
    baseline: Optional[BaselineProfile],
    findings: list[DeviationFinding],
    diagnostics: AdapterDiagnostics,
    drifts: list[StrataDrift],
    medium: MediumChangeAssessment,
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
            f"{cluster.family_count} eksende ({families}) kalıcı sapma aynı pencerede: "
            f"{cluster.window_start.date()} → {cluster.window_end.date()}, "
            f"kalıcılık {cluster.persistence_days:.0f} gün."
        )
        if cluster.dropped:
            lines.append(
                f"Küme dışında bırakılan {len(cluster.dropped)} kayıt: kalıcılık/kapsama/rebound."
            )
        if not cluster.independence.is_confirmed:
            lines.append(
                "Bağımsızlık DOĞRULANMADI: bu nedenle sonuç aday (CANDIDATE) sayıldı, "
                "kesin küme değil."
            )
        else:
            lines.append(
                f"Bağımsızlık doğrulandı: {cluster.independence.status}, "
                f"{len(cluster.independence.verified_pairs)} çift ölçüldü."
            )

    if medium.status == "changed":
        lines.append(
            f"Üretim biçimi bu dönemde değişti ({medium.baseline_rate:.2f} → "
            f"{medium.comparison_rate:.2f}); mekân/bakış/ritüel sapmaları yaşam koşulu "
            "değişimi olarak OKUNAMAZ."
        )
    elif medium.status == "unknown":
        lines.append("Üretim biçimi karşılaştırması yapılamadı (örneklem yetersiz): sonuç BİLİNMİYOR.")
    else:
        lines.append(
            f"Üretim biçimi sabit ({medium.baseline_rate:.2f} → {medium.comparison_rate:.2f}): "
            "tek başına kurgu oranı confound sayılmadı."
        )

    if diagnostics.undated_visual_summary_skipped:
        lines.append("Tarihsiz görsel özet zaman serisine alınmadı (sahte tarih yazılmadı).")
    if diagnostics.shortcode_mismatch_refs:
        lines.append(
            f"{len(diagnostics.shortcode_mismatch_refs)} kayıt shortcode zamanıyla uyuşmadığı için reddedildi."
        )
    if drifts:
        significant = [drift for drift in drifts if drift.is_significant]
        lines.append(
            f"Pillar Strata {len(significant)} anlamlı erken/geç kaydı bildirdi "
            "(bağımsız eksen sayılmaz; aynı metin korpusundan türetilir)."
        )
    lines.append("Kök neden: BİLİNMİYOR. Bu rapor teşhis değil, gözlenen değişimin kaydıdır.")
    return lines


def _grade_counts(observations: list[SignalObservation]) -> dict[str, int]:
    """Gözlemlerin kanıt derecelerini sayar (ölçüm ≠ mutabakat).

    Derecesi yazılmamış gözlem ``measured`` sayılır: tier-1 numeric ölçümler ve
    metin/zaman sinyalleri doğrudan veriden gelir. ``corroborated`` yalnız
    mutabakatla güçlendirilmiş kare etiketlerinden doğan sinyallerdir.
    """
    counts: dict[str, int] = {}
    for observation in observations:
        grade = "measured"
        if isinstance(observation.context, Mapping):
            raw = observation.context.get("evidence_grade")
            if isinstance(raw, str) and raw:
                grade = raw
        counts[grade] = counts.get(grade, 0) + 1
    return counts


def _labels_from_frames(visual_evidence: Any) -> list[dict[str, Any]]:
    """Karelerdeki mutabakat etiketlerini raporda görünür hale getirir.

    Etiket raporda ``observation_grade="corroborated"`` olarak listelenir ki
    okuyucu hangi sinyalin araç ölçümü, hangisinin model mutabakatı olduğunu
    ayırt edebilsin. Karede yoksa liste boş kalır — uydurma satır yazılmaz.
    """
    if not isinstance(visual_evidence, Mapping):
        return []
    frames = visual_evidence.get("frames")
    if not isinstance(frames, (list, tuple)):
        return []
    rows: list[dict[str, Any]] = []
    for frame in frames:
        if not isinstance(frame, Mapping):
            continue
        frame_id = str(frame.get("frame_id") or "")
        observed_at = str(frame.get("observed_at") or "")
        if not frame_id:
            continue
        for kind, key in (("object", "corroborated_objects"), ("place", "corroborated_places")):
            for label in frame.get(key) or []:
                if not isinstance(label, str) or not label.strip():
                    continue
                rows.append(
                    {
                        "corroboration_id": "cl_" + hashlib.sha256(
                            f"report|{frame_id}|{kind}|{label}".encode("utf-8")
                        ).hexdigest()[:20],
                        "frame_id": frame_id,
                        "observed_at": observed_at,
                        "label": label,
                        "kind": kind,
                        "observation_grade": "corroborated",
                        "agreement_count": int(frame.get("corroboration_counts", {}).get(label, 2))
                        if isinstance(frame.get("corroboration_counts"), Mapping)
                        else 2,
                    }
                )
    rows.sort(key=lambda row: (row["observed_at"], row["frame_id"], row["kind"], row["label"]))
    return rows


def _inference_rows(semantic_inferences: Any) -> list[dict[str, Any]]:
    """İkinci kademe çıkarımlarını rapora girecek biçime indirger.

    Sözleşme burada zorlanır: satır ``epistemic_type="inference"`` ve
    ``counts_toward_cluster=False`` taşımıyorsa ALINMAZ (modele güvenilmez).
    """
    if semantic_inferences is None:
        return []
    rows: Any = semantic_inferences
    if not isinstance(rows, (list, tuple)):
        to_dict = getattr(semantic_inferences, "to_dict", None)
        if callable(to_dict):
            payload = to_dict()
            if isinstance(payload, Mapping):
                rows = payload.get("semantic_inferences") or []
    if not isinstance(rows, (list, tuple)):
        return []
    clean: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if row.get("epistemic_type") != "inference":
            continue
        if row.get("counts_toward_cluster") is not False:
            continue
        clean.append(dict(row))
    clean.sort(
        key=lambda row: (
            str(row.get("observed_at")),
            str(row.get("frame_id")),
            str(row.get("kind")),
            str(row.get("label_slug")),
        )
    )
    return clean


def _investigation_digest(investigation: Any) -> tuple[dict[str, Any], list[str]]:
    """Soruşturma sonucunu rapora sığacak kadar küçük, dürüst bir özete çevirir.

    Rapor tek başına okunabildiğinde "neyi soramadım" görünmelidir: kapanmayan
    sorular ``unknowns`` listesine girer. Ölçülmemiş bir şey "kapandı" diye
    raporlanmaz.
    """
    if not isinstance(investigation, Mapping):
        to_dict = getattr(investigation, "to_dict", None)
        if not callable(to_dict):
            return {}, []
        payload = to_dict()
        if not isinstance(payload, Mapping):
            return {}, []
        investigation = payload
    raw_still = investigation.get("still_unknown")
    if not isinstance(raw_still, (list, tuple)):
        # Bozuk yük "kapandı" sayılmaz ama uydurma satır da üretilmez.
        raw_still = []
    still = [str(item) for item in raw_still]
    questions = investigation.get("questions") or []
    resolved = investigation.get("resolved") or []
    if not isinstance(questions, (list, tuple)):
        questions = []
    if not isinstance(resolved, (list, tuple)):
        resolved = []
    diagnostics = investigation.get("diagnostics")
    summary = {
        "question_count": len(questions),
        "resolved_count": len(resolved),
        "still_unknown_count": len(still),
        "extra_frame_count": int(investigation.get("extra_frame_count") or 0),
        "stop_reason": str(diagnostics.get("stop_reason")) if isinstance(diagnostics, Mapping) else "",
    }
    return summary, [f"soruşturma açık: {item}" for item in still[:20]]


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
    medium_threshold: float = DEFAULT_MEDIUM_THRESHOLD,
    include_timeline: bool = True,
    investigation: Any = None,
    semantic_inferences: Any = None,
) -> LifeRuptureReport:
    """Tek çağrıda boylamsal analiz. Hata fırlatmaz; durumu raporlar.

    ``investigation``: soruşturma döngüsünün özeti (``InvestigationResult`` ya
    da ``to_dict()``i). Verilirse kapanmayan sorular raporun ``unknowns``
    listesine yazılır — rapor tek başına okunduğunda da görünür olur.
    ``semantic_inferences``: ikinci kademe model etiketleri. Rapora ÇIKARIM
    olarak girer, ``ritual.*`` sözlüğünü BESLEMEZ ve küme kanıtı sayılmaz.
    """
    report = _analyze_life_rupture_core(
        target_profile,
        visual_evidence=visual_evidence,
        frequency_map=frequency_map,
        strata_map=strata_map,
        subject_id=subject_id,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        target_start=target_start,
        target_end=target_end,
        now=now,
        window_days=window_days,
        min_families=min_families,
        min_persistence_days=min_persistence_days,
        medium_threshold=medium_threshold,
        include_timeline=include_timeline,
    )
    summary, unanswered = _investigation_digest(investigation)
    inference_rows = _inference_rows(semantic_inferences)
    grades = dict(report.diagnostics.get("evidence_grade_counts") or {})
    label_rows = _labels_from_frames(visual_evidence)
    corroborated_signals = int(grades.get("corroborated", 0))
    if not summary and not inference_rows and not label_rows and not corroborated_signals:
        return report

    diagnostics = dict(report.diagnostics)
    unknowns = list(report.unknowns)
    if summary:
        diagnostics["investigation"] = summary
        unknowns = list(dict.fromkeys(unknowns + unanswered))
    if inference_rows:
        diagnostics["semantic_inference_count"] = len(inference_rows)
        diagnostics["semantic_inferences_count_toward_cluster"] = False
        # Sessiz boşluk yok: etiketlerin ölçüm OLMADIĞI raporda yazılı.
        unknowns = list(
            dict.fromkeys(
                unknowns
                + [
                    "kare etiketleri model çıkarımıdır (ölçüm değil): "
                    f"{len(inference_rows)} etiket küme kanıtı sayılmadı"
                ]
            )
        )
    if corroborated_signals or label_rows:
        # Sessiz boşluk yok: hangi sinyalin araç ölçümü, hangisinin model
        # mutabakatı olduğu raporda YAZILI.
        unknowns = list(
            dict.fromkeys(
                unknowns
                + [
                    "kanıt dereceleri: "
                    + ", ".join(f"{grade}={count}" for grade, count in sorted(grades.items()))
                    + f"; {corroborated_signals} sinyal iki bağımsız modelin mutabakatına dayanır "
                    "(araç ölçümü değil)"
                ]
            )
        )
    return _finalize(
        report.model_copy(
            update={
                "diagnostics": diagnostics,
                "unknowns": unknowns,
                "semantic_inferences": inference_rows,
                "semantic_inference_count": len(inference_rows),
                "evidence_grade_counts": grades,
                "corroborated_signal_count": corroborated_signals,
                "corroborated_labels": label_rows,
            }
        )
    )


def _analyze_life_rupture_core(
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
    medium_threshold: float = DEFAULT_MEDIUM_THRESHOLD,
    include_timeline: bool = True,
) -> LifeRuptureReport:
    """Boylamsal analizin çekirdeği (soruşturma özeti eklenmeden)."""
    diagnostics = AdapterDiagnostics()
    observations = ObservationAdapter().transform(
        target_profile,
        visual_evidence=visual_evidence,
        frequency_map=frequency_map,
        diagnostics=diagnostics,
        now=now,
    )
    # Kanıt dereceleri burada sayılır: rapor ``measured`` ile ``corroborated``ı
    # ayrı gösterir, ikisini aynı kefeye koymaz.
    diagnostics.evidence_grade_counts = _grade_counts(observations)

    config = {
        "cluster_window_days": window_days,
        "min_families": min_families,
        "min_persistence_days": min_persistence_days,
        "medium_threshold": medium_threshold,
        "persistence": DEFAULT_PERSISTENCE_CONFIG.to_dict(),
    }

    if not observations:
        return _finalize(LifeRuptureReport(
            subject_id=subject_id,
            status="INSUFFICIENT_DATA",
            cluster_state="INSUFFICIENT_EVIDENCE",
            diagnostics=diagnostics.to_dict(),
            excluded_evidence=_excluded_evidence(diagnostics),
            unknowns=_unknowns_early(diagnostics),
            decision_summary="Ölçülebilir değişim değerlendirmesi yapılamadı: tarihli gözlem yok.",
            summary=[
                "Tarihli gözlem üretilemedi; sapma iddiası kurulmadı.",
                "Kök neden: BİLİNMİYOR. Bu rapor teşhis değil, gözlenen değişimin kaydıdır.",
            ],
            config=config,
            machine_note="no_dated_observation",
        ))

    first_seen = observations[0].timestamp
    last_seen = observations[-1].timestamp
    window_start = ensure_utc(baseline_start) if baseline_start else first_seen
    window_end = ensure_utc(baseline_end) if baseline_end else window_start + timedelta(days=DEFAULT_BASELINE_DAYS)
    report_target_start = ensure_utc(target_start) if target_start else window_end + timedelta(seconds=1)
    report_target_end = ensure_utc(target_end) if target_end else last_seen

    profile = build_baseline(subject_id, observations, window_start, window_end, registry=default_registry())
    if report_target_start > report_target_end:
        return _finalize(LifeRuptureReport(
            subject_id=subject_id,
            status="INSUFFICIENT_DATA",
            cluster_state="INSUFFICIENT_EVIDENCE",
            baseline_window_start=window_start,
            baseline_window_end=window_end,
            target_window_start=report_target_start,
            target_window_end=report_target_end,
            diagnostics=diagnostics.to_dict(),
            axes=_axis_reports(profile, [], diagnostics, observations),
            data_coverage=_data_coverage(profile, observations, (report_target_start, report_target_end)),
            excluded_evidence=_excluded_evidence(diagnostics),
            unknowns=["hedef pencerede gözlem yok: karşılaştırma yapılamadı"],
            decision_summary="Karşılaştırma dönemi boş; hüküm verilmedi.",
            summary=[
                "Hedef pencerede gözlem yok: baseline penceresi tüm seriyi kapsıyor.",
                "Kök neden: BİLİNMİYOR. Bu rapor teşhis değil, gözlenen değişimin kaydıdır.",
            ],
            config=config,
            machine_note="target_window_empty",
        ))

    if not profile.reliable_signals():
        return _finalize(LifeRuptureReport(
            subject_id=subject_id,
            status="INSUFFICIENT_BASELINE",
            cluster_state="INSUFFICIENT_EVIDENCE",
            baseline_window_start=window_start,
            baseline_window_end=window_end,
            target_window_start=report_target_start,
            target_window_end=report_target_end,
            diagnostics=diagnostics.to_dict(),
            axes=_axis_reports(profile, [], diagnostics, observations),
            data_coverage=_data_coverage(profile, observations, (report_target_start, report_target_end)),
            excluded_evidence=_excluded_evidence(diagnostics),
            unknowns=_unknowns(profile, ClusterAnalysis(), _empty_medium(), diagnostics, None),
            decision_summary="Baseline güvenilir değil; sapma hükmü verilmedi.",
            summary=[
                "Baseline penceresinde güvenilir sinyal yok; sapma iddiası ÜRETİLMEDİ.",
                "Kök neden: BİLİNMİYOR. Bu rapor teşhis değil, gözlenen değişimin kaydıdır.",
            ],
            config=config,
            machine_note="insufficient_baseline",
        ))

    medium = assess_medium_change(
        observations,
        window_start,
        window_end,
        report_target_start,
        report_target_end,
        threshold=medium_threshold,
    )
    findings = detect_deviations(
        profile,
        observations,
        report_target_start,
        report_target_end,
        medium_change=medium,
    )
    analysis: ClusterAnalysis = analyze_clusters(
        findings,
        observations,
        profile,
        window_days=window_days,
        min_families=min_families,
        min_persistence_days=min_persistence_days,
        medium_change=medium,
    )
    drifts, strata_problems = extract_strata_drifts(strata_map)
    for problem in strata_problems:
        diagnostics.warn(problem)

    cluster = analysis.best
    cluster_state = resolve_cluster_state(cluster, analysis)
    status = _status_for(cluster_state)

    timeline: Optional[EvidenceTimeline] = None
    entry_count = 0
    if include_timeline:
        timeline = _merge_timeline(
            build_evidence_timeline(findings),
            _canonical_timeline(_strata_timeline_entries(drifts)),
        )
        entry_count = len(timeline.entries)

    signal_findings = _signal_findings(
        findings,
        profile,
        observations,
        cluster,
        medium,
        (window_start, window_end),
        (report_target_start, report_target_end),
        DEFAULT_PERSISTENCE_CONFIG,
    )
    contradictions = _contradictions(signal_findings)
    recoveries = [
        {
            "signal_id": dropped.split(":")[0],
            "reason": "rebound",
            "note": "sapma sonraki gözlemlerde baseline'a döndü; 'kalıcı' iddiası düşürüldü",
        }
        for dropped in (cluster.dropped if cluster else ())
        if dropped.endswith(":rebound")
    ]

    medium_rate = medium.comparison_rate if medium.comparison_rate is not None else None
    falsification = [
        "uç-nokta karşılaştırması YAPILMADI: tüm seri kaydırmalı pencereyle tarandı",
        f"kalıcılık dilim bazlı ölçüldü (dilim {DEFAULT_PERSISTENCE_CONFIG.bucket_days} gün, "
        f"asgari ardışık {DEFAULT_PERSISTENCE_CONFIG.min_consecutive_windows}, "
        f"asgari kapsama {DEFAULT_PERSISTENCE_CONFIG.min_coverage_rate:.2f})",
        f"medium_change: {medium.status} — baseline {medium.baseline_rate} → "
        f"karşılaştırma {medium.comparison_rate} (eşik {medium.threshold:.2f})",
        f"bağımsızlık denetimi: {cluster.independence.status if cluster else 'küme yok'}; "
        "korelasyon ölçülemezse bağımsız SAYILMAZ",
        (
            f"geri sıçrama denetimi: {len(recoveries)} kayıt düşürüldü"
            if cluster
            else "geri söndürme denetimi: küme adayı yok"
        ),
        f"shortcode zaman doğrulaması: {diagnostics.visual_frame_count} kare tarandı, "
        f"{len(diagnostics.shortcode_mismatch_refs)} uyuşmazlık",
    ]

    unknowns = _unknowns(profile, analysis, medium, diagnostics, cluster)
    decision_summary = _decision_summary(status, cluster_state, cluster, medium)
    source_refs = sorted({ref for finding in signal_findings for ref in finding.source_refs})

    report = LifeRuptureReport(
        subject_id=subject_id,
        status=status,
        cluster_state=cluster_state,
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
        candidate_signal_count=cluster.candidate_signal_count if cluster else 0,
        confirmed_independent_signal_count=(
            cluster.confirmed_independent_signal_count if cluster else 0
        ),
        independence_assessment=(
            cluster.independence.to_dict()
            if cluster
            else {"status": "unknown", "method": "pearson_baseline_joint", "reasons": list(analysis.reasons[:3])}
        ),
        medium_change_assessment=medium.to_dict(),
        medium_shift_rate=medium_rate,
        confounded_axes=list(cluster.confounded_axes) if cluster else [],
        falsification_checks=falsification,
        decision_summary=decision_summary,
        axes=_axis_reports(profile, findings, diagnostics, observations),
        findings=signal_findings,
        data_coverage=_data_coverage(profile, observations, (report_target_start, report_target_end)),
        contradictions=contradictions,
        recoveries=recoveries,
        unknowns=unknowns,
        excluded_evidence=_excluded_evidence(diagnostics),
        source_refs=source_refs,
        summary=_summary(status, cluster, profile, findings, diagnostics, drifts, medium),
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
        config=config,
        machine_note=(
            f"cluster_families={cluster.family_count};independence={cluster.independence.status}"
            if cluster
            else ("; ".join(analysis.reasons[:3]) or "no_cluster")
        ),
    )
    return _finalize(report)


def _empty_medium() -> MediumChangeAssessment:
    return MediumChangeAssessment(
        status="unknown",
        baseline_rate=None,
        comparison_rate=None,
        delta=None,
        threshold=DEFAULT_MEDIUM_THRESHOLD,
        baseline_sample_size=0,
        comparison_sample_size=0,
        reasons=("baseline yok; üretim biçimi karşılaştırılamadı",),
    )


def _unknowns_early(diagnostics: AdapterDiagnostics) -> list[str]:
    unknowns = ["tarihli gözlem yok: hiçbir sinyal ölçülmedi"]
    for warning in diagnostics.warnings:
        unknowns.append(f"veri kalitesi: {warning}")
    return unknowns


def _decision_summary(
    status: str,
    cluster_state: str,
    cluster: Optional[RuptureCluster],
    medium: MediumChangeAssessment,
) -> str:
    """Tek paragraf: ne ölçüldü, ne iddia edilmedi."""
    if cluster_state == "DETECTED":
        return (
            f"{cluster.family_count if cluster else 0} bağımsız eksende kalıcı sapma aynı pencerede "
            "gözlendi; bağımsızlık doğrulandı. Bu bir teşhis değil, ölçüm kaydıdır."
        )
    if cluster_state == "CONFOUNDED":
        return (
            "Kalıcı sapma var, ancak aynı dönemde üretim biçimi de değişti; "
            f"{', '.join(cluster.confounded_axes) if cluster else ''} eksenleri yaşam koşulu "
            "değişimi olarak okunamaz."
        )
    if cluster_state == "CANDIDATE":
        reason = cluster.independence.status if cluster else "unknown"
        return (
            "Çok eksenli kalıcı sapma adayı var; bağımsızlık durumu "
            f"'{reason}' olduğu için kesin küme iddia edilmedi."
        )
    if cluster_state == "INSUFFICIENT_EVIDENCE":
        return "Kanıt yetersiz: kapsama/bağımsızlık koşulları tamamlanmadı, hüküm verilmedi."
    if status == "INSUFFICIENT_DATA":
        return "Ölçülecek veri yok; hüküm verilmedi."
    return "Yeterli veri incelendi; kuralları karşılayan kalıcı çok eksenli küme bulunmadı."


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
