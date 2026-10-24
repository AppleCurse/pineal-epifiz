"""Deviation Detector - Baseline-Normalized Behavior Drift Detection.

Kişinin kendi taban çizgisine (BaselineProfile) göre istatistiksel sapmaları tespit eder.
EvidenceTimelineEntry'nin zorunlu tüm alanlarını (epistemic_note dahil) eksiksiz sağlar.
Ölçülemeyen veriyi (not_measurable) asla sıfır (yokluk) saymaz.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import List
from agent_core.domain.evidence_models import EvidenceTimeline, EvidenceTimelineEntry
from agent_core.lifecycle.baseline_builder import BaselineProfile, SignalObservation


def make_evidence_id(signal_id: str, ts: datetime, val: float, ref: str) -> str:
    raw = f"{signal_id}|{ts.isoformat()}|{val:.4f}|{ref}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"ev_{digest}"


class DeviationDetector:
    def __init__(self, baseline: BaselineProfile, z_threshold: float = 2.0) -> None:
        self.baseline = baseline
        self.z_threshold = z_threshold

    def detect(
        self,
        observations: List[SignalObservation],
        target_start: datetime,
        target_end: datetime,
    ) -> EvidenceTimeline:
        entries: List[EvidenceTimelineEntry] = []

        for obs in observations:
            if not (target_start <= obs.timestamp <= target_end):
                continue

            # Ölçülemeyen veri kontrolü: asla sıfır veya sapma kabul edilmez
            if obs.measurement_status == "not_measurable":
                ev_id = make_evidence_id(obs.signal_id, obs.timestamp, -999.0, obs.source_ref)
                entries.append(EvidenceTimelineEntry(
                    evidence_id=ev_id,
                    timeline_at=obs.timestamp,
                    temporal_basis="observed_at",
                    epistemic_type="observation",
                    epistemic_note="Kaynak analiz edilemedi/indirilemedi; ölçüm yapılamadı (not_measurable). Sıfır kabul edilmez.",
                    source_engine="deviation_detector",
                    content=f"Sinyal '{obs.signal_id}' için kaynak ölçülemedi (not_measurable).",
                    source_metrics={
                        "signal_id": obs.signal_id,
                        "measurement_status": "not_measurable",
                        "source_ref": obs.source_ref,
                    },
                ))
                continue

            if obs.measurement_status == "invalid":
                continue

            if obs.signal_id not in self.baseline.baselines:
                continue

            base = self.baseline.baselines[obs.signal_id]
            if base.is_deviation(obs.value, self.z_threshold):
                dist = base.distance(obs.value)
                method = "constant_break" if base.is_constant else "z_score"
                ev_id = make_evidence_id(obs.signal_id, obs.timestamp, obs.value, obs.source_ref)

                # Yokluk mu (analiz edilmiş kaynakta bulunmama) yoksa pozitif sapma mı?
                is_absence = (base.mean > 0 and obs.value == 0 and ("object" in obs.signal_id or "is_" in obs.signal_id))
                epistemic_type = "absence" if is_absence else "observation"

                if is_absence:
                    note = f"Doğrulanan kaynakta '{obs.signal_id}' bulunamadı (yokluk tespiti). Taban: {base.mean:.2f}"
                else:
                    note = f"Ölçüm yöntemi: {method}, gözlem: {obs.value:.2f}, taban: {base.mean:.2f}, mesafe: {dist:.2f}, eşik: {self.z_threshold}"

                entries.append(EvidenceTimelineEntry(
                    evidence_id=ev_id,
                    timeline_at=obs.timestamp,
                    temporal_basis="observed_at",
                    epistemic_type=epistemic_type,
                    epistemic_note=note,
                    source_engine="deviation_detector",
                    content=(
                        f"Sinyal '{obs.signal_id}' taban çizgiden saptı: "
                        f"Gözlem={obs.value:.2f}, Taban={base.mean:.2f}"
                    ),
                    source_metrics={
                        "signal_id": obs.signal_id,
                        "value": obs.value,
                        "baseline_center": base.mean,
                        "distance": dist,
                        "method": method,
                        "source_ref": obs.source_ref,
                        "measurement_status": "measured",
                    },
                ))

        # ponytail: Kronolojik sıralama; liste içi kararlılık için timeline_at ve evidence_id ile sıralanır.
        return EvidenceTimeline(entries=sorted(entries, key=lambda e: (e.timeline_at or datetime.min, e.evidence_id)))
