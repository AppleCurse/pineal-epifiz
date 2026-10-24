"""Rupture Reporter - Structured Findings and Evidence Synthesis.

Her bulgunun kaynağını, yönünü, başlangıç ve karşılaştırma değerlerini açıkça belgeler.
Kişi, hesap veya hikaye adı içermez.
Belirsizlikleri, kurtarma/geri dönüşleri ve bağımsızlık durumunu eksiksiz listeler.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import List, Literal, Optional, Tuple
from agent_core.domain.evidence_models import EvidenceTimeline, EvidenceTimelineEntry
from agent_core.lifecycle.cluster_analyzer import SignalCluster

Verdict = Literal[
    "RUPTURE_CONFIRMED",
    "RUPTURE_CONFOUNDED_BY_MEDIUM_CHANGE",
    "NO_SIGNIFICANT_CLUSTER",
    "INDEPENDENCE_UNVERIFIED",
    "INSUFFICIENT_EVIDENCE",
]


@dataclass(frozen=True)
class RuptureFinding:
    signal_id: str
    baseline_value: float
    observed_value: float
    delta: float
    direction: Literal["increase", "decrease", "divergence"]
    observation_count: int
    source_refs: Tuple[str, ...]
    measurement_status: str
    contradictions: Tuple[str, ...] = ()
    alternative_explanations: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RuptureReport:
    verdict: Verdict
    window: Optional[Tuple[datetime, datetime]]
    findings: Tuple[RuptureFinding, ...]
    signal_count: int
    persistence_days: int
    continuity_ratio: float
    independence_verified: bool
    confounded_axes: Tuple[str, ...]
    timeline: EvidenceTimeline
    uncertainties: Tuple[str, ...]
    contradictions: Tuple[str, ...]
    recoveries: Tuple[str, ...]
    reason: str


def _make_cluster_evidence_id(cluster: SignalCluster, idx: int) -> str:
    key = f"{cluster.start.isoformat()}|{cluster.end.isoformat()}|{cluster.signals}|{idx}"
    return f"ev_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:20]}"


def report(
    clusters: List[SignalCluster],
    timeline: EvidenceTimeline,
    has_sufficient_observations: bool = True,
    correlation_verified: bool = True,
    recoveries: Tuple[str, ...] = (),
    contradictions: Tuple[str, ...] = (),
) -> RuptureReport:
    if not clusters:
        v: Verdict = (
            "NO_SIGNIFICANT_CLUSTER"
            if (has_sufficient_observations and correlation_verified)
            else "INSUFFICIENT_EVIDENCE"
        )
        return RuptureReport(
            verdict=v,
            window=None,
            findings=(),
            signal_count=0,
            persistence_days=0,
            continuity_ratio=0.0,
            independence_verified=correlation_verified,
            confounded_axes=(),
            timeline=timeline,
            uncertainties=(
                "Yeterli veri incelendi fakat kuralları karşılayan sapma kümesi tespit edilemedi."
                if v == "NO_SIGNIFICANT_CLUSTER" else
                "Yeterli bağımsızlık doğrulaması veya sürekli sapma verisi sağlanamadı (fail-closed)."
            ),
            contradictions=contradictions,
            recoveries=recoveries,
            reason="3+ bağımsız sinyal aynı pencerede ve 60+ gün süreklilikle gözlemlenmedi.",
        )

    primary = max(clusters, key=lambda c: (c.signal_count, c.persistence_days))

    # Bağımsızlık veya medium change kontrolü
    if not primary.independence_verified:
        verdict: Verdict = "INDEPENDENCE_UNVERIFIED"
    elif primary.is_confounded:
        verdict = "RUPTURE_CONFOUNDED_BY_MEDIUM_CHANGE"
    elif primary.medium_change_status == "unknown" and any(s.startswith(("visual.", "habitat.")) for s in primary.signals):
        verdict = "INSUFFICIENT_EVIDENCE"
    else:
        verdict = "RUPTURE_CONFIRMED"

    # Her sapan sinyal için yapılandırılmış RuptureFinding oluştur
    findings_list: List[RuptureFinding] = []
    uncertainties_list: List[str] = []

    for sig in primary.signals:
        sig_entries = [
            e for e in timeline.entries
            if e.source_metrics and e.source_metrics.get("signal_id") == sig
            and primary.start <= (e.timeline_at or datetime.min) <= primary.end
            and e.source_metrics.get("measurement_status") == "measured"
        ]
        if sig_entries:
            mean_obs = sum(e.source_metrics["value"] for e in sig_entries) / len(sig_entries)
            base_val = sig_entries[0].source_metrics.get("baseline_center", 0.0)
            delta = mean_obs - base_val
            direction: Literal["increase", "decrease", "divergence"] = (
                "increase" if delta > 0.05
                else "decrease" if delta < -0.05
                else "divergence"
            )
            refs = tuple(sorted({
                str(e.source_metrics.get("source_ref", ""))
                for e in sig_entries if e.source_metrics.get("source_ref")
            }))
            findings_list.append(RuptureFinding(
                signal_id=sig,
                baseline_value=base_val,
                observed_value=mean_obs,
                delta=delta,
                direction=direction,
                observation_count=len(sig_entries),
                source_refs=refs,
                measurement_status="measured",
            ))

    if not primary.independence_verified:
        uncertainties_list.append("Sinyaller arası korelasyon matrisi verisizlik nedeniyle doğrulanamadı; bağımsızlık varsayılmadı.")
    if primary.is_confounded:
        uncertainties_list.append("Hedef dönemde kurgusal/staged medya oranı taban çizgiye kıyasla arttı; görsel eksenler üretim tarzı değişimiyle karışık.")
    elif primary.medium_change_status == "unknown":
        uncertainties_list.append("Taban çizgide kurgusal medya oranı ölçülemedi; üretim tarzı değişimi bilinmiyor (fail-closed).")

    extra_entry = EvidenceTimelineEntry(
        evidence_id=_make_cluster_evidence_id(primary, 0),
        timeline_at=primary.start,
        temporal_basis="window_start",
        epistemic_type="inference",
        epistemic_note="Çok-boyutlu kümeleme ve süreklilik sentezi",
        source_engine="rupture_reporter",
        content=(
            f"{primary.signal_count} sinyal aynı pencerede "
            f"({primary.start.date()} → {primary.end.date()}) "
            f"{primary.persistence_days} gün süreklilikle (devamlılık oranı: {primary.continuity_ratio:.2f}) saptı."
        ),
        source_metrics={
            "signal_count": primary.signal_count,
            "persistence_days": primary.persistence_days,
            "continuity_ratio": primary.continuity_ratio,
            "independence_verified": primary.independence_verified,
            "signals": list(primary.signals),
            "confounded": primary.is_confounded,
            "confounded_axes": list(primary.confounded_axes),
        },
    )

    reason = (
        f"Zaman serisinde {primary.signal_count} sinyalin {primary.persistence_days} gün süresince "
        f"eşzamanlı sapması ölçüldü. Dijital iz dışındaki yaşam koşulu veya nedenler doğrulanmadı."
    )

    return RuptureReport(
        verdict=verdict,
        window=(primary.start, primary.end),
        findings=tuple(findings_list),
        signal_count=primary.signal_count,
        persistence_days=primary.persistence_days,
        continuity_ratio=primary.continuity_ratio,
        independence_verified=primary.independence_verified,
        confounded_axes=primary.confounded_axes,
        timeline=EvidenceTimeline(entries=list(timeline.entries) + [extra_entry]),
        uncertainties=tuple(uncertainties_list),
        contradictions=contradictions,
        recoveries=recoveries,
        reason=reason,
    )
