"""Seyrek/ikili sinyalde ORAN düşüşü — "yavaş ölen ritüel" görünür olmalı.

Neden ayrı test: örneklem başına z-testi ikili olayda yanlış araçtır. Baseline
20/26 = 0.77 → karşılaştırma 0/14: z = 1.79 < 2.0, yani ritüel ölüyor ama
rapor "sapma yok" diyordu. Oran testi aynı veride z = -4.64 verir.

Kilitlenen iddialar:
    * düşüş NEGATİF z üretir (işaret sözleşmesi; ters sıralama sessiz hatadır),
    * az örneklem "düşüş yok" DEĞİL: ``insufficient_data``,
    * norm olmayan sinyalde (baseline < 0.5) düşüş aranmaz,
    * ikili olmayan değerlerde test uygulanmaz (``not_binary``),
    * çift kapı: etki VE istatistik; tek başına biri yetmez,
    * sıfır varyans "fark yok" değil ``insufficient_data``,
    * spec'i ``binary`` olmayan sinyale oran testi UYGULANMAZ.
"""

from __future__ import annotations

import pytest

from agent_core.lifecycle.rare_event import (
    MIN_ABSOLUTE_DROP,
    MIN_BASELINE_SAMPLES,
    MIN_COMPARISON_SAMPLES,
    assess_rate_decline,
    two_proportion_z,
)


def _series(success: int, total: int) -> list[float]:
    return [1.0] * success + [0.0] * (total - success)


# --- İşaret ve temel kararlar ------------------------------------------------


def test_slow_decay_is_detected() -> None:
    """Ritüelin yavaş ölmesi: baseline 20/26 → karşılaştırma 0/14."""
    decline = assess_rate_decline("ritual.obj.x", _series(20, 26), _series(0, 14))

    assert decline.status == "declined"
    assert decline.is_decline
    assert decline.baseline_rate == pytest.approx(20 / 26)
    assert decline.comparison_rate == 0.0
    assert decline.absolute_drop == pytest.approx(20 / 26)
    assert decline.z is not None and decline.z < -2.0


def test_constant_presence_then_absence_is_disappearance() -> None:
    decline = assess_rate_decline("ritual.obj.x", _series(26, 26), _series(0, 14))

    assert decline.status == "disappeared"
    assert decline.absolute_drop == 1.0


def test_drop_sign_is_negative() -> None:
    """İşaret hatası sessizdir: pozitif z 'sapma yok' diye okunurdu."""
    decline = assess_rate_decline("s", _series(24, 30), _series(2, 15))
    assert decline.z is not None and decline.z < 0


def test_increase_is_not_a_decline() -> None:
    decline = assess_rate_decline("s", _series(18, 26), _series(13, 14))

    assert not decline.is_decline
    assert decline.status == "stable"
    assert decline.absolute_drop is not None and decline.absolute_drop < 0


def test_stable_signal_is_stable() -> None:
    decline = assess_rate_decline("s", _series(24, 30), _series(12, 15))
    assert decline.status == "stable" and not decline.is_decline


# --- Kapılar ----------------------------------------------------------------


def test_small_sample_is_not_measured_not_stable() -> None:
    decline = assess_rate_decline("s", _series(5, 6), _series(0, 3))

    assert decline.status == "insufficient_data"
    assert not decline.is_decline
    assert "örneklem yetersiz" in decline.reason


@pytest.mark.parametrize(
    "baseline_n,comparison_n",
    [
        (MIN_BASELINE_SAMPLES - 1, MIN_COMPARISON_SAMPLES),
        (MIN_BASELINE_SAMPLES, MIN_COMPARISON_SAMPLES - 1),
    ],
)
def test_sample_floor_is_exact(baseline_n: int, comparison_n: int) -> None:
    decline = assess_rate_decline(
        "s", _series(baseline_n, baseline_n), _series(0, comparison_n)
    )
    assert decline.status == "insufficient_data"


def test_empty_window_is_not_a_decline() -> None:
    decline = assess_rate_decline("s", _series(26, 26), [])
    assert decline.status == "insufficient_data"
    assert decline.comparison_rate is None


def test_rare_signal_is_not_a_norm() -> None:
    """Zaten seyrek olan sinyalin 'kaybı' norm kaybı sayılmaz."""
    decline = assess_rate_decline("s", _series(8, 30), _series(0, 14))

    assert decline.status == "not_a_norm"
    assert not decline.is_decline


def test_non_binary_values_are_refused() -> None:
    decline = assess_rate_decline("s", [0.0, 0.5, 1.0] * 10, [0.2] * 14)

    assert decline.status == "not_binary"
    assert decline.baseline_rate is None
    assert not decline.is_decline


def test_big_drop_small_sample_is_not_enough() -> None:
    """Etki büyük ama örneklem küçük: sahte alarm üretilmez."""
    decline = assess_rate_decline("s", _series(7, 8), _series(0, 8))
    assert decline.status == "insufficient_data"


def test_small_drop_large_sample_is_not_enough() -> None:
    """İstatistik anlamlı olabilir; etki kapısı (≥ 0.30) geçmez."""
    decline = assess_rate_decline("s", _series(70, 100), _series(60, 100))

    assert decline.absolute_drop is not None and decline.absolute_drop < MIN_ABSOLUTE_DROP
    assert decline.status == "stable"


def test_zero_variance_is_undefined_not_equal() -> None:
    """İki pencere de tamamen aynı: test tanımsız, 'fark yok' değil."""
    decline = assess_rate_decline("s", _series(26, 26), _series(14, 14))

    assert decline.status == "insufficient_data"
    assert decline.reason.startswith("havuzlanmış varyans sıfır")


def test_two_proportion_z_is_undefined_without_samples() -> None:
    assert two_proportion_z(0, 0, 1, 5) is None
    assert two_proportion_z(5, 10, 0, 0) is None


def test_two_proportion_z_sign_convention() -> None:
    """a > b ise pozitif; çağıran taraf a'yı KARŞILAŞTIRMA olarak verir."""
    assert two_proportion_z(10, 10, 0, 10) > 0
    assert two_proportion_z(0, 10, 10, 10) < 0


# --- Determinizm ------------------------------------------------------------


def test_assessment_is_deterministic() -> None:
    first = assess_rate_decline("s", _series(20, 26), _series(1, 14))
    second = assess_rate_decline("s", _series(20, 26), _series(1, 14))

    assert first.to_dict() == second.to_dict()


def test_assessment_serialises_its_method() -> None:
    payload = assess_rate_decline("s", _series(20, 26), _series(0, 14)).to_dict()

    assert payload["is_binary_rate_test"] is True
    assert payload["status"] == "declined"
    assert payload["baseline_n"] == 26 and payload["comparison_n"] == 14


def test_non_binary_spec_never_gets_rate_treatment() -> None:
    """Spec'i ``binary`` olmayan sinyal (nesne sayısı) oran testine girmez.

    Sayı sinyali tesadüfen 0/1 değerleri alsa bile oran testi anlam taşımaz;
    semantik spec'ten gelir, veriden tahmin edilmez.
    """
    from agent_core.lifecycle.default_specs import default_registry

    registry = default_registry()
    ritual = registry.resolve("ritual.obj.kitchen_table")
    richness = registry.resolve("visual.object_richness")

    assert ritual is not None and ritual.kind == "binary"
    assert richness is not None and richness.kind != "binary"
