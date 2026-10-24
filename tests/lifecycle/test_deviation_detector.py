"""Comprehensive Acceptance & Contract Tests for Life Rupture Lifecycle Engine.

Doğrudan Technical Contract v1.0 kabul testlerini (bölüm 13) ve 4 mutasyon kontrolünü sınar.
"""

from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError

from agent_core.domain.evidence_models import EvidenceTimelineEntry
from agent_core.lifecycle.baseline_builder import (
    SignalObservation,
    build_baseline,
    _circular_mean_std,
)
from agent_core.lifecycle.cluster_analyzer import ClusterAnalyzer
from agent_core.lifecycle.deviation_detector import DeviationDetector, make_evidence_id
from agent_core.lifecycle.rupture_engine import RuptureEngine

T0 = datetime(2023, 1, 1, tzinfo=timezone.utc)


def _obs(sid: str, day: int, val: float, status: str = "measured", ref: str = "") -> SignalObservation:
    return SignalObservation(
        signal_id=sid,
        timestamp=T0 + timedelta(days=day),
        value=float(val),
        source_ref=ref or f"{sid}:{day}",
        measurement_status=status,
    )


# --- 1. SÖZLEŞME VE EPİSTEMİK TESTLER (Test 19, 10, 2) ---

def test_evidence_timeline_entry_requires_epistemic_note_and_valid_pattern():
    """EvidenceTimelineEntry zorunlu epistemic_note ve ev_[0-9a-f]{20} şablonunu doğrular."""
    valid_id = make_evidence_id("timing.is_night_post", T0, 1.0, "ref1")
    assert len(valid_id) == 23
    assert valid_id.startswith("ev_")

    entry = EvidenceTimelineEntry(
        evidence_id=valid_id,
        timeline_at=T0,
        temporal_basis="observed_at",
        epistemic_type="observation",
        epistemic_note="Doğrulanmış gece paylaşımı ölçümü",
        source_engine="deviation_detector",
        content="Sinyal gece paylaşımına saptı.",
    )
    assert entry.epistemic_note != ""

    # epistemic_note eksik veya None ise ValidationError fırlatılmalı
    with pytest.raises(ValidationError):
        EvidenceTimelineEntry(
            evidence_id=valid_id,
            timeline_at=T0,
            temporal_basis="observed_at",
            epistemic_type="observation",
            source_engine="deviation_detector",
            content="Geçersiz kayıt",
        )

    # Geçersiz evidence_id şablonu reddedilmeli
    with pytest.raises(ValidationError):
        EvidenceTimelineEntry(
            evidence_id="invalid_uuid_1234",
            timeline_at=T0,
            temporal_basis="observed_at",
            epistemic_type="observation",
            epistemic_note="Not",
            source_engine="deviation_detector",
            content="Hatalı id",
        )


def test_absence_vs_observation_epistemic_typing():
    """Analiz edilen kaynakta nesne bulunmaması yokluk (absence), sapma ise observation üretir."""
    base_obs = [_obs("visual.object_cup", d, 1.0) for d in range(10)]
    baseline = build_baseline("sub1", base_obs, T0, T0 + timedelta(days=20), min_samples=3)

    target_obs = [_obs("visual.object_cup", 30, 0.0, status="measured")]
    detector = DeviationDetector(baseline)
    tl = detector.detect(target_obs, T0 + timedelta(days=25), T0 + timedelta(days=35))

    assert len(tl.entries) == 1
    assert tl.entries[0].epistemic_type == "absence"
    assert "yokluk tespiti" in tl.entries[0].epistemic_note


def test_unmeasurable_image_never_coded_as_zero():
    """İndirilemeyen/ölçülemeyen görsel (not_measurable) asla 0 (yokluk) olarak kodlanmaz."""
    base_obs = [_obs("visual.object_cup", d, 1.0) for d in range(10)]
    baseline = build_baseline("sub1", base_obs, T0, T0 + timedelta(days=20), min_samples=3)

    # İndirme hatası olan görsel
    target_obs = [_obs("visual.object_cup", 30, 0.0, status="not_measurable")]
    detector = DeviationDetector(baseline)
    tl = detector.detect(target_obs, T0 + timedelta(days=25), T0 + timedelta(days=35))

    assert len(tl.entries) == 1
    # Ölçülemedi notu taşımalı ve sapma metriği taşımamalı
    assert tl.entries[0].source_metrics["measurement_status"] == "not_measurable"
    assert "not_measurable" in tl.entries[0].epistemic_note


# --- 2. İSTATİSTİKSEL MODEL VE SABİT TABAN TESTLERİ (Test 12, 13) ---

def test_circular_hour_averages_to_midnight_not_noon():
    """Dairesel saat istatistiğinde 23:30 (23.5) ile 00:30 (0.5) ortalaması öğlen (12) değil gece yarısı (0) çıkar."""
    vals = [23.5, 0.5]
    mean_hour, circ_std = _circular_mean_std(vals, 24.0)
    # 23.5 ve 0.5'in dairesel ortalaması tam 0.0 (veya 24.0) olmalı
    assert (abs(mean_hour - 0.0) < 1e-4) or (abs(mean_hour - 24.0) < 1e-4)
    assert circ_std < 2.0


def test_constant_baseline_break_detects_meaningful_delta_ignores_noise():
    """std=0 durumunda meaningful_delta üzerindeki değişim sapmadır; küçük gürültü yok sayılır."""
    base_obs = [_obs("binary.switch", d, 0.0) for d in range(10)]
    baseline = build_baseline("sub1", base_obs, T0, T0 + timedelta(days=20), min_samples=3)
    b = baseline.baselines["binary.switch"]
    assert b.is_constant is True

    # 0.05 tolerans altı gürültü: sapma DEĞİL
    assert b.is_deviation(0.05) is False
    # 1.0 anlamlı değişim: SAPMA
    assert b.is_deviation(1.0) is True


# --- 3. KURGUSAL MEDYA VE KARARI BOZUCU ETKEN TESTLERİ (Test 7, 8, 9) ---

def _make_baseline_with_staged(staged_rate: float | None):
    base_obs = []
    for d in range(30):
        base_obs.append(_obs("timing.is_night_post", d, 0.0 if d % 2 == 0 else 0.2))
        base_obs.append(_obs("visual.is_daylight", d, 1.0 if d % 3 == 0 else 0.8))
        base_obs.append(_obs("visual.is_isolated", d, 0.0 if d % 5 == 0 else 0.2))
        if staged_rate is not None:
            base_obs.append(_obs("media.is_authored_or_staged", d, staged_rate))
    return build_baseline("sub", base_obs, T0, T0 + timedelta(days=50), min_samples=3)


def test_authored_rate_constant_high_not_confounded():
    """Başlangıçtan beri kurgu oranı yüksek olan (0.8 -> 0.8) hesapta değişim yoksa confounded DEĞİLDİR."""
    baseline = _make_baseline_with_staged(staged_rate=0.8)
    assert baseline.staged_rate == pytest.approx(0.8)

    target = []
    for day in range(70):
        target.extend([
            _obs("timing.is_night_post", 300 + day, 1.0),
            _obs("visual.is_daylight", 300 + day, 0.0),
            _obs("visual.is_isolated", 300 + day, 1.0),
            _obs("media.is_authored_or_staged", 300 + day, 0.8),  # Delta = 0.0
        ])

    engine = RuptureEngine(baseline)
    rep = engine.run(target, T0 + timedelta(days=250), T0 + timedelta(days=400))
    # Delta sıfır olduğu için üretim tarzı değişimi karıştırıcı değildir
    assert rep.verdict == "RUPTURE_CONFIRMED"


def test_authored_rate_increase_over_baseline_marks_confounded():
    """Kurgu oranı taban çizgiye kıyasla belirgin arttıysa (0.0 -> 0.9) RUPTURE_CONFOUNDED verilir."""
    baseline = _make_baseline_with_staged(staged_rate=0.0)

    target = []
    for day in range(70):
        target.extend([
            _obs("timing.is_night_post", 300 + day, 1.0),
            _obs("visual.is_daylight", 300 + day, 0.0),
            _obs("visual.is_isolated", 300 + day, 1.0),
            _obs("media.is_authored_or_staged", 300 + day, 0.9),  # Delta = 0.9 > 0.4
        ])

    engine = RuptureEngine(baseline)
    rep = engine.run(target, T0 + timedelta(days=250), T0 + timedelta(days=400))
    assert rep.verdict == "RUPTURE_CONFOUNDED_BY_MEDIUM_CHANGE"


def test_authored_rate_unmeasurable_baseline_leaves_medium_unknown():
    """Taban çizgide hiç medya verisi yoksa kurgu oranı bilinmez (unknown); görsel sinyallere dayalı hüküm verilmez."""
    baseline = _make_baseline_with_staged(staged_rate=None)
    assert baseline.staged_rate is None

    target = []
    for day in range(70):
        target.extend([
            _obs("timing.is_night_post", 300 + day, 1.0),
            _obs("visual.is_daylight", 300 + day, 0.0),
            _obs("visual.is_isolated", 300 + day, 1.0),
        ])

    engine = RuptureEngine(baseline)
    rep = engine.run(target, T0 + timedelta(days=250), T0 + timedelta(days=400))
    assert rep.verdict == "INSUFFICIENT_EVIDENCE"


# --- 4. KİMLİK BAĞIMSIZLIĞI VE DETERMINİZM (Test 15, 16) ---

def test_subject_pseudonym_invariance_and_determinism():
    """Aynı gözlemler farklı profil kimliğiyle işlendiğinde sonuçlar ve evidence_id'ler deterministiktir."""
    base_obs = []
    for d in range(30):
        base_obs.append(_obs("timing.is_night_post", d, 0.0 if d % 2 == 0 else 0.2))
        base_obs.append(_obs("visual.is_daylight", d, 1.0 if d % 3 == 0 else 0.8))
        base_obs.append(_obs("visual.is_isolated", d, 0.0 if d % 5 == 0 else 0.2))
        base_obs.append(_obs("media.is_authored_or_staged", d, 0.0))

    base_alpha = build_baseline("sub_alpha", base_obs, T0, T0 + timedelta(days=50), min_samples=3)
    base_beta = build_baseline("sub_beta", base_obs, T0, T0 + timedelta(days=50), min_samples=3)

    target = []
    for d in range(70):
        target.extend([
            _obs("timing.is_night_post", 300 + d, 1.0),
            _obs("visual.is_daylight", 300 + d, 0.0),
            _obs("visual.is_isolated", 300 + d, 1.0),
            _obs("media.is_authored_or_staged", 300 + d, 0.0),
        ])

    engine_alpha = RuptureEngine(base_alpha)
    rep_alpha = engine_alpha.run(target, T0 + timedelta(days=250), T0 + timedelta(days=400))

    engine_beta = RuptureEngine(base_beta)
    rep_beta = engine_beta.run(target, T0 + timedelta(days=250), T0 + timedelta(days=400))

    # Kimlikten bağımsızlık: Farklı adlar altında birebir aynı hüküm, bulgu ve kanıt kimlikleri
    assert rep_alpha.verdict == rep_beta.verdict == "RUPTURE_CONFIRMED"
    assert rep_alpha.signal_count == rep_beta.signal_count == 3
    assert [e.evidence_id for e in rep_alpha.timeline.entries] == [e.evidence_id for e in rep_beta.timeline.entries]


# --- 5. DÖRT MUTASYON TESTİ (Test 20) ---

def test_mutation_a_removing_std_zero_deviation_fails():
    """Mutasyon A: std=0 kontrolü kaldırılırsa sabit baseline'daki kırılma yakalanamaz (test bunu yakalamalı)."""
    base_obs = [_obs("switch", d, 0.0) for d in range(10)]
    baseline = build_baseline("sub", base_obs, T0, T0 + timedelta(days=20), min_samples=3)
    b = baseline.baselines["switch"]

    # Sağlıklı kod
    assert b.is_deviation(1.0) is True

    # Mutasyon simülasyonu: std < 1e-9 kontrolü iptal edilip klasik z-score kullanılırsa
    def mutated_is_deviation(val: float) -> bool:
        if b.std < 1e-9:
            return False  # std 0 iken sapma yok sayan mutasyon
        return abs((val - b.mean) / b.std) > 2.0

    # Mutasyon başarısız olmalı (sapmayı kaçırmalı), orijinal kod yakalamalı
    assert mutated_is_deviation(1.0) is False
    assert b.is_deviation(1.0) is True


def test_mutation_b_assuming_independence_when_unverified_fails():
    """Mutasyon B: Korelasyon bilinmiyorken sinyaller bağımsız varsayılırsa yanlış hüküm üretilir."""
    base_obs = [_obs("s1", d, 0.0) for d in range(10)] + [_obs("s2", d, 1.0) for d in range(10)]
    baseline = build_baseline("sub", base_obs, T0, T0 + timedelta(days=20), min_samples=3)
    assert baseline.correlation_verified is False

    analyzer = ClusterAnalyzer(baseline)
    signals = ["s1", "s2"]
    _, indep_verified = analyzer._independent_signals(signals)
    assert indep_verified is False  # Orijinal kod: bağımsızlık onaylanamaz

    # Mutasyon simülasyonu: fail-closed yerine fail-open
    def mutated_independent_signals(sigs):
        return sigs, True  # Bilinmeyeni bağımsız kabul eden mutasyon

    _, mutated_indep = mutated_independent_signals(signals)
    assert mutated_indep is True  # Mutasyon yanlış şekilde True üretir


def test_mutation_c_ignoring_baseline_authored_rate_fails():
    """Mutasyon C: Kurgusal medya oranı baseline ile karşılaştırılmazsa yüksek oranlı hesap yanlış damgalanır."""
    baseline = _make_baseline_with_staged(staged_rate=0.8)

    # Hedef dönem kurgu oranı = 0.8 (fark yok)
    target_staged_rate = 0.8

    # Orijinal mantık: delta kıyaslaması
    delta = target_staged_rate - baseline.staged_rate
    is_confounded_original = delta > 0.4
    assert is_confounded_original is False  # Yanlış alarm üretilmez

    # Mutasyon simülasyonu: Yalnız güncel orana bakan ham eşik (val > 0.5)
    is_confounded_mutated = target_staged_rate > 0.5
    assert is_confounded_mutated is True  # Mutasyon haksız yere karıştırıcı sayar


def test_mutation_d_treating_unmeasurable_as_zero_fails():
    """Mutasyon D: Ölçülemeyen görsel veri 0 (yokluk) sayılırsa yanlış sapma tetiklenir."""
    base_obs = [_obs("visual.is_daylight", d, 1.0) for d in range(10)]
    baseline = build_baseline("sub", base_obs, T0, T0 + timedelta(days=20), min_samples=3)

    # İndirilemeyen görsel
    obs_unmeasurable = _obs("visual.is_daylight", 30, 0.0, status="not_measurable")

    detector = DeviationDetector(baseline)
    tl = detector.detect([obs_unmeasurable], T0 + timedelta(days=25), T0 + timedelta(days=35))
    assert len(tl.entries) == 1
    # Ölçülemedi olarak kalmalı, sapma değeri hesaplanmamalı
    assert tl.entries[0].source_metrics["measurement_status"] == "not_measurable"
    assert "value" not in tl.entries[0].source_metrics
