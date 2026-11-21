"""Lilith NeuroMetrics girdilerini deterministik MOTOR ÖLÇÜMLERİNDEN türeten tek kaynak.

Neden var?
    ``/api/lilith/strategy`` ve ``PinealExecutor`` Lilith hattı, dış LLM
    olmadığında ``NeuroMetrics``'i motor sinyallerinden hesaplamak zorundadır.
    Eski kodda motor sinyali bulunamadığında sabitler (0.55 / 0.50 / 0.45 / 0.50)
    ``metrics_source="deterministic_engines"`` etiketiyle basılıyordu — kaynak
    hukuku ihlali (sabit ≠ ölçüm). Bu modül kuralı tek yerde uygular:

    * D=güven, S=etkileşim→0..1, C=reaksiyon-formasyonu, O=gece-share —
      HEPSİ motor çıktısının GERÇEKT anahtarlarından okunur ve 0..1'e
      normalize edilir.
    * Herhangi biri eksik/ölçümsüzse → ``None`` döner; çağıran taraf metrics
      üretmez, açık ``fallback_reason`` yazar. Sabit YEDEK YOKTUR.
    * ``psychodynamic_depth.verdict != "ok"`` ise (kanıt yetersiz) derinlik
      sinyalleri ölçümsüz sayılır.

Eşleme (sezgisel, dokümante; kanıt DEĞİL, üretim girdisidir):
    dopamine          ← psychodynamic_depth.confidence            (0..1)
    serotonin         ← follower_audit.engagement_rate (yüzde puan) / 10 (0..1)
    cortisol          ← psychodynamic_depth.reaction_formation_index (0..1)
    oxytocin          ← timing_forensics.night_share              (0..1)
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

__all__ = ["neuro_inputs_from_engines"]


def _finite(value: Any) -> Optional[float]:
    """Sonlu gerçek sayı (bool hariç) değilse None — ölçülmemiş demektir."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
        if result == result and result not in (float("inf"), float("-inf")):
            return result
        return None
    return None


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)


def neuro_inputs_from_engines(
    psychodynamic_depth: Mapping[str, Any] | None,
    timing_forensics: Mapping[str, Any] | None,
    follower_audit: Mapping[str, Any] | None,
) -> Optional[Dict[str, float]]:
    """4'ü de ölçülmüşse normalize edilmiş girdi dict'i; yoksa ``None``.

    Dönüş: ``{"dopamine", "serotonin", "cortisol", "oxytocin"}`` — her biri
    [0, 1] aralığında. Sabit yedek DEĞER ÜRETİLMEZ.
    """
    depth = psychodynamic_depth if isinstance(psychodynamic_depth, Mapping) else {}
    timing = timing_forensics if isinstance(timing_forensics, Mapping) else {}
    audit = follower_audit if isinstance(follower_audit, Mapping) else {}

    depth_ok = str(depth.get("verdict") or "").strip().lower() == "ok"
    dopamine = _finite(depth.get("confidence")) if depth_ok else None
    cortisol = _finite(depth.get("reaction_formation_index")) if depth_ok else None

    engagement_rate = _finite(audit.get("engagement_rate"))  # yüzde puanı (ör. 5.0 → 5%)
    serotonin = _clamp01(engagement_rate / 10.0) if engagement_rate is not None else None

    night_share = _finite(timing.get("night_share"))
    oxytocin = night_share if (night_share is not None and 0.0 <= night_share <= 1.0) else None

    dopamine = _clamp01(dopamine) if dopamine is not None else None
    cortisol = _clamp01(cortisol) if cortisol is not None else None

    if dopamine is None or serotonin is None or cortisol is None or oxytocin is None:
        return None
    return {
        "dopamine": dopamine,
        "serotonin": serotonin,
        "cortisol": cortisol,
        "oxytocin": oxytocin,
    }
