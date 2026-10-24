"""Rupture Engine - End-to-End Deterministic Life Rupture Pipeline.

Tüm deterministik yaşam kırılması bileşenlerini orkestre eder:
1. Gözlemler (SignalObservation)
2. Taban Çizgisi (BaselineProfile)
3. Sapma Tespiti (DeviationDetector)
4. Kümeleme ve Kalıcılık Analizi (ClusterAnalyzer)
5. Kanıt Sözleşmeli Yapılandırılmış Rapor (RuptureReport)
"""

from __future__ import annotations

from datetime import datetime
from typing import List
from agent_core.lifecycle.baseline_builder import BaselineProfile, SignalObservation
from agent_core.lifecycle.cluster_analyzer import ClusterAnalyzer, DeviationEvent
from agent_core.lifecycle.deviation_detector import DeviationDetector
from agent_core.lifecycle.rupture_reporter import RuptureReport, report


class RuptureEngine:
    def __init__(self, baseline: BaselineProfile) -> None:
        self.baseline = baseline
        self.detector = DeviationDetector(baseline)
        self.clusterer = ClusterAnalyzer(baseline)

    def run(
        self,
        observations: List[SignalObservation],
        target_start: datetime,
        target_end: datetime,
    ) -> RuptureReport:
        target_obs = [
            o for o in observations
            if target_start <= o.timestamp <= target_end
            and o.measurement_status != "invalid"
        ]

        timeline = self.detector.detect(observations, target_start, target_end)

        events = [
            DeviationEvent(
                signal_id=e.source_metrics["signal_id"],
                timestamp=e.timeline_at,
                value=e.source_metrics["value"],
                baseline_center=e.source_metrics["baseline_center"],
                distance=e.source_metrics["distance"],
                method=e.source_metrics["method"],
                source_ref=e.source_metrics["source_ref"],
            )
            for e in timeline.entries
            if e.timeline_at is not None
            and e.source_metrics is not None
            and e.source_metrics.get("measurement_status") == "measured"
            and "value" in e.source_metrics
        ]

        clusters = self.clusterer.analyze(
            events, target_end, all_target_observations=target_obs
        )

        recoveries: List[str] = []
        contradictions: List[str] = []

        if clusters:
            primary = clusters[0]
            for sig in primary.signals:
                base = self.baseline.baselines.get(sig)
                if not base:
                    continue
                sig_post_obs = [
                    o for o in target_obs
                    if o.signal_id == sig and o.timestamp > primary.end
                    and o.measurement_status == "measured"
                ]
                if sig_post_obs and all(not base.is_deviation(o.value) for o in sig_post_obs):
                    recoveries.append(f"Sinyal '{sig}' {primary.end.date()} sonrası taban çizgi toleransına geri döndü.")

        has_sufficient = len(target_obs) >= 10

        return report(
            clusters=clusters,
            timeline=timeline,
            has_sufficient_observations=has_sufficient,
            correlation_verified=self.baseline.correlation_verified,
            recoveries=tuple(recoveries),
            contradictions=tuple(contradictions),
        )
