"""Boylamsal **kişisel normal** (baseline) — sapma ölçümünün tek referansı.

Neden ayrı bir katman (denetim 2026-10-24 · "nüfus kağıdı fotokopisi" bulgusu):
    Mevcut zincir "şu an kim?" sorusuna cevap veriyordu; "bu kişinin kendi
    normalinden ne zaman saptı?" sorusuna cevap veren bir referans YOKTU.
    Sabit eşikle ("günde 3 post normaldir") ölçüm yapmak, İstanbul'daki hesap
    ile Anadolu'daki hesabı aynı cetvelle kesmek demektir. Bu modül cetveli
    kişinin KENDİ geçmişinden üretir; tek bir evrensel şablon taşımaz.

Üç sessiz yanlış burada kapatılır (hepsi testlidir):
    1. **std = 0**: 20 gözlem hep 14:00 ise ``z = 0/0`` çöker ve hiçbir sapma
       görünmez. ``constant_break`` dalı, sabit baseline'da kırılmayı mutlak
       farkla ölçer (``min_meaningful_delta``).
    2. **Dairesel saat**: 23:30 ve 00:30 postlarının aritmetik ortalaması
       12:00'dir — yani "gece kuşu" bir hesap "öğlen paylaşıyor" sanılır.
       Saat-of-day dairesel büyüklüktür; birim vektör ortalaması kullanılır.
    3. **Semantiği uydurma**: tolerans (``min_meaningful_delta``) sinyalin
       anlamına bağlıdır (0→1 kırılma mı, 14.0→14.0001 gürültü mü?). Baseline
       bunu TAHMİN ETMEZ; extractor ``SignalSpec`` ile BEYAN eder. Spec'i
       olmayan sinyal baseline'a GİRMEZ, ``unspecified_signals``'a yazılır.

Sınır: bu modül yorum üretmez. Yalnız "gözlenen değer, kişinin merkezinden ne
kadar uzak, hangi yöntemle anlamlı sayıldı" sorusuna sayısal cevap verir.

Tüketici: ``agent_core.lifecycle.deviation_detector``, ``cluster_analyzer``,
``pipeline``.
Test: ``tests/lifecycle/test_lifecycle_baseline.py``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, Sequence

import numpy as np

SignalKind = Literal["binary", "continuous", "count", "ratio", "circular"]
DeviationMethod = Literal["z_score", "constant_break", "insufficient_baseline", "no_baseline"]

#: Bir sinyalin "güvenilir" sayılması için gereken en az gözlem sayısı.
MIN_SAMPLES = 5
#: Pencere verilmezse kullanılan varsayılan baseline uzunluğu (gün).
DEFAULT_BASELINE_DAYS = 180
#: IQR uç-değer katsayısı (tek bir olağandışı gün normu zehirlemesin).
IQR_OUTLIER_FACTOR = 1.5
#: z eşiği (yalnız sürekli sinyallerde; ikinci kapı min_meaningful_delta'dır).
DEFAULT_DEVIATION_Z = 2.0
#: Bu değerin altındaki yayılım "sabit" sayılır (kayan nokta gürültüsü).
CONSTANT_EPS = 1e-9

__all__ = [
    "BaselineProfile",
    "CONSTANT_EPS",
    "DEFAULT_DEVIATION_Z",
    "DEFAULT_BASELINE_DAYS",
    "DeviationMethod",
    "DeviationResult",
    "MIN_SAMPLES",
    "SignalBaseline",
    "SignalKind",
    "SignalObservation",
    "SignalRegistry",
    "SignalSpec",
    "build_baseline",
    "circular_distance",
    "circular_mean_hours",
    "ensure_utc",
]


def ensure_utc(dt: datetime) -> datetime:
    """Naive/aware karışımından doğacak ``TypeError``'ı ve sıralama kaymasını engeller."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Sinyal semantiği — extractor BEYAN eder, baseline TAHMİN ETMEZ
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SignalSpec:
    """Bir sinyalin türü ve anlamlılık toleransı.

    ``min_meaningful_delta``: bu eşiğin altındaki fark GÜRÜLTÜDÜR, sapma
    değildir. Sinyalin birimi cinsindendir (saat, oran, kelime, derece...).
    """

    signal_id: str
    kind: SignalKind
    min_meaningful_delta: float
    circular_period: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.signal_id:
            raise ValueError("SignalSpec.signal_id boş olamaz")
        if self.kind == "circular" and not self.circular_period:
            raise ValueError(f"{self.signal_id}: circular sinyal circular_period ister")
        if self.min_meaningful_delta < 0:
            raise ValueError(f"{self.signal_id}: min_meaningful_delta negatif olamaz")


class SignalRegistry:
    """``signal_id`` → ``SignalSpec``. Tam eşleşme, yoksa EN UZUN prefix.

    Prefix kaydı ``"ritual.obj.*"`` gibi yıldızla biter. Örneğe kilitlenmemek
    için sözlük koda gömülmez: hangi etiketin üretildiğini veri söyler,
    toleransını spec söyler.
    """

    def __init__(self, specs: Optional[Sequence[SignalSpec]] = None) -> None:
        self._exact: dict[str, SignalSpec] = {}
        self._prefix: dict[str, SignalSpec] = {}
        for spec in specs or []:
            self.register(spec)

    def register(self, spec: SignalSpec) -> None:
        if spec.signal_id.endswith("*"):
            self._prefix[spec.signal_id[:-1]] = spec
        else:
            self._exact[spec.signal_id] = spec

    def resolve(self, signal_id: str) -> Optional[SignalSpec]:
        exact = self._exact.get(signal_id)
        if exact is not None:
            return exact
        best: Optional[SignalSpec] = None
        best_len = -1
        for prefix, spec in self._prefix.items():
            if signal_id.startswith(prefix) and len(prefix) > best_len:
                best, best_len = spec, len(prefix)
        if best is None:
            return None
        return SignalSpec(
            signal_id=signal_id,
            kind=best.kind,
            min_meaningful_delta=best.min_meaningful_delta,
            circular_period=best.circular_period,
        )

    def known_prefixes(self) -> tuple[str, ...]:
        return tuple(sorted(self._prefix))

    def known_exact(self) -> tuple[str, ...]:
        return tuple(sorted(self._exact))


# ---------------------------------------------------------------------------
# Gözlem ve sapma sonucu
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SignalObservation:
    """Tek bir sinyal gözlemi: zaman damgası ZORUNLU, değer SONLU olmalı.

    Tarihsiz gözlem (pooled görsel özet gibi) bu tipe GİREMEZ: zaman serisi
    olmayan veriden baseline üretmek uydurmadır. Adapter böyle veriyi
    ``diagnostics`` içine yazar, gözlem üretmez.
    """

    signal_id: str
    timestamp: datetime
    value: float
    source_ref: str
    context: dict = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not self.signal_id:
            raise ValueError("SignalObservation.signal_id boş olamaz")
        if not isinstance(self.timestamp, datetime):
            raise ValueError(f"{self.signal_id}: timestamp datetime olmalı")
        object.__setattr__(self, "timestamp", ensure_utc(self.timestamp))
        value = float(self.value)
        if not math.isfinite(value):
            # NaN/Inf sessizce baseline'a girerse ortalama ve yayılım çöker.
            raise ValueError(f"{self.signal_id}: değer sonlu olmalı ({self.value!r})")
        object.__setattr__(self, "value", value)


@dataclass(frozen=True)
class DeviationResult:
    """Sapma kararı: hangi yöntemle verildiği AÇIKÇA yazılır."""

    signal_id: str
    value: float
    baseline_center: float
    baseline_spread: float
    distance: float
    is_deviation: bool
    method: DeviationMethod
    z_score: Optional[float]
    reason: str


# ---------------------------------------------------------------------------
# Dairesel (saat) aritmetiği
# ---------------------------------------------------------------------------


def _circular_stats(values: np.ndarray, period: float) -> tuple[float, float, float]:
    """Birim vektör ortalaması: 23:30 + 00:30 → 00:00 (12:00 DEĞİL)."""
    k = 2.0 * math.pi / period
    angles = values * k
    cos_mean = float(np.cos(angles).mean())
    sin_mean = float(np.sin(angles).mean())
    resultant = math.hypot(cos_mean, sin_mean)
    mean = (math.atan2(sin_mean, cos_mean) % (2.0 * math.pi)) / k
    if resultant >= 1.0 - 1e-12:
        spread = 0.0
    else:
        spread = math.sqrt(-2.0 * math.log(resultant)) / k
    return mean, spread, resultant


def circular_distance(a: float, b: float, period: float) -> float:
    """Dairesel mesafe: 23:00 ile 01:00 arası 2 saat, 22 saat değil."""
    diff = abs(a - b) % period
    return min(diff, period - diff)


def circular_mean_hours(hours: Sequence[float]) -> Optional[float]:
    """Yardımcı: gece yarısını kesen saat listesinin dairesel ortalaması."""
    if not hours:
        return None
    mean, _, _ = _circular_stats(np.asarray(hours, dtype=float), 24.0)
    return mean


# ---------------------------------------------------------------------------
# Baseline ve değerlendirme
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SignalBaseline:
    """Bir sinyalin kişisel normali. Yorum değil, sayı."""

    signal_id: str
    kind: SignalKind
    center: float
    spread: float
    n: int
    min_value: float
    max_value: float
    is_reliable: bool
    is_constant: bool
    min_meaningful_delta: float
    circular_period: Optional[float]
    window_start: datetime
    window_end: datetime

    def distance_from_center(self, value: float) -> float:
        if self.kind == "circular" and self.circular_period:
            return circular_distance(value, self.center, self.circular_period)
        return abs(value - self.center)

    def evaluate(self, value: float, z_threshold: float = DEFAULT_DEVIATION_Z) -> DeviationResult:
        distance = self.distance_from_center(float(value))

        if not self.is_reliable:
            return DeviationResult(
                signal_id=self.signal_id,
                value=float(value),
                baseline_center=self.center,
                baseline_spread=self.spread,
                distance=distance,
                is_deviation=False,
                method="insufficient_baseline",
                z_score=None,
                reason=f"baseline n={self.n} < {MIN_SAMPLES}; sapma iddiası üretilmez",
            )

        if self.is_constant:
            broke = distance > self.min_meaningful_delta
            return DeviationResult(
                signal_id=self.signal_id,
                value=float(value),
                baseline_center=self.center,
                baseline_spread=self.spread,
                distance=distance,
                is_deviation=broke,
                method="constant_break",
                z_score=None,
                reason=(
                    f"sabit baseline ({self.n} gözlem, hepsi ~{self.center:.4g}); "
                    f"fark={distance:.4g} {'>' if broke else '<='} tolerans={self.min_meaningful_delta:.4g}"
                ),
            )

        z = distance / self.spread
        # İkinci kapı: yayılım çok küçükse mikroskobik gürültü z eşiğini aşar.
        significant = distance > self.min_meaningful_delta
        is_deviation = bool(z >= z_threshold and significant)
        return DeviationResult(
            signal_id=self.signal_id,
            value=float(value),
            baseline_center=self.center,
            baseline_spread=self.spread,
            distance=distance,
            is_deviation=is_deviation,
            method="z_score",
            z_score=float(z),
            reason=(
                f"z={z:.2f} (eşik {z_threshold}); fark={distance:.4g} "
                f"(anlamlılık eşiği {self.min_meaningful_delta:.4g}) → "
                f"{'sapma' if is_deviation else 'sapma değil'}"
            ),
        )


@dataclass
class BaselineProfile:
    """Bir öznenin tüm sinyalleri için kişisel normal profili."""

    subject_id: str
    baseline_window: tuple[datetime, datetime]
    baselines: dict[str, SignalBaseline]
    unspecified_signals: tuple[str, ...] = ()
    signal_order: tuple[str, ...] = ()
    signal_correlation: Optional[np.ndarray] = None
    observation_counts: dict[str, int] = field(default_factory=dict)

    def get(self, signal_id: str) -> Optional[SignalBaseline]:
        return self.baselines.get(signal_id)

    def evaluate(self, observation: SignalObservation, z_threshold: float = DEFAULT_DEVIATION_Z) -> DeviationResult:
        baseline = self.baselines.get(observation.signal_id)
        if baseline is None:
            return DeviationResult(
                signal_id=observation.signal_id,
                value=observation.value,
                baseline_center=float("nan"),
                baseline_spread=float("nan"),
                distance=float("nan"),
                is_deviation=False,
                method="no_baseline",
                z_score=None,
                reason="bu sinyal baseline penceresinde görülmedi; sapma değil, YENİLİK",
            )
        return baseline.evaluate(observation.value, z_threshold)

    def reliable_signals(self) -> list[str]:
        return sorted(sid for sid, baseline in self.baselines.items() if baseline.is_reliable)

    def correlation_between(self, a: str, b: str) -> Optional[float]:
        """İki sinyal arasındaki Pearson korelasyonu — ÖLÇÜLEMEDİYSE ``None``.

        ``None`` "ilişki yok" demek DEĞİLDİR. Sabit bir seride Pearson
        tanımsızdır (0/0); eski kod bunu ``nan_to_num`` ile 0.0'a çeviriyor ve
        "bağımsız" hükmü doğuruyordu. Ölçülemeyen ilişki bağımsızlık kanıtı
        sayılmaz; çağıran taraf ``unknown`` durumuna düşer.
        """
        if self.signal_correlation is None or a == b:
            return None
        try:
            ia = self.signal_order.index(a)
            ib = self.signal_order.index(b)
        except ValueError:
            return None
        value = float(self.signal_correlation[ia, ib])
        return value if math.isfinite(value) else None


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def _remove_outliers(values: list[float]) -> list[float]:
    """IQR ile uç değerleri çıkar (düğün/cenaze günü normu zehirlemesin)."""
    if len(values) < 4:
        return values
    arr = np.asarray(values, dtype=float)
    q1, q3 = np.percentile(arr, [25, 75])
    iqr = float(q3 - q1)
    if iqr < CONSTANT_EPS:
        return values
    low = q1 - IQR_OUTLIER_FACTOR * iqr
    high = q3 + IQR_OUTLIER_FACTOR * iqr
    kept = [v for v in values if low <= v <= high]
    return kept or values


def _compute_correlation(
    observations: Sequence[SignalObservation], signal_ids: Sequence[str]
) -> Optional[np.ndarray]:
    """Sinyaller arası Pearson matrisi — bağımsızlık iddiasının kanıtı.

    Neden: ``gaze.ear_left`` ile ``gaze.ear_mean`` aynı ölçümün iki adıdır.
    İkisi birlikte sapınca "iki bağımsız sinyal" değil, "tek eksen" sayılmalı.
    """
    if len(signal_ids) < 2:
        return None
    series: dict[str, dict[datetime, float]] = {}
    for obs in observations:
        series.setdefault(obs.signal_id, {})[obs.timestamp] = obs.value
    common: Optional[set[datetime]] = None
    for sid in signal_ids:
        stamps = set(series.get(sid, {}))
        common = stamps if common is None else (common & stamps)
    if not common or len(common) < 10:
        return None
    ordered = sorted(common)
    matrix = np.asarray([[series[sid][ts] for sid in signal_ids] for ts in ordered], dtype=float)
    matrix = matrix[~np.isnan(matrix).any(axis=1)]
    if len(matrix) < 10:
        return None
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = np.corrcoef(matrix, rowvar=False)
    # NaN KORUNUR: sabit seride korelasyon tanımsızdır. 0.0'a çevirmek
    # "ilişki yok" uydurmak olurdu (bkz. correlation_between).
    return np.asarray(corr, dtype=float)


# ---------------------------------------------------------------------------
# Kurulum
# ---------------------------------------------------------------------------


def build_baseline(
    subject_id: str,
    observations: Sequence[SignalObservation],
    baseline_start: datetime,
    baseline_end: Optional[datetime] = None,
    registry: Optional[SignalRegistry] = None,
    strict: bool = False,
) -> BaselineProfile:
    """Kişinin kendi geçmişinden normal profilini kurar.

    ``strict=True``: spec'i olmayan sinyal ``ValueError`` fırlatır (üretimde
    yeni sinyal eklerken toleransı beyan etmeyi ZORUNLU kılar).
    ``strict=False``: spec'siz sinyal baseline'a GİRMEZ, adı
    ``unspecified_signals``'a yazılır — sessizce varsayılan tolerans uydurulmaz.
    """
    start = ensure_utc(baseline_start)
    end = ensure_utc(baseline_end) if baseline_end is not None else start + timedelta(days=DEFAULT_BASELINE_DAYS)
    if end < start:
        raise ValueError("baseline_end < baseline_start")
    registry = registry or SignalRegistry()

    window = [obs for obs in observations if start <= obs.timestamp <= end]

    by_signal: dict[str, list[SignalObservation]] = {}
    for obs in window:
        by_signal.setdefault(obs.signal_id, []).append(obs)

    baselines: dict[str, SignalBaseline] = {}
    unspecified: list[str] = []
    counts: dict[str, int] = {}

    for signal_id, obs_list in by_signal.items():
        spec = registry.resolve(signal_id)
        if spec is None:
            if strict:
                raise ValueError(f"{signal_id}: SignalSpec yok. Semantiği beyan et.")
            unspecified.append(signal_id)
            continue

        raw = [obs.value for obs in obs_list]
        # Dairesel veride IQR anlamsız: 23.5 ve 0.5 "uç değer" sanılırdı.
        values = raw if spec.kind == "circular" else _remove_outliers(raw)
        if not values:
            continue

        arr = np.asarray(values, dtype=float)
        if spec.kind == "circular" and spec.circular_period:
            center, spread, _ = _circular_stats(arr, spec.circular_period)
        else:
            center = float(arr.mean())
            spread = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0

        baselines[signal_id] = SignalBaseline(
            signal_id=signal_id,
            kind=spec.kind,
            center=center,
            spread=spread,
            n=len(values),
            min_value=float(arr.min()),
            max_value=float(arr.max()),
            is_reliable=len(values) >= MIN_SAMPLES,
            is_constant=spread < CONSTANT_EPS,
            min_meaningful_delta=spec.min_meaningful_delta,
            circular_period=spec.circular_period,
            window_start=min(obs.timestamp for obs in obs_list),
            window_end=max(obs.timestamp for obs in obs_list),
        )
        counts[signal_id] = len(values)

    reliable = sorted(sid for sid, baseline in baselines.items() if baseline.is_reliable)
    correlation = _compute_correlation(window, reliable) if len(reliable) >= 2 else None

    return BaselineProfile(
        subject_id=subject_id,
        baseline_window=(start, end),
        baselines=baselines,
        unspecified_signals=tuple(sorted(unspecified)),
        signal_order=tuple(reliable),
        signal_correlation=correlation,
        observation_counts=counts,
    )
