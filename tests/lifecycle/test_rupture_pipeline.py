from datetime import datetime, timedelta, timezone

from agent_core.lifecycle.baseline_builder import (
    SignalObservation,
    build_baseline,
)
from agent_core.lifecycle.observation_adapter import ObservationAdapter
from agent_core.lifecycle.rupture_engine import RuptureEngine

T0 = datetime(2022, 1, 1, tzinfo=timezone.utc)


def _obs(sid: str, day: int, val: float) -> SignalObservation:
    return SignalObservation(
        signal_id=sid,
        timestamp=T0 + timedelta(days=day),
        value=float(val),
        source_ref=f"{sid}:{day}",
    )


def _make_independent_baseline(staged_rate: float = 0.0):
    # 30 gün boyunca aralarında doğrusal bağ olmayan (aralarında asal periyotlu) bağımsız sinyaller
    base_obs = []
    for d in range(30):
        # timing: periyot 2
        base_obs.append(_obs("timing.is_night_post", d, 0.0 if d % 2 == 0 else 0.2))
        # daylight: periyot 3
        base_obs.append(_obs("visual.is_daylight", d, 1.0 if d % 3 == 0 else 0.8))
        # isolated: periyot 5
        base_obs.append(_obs("visual.is_isolated", d, 0.0 if d % 5 == 0 else 0.2))
        # staged
        base_obs.append(_obs("media.is_authored_or_staged", d, staged_rate))

    return build_baseline(
        subject_id="subject_alpha",
        observations=base_obs,
        baseline_start=T0,
        baseline_end=T0 + timedelta(days=50),
        min_samples=3,
    )


def test_zero_variance_std_zero_deviation():
    """std=0 durumunda sabit değerden sapmanın doğru tetiklendiğini test eder."""
    base_obs = [_obs("timing.is_night_post", d, 0.0) for d in range(10)]
    base = build_baseline("sub", base_obs, T0, T0 + timedelta(days=20), min_samples=3)
    night_b = base.baselines["timing.is_night_post"]
    assert night_b.is_constant is True
    assert night_b.is_deviation(0.0) is False
    assert night_b.is_deviation(1.0) is True


def test_three_independent_signals_persistent_triggers_rupture():
    """3+ bağımsız sinyal 60+ gün düzenli süreklilikle saptığında RUPTURE_CONFIRMED tetiklenir."""
    baseline = _make_independent_baseline(staged_rate=0.0)
    assert baseline.correlation_verified is True

    # 300. günden 370. güne kadar düzenli aralıklarla gözlem (tüm alt dilimlere dağılmış)
    target = []
    for day in range(70):
        target.extend([
            _obs("timing.is_night_post", 300 + day, 1.0),
            _obs("visual.is_daylight", 300 + day, 0.0),
            _obs("visual.is_isolated", 300 + day, 1.0),
            _obs("media.is_authored_or_staged", 300 + day, 0.0), # Staged oranı artmamış
        ])

    engine = RuptureEngine(baseline)
    rep = engine.run(
        observations=target,
        target_start=T0 + timedelta(days=250),
        target_end=T0 + timedelta(days=400),
    )

    assert rep.verdict == "RUPTURE_CONFIRMED"
    assert rep.signal_count >= 3
    assert rep.persistence_days >= 60
    assert rep.continuity_ratio == 1.0
    assert len(rep.findings) >= 3


def test_unverified_correlation_fails_closed():
    """Korelasyon ölçülemiyorsa (tüm sinyaller sabit, varyans yok), sistem bağımsızlık varsaymaz (fail-closed)."""
    base_obs = [
        _obs("timing.is_night_post", d, 0.0) for d in range(10)
    ] + [
        _obs("visual.is_daylight", d, 1.0) for d in range(10)
    ]
    baseline = build_baseline("sub", base_obs, T0, T0 + timedelta(days=20), min_samples=3)
    assert baseline.correlation_verified is False

    target = []
    for day in range(70):
        target.extend([
            _obs("timing.is_night_post", 300 + day, 1.0),
            _obs("visual.is_daylight", 300 + day, 0.0),
        ])

    engine = RuptureEngine(baseline)
    rep = engine.run(
        observations=target,
        target_start=T0 + timedelta(days=250),
        target_end=T0 + timedelta(days=400),
    )

    assert rep.verdict == "INSUFFICIENT_EVIDENCE"


def test_discontinuous_window_is_insufficient():
    """Yalnızca iki uçta görülen ve aralığı boş kalan sapmalar süreklilik şartını sağlamaz."""
    baseline = _make_independent_baseline()

    # Yalnızca 300. gün ve 365. günde gözlem var, 60 gün boyunca arada HİÇBİR ŞEY yok
    target = [
        _obs("timing.is_night_post", 300, 1.0),
        _obs("visual.is_daylight", 300, 0.0),
        _obs("visual.is_isolated", 300, 1.0),
        _obs("timing.is_night_post", 365, 1.0),
        _obs("visual.is_daylight", 365, 0.0),
        _obs("visual.is_isolated", 365, 1.0),
    ]

    engine = RuptureEngine(baseline)
    rep = engine.run(
        observations=target,
        target_start=T0 + timedelta(days=250),
        target_end=T0 + timedelta(days=400),
    )
    assert rep.verdict == "INSUFFICIENT_EVIDENCE"


def test_medium_change_marks_confounded():
    """Hedef dönemde kurgusal görsel üretimi (staged) baseline'a göre belirgin arttıysa CONFOUNDED uyarısı verilir."""
    baseline = _make_independent_baseline(staged_rate=0.0)

    target = []
    for day in range(70):
        target.extend([
            _obs("timing.is_night_post", 300 + day, 1.0),
            _obs("visual.is_daylight", 300 + day, 0.0),
            _obs("visual.is_isolated", 300 + day, 1.0),
            _obs("media.is_authored_or_staged", 300 + day, 1.0), # Staged oranı 0.0 -> 1.0 oldu
        ])

    engine = RuptureEngine(baseline)
    rep = engine.run(
        observations=target,
        target_start=T0 + timedelta(days=250),
        target_end=T0 + timedelta(days=400),
    )

    assert rep.verdict == "RUPTURE_CONFOUNDED_BY_MEDIUM_CHANGE"
    assert len(rep.confounded_axes) > 0


def test_structured_findings_contain_required_fields():
    """Raporlanan her bulgunun yön, gözlem sayısı ve kaynak referansı içerdiğini doğrular."""
    baseline = _make_independent_baseline()

    target = []
    for day in range(70):
        target.extend([
            _obs("timing.is_night_post", 300 + day, 1.0),
            _obs("visual.is_daylight", 300 + day, 0.0),
            _obs("visual.is_isolated", 300 + day, 1.0),
        ])

    engine = RuptureEngine(baseline)
    rep = engine.run(target, T0 + timedelta(days=250), T0 + timedelta(days=400))

    assert len(rep.findings) >= 3
    for f in rep.findings:
        assert f.signal_id in ["timing.is_night_post", "visual.is_daylight", "visual.is_isolated"]
        assert f.direction in ["increase", "decrease", "divergence"]
        assert f.observation_count >= 60
        assert len(f.source_refs) > 0
        assert f.measurement_status == "measured"


def test_observation_adapter_extracts_cleanly():
    """ObservationAdapter'ın ham veriyi doğru sinyallere dönüştürdüğünü test eder."""
    raw = {
        "post_times": ["2022-01-12T14:30:00Z", "2022-01-15T02:15:00Z"],
        "posts": ["Gündüz vakti kahve içildi.", "Gece yalnızlık."],
        "posts_with_media": [
            {
                "post_id": "m1",
                "timestamp": "2022-01-12T14:30:00Z",
                "is_daylight": True,
                "is_isolated": False,
            }
        ]
    }
    adapter = ObservationAdapter()
    obs = adapter.extract(raw)
    assert len(obs) >= 6
    signal_ids = {o.signal_id for o in obs}
    assert "timing.is_night_post" in signal_ids
    assert "text.word_count" in signal_ids
    assert "visual.is_daylight" in signal_ids
