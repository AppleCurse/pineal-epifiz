"""Gözlem adaptörü — mevcut Pineal verisini TARİHLİ sinyal serisine çevirir.

Girdi (gerçek sözleşmeler, uydurma yok):
    * ``target_profile`` — ``posts`` / ``post_times`` / ``post_evidence_types`` /
      ``posts_meta`` paralel dizileri (bkz. ``agent_core/domain/content_basis.py``,
      ``agent_core/services/platform_registry.ig_target_profile_update``).
    * ``TaskSnapshot.visual_evidence["frames"]`` — tarihli kare kayıtları
      (bkz. ``agent_core.lifecycle.visual_frames``).
    * ``TaskSnapshot.frequency_map["samples"]`` — Wave-1 zaman serisi
      (``pillar_models.WaveSample`` alanları: ``t``/``energy``/``post_count``).

Çıktı: ``list[SignalObservation]`` (kronolojik) + ``AdapterDiagnostics``.

Dört sessiz yanlış burada kapatılır (hepsi testlidir):
    1. **Paralel dizi kayması**: ``len(posts) != len(post_times)`` ise Python
       ``zip()`` sessizce indeks kaydırır ve 1. postun tarihini 5. postun
       metnine yapıştırır. Eşitsizlikte gözlem ÜRETİLMEZ (fail-closed).
    2. **Snippet sızıntısı**: ``post_evidence_types[i] != platform_post`` olan
       metin üçüncü şahıs arama özetidir; kişinin kendi dilinin baseline'ına
       giremez → filtrelenir ve sayılır.
    3. **Tarih bütünlüğü**: ``timestamp > now`` (saat dilimi toleransı dışında)
       reddedilir; shortcode varsa matematiksel çapraz doğrulama yapılır.
       Uyuşmazlıkta kare atılır, sessizce "düzeltilmez".
    4. **Tarihsiz görsel çorbası**: düz ``VisualEvidence`` özetinden zaman
       serisi ÜRETİLMEZ; durum ``undated_visual_summary_skipped`` ile bildirilir.

Ayrıca eksen ayrımı korunur: kurgu/montaj kareden ``habitat.*`` ve ``gaze.*``
ÜRETİLMEZ (bkz. ``media_provenance``); ``media.*`` ve ``ritual.*`` akış ekseni
olarak her tarihli karede ölçülür.

Tüketici: ``agent_core.lifecycle.pipeline``.
Test: ``tests/lifecycle/test_lifecycle_adapter.py``.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Protocol, Sequence, runtime_checkable

from agent_core.engines.frequency_engine import parse_timestamp
from agent_core.lifecycle.baseline_builder import SignalObservation, ensure_utc
from agent_core.lifecycle.ig_time import shortcode_time_drift_hours
from agent_core.lifecycle.media_provenance import CaptureClass
from agent_core.lifecycle.visual_frames import GAZE_KEYS, VisualFrameRecord, frames_from_visual_evidence

logger = logging.getLogger(__name__)

#: Gelecek tarih toleransı: saat dilimi/sunucu kayması için makul pencere.
FUTURE_TOLERANCE = timedelta(hours=6)
#: Shortcode ile beyan edilen zaman arasında kabul edilen azami sapma.
SHORTCODE_MAX_DRIFT_HOURS = 48.0
#: Ritüel sözlüğü için varsayılan keşif penceresi (gün).
VOCABULARY_WINDOW_DAYS = 180
#: Bir etiketin sözlüğe girmesi için baseline karelerindeki asgari oran.
VOCABULARY_MIN_RATIO = 0.20

#: Platform gönderisi sayılan kanıt tipleri (``content_basis`` ile aynı dil).
_PLATFORM_TYPES = frozenset(
    {"platform_post", "text", "image", "video", "reel", "carousel", "unknown", ""}
)

__all__ = [
    "AdapterDiagnostics",
    "AdapterInputs",
    "AlignedPost",
    "ObservationAdapter",
    "SignalExtractor",
    "TextLinguisticExtractor",
    "TimingExtractor",
    "VisualFrameExtractor",
    "align_platform_posts",
]


# ---------------------------------------------------------------------------
# Hizalama
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AlignedPost:
    """Gerçek bir platform postu + tarihi (ikisi ayrılmaz)."""

    post_ref: str
    timestamp: datetime
    text: str
    media_ref: Optional[str] = None


@dataclass
class AdapterDiagnostics:
    """Adaptörün ne yaptığını/ne yapamadığını taşıyan defter.

    Boş liste dönmek yasak ilkesi burada da geçerli: "gözlem yok" ile "veri
    gelmedi" ayrımı ``reasons``/``warnings`` alanlarından okunur.
    """

    aligned_post_count: int = 0
    undated_post_count: int = 0
    filtered_non_platform_count: int = 0
    rejected_future_timestamp_count: int = 0
    visual_frame_count: int = 0
    rejected_frame_count: int = 0
    habitat_suppressed_frame_count: int = 0
    gaze_suppressed_frame_count: int = 0
    undated_visual_summary_skipped: bool = False
    shortcode_mismatch_refs: list[str] = field(default_factory=list)
    vocabulary_until: Optional[datetime] = None
    object_vocabulary_size: int = 0
    place_vocabulary_size: int = 0
    warnings: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "aligned_post_count": self.aligned_post_count,
            "undated_post_count": self.undated_post_count,
            "filtered_non_platform_count": self.filtered_non_platform_count,
            "rejected_future_timestamp_count": self.rejected_future_timestamp_count,
            "visual_frame_count": self.visual_frame_count,
            "rejected_frame_count": self.rejected_frame_count,
            "habitat_suppressed_frame_count": self.habitat_suppressed_frame_count,
            "gaze_suppressed_frame_count": self.gaze_suppressed_frame_count,
            "undated_visual_summary_skipped": self.undated_visual_summary_skipped,
            "shortcode_mismatch_refs": list(self.shortcode_mismatch_refs),
            "vocabulary_until": self.vocabulary_until.isoformat() if self.vocabulary_until else None,
            "object_vocabulary_size": self.object_vocabulary_size,
            "place_vocabulary_size": self.place_vocabulary_size,
            "warnings": list(self.warnings),
        }


def _post_text(post: Any) -> str:
    if isinstance(post, str):
        return post
    if isinstance(post, Mapping):
        for key in ("text", "caption", "content"):
            value = post.get(key)
            if isinstance(value, str):
                return value
    return ""


def _is_platform_post(raw_type: Any) -> bool:
    if raw_type is None:
        return True
    return str(raw_type).strip().lower() in _PLATFORM_TYPES


def _post_timestamp(post: Any, times: Sequence[Any], meta: Sequence[Any], index: int) -> Optional[datetime]:
    """Öncelik: ``post_times[i]`` → post sözlüğü → ``posts_meta[i]``."""
    candidates: list[Any] = []
    if index < len(times):
        candidates.append(times[index])
    if isinstance(post, Mapping):
        candidates.append(post.get("created_at"))
        candidates.append(post.get("timestamp"))
    if index < len(meta) and isinstance(meta[index], Mapping):
        candidates.append(meta[index].get("created_at"))
        candidates.append(meta[index].get("timestamp"))
    for raw in candidates:
        parsed = parse_timestamp(raw)
        if parsed is not None:
            return parsed
    return None


def align_platform_posts(
    target_profile: Optional[Mapping[str, Any]],
    diagnostics: AdapterDiagnostics,
    *,
    now: Optional[datetime] = None,
) -> list[AlignedPost]:
    """Paralel dizileri tek bir tarihli post listesine indirger (fail-closed)."""
    if not isinstance(target_profile, Mapping):
        diagnostics.warn("target_profile_missing")
        return []

    raw_posts = target_profile.get("posts")
    if not isinstance(raw_posts, (list, tuple)):
        diagnostics.warn("posts_missing_or_not_list")
        return []

    raw_times = target_profile.get("post_times")
    times = list(raw_times) if isinstance(raw_times, (list, tuple)) else []
    raw_meta = target_profile.get("posts_meta")
    meta = list(raw_meta) if isinstance(raw_meta, (list, tuple)) else []
    raw_types = target_profile.get("post_evidence_types")
    types = list(raw_types) if isinstance(raw_types, (list, tuple)) else []
    raw_images = target_profile.get("images")
    images = list(raw_images) if isinstance(raw_images, (list, tuple)) else []

    if times and len(times) != len(raw_posts):
        diagnostics.warn(
            f"parallel_array_mismatch: len(posts)={len(raw_posts)} != len(post_times)={len(times)}; "
            "indeks kayması riski nedeniyle gözlem üretilmedi"
        )
        return []
    if types and len(types) != len(raw_posts):
        diagnostics.warn(
            f"evidence_types_mismatch: len(post_evidence_types)={len(types)} != len(posts)={len(raw_posts)}"
        )
        return []

    now_utc = ensure_utc(now or datetime.now(timezone.utc))
    aligned: list[AlignedPost] = []

    for index, post in enumerate(raw_posts):
        if types and not _is_platform_post(types[index]):
            diagnostics.filtered_non_platform_count += 1
            continue

        text = _post_text(post)
        timestamp = _post_timestamp(post, times, meta, index)
        if timestamp is None:
            diagnostics.undated_post_count += 1
            continue
        if timestamp > now_utc + FUTURE_TOLERANCE:
            diagnostics.rejected_future_timestamp_count += 1
            diagnostics.warn(f"timestamp_in_future[{index}]:{timestamp.isoformat()}")
            continue

        media_ref = images[index] if index < len(images) and isinstance(images[index], str) else None
        aligned.append(
            AlignedPost(
                post_ref=f"post_{index:04d}",
                timestamp=timestamp,
                text=text,
                media_ref=media_ref,
            )
        )

    aligned.sort(key=lambda item: (item.timestamp, item.post_ref))
    diagnostics.aligned_post_count = len(aligned)
    return aligned


# ---------------------------------------------------------------------------
# Çıkarıcılar
# ---------------------------------------------------------------------------


@dataclass
class AdapterInputs:
    """Tüm çıkarıcıların gördüğü tek bağlam (yan etkisiz, salt okunur)."""

    aligned_posts: list[AlignedPost]
    visual_evidence: Any = None
    frequency_map: Any = None
    diagnostics: AdapterDiagnostics = field(default_factory=AdapterDiagnostics)
    now: Optional[datetime] = None


@runtime_checkable
class SignalExtractor(Protocol):
    extractor_id: str

    def extract(self, inputs: AdapterInputs) -> list[SignalObservation]: ...


class TimingExtractor:
    """Paylaşım saati, gece oranı ve post aralığı — kişinin zaman normu."""

    extractor_id = "timing"

    def extract(self, inputs: AdapterInputs) -> list[SignalObservation]:
        posts = inputs.aligned_posts
        observations: list[SignalObservation] = []
        for index, post in enumerate(posts):
            ts = post.timestamp
            hour = ts.hour + ts.minute / 60.0 + ts.second / 3600.0
            is_night = 1.0 if (ts.hour >= 22 or ts.hour < 6) else 0.0

            observations.append(
                SignalObservation("timing.post_hour", ts, hour, post.post_ref, {"weekend": ts.weekday() >= 5})
            )
            observations.append(SignalObservation("timing.is_night_post", ts, is_night, post.post_ref))

            if index > 0:
                gap_days = (ts - posts[index - 1].timestamp).total_seconds() / 86400.0
                observations.append(SignalObservation("timing.inter_post_days", ts, gap_days, post.post_ref))
        return observations


class TextLinguisticExtractor:
    """Metin vitrini değil, dilsel ufuk: gelecek-irade ve tükenmişlik yoğunluğu.

    Yoğunluk 100 kelime başına sayılır (``per-100-word``) — kısa caption'ın
    tek isabetle devasa orana fırlamasını engeller.
    """

    extractor_id = "text_linguistics"

    _FUTURE_VERB_RE = re.compile(r"\b(\w{2,}?(?:acağ|eceğ)(?:ım|im|ız|iz|um|üm|ınız|iniz)?)\b", re.UNICODE)
    _FUTURE_LEX_RE = re.compile(
        r"\b(planl\w*|hedef\w*|hazırlan\w*|başlıyor\w*|yakında|gelecek\s+ay|üzerinde\s+çalış\w*)\b",
        re.IGNORECASE | re.UNICODE,
    )
    #: Gelecek-zaman gövdesine benzeyen fakat İSİM olan sözcükler (yanlış pozitif).
    _NOUN_STOPLIST = frozenset(
        {
            "yiyeceğim",
            "içeceğim",
            "giyeceğim",
            "alacağım",
            "vereceğim",
            "geleceğim",
            "gideceğim",
            "edeceğim",
        }
    )
    _REGRET_RE = re.compile(
        r"\b(keşke|boşver\w*|yoruldum|tükendim|bıktım|eskiden|artık|bıraktım|yapamıyorum|olmuyor|mecbur\w*)\b",
        re.IGNORECASE | re.UNICODE,
    )
    _WORD_RE = re.compile(r"\w+", re.UNICODE)

    def extract(self, inputs: AdapterInputs) -> list[SignalObservation]:
        observations: list[SignalObservation] = []
        for post in inputs.aligned_posts:
            ts = post.timestamp
            text = (post.text or "").strip()
            words = self._WORD_RE.findall(text)
            word_count = len(words)

            observations.append(SignalObservation("text.word_count", ts, float(word_count), post.post_ref))
            observations.append(
                SignalObservation("text.is_silent_caption", ts, 1.0 if word_count == 0 else 0.0, post.post_ref)
            )
            if word_count == 0:
                # Sessiz caption'da yoğunluk ölçülmez; 0.0 yazmak "ölçüldü" demek
                # olurdu. Bu yüzden gözlem ÜRETİLMEZ (eksik gözlem ≠ yokluk).
                continue

            future_hits = [
                match.group(1).lower()
                for match in self._FUTURE_VERB_RE.finditer(text)
                if match.group(1).lower() not in self._NOUN_STOPLIST
            ]
            future_hits.extend(match.group(0).lower() for match in self._FUTURE_LEX_RE.finditer(text))
            regret_hits = self._REGRET_RE.findall(text)

            observations.append(
                SignalObservation(
                    "text.future_agency_density", ts, len(future_hits) * 100.0 / word_count, post.post_ref
                )
            )
            observations.append(
                SignalObservation(
                    "text.regret_exhaustion_density", ts, len(regret_hits) * 100.0 / word_count, post.post_ref
                )
            )
        return observations


def _slug_tag(raw: Any) -> str:
    """Etiketi deterministik anahtara çevirir (kişiye/örneğe bağlı liste YOK)."""
    if not isinstance(raw, str):
        return ""
    lowered = raw.strip().lower()
    if not lowered:
        return ""
    collapsed = re.sub(r"\s+", "_", lowered)
    return re.sub(r"[^\w]", "", collapsed, flags=re.UNICODE)


class VisualFrameExtractor:
    """Tarihli görsel kareleri zaman serisine çevirir.

    Ritüel sözlüğü VERİDEN çıkar (``vocabulary_until``'e kadar olan kareler);
    sonraki her karede sözlükteki her etiket için 1.0/0.0 yazılır — böylece
    "ölü ritüel" ölçülebilir olur (yokluk 0.0'dır, kayıtsızlık değil).

    Sözlük TÜM zaman çizgisinden çıkarılırsa ölen ritüel genel orandan düşer ve
    eşiğin altında kalıp elenir; yani tam görmek istediğimiz şey silinir. Bu
    yüzden keşif penceresi baseline ile sınırlıdır.
    """

    extractor_id = "visual_frames"

    def __init__(
        self,
        vocabulary_until: Optional[datetime] = None,
        vocabulary_window_days: int = VOCABULARY_WINDOW_DAYS,
        min_presence_ratio: float = VOCABULARY_MIN_RATIO,
    ) -> None:
        self.vocabulary_until = ensure_utc(vocabulary_until) if vocabulary_until else None
        self.vocabulary_window_days = vocabulary_window_days
        self.min_presence_ratio = min_presence_ratio
        self.object_vocabulary: tuple[str, ...] = ()
        self.place_vocabulary: tuple[str, ...] = ()

    def _load_frames(self, inputs: AdapterInputs) -> list[VisualFrameRecord]:
        diagnostics = inputs.diagnostics
        evidence = inputs.visual_evidence

        frames, problems = frames_from_visual_evidence(evidence)
        for problem in problems:
            diagnostics.warn(problem)
            diagnostics.rejected_frame_count += 1

        if isinstance(evidence, Mapping):
            has_flat_summary = bool(
                evidence.get("detected_objects")
                or evidence.get("environment_and_places")
                or evidence.get("activity_signals")
            )
            if has_flat_summary and not frames:
                diagnostics.undated_visual_summary_skipped = True
                diagnostics.warn(
                    "undated_visual_summary: düz VisualEvidence özetinde tarih yok; "
                    "zaman serisi üretilmedi (sahte tarih yazılmadı)"
                )
        elif evidence is not None:
            diagnostics.warn(f"visual_evidence_unexpected_type:{type(evidence).__name__}")

        now = ensure_utc(inputs.now or datetime.now(timezone.utc))
        verified: list[VisualFrameRecord] = []
        for record in frames:
            if not record.data_confidence:
                diagnostics.rejected_frame_count += 1
                diagnostics.warn(
                    f"frame_without_confidence:{record.frame_id}:{record.fallback_reason or 'no_reason'}"
                )
                continue
            if record.observed_at > now + FUTURE_TOLERANCE:
                diagnostics.rejected_future_timestamp_count += 1
                diagnostics.warn(f"frame_timestamp_in_future:{record.frame_id}")
                continue
            if record.shortcode:
                drift = shortcode_time_drift_hours(record.observed_at, record.shortcode)
                if drift is None:
                    diagnostics.warn(f"shortcode_unverified:{record.frame_id}:{record.shortcode}")
                elif drift > SHORTCODE_MAX_DRIFT_HOURS:
                    diagnostics.shortcode_mismatch_refs.append(record.frame_id)
                    diagnostics.warn(
                        f"shortcode_timestamp_mismatch:{record.frame_id}:drift_hours={drift:.1f}"
                    )
                    continue
            verified.append(record)

        diagnostics.visual_frame_count = len(verified)
        return verified

    def _build_vocabularies(self, frames: Sequence[VisualFrameRecord]) -> None:
        if not frames:
            self.object_vocabulary = ()
            self.place_vocabulary = ()
            return
        cutoff = self.vocabulary_until or (frames[0].observed_at + timedelta(days=self.vocabulary_window_days))
        discovery = [frame for frame in frames if frame.observed_at <= cutoff]
        self.object_vocabulary = self._discover(
            [{_slug_tag(item) for item in frame.detected_objects if _slug_tag(item)} for frame in discovery]
        )
        self.place_vocabulary = self._discover(
            [{_slug_tag(item) for item in frame.environment_and_places if _slug_tag(item)} for frame in discovery]
        )

    def _discover(self, tag_sets: Sequence[set[str]]) -> tuple[str, ...]:
        if not tag_sets:
            return ()
        total = len(tag_sets)
        counts: dict[str, int] = {}
        for tags in tag_sets:
            for tag in tags:
                counts[tag] = counts.get(tag, 0) + 1
        return tuple(sorted(tag for tag, count in counts.items() if count / total >= self.min_presence_ratio))

    def extract(self, inputs: AdapterInputs) -> list[SignalObservation]:
        frames = self._load_frames(inputs)
        if not frames:
            return []

        self._build_vocabularies(frames)
        diagnostics = inputs.diagnostics
        diagnostics.vocabulary_until = (
            self.vocabulary_until or frames[0].observed_at + timedelta(days=self.vocabulary_window_days)
        )
        diagnostics.object_vocabulary_size = len(self.object_vocabulary)
        diagnostics.place_vocabulary_size = len(self.place_vocabulary)

        observations: list[SignalObservation] = []
        for frame in frames:
            ts = frame.observed_at
            ref = frame.frame_id
            capture: CaptureClass = frame.capture_class

            # 1) Üretim biçimi: her tarihli karede ölçülür (kendi ekseni).
            is_incidental = 1.0 if capture == "camera_incidental" else 0.0
            is_authored = 1.0 if capture in ("camera_staged", "edited_composite", "synthetic_or_render") else 0.0
            observations.append(SignalObservation("media.is_incidental_life", ts, is_incidental, ref))
            observations.append(SignalObservation("media.is_authored_or_staged", ts, is_authored, ref))

            # 2) Akış ritüelleri: varlık=1.0, YOKLUK=0.0 (yokluk kaydedilmezse ölçülemez).
            objects = {_slug_tag(item) for item in frame.detected_objects if _slug_tag(item)}
            places = {_slug_tag(item) for item in frame.environment_and_places if _slug_tag(item)}
            observations.append(
                SignalObservation("visual.object_richness", ts, float(len(objects)), ref)
            )
            for tag in self.object_vocabulary:
                observations.append(
                    SignalObservation(f"ritual.obj.{tag}", ts, 1.0 if tag in objects else 0.0, ref)
                )
            for tag in self.place_vocabulary:
                observations.append(
                    SignalObservation(f"ritual.place.{tag}", ts, 1.0 if tag in places else 0.0, ref)
                )

            # 3) Habitat: YALNIZCA gerçek çekim + ölçülebilir arka plan.
            if capture == "camera_incidental" and frame.has_measurable_background:
                if frame.lighting != "unknown":
                    observations.append(
                        SignalObservation(
                            "habitat.is_daylight", ts, 1.0 if frame.lighting == "daylight" else 0.0, ref
                        )
                    )
                    observations.append(
                        SignalObservation(
                            "habitat.is_dark_lowkey",
                            ts,
                            1.0 if frame.lighting in ("low_key_dark", "night_artificial") else 0.0,
                            ref,
                        )
                    )
                if frame.person_count is not None:
                    observations.append(
                        SignalObservation("habitat.person_count", ts, float(frame.person_count), ref)
                    )
                    observations.append(
                        SignalObservation(
                            "habitat.is_solitary", ts, 1.0 if frame.person_count == 1 else 0.0, ref
                        )
                    )
            else:
                diagnostics.habitat_suppressed_frame_count += 1

            # 4) Somatik/bakış: montaj ve sentetik karede ÜRETİLMEZ.
            if capture in ("camera_incidental", "camera_staged") and frame.gaze:
                produced = 0
                for key in GAZE_KEYS:
                    value = frame.gaze.get(key)
                    if isinstance(value, (int, float)) and math.isfinite(float(value)):
                        observations.append(SignalObservation(f"gaze.{key}", ts, float(value), ref))
                        produced += 1
                if produced == 0:
                    diagnostics.gaze_suppressed_frame_count += 1
            else:
                diagnostics.gaze_suppressed_frame_count += 1

        return observations


class FrequencyWaveExtractor:
    """Wave-1 zaman serisini (``frequency_map["samples"]``) sinyale çevirir.

    Tekil özet skorlar OKUNMAZ; yalnız tarihli örnekler seriye girer. ``t``
    alanı ``WaveSample.t``dir (JSON modunda ISO string).
    """

    extractor_id = "frequency_wave"

    def extract(self, inputs: AdapterInputs) -> list[SignalObservation]:
        frequency_map = inputs.frequency_map
        if not isinstance(frequency_map, Mapping):
            return []
        samples = frequency_map.get("samples")
        if not isinstance(samples, (list, tuple)):
            return []

        observations: list[SignalObservation] = []
        for index, sample in enumerate(samples):
            if not isinstance(sample, Mapping):
                inputs.diagnostics.warn(f"invalid_wave_sample[{index}]")
                continue
            timestamp = parse_timestamp(sample.get("t"))
            if timestamp is None:
                inputs.diagnostics.warn(f"undated_wave_sample[{index}]")
                continue
            reference = f"wave_{index:04d}"
            energy = sample.get("energy")
            post_count = sample.get("post_count")
            if isinstance(energy, (int, float)) and math.isfinite(float(energy)):
                observations.append(SignalObservation("wave.energy", timestamp, float(energy), reference))
            if isinstance(post_count, (int, float)) and math.isfinite(float(post_count)):
                observations.append(
                    SignalObservation("wave.post_count", timestamp, float(post_count), reference)
                )
        return observations


class ObservationAdapter:
    """Çıkarıcıları koordine eder: biri çökerse diğerleri çalışmaya devam eder."""

    def __init__(self, extractors: Optional[Sequence[SignalExtractor]] = None) -> None:
        self.extractors: list[SignalExtractor] = list(
            extractors
            if extractors is not None
            else [TimingExtractor(), TextLinguisticExtractor(), VisualFrameExtractor(), FrequencyWaveExtractor()]
        )

    def transform(
        self,
        target_profile: Optional[Mapping[str, Any]] = None,
        *,
        visual_evidence: Any = None,
        frequency_map: Any = None,
        diagnostics: Optional[AdapterDiagnostics] = None,
        now: Optional[datetime] = None,
    ) -> list[SignalObservation]:
        diag = diagnostics if diagnostics is not None else AdapterDiagnostics()
        aligned = align_platform_posts(target_profile, diag, now=now)
        inputs = AdapterInputs(
            aligned_posts=aligned,
            visual_evidence=visual_evidence,
            frequency_map=frequency_map,
            diagnostics=diag,
            now=now,
        )

        observations: list[SignalObservation] = []
        for extractor in self.extractors:
            try:
                observations.extend(extractor.extract(inputs))
            except Exception as exc:  # fail-isolated: bir eksen diğerini düşürmez
                extractor_id = getattr(extractor, "extractor_id", type(extractor).__name__)
                diag.warn(f"extractor_failed:{extractor_id}:{type(exc).__name__}")
                logger.error(
                    "Extractor %s failed: %s", extractor_id, exc, exc_info=True
                )

        observations.sort(key=lambda obs: (obs.timestamp, obs.signal_id, obs.source_ref))
        return observations
