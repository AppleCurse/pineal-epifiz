"""Tarihli kare kanıtı — havuzlanmış görsel özetin yerini alan hat.

Sorun: ``vision_analyzer`` görev başına TEK bir düz özet üretir; 100 görsel
analiz edilse bile "2022'de masa vardı" ile "2026'da stüdyo" aynı zamansız
çorbaya düşer. Zamansız kanıttan ne baseline kurulur ne değişim ölçülür.

Bu modül gönderi başına TARİHLİ kare üretir ve iki kademeli tarama uygular:

    1. kademe (burada, 0 LLM): indir → yerel ölçüm (parlaklık, doygunluk,
       kontrast, kenar yoğunluğu, renklilik) → komşu kareler arasında
       deterministik "değişim noktası" işaretleme.
    2. kademe (bu modülde YOK): yalnız değişim noktaları pahalı anlamsal
       analize gider. Anlamsal etiket (nesne/mekân) ölçülmedikçe kare
       ``detected_objects=[]`` taşır — UYDURULMAZ.

Dürüstlük sınırları (bilinçli):
    * ``capture_class`` burada **unknown** kalır. Kamera/EXIF/üretim yazılımı
      kanıtı olmadan "gerçek çekim" demek, kurgu bir kareyi yaşam kanıtı
      saymak olurdu. Bu yüzden habitat/bakış eksenleri KAPALI kalır.
    * Yerel ölçümler **yayınlanan görselin** özellikleridir: bunlar
      ``media.frame_*`` sinyalleridir (editoryal eksen), "oda karardı" iddiası
      değildir. Yorum katmanı bu ayrımı korur.
    * İndirilemeyen/çözülemeyen kare **yokluk değildir**: kayıt üretilmez,
      sebep teşhis listesine yazılır.

Tüketici: ``agent_core.task_executor`` (``visual_evidence["frames"]``),
``agent_core.lifecycle.observation_adapter``.
Test: ``tests/unit/test_frame_evidence.py``.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Mapping, Optional, Sequence

from agent_core.engines.frequency_engine import parse_timestamp

__all__ = [
    "DEFAULT_MAX_FRAMES",
    "FrameCandidate",
    "FrameCollection",
    "FrameFeatures",
    "change_point_indices",
    "collect_frames",
    "decode_image",
    "measure_frame_features",
    "select_frame_candidates",
]

#: LLM'siz kademenin maliyet tavanı: görev başına en fazla bu kadar kare.
DEFAULT_MAX_FRAMES = 12
#: Aynı anda indirilecek kare sayısı (sunucuyu boğmamak için).
DOWNLOAD_CONCURRENCY = 4
#: Toplam indirme bütçesi (saniye); aşılırsa elde ne varsa onunla devam edilir.
DOWNLOAD_BUDGET_SECONDS = 45.0
#: Gelecek tarih toleransı (saat dilimi/sunucu kayması).
FUTURE_TOLERANCE = timedelta(hours=6)
#: Değişim noktası eşikleri (normalize özellik biriminde).
CHANGE_POINT_THRESHOLD = 0.12
#: Kenar yoğunluğu bunun altındaysa arka planda yapı yok (düz fon/stüdyo).
BACKGROUND_EDGE_FLOOR = 0.004

FetchFn = Callable[[str], Awaitable[Mapping[str, Any]]]

_PLATFORM_TYPES = {"platform_post", "post", "instagram_post"}


@dataclass(frozen=True)
class FrameCandidate:
    """Tarihi belli, görseli olan tek bir gönderi."""

    frame_id: str
    post_ref: str
    observed_at: datetime
    image_url: str

    def to_payload(self) -> dict:
        return {
            "frame_id": self.frame_id,
            "post_ref": self.post_ref,
            "observed_at": self.observed_at.isoformat(),
            "image_url": self.image_url,
        }


@dataclass(frozen=True)
class FrameFeatures:
    """Yayınlanan görselin ölçülebilir özellikleri (0..1 normalize)."""

    brightness: float
    saturation: float
    contrast: float
    edge_density: float
    colorfulness: float
    # Piksel boyutu yalnız teşhis içindir; yeniden kurulumda bilinmeyebilir.
    width: int = 0
    height: int = 0

    @property
    def has_background_structure(self) -> bool:
        return self.edge_density >= BACKGROUND_EDGE_FLOOR

    def to_dict(self) -> dict:
        return {
            "brightness": round(self.brightness, 6),
            "saturation": round(self.saturation, 6),
            "contrast": round(self.contrast, 6),
            "edge_density": round(self.edge_density, 6),
            "colorfulness": round(self.colorfulness, 6),
            "width": self.width,
            "height": self.height,
        }


@dataclass
class FrameCollection:
    """Kare hattının çıktısı: tarihli kareler + teşhis defteri."""

    frames: list[dict] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"frames": self.frames, "problems": self.problems, "diagnostics": self.diagnostics}


def _frame_id(post_ref: str, observed_at: datetime, image_url: str) -> str:
    key = f"{post_ref}|{observed_at.isoformat()}|{image_url}"
    return "fr_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def select_frame_candidates(
    target_profile: Optional[Mapping[str, Any]],
    *,
    max_frames: int = DEFAULT_MAX_FRAMES,
    now: Optional[datetime] = None,
) -> tuple[list[FrameCandidate], list[str]]:
    """Gönderi/görsel paralel dizilerinden TARİHLİ kare adayları seçer.

    Fail-closed: paralel diziler hizasızsa hiçbir aday üretilmez (indeks
    kayması yanlış gönderiye yanlış tarih yapıştırır). Tarihi çözülemeyen
    gönderi atlanır — tarih uydurulmaz.
    """
    problems: list[str] = []
    if not isinstance(target_profile, Mapping):
        return [], ["target_profile_missing"]

    posts = target_profile.get("posts")
    times = target_profile.get("post_times")
    images = target_profile.get("images")
    if not isinstance(posts, (list, tuple)) or not isinstance(times, (list, tuple)):
        return [], ["posts_or_times_missing"]
    if not isinstance(images, (list, tuple)) or not images:
        return [], ["images_missing"]
    if not (len(posts) == len(times) == len(images)):
        problems.append(
            f"parallel_array_mismatch: posts={len(posts)} times={len(times)} images={len(images)}"
        )
        return [], problems

    raw_types = target_profile.get("post_evidence_types")
    types = list(raw_types) if isinstance(raw_types, (list, tuple)) else []
    if types and len(types) != len(posts):
        problems.append(f"evidence_types_mismatch: {len(types)} != {len(posts)}")
        return [], problems

    now_utc = now or datetime.now(timezone.utc)
    candidates: list[FrameCandidate] = []
    for index, url in enumerate(images):
        if types:
            raw_type = str(types[index]).strip().lower()
            if raw_type not in _PLATFORM_TYPES:
                problems.append(f"non_platform_post[{index}]:{raw_type}")
                continue
        if not isinstance(url, str) or not url.startswith("http"):
            problems.append(f"image_url_missing[{index}]")
            continue
        observed_at = parse_timestamp(times[index])
        if observed_at is None:
            problems.append(f"undated_post[{index}]")
            continue
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        if observed_at > now_utc + FUTURE_TOLERANCE:
            problems.append(f"future_timestamp[{index}]")
            continue
        post_ref = f"post_{index:04d}"
        candidates.append(
            FrameCandidate(
                frame_id=_frame_id(post_ref, observed_at, url),
                post_ref=post_ref,
                observed_at=observed_at,
                image_url=url,
            )
        )

    candidates.sort(key=lambda candidate: (candidate.observed_at, candidate.frame_id))
    if len(candidates) > max_frames > 0:
        candidates = _stratified_sample(candidates, max_frames)
        problems.append(f"frame_budget_applied: {max_frames}")

    if not candidates:
        problems.append("no_dated_frame_candidate")
    return candidates, problems


def _stratified_sample(candidates: Sequence[FrameCandidate], limit: int) -> list[FrameCandidate]:
    """Zaman çizelgesinin TAMAMINI temsil eden deterministik seçim.

    İlk/son ayıklanmaz: değişimin uçları çoğu zaman oradadır.
    """
    if limit >= len(candidates):
        return list(candidates)
    if limit == 1:
        return [candidates[-1]]
    step = (len(candidates) - 1) / (limit - 1)
    indices = sorted({int(round(index * step)) for index in range(limit)})
    return [candidates[index] for index in indices]


# ---------------------------------------------------------------------------
# Yerel ölçüm (LLM YOK)
# ---------------------------------------------------------------------------


def decode_image(data: bytes) -> Any:
    """Bayt → PIL.Image (RGB). Çözülemezse ``None`` — uydurma yok."""
    try:
        from PIL import Image
    except Exception:  # pragma: no cover - opsiyonel bağımlılık
        return None
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        return image.convert("RGB")
    except Exception:
        return None


def measure_frame_features(image: Any) -> Optional[FrameFeatures]:
    """PIL görüntüsünden normalize özellikler çıkarır.

    Tüm değerler 0..1 aralığındadır ve YALNIZ yayınlanan görselin kendisini
    anlatır (oda/ışık yorumu değil). numpy yoksa ``None`` döner: ölçüm
    yapılmadığı açıkça bellidir.
    """
    try:
        import numpy as np
    except Exception:  # pragma: no cover - zorunlu bağımlılık
        return None
    if image is None:
        return None

    width, height = image.size
    if width < 8 or height < 8:
        return None

    # Küçültme: ölçüm maliyeti sabit kalır, sonuç deterministik olur.
    thumb = image.copy()
    thumb.thumbnail((128, 128))
    pixels = np.asarray(thumb, dtype=np.float32) / 255.0
    if pixels.size == 0:
        return None

    red, green, blue = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    gray = 0.299 * red + 0.587 * green + 0.114 * blue

    brightness = float(gray.mean())
    contrast = float(min(1.0, gray.std() / 0.3))

    max_channel = pixels.max(axis=2)
    min_channel = pixels.min(axis=2)
    saturation = float(np.mean((max_channel - min_channel) / np.maximum(max_channel, 1e-6)))

    # Renklilik: Hasler–Süsstrunk yaklaşımının 0..1'e normalize hâli.
    rg = red - green
    yb = 0.5 * (red + green) - blue
    colorfulness = float(
        min(
            1.0,
            (math.hypot(float(rg.std()), float(yb.std())) + 0.3 * math.hypot(float(rg.mean()), float(yb.mean())))
            / 1.5,
        )
    )

    # Kenar yoğunluğu: komşu fark eşiği (Sobel/Canny bağımlılığı olmadan).
    gx = np.abs(np.diff(gray, axis=1)).mean() if gray.shape[1] > 1 else 0.0
    gy = np.abs(np.diff(gray, axis=0)).mean() if gray.shape[0] > 1 else 0.0
    edge_density = float(min(1.0, (float(gx) + float(gy)) * 2.5))

    return FrameFeatures(
        brightness=brightness,
        saturation=saturation,
        contrast=contrast,
        edge_density=edge_density,
        colorfulness=colorfulness,
        width=int(width),
        height=int(height),
    )


def change_point_indices(features: Sequence[FrameFeatures], threshold: float = CHANGE_POINT_THRESHOLD) -> list[int]:
    """Komşu kareler arasında belirgin değişimin olduğu indeksler.

    Pahalı anlamsal analizin nereye harcanacağını belirler. Deterministik:
    aynı seri aynı indeksleri verir. İlk ve son kare her zaman adaydır.
    """
    if not features:
        return []
    points = {0, len(features) - 1}
    for index in range(1, len(features)):
        previous, current = features[index - 1], features[index]
        delta = max(
            abs(current.brightness - previous.brightness),
            abs(current.saturation - previous.saturation),
            abs(current.contrast - previous.contrast),
            abs(current.edge_density - previous.edge_density),
            abs(current.colorfulness - previous.colorfulness),
        )
        if delta >= threshold:
            points.add(index)
    return sorted(points)


# ---------------------------------------------------------------------------
# Toplama
# ---------------------------------------------------------------------------


def _decode_and_measure(record: Mapping[str, Any]) -> tuple[Optional[FrameFeatures], Optional[str]]:
    encoded = record.get("b64")
    if not isinstance(encoded, str) or not encoded:
        return None, "no_payload"
    try:
        data = base64.b64decode(encoded)
    except Exception:
        return None, "base64_decode_error"
    image = decode_image(data)
    if image is None:
        return None, "image_decode_error"
    features = measure_frame_features(image)
    if features is None:
        return None, "feature_measurement_failed"
    return features, None


def _features_from_stats(stats: Any) -> Optional[FrameFeatures]:
    """``visual_stats`` sözlüğünü yeniden ``FrameFeatures``e çevirir (salt okuma)."""
    if not isinstance(stats, Mapping):
        return None
    try:
        return FrameFeatures(
            brightness=float(stats["brightness"]),
            saturation=float(stats["saturation"]),
            contrast=float(stats["contrast"]),
            edge_density=float(stats["edge_density"]),
            colorfulness=float(stats["colorfulness"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


async def collect_frames(
    target_profile: Optional[Mapping[str, Any]],
    *,
    fetch: FetchFn,
    max_frames: int = DEFAULT_MAX_FRAMES,
    now: Optional[datetime] = None,
    budget_seconds: float = DOWNLOAD_BUDGET_SECONDS,
    concurrency: int = DOWNLOAD_CONCURRENCY,
) -> FrameCollection:
    """Adayları indirir, yerel ölçümü yapar ve ``VisualFrameRecord`` sözlükleri döner.

    ``fetch`` SSRF-güvenli indirici olmalıdır (bkz. ``vision_analyzer``) ve
    ``{"status": "downloaded", "b64": ...}`` biçiminde kayıt döndürmelidir.
    Hata fırlatmaz: indirilemeyen kare kayıt ÜRETMEZ, sebebi listeye yazılır.
    """
    candidates, problems = select_frame_candidates(target_profile, max_frames=max_frames, now=now)
    collection = FrameCollection(problems=list(problems))
    collection.diagnostics.update(
        {
            "candidate_count": len(candidates),
            "max_frames": max_frames,
            "downloaded_count": 0,
            "measured_count": 0,
            "budget_exceeded": False,
        }
    )
    if not candidates:
        collection.diagnostics["measured_count"] = 0
        return collection

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _one(candidate: FrameCandidate) -> dict:
        async with semaphore:
            try:
                record = await fetch(candidate.image_url)
            except Exception as error:  # noqa: BLE001 — fail-closed
                collection.problems.append(f"fetch_error:{candidate.frame_id}:{type(error).__name__}")
                return {}
        if not isinstance(record, Mapping):
            collection.problems.append(f"fetch_bad_record:{candidate.frame_id}")
            return {}
        if record.get("status") != "downloaded":
            reason = record.get("reason") or "unknown"
            collection.problems.append(f"download_failed:{candidate.frame_id}:{reason}")
            return {}
        collection.diagnostics["downloaded_count"] += 1
        features, reason = _decode_and_measure(record)
        if features is None:
            collection.problems.append(f"measurement_failed:{candidate.frame_id}:{reason}")
            return {}
        return {
            "frame_id": candidate.frame_id,
            "observed_at": candidate.observed_at.isoformat(),
            # Kanıt YOK: gerçek çekim/kurgu ayrımı bu kademede yapılmaz.
            "capture_class": "unknown",
            "has_measurable_background": features.has_background_structure,
            "detected_objects": [],
            "environment_and_places": [],
            "lighting": "unknown",
            "visual_stats": features.to_dict(),
            "data_confidence": True,
            "fallback_reason": "",
            "source_sha256": record.get("sha256"),
            "source_bytes": record.get("bytes") if isinstance(record.get("bytes"), int) else None,
            "post_ref": candidate.post_ref,
        }

    try:
        results = await asyncio.wait_for(
            asyncio.gather(
                *(_one(candidate) for candidate in candidates), return_exceptions=True
            ),
            timeout=max(1.0, budget_seconds),
        )
    except asyncio.TimeoutError:
        collection.diagnostics["budget_exceeded"] = True
        collection.problems.append("download_budget_exceeded")
        results = []

    frames: list[dict[str, Any]] = []
    for candidate, item in zip(candidates, results, strict=False):
        if isinstance(item, BaseException):
            collection.problems.append(f"frame_task_error:{candidate.frame_id}:{type(item).__name__}")
            continue
        if isinstance(item, Mapping) and item:
            frames.append(dict(item))

    frames.sort(key=lambda item: (item["observed_at"], item["frame_id"]))
    collection.frames = frames
    collection.diagnostics["measured_count"] = len(frames)
    # İkinci kademe (pahalı anlamsal analiz) nereye harcanacak? Değişim
    # noktaları burada hesaplanır ki liste yalnız ÖLÇÜLMÜŞ kareleri göstersin.
    ordered = [_features_from_stats(frame.get("visual_stats")) for frame in frames]
    features = [item for item in ordered if item is not None]
    if len(features) == len(frames):
        points = change_point_indices(features)
        collection.diagnostics["change_points"] = points
        collection.diagnostics["change_point_frame_ids"] = [frames[index]["frame_id"] for index in points]
    else:  # pragma: no cover - savunma: ölçüm sözlüğü bozulursa
        collection.diagnostics["change_points"] = []
        collection.diagnostics["change_point_frame_ids"] = []
        collection.problems.append("change_point_unavailable")
    return collection
