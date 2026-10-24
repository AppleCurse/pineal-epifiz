"""Tarihli görsel kare sözleşmesi — zaman serisi görsel kanıtın TEK taşıyıcısı.

Neden (denetim 2026-10-24 · "visual_evidence zamanı yok ediyor" bulgusu):
    ``agent_core/services/vision_analyzer.py`` içindeki ``VisualEvidence``
    GÖREV BAŞINA tek düz özettir: ``detected_objects`` tek listeye toplanır.
    100 medya analiz edilse bile "2022'de köpek/bebek" ile "2026'da bıçak/maske"
    aynı zamansız çorbaya düşer. Zamanı silinmiş kanıttan ne baseline kurulur
    ne fosil çıkarılır.

Bu sözleşme ``TaskSnapshot.visual_evidence["frames"]`` altında taşınır ve
``VisualEvidence`` alanlarını BOZMAZ (geriye dönük uyum korunur). Üretici
(``vision_analyzer`` → medya başına analiz) bu kayıtları yazdığında hat
tarihli görselle çalışır; yazmadığında adapter SAHTE TARİH UYDURMAZ, durumu
``undated_visual_summary_skipped`` olarak raporlar.

Kural: ``capture_class`` bu kayıtta BEYAN edilir (bkz. ``media_provenance``).
Beyan yoksa ``unknown``'dur ve habitat/somatik eksenlerini beslemez.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_core.lifecycle.baseline_builder import ensure_utc
from agent_core.lifecycle.media_provenance import CaptureClass

LightingClass = Literal["daylight", "indoor", "low_key_dark", "night_artificial", "unknown"]

__all__ = [
    "FRAME_SIGNAL_PREFIX",
    "FRAME_STAT_KEYS",
    "FRAME_STAT_SIGNALS",
    "GAZE_KEYS",
    "LightingClass",
    "VisualFrameRecord",
    "frames_from_visual_evidence",
]

#: Somatik eksende okunabilen bakış anahtarları (gaze_metrics çıktısı).
GAZE_KEYS = ("ear_mean", "head_pitch", "duchenne_contraction", "engagement")

#: Kare özelliği → sinyal kimliği eşlemesi (TEK beyan yeri).
#: Hepsi 0..1 normalize; yorum değil ÖLÇÜM taşır ve EDİTORYAL eksene gider.
FRAME_STAT_SIGNALS: dict[str, str] = {
    "brightness": "media.frame_brightness",
    "saturation": "media.frame_saturation",
    "contrast": "media.frame_contrast",
    "edge_density": "media.frame_edge_density",
    "colorfulness": "media.frame_colorfulness",
}

#: Ölçülen özellik anahtarları (sıra deterministik).
FRAME_STAT_KEYS: tuple[str, ...] = tuple(FRAME_STAT_SIGNALS)

#: Kare sinyallerinin ortak öneki — TÜRETİLİR, elle yazılmaz. Elle yazılan
#: yarım sinyal adı (``media.frame_``) statik taramada "spec'i olmayan sinyal"
#: gibi görünür; türetme bu tuzağı kapatır.
FRAME_SIGNAL_PREFIX: str = os.path.commonprefix(sorted(FRAME_STAT_SIGNALS.values()))


class VisualFrameRecord(BaseModel):
    """Tek bir tarihli medya karesi ve ondan çıkarılan gözlemler.

    ``extra="forbid"``: sözleşme dışı alan sessizce taşınmaz; şema değişikliği
    bilinçli bir karar (ve test) olur.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    frame_id: str = Field(min_length=1)
    observed_at: datetime
    shortcode: Optional[str] = None
    capture_class: CaptureClass = "unknown"
    has_measurable_background: bool = False
    detected_objects: list[str] = Field(default_factory=list)
    environment_and_places: list[str] = Field(default_factory=list)
    activity_signals: list[str] = Field(default_factory=list)
    lighting: LightingClass = "unknown"
    person_count: Optional[int] = Field(default=None, ge=0)
    gaze: Optional[dict[str, float]] = None
    #: Yayınlanan görselin ÖLÇÜLMÜŞ özellikleri (parlaklık, doygunluk, …).
    #: Bunlar ``media.frame_*`` sinyallerine gider; oda/ışık yorumu DEĞİLDİR.
    visual_stats: Optional[dict[str, float]] = None
    #: İndirilen baytın kimliği (kanıt zinciri; içerik taşınmaz).
    source_sha256: Optional[str] = None
    source_bytes: Optional[int] = Field(default=None, ge=0)
    #: Hangi gönderiye ait olduğu (varsa).
    post_ref: Optional[str] = None
    #: Üretici bu kare için ölçüm yapabildi mi? False ise kare yok sayılır.
    data_confidence: bool = True
    #: Ölçüm yapılamadıysa neden (uydurma değerin yerine sebep).
    fallback_reason: str = ""

    @field_validator("observed_at")
    @classmethod
    def _normalize_observed_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)


def frames_from_visual_evidence(
    visual_evidence: object,
) -> tuple[list[VisualFrameRecord], list[str]]:
    """``visual_evidence["frames"]`` → doğrulanmış kayıtlar + ret sebepleri.

    Dönüş: ``(frames, problems)``. Bozuk kayıt sessizce yutulmaz; ``problems``
    içinde indeksiyle raporlanır. Düz (tarihsiz) özetten kayıt ÜRETİLMEZ.
    """
    if not isinstance(visual_evidence, dict):
        return [], []
    raw_frames = visual_evidence.get("frames")
    if not isinstance(raw_frames, list) or not raw_frames:
        return [], []

    frames: list[VisualFrameRecord] = []
    problems: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_frames):
        try:
            record = item if isinstance(item, VisualFrameRecord) else VisualFrameRecord.model_validate(item)
        except Exception as exc:  # pydantic hata metni indeksle raporlanır
            problems.append(f"invalid_frame[{index}]:{type(exc).__name__}")
            continue
        if record.frame_id in seen:
            problems.append(f"duplicate_frame_id[{index}]:{record.frame_id}")
            continue
        seen.add(record.frame_id)
        frames.append(record)

    frames.sort(key=lambda frame: (frame.observed_at, frame.frame_id))
    return frames, problems
