"""FAZ A (2) · KANIT MÜHRÜ KÖPRÜSÜ — capability çıktısı → EvidenceTimeline.

Bugün maigret/socid sonuçları yalnızca profile dict olarak yazılıyor; kanıt
zincirine (EvidenceTimeline) girmiyor. Bu köprü o boşluğu kapatır:

    capability.run(...)  →  CapabilityResult.items (EvidenceItem)
                         →  build_evidence_timeline(...)
                         →  EvidenceTimeline (mühürlü, sıralı, reddedilen sayısıyla)

Sözleşme: kanıt mührü burada da geçerlidir — hiçbir aşamada içerik türetilmez;
yalnızca yeteneğin ürettiği kayıtlar zaman çizelgesine alınır.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from agent_core.capabilities.base import CapabilityResult
from agent_core.domain.evidence_models import EvidenceItem, EvidenceTimeline
from agent_core.services.evidence_timeline import build_evidence_timeline

__all__ = ["seal_items", "seal_results", "merge_items"]


def merge_items(results: Iterable[CapabilityResult]) -> list[EvidenceItem]:
    """Birden çok capability sonucunun kanıtlarını sırayla tek listeye indirger."""
    merged: list[EvidenceItem] = []
    for result in results or []:
        for item in getattr(result, "items", ()) or ():
            merged.append(item)
    return merged


def seal_items(items: Sequence[EvidenceItem] | None) -> EvidenceTimeline:
    """Kanıt listesini mühürlü zaman çizelgesine çevirir."""
    return build_evidence_timeline(list(items or []))


def seal_results(results: Iterable[CapabilityResult]) -> EvidenceTimeline:
    """Capability sonuçlarını tek zaman çizelgesinde mühürler."""
    return seal_items(merge_items(results))


def seal_summary(results: Iterable[CapabilityResult]) -> dict[str, Any]:
    """Telemetri/UI için özet: hangi yetenek ne üretti, ne kadar kanıt mühürlendi."""
    rows: list[dict[str, Any]] = []
    for result in results or []:
        rows.append(
            {
                "capability_id": result.capability_id,
                "available": result.available,
                "reason": result.unavailable_reason,
                "denied_by": result.denied_by,
                "evidence_count": len(result.items),
            }
        )
    timeline = seal_items(merge_items(results))
    return {
        "capabilities": rows,
        "timeline": timeline,
        "sealed_count": len(timeline.entries),
        "rejected_count": timeline.rejected_item_count,
    }
