"""Mutasyon testleri — "testler gerçekten ısırıyor mu?" (sözleşme #20).

Bir testin var olması, onun kusuru yakaladığını göstermez. Burada dört davranış
mutasyonu bilerek enjekte edilir ve İLGİLİ değişmezin kırıldığı gösterilir:

    (a) std=0 sapma kontrolünü kaldırma,
    (b) korelasyon yokken bağımsızlığı true yapma,
    (c) authored baseline karşılaştırmasını kaldırma,
    (d) ölçülemez görseli sıfır sayma.

Beşinci kontrol STATİKTİR: kodda geçen sinyal adı ``default_specs`` içinde
yoksa (ör. ``media.is_authored`` yazımı) test kırmızıya döner — sinyal adı
kayması sessizce baseline dışında kalamaz.
"""

from __future__ import annotations

import ast
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent_core.lifecycle.baseline_builder import (
    BaselineProfile,
    DeviationResult,
    SignalBaseline,
    SignalObservation,
)
from agent_core.lifecycle.cluster_analyzer import analyze_clusters
from agent_core.lifecycle.default_specs import default_registry
from agent_core.lifecycle.deviation_detector import (
    MEDIUM_SIGNAL,
    DeviationFinding,
    detect_deviations,
)
from agent_core.lifecycle.families import signal_family
from agent_core.lifecycle.medium_change import DEFAULT_MEDIUM_THRESHOLD
from agent_core.lifecycle.observation_adapter import ObservationAdapter

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = REPO_ROOT / "agent_core" / "lifecycle"


def _constant_baseline(signal_id: str, center: float = 1.0, delta: float = 0.5) -> SignalBaseline:
    return SignalBaseline(
        signal_id=signal_id,
        kind="binary",
        center=center,
        spread=0.0,
        n=12,
        min_value=center,
        max_value=center,
        is_reliable=True,
        is_constant=True,
        min_meaningful_delta=delta,
        circular_period=None,
        window_start=T0,
        window_end=T0 + timedelta(days=90),
    )


def _mutation_is_caught(mutated_invariant) -> bool:
    """Değişmez, mutasyon altında KIRILIYORSA test ısırıyor demektir."""
    try:
        mutated_invariant()
    except AssertionError:
        return True
    return False


# --- (a) std=0 kontrolünü kaldırma -----------------------------------------


def _mutant_evaluate(self, value, z_threshold: float = 3.0) -> DeviationResult:
    """Sabit baseline dalı SİLİNMİŞ sürüm: z = distance / spread."""
    distance = self.distance_from_center(float(value))
    z = distance / self.spread if self.spread > 0 else math.inf
    return DeviationResult(
        signal_id=self.signal_id,
        value=float(value),
        baseline_center=self.center,
        baseline_spread=self.spread,
        distance=distance,
        is_deviation=bool(z >= z_threshold),
        method="z_score",
        z_score=float(z),
        reason="mutant",
    )


def test_constant_baseline_tolerance_mutation_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = _constant_baseline("timing.is_night_post")

    def invariant() -> None:
        # Gürültü (0.1) toleransın (0.5) altında: sapma SAYILMAZ.
        assert baseline.evaluate(1.1).is_deviation is False

    invariant()  # gerçek kod doğru davranıyor
    monkeypatch.setattr(SignalBaseline, "evaluate", _mutant_evaluate)
    assert _mutation_is_caught(invariant), "sabit baseline toleransı mutasyonu YAKALANMADI"


# --- (b) korelasyon yokken bağımsızlık -------------------------------------


def _mutant_correlation_between(self, a: str, b: str):
    """Ölçülemeyen ilişkiyi 0.0 (=bağımsız) sayan sürüm."""
    value = self.signal_correlation
    if value is None:
        return 0.0
    return 0.0


def _cluster_status_without_correlation() -> str:
    signal_ids = ["timing.is_night_post", "text.future_agency_density", "ritual.obj.kitchen_table"]
    baselines = {
        signal_id: SignalBaseline(
            signal_id=signal_id,
            kind="binary",
            center=1.0,
            spread=0.0,
            n=12,
            min_value=1.0,
            max_value=1.0,
            is_reliable=True,
            is_constant=True,
            min_meaningful_delta=0.5,
            circular_period=None,
            window_start=T0 - timedelta(days=100),
            window_end=T0,
        )
        for signal_id in signal_ids
    }
    profile = BaselineProfile(
        subject_id="mutation",
        baseline_window=(T0 - timedelta(days=100), T0),
        baselines=baselines,
        signal_order=tuple(sorted(signal_ids)),
        signal_correlation=None,  # ÖLÇÜLEMEDİ
    )
    findings, observations = [], []
    for signal_id in signal_ids:
        for index in range(11):
            moment = T0 + timedelta(days=7 * index)
            observation = SignalObservation(signal_id, moment, 0.0, f"{signal_id}:{index}")
            observations.append(observation)
            findings.append(
                DeviationFinding(
                    observation=observation,
                    result=profile.evaluate(observation),
                    family=signal_family(signal_id),
                    medium_change_status="stable",
                )
            )
    analysis = analyze_clusters(
        findings,
        observations,
        profile,
        window_days=180,
        min_persistence_days=60,
    )
    assert analysis.best is not None
    return analysis.best.independence.status


def test_unknown_correlation_mutation_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    def invariant() -> None:
        assert _cluster_status_without_correlation() == "unknown"

    invariant()
    monkeypatch.setattr(BaselineProfile, "correlation_between", _mutant_correlation_between)
    assert _mutation_is_caught(invariant), "korelasyon mutasyonu YAKALANMADI"


# --- (c) authored baseline karşılaştırmasını kaldırma ---------------------


def test_absolute_authored_rate_mutation_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """Eski %50 kuralı: yüksek ama SABİT oranı "değişti" sanar."""
    from agent_core.lifecycle.baseline_builder import build_baseline
    from agent_core.lifecycle.medium_change import MediumChangeAssessment

    observations = []
    for index in range(10):
        observations.append(
            SignalObservation(MEDIUM_SIGNAL, T0 + timedelta(days=7 * index), 1.0, f"b{index}")
        )
        observations.append(
            SignalObservation("ritual.obj.kitchen_table", T0 + timedelta(days=7 * index), 1.0, f"r{index}")
        )
    for index in range(10):
        observations.append(
            SignalObservation(MEDIUM_SIGNAL, T0 + timedelta(days=200 + 7 * index), 1.0, f"c{index}")
        )
    observations.append(
        SignalObservation("ritual.obj.kitchen_table", T0 + timedelta(days=200), 0.0, "r-target")
    )

    baseline = build_baseline("mutation", observations, T0, T0 + timedelta(days=90), registry=default_registry())

    def invariant() -> None:
        findings = detect_deviations(
            baseline, observations, T0 + timedelta(days=180), T0 + timedelta(days=400)
        )
        ritual = [finding for finding in findings if finding.signal_id.startswith("ritual.")]
        assert ritual, "senaryo kurulamadı: ritual sapması yok"
        assert all(finding.confounded_by_medium_change is False for finding in findings)

    invariant()  # gerçek kod: oran yüksek ama SABİT → confound değil

    def _mutant_assess(target, baseline_start, baseline_end, comparison_start, comparison_end, **kwargs):
        """Mutasyon: yalnız karşılaştırma penceresindeki MUTLAK orana bak."""
        values = [
            obs.value
            for obs in target
            if obs.signal_id == MEDIUM_SIGNAL and comparison_start <= obs.timestamp <= comparison_end
        ]
        rate = sum(values) / len(values) if values else None
        shifted = rate is not None and rate > 0.5
        return MediumChangeAssessment(
            status="changed" if shifted else "stable",
            baseline_rate=rate,
            comparison_rate=rate,
            delta=0.0,
            threshold=DEFAULT_MEDIUM_THRESHOLD,
            baseline_sample_size=len(values),
            comparison_sample_size=len(values),
            reasons=("mutant: mutlak oran kuralı",),
        )

    monkeypatch.setattr("agent_core.lifecycle.deviation_detector.assess_medium_change", _mutant_assess)
    assert _mutation_is_caught(invariant), "authored oran mutasyonu YAKALANMADI"


# --- (d) ölçülemez görseli sıfır sayma ------------------------------------


def test_unmeasured_frame_mutation_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_core.lifecycle.observation_adapter import VisualFrameExtractor

    frames = {
        "frames": [
            {
                "frame_id": "f0",
                "observed_at": (T0 + timedelta(days=7 * index)).isoformat(),
                "capture_class": "camera_incidental",
                "has_measurable_background": True,
                "detected_objects": ["kitchen_table"],
                "environment_and_places": ["home_living_room"],
                "lighting": "daylight",
                "person_count": 2,
                "data_confidence": False,  # ÖLÇÜM YAPILAMADI
                "fallback_reason": "vision_failed",
            }
            for index in range(6)
        ]
    }

    def invariant() -> None:
        observations = ObservationAdapter().transform(None, visual_evidence=frames)
        assert not [obs for obs in observations if obs.signal_id.startswith("ritual.")]
        assert not [obs for obs in observations if obs.signal_id.startswith("habitat.")]

    invariant()  # ölçülemeyen kare yokluk ÜRETMEZ

    def _mutant_load_frames(self, inputs):
        diagnostics = inputs.diagnostics
        from agent_core.lifecycle.visual_frames import frames_from_visual_evidence

        raw, problems = frames_from_visual_evidence(inputs.visual_evidence)
        for _ in problems:
            diagnostics.rejected_frame_count += 1
        diagnostics.visual_frame_count = len(raw)
        return raw  # data_confidence filtresi YOK

    monkeypatch.setattr(VisualFrameExtractor, "_load_frames", _mutant_load_frames)
    assert _mutation_is_caught(invariant), "ölçülemez kare mutasyonu YAKALANMADI"


# --- (e) sinyal adı kayması (statik kontrol) ------------------------------


_SIGNAL_LITERAL = re.compile(
    r"^(timing|text|media|ritual|habitat|gaze|wave|strata|visual)\.[a-z0-9_]+(\.[a-z0-9_]+)*$"
)


def _string_literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def test_every_signal_literal_in_package_resolves_to_a_spec() -> None:
    """Kodda geçen sinyal adı ``default_specs``te yoksa sessizce ölçüm dışı kalır."""
    registry = default_registry()
    unresolved: list[str] = []
    for path in sorted(PACKAGE.glob("*.py")):
        for literal in _string_literals(path):
            if not _SIGNAL_LITERAL.match(literal):
                continue
            if registry.resolve(literal) is None:
                unresolved.append(f"{path.name}:{literal}")
    assert not unresolved, f"spec'i olmayan sinyal adları: {unresolved}"


def test_plausible_but_wrong_signal_name_is_rejected() -> None:
    """Eski kısaltma (``media.is_authored``) resolve EDİLEMEZ — sessiz kayma yok."""
    registry = default_registry()
    assert registry.resolve("media.is_authored_or_staged") is not None
    assert registry.resolve("media.is_authored") is None
    assert registry.resolve("ritual.obj.kitchen_table") is not None  # joker prefix
    assert registry.resolve("ritual.activity.singing") is None  # tanımsız aile


def test_medium_signal_name_is_shared_not_duplicated() -> None:
    """Dedektör ile medium_change modülü AYNI adı kullanır (kopya sabit yok)."""
    from agent_core.lifecycle.medium_change import MEDIUM_CHANGE_SIGNAL

    assert MEDIUM_SIGNAL == MEDIUM_CHANGE_SIGNAL
    assert default_registry().resolve(MEDIUM_SIGNAL) is not None
