"""Strata köprüsü — pillar'ın ÖN-HESAPLANMIŞ erken/geç karşılaştırmasını okur.

``TaskSnapshot.strata_map`` gerçekte ``StrataReport.model_dump(mode="json")``
çıktısıdır ve iki kanal taşır (bkz. ``agent_core/domain/pillar_wave2_models.py``):

    * ``fossils``: ``FossilRecord`` — bir tema öldü mü? (``early_presence`` →
      ``late_presence``, ``last_seen_iso``, ``extinction_confidence``)
    * ``drifts`` : ``IdentityDrift`` — bir metrik kaydı mı? (— alan adı
      ``drifts``'tir; ``identity_drifts`` DEĞİL. Tahmin edilen ad sessizce boş
      liste üretirdi.)

Bu iki kanal yeniden HESAPLANMAZ (motor zaten hesapladı) — yalnız okunur ve
kaynak etiketiyle rapora taşınır. Tarihi olmayan drift kaydı sahte tarih
almadan ``undated`` olarak işaretlenir.

Tüketici: ``agent_core.lifecycle.pipeline``, ``cluster_analyzer``.
Test: ``tests/lifecycle/test_lifecycle_strata_bridge.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional

from agent_core.engines.frequency_engine import parse_timestamp

__all__ = ["StrataDrift", "extract_strata_drifts"]


def _slug(raw: Any) -> str:
    if not isinstance(raw, str):
        return ""
    lowered = raw.strip().lower()
    if not lowered:
        return ""
    return re.sub(r"[^\w]", "", re.sub(r"\s+", "_", lowered), flags=re.UNICODE)


@dataclass(frozen=True)
class StrataDrift:
    """Pillar'ın beyan ettiği erken/geç farkı (yeniden hesaplanmaz)."""

    signal_id: str
    label: str
    early_value: float
    late_value: float
    drift_ratio: float
    is_significant: bool
    last_seen: Optional[datetime] = None
    source: str = "strata_map"
    evidence_refs: tuple[str, ...] = ()

    @property
    def is_fossil(self) -> bool:
        return self.source == "strata_map.fossil"


def extract_strata_drifts(strata_map: Any) -> tuple[list[StrataDrift], list[str]]:
    """``strata_map`` → (kayıtlar, problem notları). Bozuk kayıt yutulmaz."""
    if not isinstance(strata_map, Mapping):
        return [], []

    drift_records: list[StrataDrift] = []
    problems: list[str] = []

    fossils = strata_map.get("fossils")
    if isinstance(fossils, (list, tuple)):
        for index, item in enumerate(fossils):
            if not isinstance(item, Mapping):
                problems.append(f"invalid_fossil[{index}]")
                continue
            topic = _slug(item.get("topic"))
            if not topic:
                problems.append(f"fossil_without_topic[{index}]")
                continue
            try:
                early = float(item.get("early_presence", 0.0))
                late = float(item.get("late_presence", 0.0))
                confidence = float(item.get("extinction_confidence", 0.0))
            except (TypeError, ValueError):
                problems.append(f"non_numeric_fossil[{index}]")
                continue
            refs = item.get("evidence_refs")
            drift_records.append(
                StrataDrift(
                    signal_id=f"strata.fossil.{topic}",
                    label=str(item.get("topic")),
                    early_value=early,
                    late_value=late,
                    drift_ratio=(early - late) / early if early > 0 else 0.0,
                    # Yok oluş iddiası pillar'ın kendi eşiğiyle sınırlıdır.
                    is_significant=confidence >= 0.7 and (early - late) >= 0.5,
                    last_seen=parse_timestamp(item.get("last_seen_iso")),
                    source="strata_map.fossil",
                    evidence_refs=tuple(str(ref) for ref in refs) if isinstance(refs, (list, tuple)) else (),
                )
            )

    drifts = strata_map.get("drifts")
    if isinstance(drifts, (list, tuple)):
        for index, item in enumerate(drifts):
            if not isinstance(item, Mapping):
                problems.append(f"invalid_drift[{index}]")
                continue
            metric = _slug(item.get("metric"))
            if not metric:
                problems.append(f"drift_without_metric[{index}]")
                continue
            try:
                early = float(item.get("early_value", 0.0))
                late = float(item.get("late_value", 0.0))
                ratio = float(item.get("drift_ratio", 0.0))
            except (TypeError, ValueError):
                problems.append(f"non_numeric_drift[{index}]")
                continue
            drift_records.append(
                StrataDrift(
                    signal_id=f"strata.drift.{metric}",
                    label=str(item.get("metric")),
                    early_value=early,
                    late_value=late,
                    drift_ratio=ratio,
                    is_significant=bool(item.get("is_significant", False)),
                    last_seen=None,  # drift kaydı tarih taşımaz → undated
                    source="strata_map.drift",
                    evidence_refs=tuple(str(r) for r in item.get("evidence_refs", []) or ()),
                )
            )

    return drift_records, problems
