"""Seyrek/ikili sinyalde ORAN düşüşü — "yavaş ölen ritüel" kaybolmasın.

Problem (gerçek, testle bulundu): ``ritual.obj.x`` ikili bir sinyaldir (var=1,
yok=0). Ritüel baseline penceresinin bir kısmında sürüp sonra ölürse baseline
merkezi 0.77, yayılımı 0.43 olur; yokluk (0.0) için z = 1.79 çıkar ve 2.0
eşiğinin ALTINDA kalır. Yani **yavaş ölen ritüel görünmez**. Örneklem başına
z-testi ikili olaylar için yanlış araçtır: 0/1 değerinin "yayılımı" payın
kendisinden türer, ölçüm hatası değildir.

Doğru araç: **pencere oranı**. Baseline'da p₀, karşılaştırmada p₁. İki oranın
farkı, örneklem büyüklüğüne duyarlı bir testle sınanır (havuzlanmış iki oran
z-testi; normal yaklaşım — sınırı yazılı).

Kurallar (hepsi testlidir):

    1. **Yalnız ikili sinyaller.** Değerler {0,1} değilse ``not_binary``;
       sürekli sinyale oran testi uygulamak sahte kesinlik olurdu.
    2. **Az örneklem "düşüş yok" DEĞİLDİR.** ``baseline_n < 20`` ya da
       ``comparison_n < 8`` ise ``insufficient_data``. Sessizce "stable"
       demek, ölçülmemişi ölçülmüş gibi göstermek olurdu.
    3. **Norm olmayan sinyalde düşüş aranmaz.** Baseline oranı 0.5'in altındaysa
       sinyal zaten seyrek; düşüşü "kayıp" saymak yanıltıcı → ``not_a_norm``.
    4. **Çift kapı**: hem etki (mutlak düşüş ≥ 0.30) hem istatistik (z ≤ -2.0).
       Tek başına biri yeterli değil — küçük örneklemde büyük düşüş, büyük
       örneklemde önemsiz düşüş sahte alarm üretirdi.
    5. **Yokluk ≠ 0**: bu modül yalnız ORAN karşılaştırır; "hiç gözlem yok"
       durumunu düşüş saymaz (n=0 → ``insufficient_data``).

Tüketici: ``agent_core.lifecycle.deviation_detector.detect_deviations``.
Test: ``tests/lifecycle/test_rare_event_decline.py``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Optional, Sequence

from agent_core.lifecycle.baseline_builder import SignalObservation, ensure_utc

__all__ = [
    "MIN_ABSOLUTE_DROP",
    "MIN_BASELINE_SAMPLES",
    "MIN_COMPARISON_SAMPLES",
    "MIN_BASELINE_RATE",
    "RATE_Z_THRESHOLD",
    "RateDecline",
    "assess_rate_decline",
    "two_proportion_z",
]

RateStatus = Literal["declined", "stable", "disappeared", "insufficient_data", "not_a_norm", "not_binary"]

#: Az örneklem sınırları (altında hüküm YOK).
MIN_BASELINE_SAMPLES = 20
MIN_COMPARISON_SAMPLES = 8
#: Bir sinyalin "norm" sayılması için baseline'daki asgari var olma oranı.
MIN_BASELINE_RATE = 0.5
#: Anlamlı sayılan en küçük mutlak oran düşüşü.
MIN_ABSOLUTE_DROP = 0.30
#: Havuzlanmış iki oran z-testi eşiği (tek yönlü düşüş).
RATE_Z_THRESHOLD = 2.0


@dataclass(frozen=True)
class RateDecline:
    """İki pencere oranının karşılaştırması — karar ve gerekçesi birlikte."""

    signal_id: str
    status: RateStatus
    baseline_rate: Optional[float]
    baseline_n: int
    comparison_rate: Optional[float]
    comparison_n: int
    absolute_drop: Optional[float]
    z: Optional[float]
    reason: str

    @property
    def is_decline(self) -> bool:
        return self.status in ("declined", "disappeared")

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "status": self.status,
            "baseline_rate": self.baseline_rate,
            "baseline_n": self.baseline_n,
            "comparison_rate": self.comparison_rate,
            "comparison_n": self.comparison_n,
            "absolute_drop": self.absolute_drop,
            "z": self.z,
            "reason": self.reason,
            "is_binary_rate_test": True,
        }


def _binary_values(values: Sequence[float]) -> Optional[list[float]]:
    """Değerlerin tamamı {0,1} ise listeyi döner; değilse ``None``."""
    out: list[float] = []
    for value in values:
        if not isinstance(value, (int, float)):
            return None
        number = float(value)
        if not math.isfinite(number) or number not in (0.0, 1.0):
            return None
        out.append(number)
    return out


def two_proportion_z(success_a: int, n_a: int, success_b: int, n_b: int) -> Optional[float]:
    """Havuzlanmış iki oran z'si: ``a`` eksi ``b``. Tanımsızsa ``None``.

    İşaret sözleşmesi: çağıran taraf ``a``yı KARŞILAŞTIRMA, ``b``yi BASELINE
    verir; böylece **düşüş negatif z** üretir ve eşik (`z ≤ -2`) sezgisel kalır.
    Ters sıralama sessiz bir işaret hatasıdır (testle kilitli).
    

    ``None`` "fark yok" demek DEĞİLDİR: iki pencere de tamamen aynıysa
    (0/0 ya da 1/1) zaten test edilecek fark yoktur; çağıran taraf bunu
    "ölçülemedi" olarak okur.
    """
    if n_a <= 0 or n_b <= 0:
        return None
    p_a = success_a / n_a
    p_b = success_b / n_b
    pooled = (success_a + success_b) / (n_a + n_b)
    variance = pooled * (1.0 - pooled) * (1.0 / n_a + 1.0 / n_b)
    if variance <= 0.0:
        return None
    return (p_a - p_b) / math.sqrt(variance)


def assess_rate_decline(
    signal_id: str,
    baseline_values: Sequence[float],
    comparison_values: Sequence[float],
) -> RateDecline:
    """İkili sinyalde pencere oranı karşılaştırması (deterministik)."""
    baseline = _binary_values(baseline_values)
    comparison = _binary_values(comparison_values)

    if baseline is None or comparison is None:
        return RateDecline(
            signal_id=signal_id,
            status="not_binary",
            baseline_rate=None,
            baseline_n=len(baseline_values),
            comparison_rate=None,
            comparison_n=len(comparison_values),
            absolute_drop=None,
            z=None,
            reason="değerler {0,1} değil; oran testi uygulanmaz",
        )

    n_base, n_cmp = len(baseline), len(comparison)
    if n_base < MIN_BASELINE_SAMPLES or n_cmp < MIN_COMPARISON_SAMPLES:
        return RateDecline(
            signal_id=signal_id,
            status="insufficient_data",
            baseline_rate=(sum(baseline) / n_base) if n_base else None,
            baseline_n=n_base,
            comparison_rate=(sum(comparison) / n_cmp) if n_cmp else None,
            comparison_n=n_cmp,
            absolute_drop=None,
            z=None,
            reason=(
                f"örneklem yetersiz (baseline {n_base} < {MIN_BASELINE_SAMPLES} veya "
                f"karşılaştırma {n_cmp} < {MIN_COMPARISON_SAMPLES}); düşüş iddiası üretilmedi"
            ),
        )

    base_success = int(sum(baseline))
    cmp_success = int(sum(comparison))
    base_rate = base_success / n_base
    cmp_rate = cmp_success / n_cmp
    drop = base_rate - cmp_rate
    # Düşüş NEGATİF z üretsin diye (karşılaştırma - baseline) sırası.
    z = two_proportion_z(cmp_success, n_cmp, base_success, n_base)

    if base_rate < MIN_BASELINE_RATE:
        return RateDecline(
            signal_id=signal_id,
            status="not_a_norm",
            baseline_rate=base_rate,
            baseline_n=n_base,
            comparison_rate=cmp_rate,
            comparison_n=n_cmp,
            absolute_drop=drop,
            z=z,
            reason=(
                f"baseline oranı {base_rate:.2f} < {MIN_BASELINE_RATE}: sinyal zaten seyrek, "
                "düşüş 'norm kaybı' sayılmaz"
            ),
        )

    if z is None:
        return RateDecline(
            signal_id=signal_id,
            status="insufficient_data",
            baseline_rate=base_rate,
            baseline_n=n_base,
            comparison_rate=cmp_rate,
            comparison_n=n_cmp,
            absolute_drop=drop,
            z=None,
            reason="havuzlanmış varyans sıfır: iki pencere de tamamen aynı, test tanımsız",
        )

    effect_gate = drop >= MIN_ABSOLUTE_DROP
    stat_gate = z <= -RATE_Z_THRESHOLD
    reason = (
        f"oran {base_rate:.2f} ({base_success}/{n_base}) → {cmp_rate:.2f} ({cmp_success}/{n_cmp}); "
        f"düşüş={drop:.2f} {'≥' if effect_gate else '<'} {MIN_ABSOLUTE_DROP:.2f}, "
        f"z={z:.2f} {'≤' if stat_gate else '>'} -{RATE_Z_THRESHOLD:.1f}"
    )
    if not (effect_gate and stat_gate):
        return RateDecline(
            signal_id=signal_id,
            status="stable",
            baseline_rate=base_rate,
            baseline_n=n_base,
            comparison_rate=cmp_rate,
            comparison_n=n_cmp,
            absolute_drop=drop,
            z=z,
            reason=reason + " → düşüş iddiası yok",
        )

    disappeared = cmp_success == 0 and base_rate >= 0.8
    return RateDecline(
        signal_id=signal_id,
        status="disappeared" if disappeared else "declined",
        baseline_rate=base_rate,
        baseline_n=n_base,
        comparison_rate=cmp_rate,
        comparison_n=n_cmp,
        absolute_drop=drop,
        z=z,
        reason=reason + (" → pencere boyunca hiç görülmedi" if disappeared else " → oran düşüşü"),
    )


def window_values(
    observations: Sequence[SignalObservation],
    signal_id: str,
    window_start: datetime,
    window_end: datetime,
) -> list[float]:
    """Bir sinyalin penceredeki değerleri (kronolojik)."""
    start, end = ensure_utc(window_start), ensure_utc(window_end)
    return [
        float(observation.value)
        for observation in observations
        if observation.signal_id == signal_id and start <= observation.timestamp <= end
    ]
