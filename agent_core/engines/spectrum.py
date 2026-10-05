"""FAZ B · B6 — GERÇEK SPEKTRAL ANALİZ (FFT periodogramı).

Bugüne dek Frequency motoru yalnızca sin/cos biçiminde bir **model** taşıyordu
ve `FrequencyReport.dominant_period_days` alanı declared ama HİÇ doldurulmayan
bir kabuktu (yarım entegrasyon). Bu modül o alanı GERÇEK ÖLÇÜME çevirir.

Yöntem (uydurma yok):
    1. Ortalama çıkarılır (DC/ trend bastırma), Hann penceresi uygulanır.
    2. `numpy.fft.rfft` ile tek taraflı genlik spektrumu; güç = |X|².
    3. DC (0. harmanik) ve Nyquist hariç tutulur — "sabit enerji" bir ritim
       değildir; onu tepe sanmak klasik bir sahteciliktir.
    4. En güçlü harmanik → periyot = (kova_saati / 24) * (N / k) gün.
    5. `periodic_strength` = tepe gücünün TOPLAM güce oranı (0..1). Düşükse
       "ritim var" DENMEZ; rapor yalnız sayıyı taşır.

Dürüstlük sözleşmesi:
- Örnek sayısı yetersizse (`min_samples`) → `available=False`, sebep
  `insufficient_samples`; periyot **None** kalır (tahmin ÜRETİLMEZ).
- Sabit (varyanssız) seride → sebep `flat_signal`; periyot None.
- numpy yoksa → sebep `dependency_missing:numpy` (numpy temel bağımlılıktır;
  yine de sessiz çökme olmasın diye açıkça raporlanır).
"""

from __future__ import annotations

from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "SpectralPeak",
    "SpectralAnalysis",
    "analyze_spectrum",
    "MIN_SAMPLES",
]

#: En az bu kadar kova olmadan periyot iddia edilmez (8 kova = en az 8 gün/4 saat
#: kovalarında 32 saat). Spektral kestirimde kural: en uzun periyodu görmek için
#: en az iki tam döngü gerekir; biz yalnız ilk harmaniği okuduğumuz için bu
#: eşik "en uzun periyot = seri uzunluğu" kabulüne dayanır ve raporlanır.
MIN_SAMPLES = 8


class SpectralPeak(BaseModel):
    """Tek bir spektral tepe (harmanik)."""

    harmonic: int
    period_days: float
    power_share: float = Field(ge=0.0, le=1.0)
    model_config = ConfigDict(extra="forbid")


class SpectralAnalysis(BaseModel):
    """FFT sonucu — alanların hepsi ÖLÇÜM; tahminle doldurulmaz."""

    available: bool = False
    reason: str | None = None
    method: str = "fft_periodogram_hann"
    sample_count: int = 0
    bucket_hours: int = 24
    #: En güçlü döngü (gün). Yetersiz/boş veri -> None (uydurma YOK).
    dominant_period_days: float | None = None
    dominant_harmonic: int | None = None
    #: Tepe gücünün toplam güce oranı: 1'e yakınsa tek bir baskın ritim var.
    periodic_strength: float | None = None
    #: Normalize güç spektrumu (DC ve Nyquist hariç) — UI grafiği için.
    spectrum: list[float] = Field(default_factory=list)
    peaks: list[SpectralPeak] = Field(default_factory=list)
    machine_note: str = ""
    model_config = ConfigDict(extra="forbid")


def analyze_spectrum(
    energy: Sequence[float],
    *,
    bucket_hours: int = 24,
    min_samples: int = MIN_SAMPLES,
    top_k: int = 3,
) -> SpectralAnalysis:
    """Zaman kovalarındaki enerji serisinin GERÇEK periyodunu ölçer.

    `energy` sırası eşit aralıklı kovaların enerjisidir (FrequencyEngine'in
    ürettiği `WaveSample.energy` dizisi). Uydurma tepe üretilmez: koşullar
    sağlanmazsa `available=False` + makine-okunur sebep döner.
    """
    series = [float(v) for v in (energy or [])]
    n = len(series)
    base = SpectralAnalysis(sample_count=n, bucket_hours=int(bucket_hours))

    if n < min_samples:
        base.reason = "insufficient_samples"
        base.machine_note = (
            f"SPEKTRUM: {n} kova < {min_samples} — periyot iddia edilmedi."
        )
        return base

    try:
        import numpy as np
    except Exception:  # pragma: no cover - numpy temel bağımlılıktır
        base.reason = "dependency_missing:numpy"
        base.machine_note = "SPEKTRUM: numpy yok — periyot ölçülemedi."
        return base

    x = np.asarray(series, dtype=float)
    x = x - float(x.mean())  # DC/trend bastırma
    if float(np.max(np.abs(x))) <= 1e-9:
        base.reason = "flat_signal"
        base.machine_note = "SPEKTRUM: seri sabit (varyans 0) — ritim ölçülemedi."
        return base

    window = np.hanning(n)
    spectrum = np.abs(np.fft.rfft(x * window)) ** 2

    # DC (k=0) ve Nyquist bir ritim DEĞİLDİR: çıkarılır.
    usable = spectrum[1:]
    if n % 2 == 0:
        usable = usable[:-1]
    if usable.size == 0 or float(usable.sum()) <= 1e-12:
        base.reason = "no_periodic_component"
        base.machine_note = "SPEKTRUM: periyodik bileşen bulunamadı."
        return base

    total = float(usable.sum())
    normalized = (usable / total).tolist()
    order = sorted(range(len(usable)), key=lambda i: float(usable[i]), reverse=True)
    top = order[: max(1, top_k)]

    bucket_days = float(bucket_hours) / 24.0
    all_peaks = [
        SpectralPeak(
            harmonic=int(k + 1),
            period_days=round(bucket_days * (n / float(k + 1)), 4),
            power_share=round(float(usable[k]) / total, 6),
        )
        for k in range(len(usable))
        if float(usable[k]) > 0
    ]
    if not all_peaks:
        base.reason = "no_periodic_component"
        base.machine_note = "SPEKTRUM: periyodik bileşen bulunamadı."
        return base

    # HARMONİK ÇÖZÜMÜ: dürtü-treni (haftada bir paylaşım) spektrumda temel
    # periyotla BİRLİKTE katlarına (7, 3.5, 2.33 gün...) eşit güç yayar. En
    # yüksek çubuğu "baskın periyot" sanmak temel ritmi kaçırmaktır. Kural:
    # en güçlü çubuğun en az yarısı güce sahip adaylar arasından EN UZUN
    # periyot (en düşük harmanik) temel kabul edilir. Akraba olmayan iki ayrı
    # ritimde bu kural işlemez — o zaman zaten en güçlü çubuk seçilir.
    max_power = max(p.power_share for p in all_peaks)
    related = [p for p in all_peaks if p.power_share >= 0.5 * max_power]
    dominant = min(related, key=lambda p: p.harmonic)

    peaks = sorted(all_peaks, key=lambda p: p.power_share, reverse=True)[: max(1, top_k)]
    if dominant not in peaks:
        peaks = [dominant] + peaks[: max(0, max(1, top_k) - 1)]
    base.available = True
    base.reason = None
    base.dominant_period_days = dominant.period_days
    base.dominant_harmonic = dominant.harmonic
    base.periodic_strength = dominant.power_share
    base.spectrum = [round(v, 8) for v in normalized]
    base.peaks = peaks
    base.machine_note = (
        f"SPEKTRUM: baskın periyot {dominant.period_days:g} gün "
        f"(h={dominant.harmonic}, güç payı {dominant.power_share:.2f}, {n} kova)."
    )
    return base


def to_payload(analysis: SpectralAnalysis) -> dict[str, Any]:
    """Telemetri/kanıt alanları için düz sözlük (kanıt şeması katıdır)."""
    return {
        "available": analysis.available,
        "reason": analysis.reason,
        "method": analysis.method,
        "sample_count": analysis.sample_count,
        "dominant_period_days": analysis.dominant_period_days,
        "dominant_harmonic": analysis.dominant_harmonic,
        "periodic_strength": analysis.periodic_strength,
        "peaks": [p.model_dump() for p in analysis.peaks],
    }
