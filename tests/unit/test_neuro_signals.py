"""Nöro sinyal türetici (`agent_core.services.neuro_signals`) — kaynak hukuku testleri.

Kural: motor ölçümü eksikse NeuroMetrics Üretilmez. Bu dosyada hiçbir sabit
yedek değer (0.55 / 0.50 / …) meşru değildir; eksik ölçüm ``None`` döndürür.
"""

from __future__ import annotations

from agent_core.services.neuro_signals import neuro_inputs_from_engines


def _depth(verdict="ok", confidence=0.8, rpi=0.3):
    return {
        "verdict": verdict,
        "confidence": confidence,
        "reaction_formation_index": rpi,
    }


def _timing(night_share=0.4):
    return {"night_share": night_share, "peak_hour": "23:00"}


def _audit(engagement_rate=5.0):
    return {"engagement_rate": engagement_rate, "data_completeness": 0.7}


def test_all_engines_measured_returns_normalized_inputs():
    out = neuro_inputs_from_engines(_depth(), _timing(), _audit(5.0))
    assert out is not None
    assert out["dopamine"] == 0.8
    assert out["serotonin"] == 0.5  # yüzde puanı → 0..1
    assert out["cortisol"] == 0.3
    assert out["oxytocin"] == 0.4
    for v in out.values():
        assert 0.0 <= v <= 1.0


def test_missing_engagement_rate_yields_no_metrics_not_a_constant():
    # GİZLİ ETKİLEŞİM (like'lar yok) → engagement_rate None → metrics YOK.
    assert neuro_inputs_from_engines(_depth(), _timing(), _audit(None)) is None


def test_depth_without_ok_verdict_counts_as_unmeasured():
    for verdict in ("no_evidence", "HOLDOUT", "", None):
        assert neuro_inputs_from_engines(_depth(verdict=verdict), _timing(), _audit()) is None


def test_missing_timing_counts_as_unmeasured():
    assert neuro_inputs_from_engines(_depth(), None, _audit()) is None
    assert neuro_inputs_from_engines(_depth(), {"night_share": None}, _audit()) is None
    # Aralık dışı değer: ölçüm değil → reddet
    assert neuro_inputs_from_engines(_depth(), _timing(night_share=1.5), _audit()) is None


def test_out_of_range_engagement_is_clamped_not_fabricated():
    out = neuro_inputs_from_engines(_depth(), _timing(), _audit(25.0))
    assert out is not None
    assert out["serotonin"] == 1.0
    out = neuro_inputs_from_engines(_depth(), _timing(), _audit(-3.0))
    assert out is not None
    assert out["serotonin"] == 0.0


def test_non_finite_and_bool_values_are_not_measurements():
    nan = float("nan")
    inf = float("inf")
    assert neuro_inputs_from_engines(_depth(confidence=nan), _timing(), _audit()) is None
    assert neuro_inputs_from_engines(_depth(confidence=inf), _timing(), _audit()) is None
    # bool sayı değildir — ölçüm olarak kabul edilmez
    assert neuro_inputs_from_engines(_depth(confidence=True), _timing(), _audit()) is None


def test_partial_engine_presence_is_never_backfilled_with_constants():
    # Yalnız 3/4 motor varsa bile sonuç None'dur (sessiz sabit yok).
    assert neuro_inputs_from_engines(_depth(), _timing(), None) is None
    assert neuro_inputs_from_engines(None, _timing(), _audit()) is None
