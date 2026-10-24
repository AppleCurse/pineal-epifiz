"""Sinyal aileleri — bağımsızlık sayımının tek kaynağı.

Neden: aynı fiziksel olayın yansımaları "ayrı sapma" sayılmamalı. Baş öne
eğildiğinde ``gaze.head_pitch`` negatifleşir, göz kapağı düşer
(``gaze.ear_mean``), bakış aşağı olur. Bunlar üç bağımsız sinyal DEĞİL, tek
hareketin üç gölgesidir. Aile = "bu sinyaller aynı ölçüm kanalından mı geliyor?"

Kural: burada hiçbir kişi/nesne/şehir adı yoktur; yalnız ölçüm kanalları
vardır. Hangi nesnenin ritüel olduğunu kod değil, kişinin kendi verisindeki
frekans belirler (``ritual.obj.*`` joker ailesi).

Tüketici: ``agent_core.lifecycle.cluster_analyzer``, ``deviation_detector``.
Test: ``tests/lifecycle/test_lifecycle_cluster_analyzer.py``.
"""

from __future__ import annotations

__all__ = ["FAMILY_ORDER", "LIFE_AXES", "MEDIUM_AXIS", "signal_family"]

#: Ölçüm kanalları (öncelik sırası: ilk eşleşen kazanır).
_PREFIX_FAMILIES: tuple[tuple[str, str], ...] = (
    ("ritual.obj.", "ritual"),
    ("ritual.place.", "ritual"),
    ("ritual.", "ritual"),
    ("habitat.", "habitat"),
    ("gaze.", "gaze"),
    ("media.", "media"),
    ("visual.", "media"),
    ("timing.", "timing"),
    ("text.", "text"),
    ("wave.", "wave"),
    ("strata.", "strata"),
)

FAMILY_ORDER: tuple[str, ...] = ("timing", "text", "media", "ritual", "habitat", "gaze", "wave", "strata")

#: Üretim biçimini taşıyan eksen: değişimi TEK BAŞINA yaşam koşulu değişimi değildir.
MEDIUM_AXIS = "media"

#: Fiziksel yaşam koşulunu iddia eden eksenler (confound denetimine girerler).
LIFE_AXES = ("habitat", "gaze", "ritual")


def signal_family(signal_id: str) -> str:
    """``signal_id`` → ölçüm kanalı. Bilinmeyen sinyal kendi ailesidir."""
    if not signal_id:
        return "unknown"
    for prefix, family in _PREFIX_FAMILIES:
        if signal_id.startswith(prefix):
            return family
    return "other"
