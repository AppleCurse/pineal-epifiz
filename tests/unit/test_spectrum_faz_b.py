"""FAZ B · B6 — GERÇEK SPEKTRAL ANALİZ (FFT) sözleşme testleri.

Kilitlenen iddialar:
1. `FrequencyReport.dominant_period_days` artık declared-boş bir alan değil;
   GERÇEK ölçümle doluyor (eski durum: hiç yazılmıyordu).
2. Bilinen periyotlu serilerde periyot DOĞRU ölçülür (model değil, FFT).
3. Yetersiz/sabit seride periyot UYDURULMAZ (None + makine-okunur sebep).
4. Harmonik tuzağı: haftalık dürtü treninde 2.33/3.5 gün değil **7 gün** temel
   periyot olarak raporlanır.
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta, timezone

import pytest

from agent_core.engines.frequency_engine import FrequencyEngine
from agent_core.engines.spectrum import (
    MIN_SAMPLES,
    SpectralAnalysis,
    analyze_spectrum,
    to_payload,
)


def _sine(period: float, n: int = 32, amplitude: float = 1.0) -> list[float]:
    return [2.0 + amplitude * math.sin(2 * math.pi * i / period) for i in range(n)]


def _spike_train(period_days: int, days: int = 28, spike: int = 5) -> dict:
    """Belirlenen günde bir yoğunlaşan gönderi serisi (haftalık ritim gibi)."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    posts: list[str] = []
    times: list[str] = []
    meta: list[dict] = []
    for day in range(days):
        count = spike if day % period_days == 0 else 1
        for _ in range(count):
            posts.append("gönderi")
            times.append((base + timedelta(days=day)).isoformat())
            meta.append({"like_count": 10, "comment_count": 1})
    return {"target_profile": {"posts": posts, "post_times": times, "posts_meta": meta}}


# ------------------------------------------------------------ 1 · ölçüm doğru
def test_recovers_known_sine_period():
    for period in (4.0, 8.0, 16.0):
        analysis = analyze_spectrum(_sine(period), bucket_hours=24)
        assert analysis.available is True
        assert analysis.dominant_period_days == pytest.approx(period, abs=0.05)


def test_recovers_weekly_rhythm_from_post_series():
    """Haftalık ritim: temel periyot 7 gün (harmonik tuzağına düşmez)."""
    report = asyncio.run(FrequencyEngine().analyze(_spike_train(7)))
    assert report.dominant_period_days is not None
    assert report.dominant_period_days == pytest.approx(7.0, abs=0.3)
    assert report.spectral_method == "fft_periodogram_hann"
    assert report.periodic_strength is not None
    assert "baskın periyot" in report.machine_note


def test_harmonic_trap_resolves_to_fundamental():
    """Dürtü treni katlarına eşit güç yayar; en uzun periyot temeldir."""
    analysis = analyze_spectrum(_sine(1.0) if False else _spike_series_energy(), bucket_hours=24)
    assert analysis.available is True
    # 2.33 veya 3.5 gün DEĞİL, 7 gün.
    assert analysis.dominant_period_days == pytest.approx(7.0, abs=0.3)
    assert analysis.dominant_harmonic == 4  # 28 kova / 7 gün


def _spike_series_energy() -> list[float]:
    report = asyncio.run(FrequencyEngine().analyze(_spike_train(7)))
    return [s.energy for s in report.samples]


# ---------------------------------------------------- 2 · dürüstlük (uydurma yok)
def test_insufficient_samples_claims_no_period():
    analysis = analyze_spectrum([1.0, 2.0, 3.0])
    assert analysis.available is False
    assert analysis.reason == "insufficient_samples"
    assert analysis.dominant_period_days is None
    assert MIN_SAMPLES == 8


def test_flat_signal_claims_no_period():
    analysis = analyze_spectrum([1.0] * 16)
    assert analysis.available is False
    assert analysis.reason == "flat_signal"
    assert analysis.dominant_period_days is None


def test_empty_series_claims_no_period():
    analysis = analyze_spectrum([])
    assert analysis.available is False
    assert analysis.dominant_period_days is None
    assert analysis.sample_count == 0


def test_frequency_report_leaves_period_none_when_unmeasurable():
    """Kova sayısı motorun eşiğini geçer ama spektrum için YETERSİZ kalırsa
    rapor periyot UYDURMAZ: alan None + makine-okunur sebep.
    """
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    data = {
        "target_profile": {
            "posts": ["a"] * 6,
            "post_times": [
                (base + timedelta(days=d)).isoformat() for d in range(6)
            ],
            "posts_meta": [],
        }
    }
    report = asyncio.run(FrequencyEngine().analyze(data))
    assert len(report.samples) == 6  # motor eşiğini (4) geçti
    assert report.dominant_period_days is None
    assert report.spectral_reason == "insufficient_samples"
    assert "periyot ölçülemedi" in report.machine_note


def test_report_without_timestamps_never_invents_spectrum():
    report = asyncio.run(FrequencyEngine().analyze({"target_profile": {"posts": ["a"]}}))
    assert report.dominant_period_days is None
    assert report.spectrum == []


# ------------------------------------------------------- 3 · spektrum bütünlüğü
def test_spectrum_shape_excludes_dc_and_normalizes():
    analysis = analyze_spectrum(_sine(8.0, n=32))
    # DC ve Nyquist hariç: n=32 -> rfft 17 çubuk - DC - Nyquist = 15
    assert len(analysis.spectrum) == 15
    assert sum(analysis.spectrum) == pytest.approx(1.0, abs=1e-6)  # normalize
    assert min(analysis.spectrum) >= 0.0


def test_peaks_are_sorted_and_bounded():
    analysis = analyze_spectrum(_sine(5.0, n=32), top_k=3)
    assert len(analysis.peaks) <= 3
    assert all(0.0 <= p.power_share <= 1.0 for p in analysis.peaks)
    shares = [p.power_share for p in analysis.peaks]
    assert shares == sorted(shares, reverse=True) or analysis.peaks[0].harmonic == min(
        p.harmonic for p in analysis.peaks
    )


def test_to_payload_is_json_ready():
    payload = to_payload(analyze_spectrum(_sine(6.0, n=32)))
    assert payload["available"] is True
    assert isinstance(payload["dominant_period_days"], float)
    assert isinstance(payload["peaks"], list)


def test_analysis_model_rejects_unknown_fields():
    with pytest.raises(Exception):
        SpectralAnalysis(available=False, uydurma_alan=1)  # type: ignore[call-arg]
