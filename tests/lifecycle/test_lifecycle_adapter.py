"""Gözlem adaptörü — dört sessiz yanlışın kilidi (kayma, sızıntı, tarih, çorba)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent_core.lifecycle.observation_adapter import (
    AdapterDiagnostics,
    FrequencyWaveExtractor,
    ObservationAdapter,
    TextLinguisticExtractor,
    VisualFrameExtractor,
    align_platform_posts,
)

T0 = datetime(2022, 1, 10, 12, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _frame(frame_id: str, observed_at: datetime, **overrides) -> dict:
    payload = {
        "frame_id": frame_id,
        "observed_at": _iso(observed_at),
        "capture_class": "camera_incidental",
        "has_measurable_background": True,
        "detected_objects": ["kitchen_table"],
        "environment_and_places": ["home_living_room"],
        "lighting": "daylight",
        "person_count": 2,
    }
    payload.update(overrides)
    return payload


def _profile(posts: list, times: list, **extra) -> dict:
    payload = {"posts": posts, "post_times": times}
    payload.update(extra)
    return payload


# --- 1) Paralel dizi kayması -------------------------------------------------


def test_parallel_array_mismatch_returns_no_observation() -> None:
    diagnostics = AdapterDiagnostics()
    aligned = align_platform_posts(
        _profile(["a", "b", "c"], [_iso(T0), _iso(T0 + timedelta(days=1))]), diagnostics
    )
    assert aligned == []
    assert any("parallel_array_mismatch" in warning for warning in diagnostics.warnings)


def test_evidence_types_mismatch_returns_no_observation() -> None:
    diagnostics = AdapterDiagnostics()
    aligned = align_platform_posts(
        _profile(["a"], [_iso(T0)], post_evidence_types=["platform_post", "search_snippet"]),
        diagnostics,
    )
    assert aligned == []
    assert any("evidence_types_mismatch" in warning for warning in diagnostics.warnings)


# --- 2) Snippet sızıntısı ----------------------------------------------------


def test_non_platform_evidence_is_filtered_and_counted() -> None:
    diagnostics = AdapterDiagnostics()
    profile = _profile(
        ["gerçek gönderi", "üçüncü şahıs arama özeti"],
        [_iso(T0), _iso(T0 + timedelta(days=1))],
        post_evidence_types=["platform_post", "search_snippet"],
    )
    aligned = align_platform_posts(profile, diagnostics)

    assert [post.text for post in aligned] == ["gerçek gönderi"]
    assert diagnostics.filtered_non_platform_count == 1


# --- 3) Tarihsiz ve gelecek tarih --------------------------------------------


def test_empty_timestamp_is_undated_not_zero() -> None:
    diagnostics = AdapterDiagnostics()
    profile = _profile(["a", "b"], ["", _iso(T0)])
    aligned = align_platform_posts(profile, diagnostics)

    assert len(aligned) == 1
    assert diagnostics.undated_post_count == 1


def test_future_timestamp_is_rejected_loudly() -> None:
    diagnostics = AdapterDiagnostics()
    profile = _profile(["gelecekten"], [_iso(datetime(2999, 1, 1, tzinfo=timezone.utc))])
    aligned = align_platform_posts(profile, diagnostics)

    assert aligned == []
    assert diagnostics.rejected_future_timestamp_count == 1
    assert any("timestamp_in_future" in warning for warning in diagnostics.warnings)


def test_dict_posts_fall_back_to_created_at() -> None:
    diagnostics = AdapterDiagnostics()
    profile = {
        "posts": [{"text": "bir gönderi", "created_at": _iso(T0)}],
    }
    aligned = align_platform_posts(profile, diagnostics)

    assert len(aligned) == 1
    assert aligned[0].text == "bir gönderi"


# --- 4) Tarihsiz görsel çorbası ---------------------------------------------


def test_flat_visual_summary_is_skipped_not_dated() -> None:
    adapter = ObservationAdapter()
    diagnostics = AdapterDiagnostics()
    observations = adapter.transform(
        None,
        visual_evidence={
            "detected_objects": ["kitchen_table", "blade"],
            "environment_and_places": ["dark_studio"],
            "aesthetic_style": "low-key",
        },
        diagnostics=diagnostics,
    )

    assert observations == []
    assert diagnostics.undated_visual_summary_skipped is True
    assert any("undated_visual_summary" in warning for warning in diagnostics.warnings)


def test_invalid_frame_payload_is_rejected_not_coerced() -> None:
    adapter = ObservationAdapter()
    diagnostics = AdapterDiagnostics()
    bad = _frame("bad", T0)
    bad["unexpected_field"] = "şema dışı"  # extra="forbid"
    observations = adapter.transform(None, visual_evidence={"frames": [bad]}, diagnostics=diagnostics)

    assert observations == []
    assert diagnostics.rejected_frame_count == 1
    assert any("invalid_frame" in warning for warning in diagnostics.warnings)


# --- 5) Eksen ayrımı (kurgu ≠ sızıntı) --------------------------------------


def test_authored_frame_produces_media_signal_but_no_habitat_or_gaze() -> None:
    adapter = ObservationAdapter()
    diagnostics = AdapterDiagnostics()
    frame = _frame(
        "authored",
        T0,
        capture_class="edited_composite",
        has_measurable_background=True,
        gaze={"ear_mean": 0.3, "head_pitch": 5.0},
    )
    observations = adapter.transform(None, visual_evidence={"frames": [frame]}, diagnostics=diagnostics)

    signal_ids = {obs.signal_id for obs in observations}
    assert "media.is_authored_or_staged" in signal_ids
    assert not any(signal_id.startswith("habitat.") for signal_id in signal_ids)
    assert not any(signal_id.startswith("gaze.") for signal_id in signal_ids)
    assert diagnostics.habitat_suppressed_frame_count == 1
    assert diagnostics.gaze_suppressed_frame_count == 1


def test_staged_frame_feeds_gaze_but_not_habitat() -> None:
    adapter = ObservationAdapter()
    frame = _frame(
        "staged",
        T0,
        capture_class="camera_staged",
        has_measurable_background=False,
        gaze={"ear_mean": 0.28, "head_pitch": -6.0},
    )
    observations = adapter.transform(None, visual_evidence={"frames": [frame]})

    signal_ids = {obs.signal_id for obs in observations}
    assert "gaze.ear_mean" in signal_ids
    assert not any(signal_id.startswith("habitat.") for signal_id in signal_ids)


def test_incidental_frame_feeds_habitat() -> None:
    adapter = ObservationAdapter()
    observations = adapter.transform(None, visual_evidence={"frames": [_frame("inc", T0)]})

    signal_ids = {obs.signal_id for obs in observations}
    assert {"habitat.is_daylight", "habitat.person_count", "habitat.is_solitary"} <= signal_ids
    assert "habitat.is_solitary" in signal_ids


# --- 6) Ritüel sözlüğü ve yokluk kaydı --------------------------------------


def test_absent_ritual_is_recorded_as_zero() -> None:
    frames = [_frame(f"base{i}", T0 + timedelta(days=7 * i)) for i in range(5)]
    frames += [
        _frame(f"late{i}", T0 + timedelta(days=200 + 7 * i), detected_objects=["blade"])
        for i in range(5)
    ]
    extractor = VisualFrameExtractor(vocabulary_until=T0 + timedelta(days=120))
    adapter = ObservationAdapter([extractor])
    observations = adapter.transform(None, visual_evidence={"frames": frames})

    cutoff = T0 + timedelta(days=120)
    ritual = [obs for obs in observations if obs.signal_id == "ritual.obj.kitchen_table"]
    assert len(ritual) == 10  # her tarihli kare için kayıt
    baseline_values = [obs.value for obs in ritual if obs.timestamp <= cutoff]
    late_values = [obs.value for obs in ritual if obs.timestamp > cutoff]
    assert len(baseline_values) == 5 and len(late_values) == 5
    assert all(value == 1.0 for value in baseline_values)
    assert all(value == 0.0 for value in late_values)  # YOKLUK kaydedildi


def test_dead_ritual_stays_in_vocabulary() -> None:
    """Sözlük TÜM seriden çıkarılırsa ölen ritüel oranla elenir; ölçüm kaybolur."""
    frames = [_frame(f"base{i}", T0 + timedelta(days=7 * i)) for i in range(5)]
    frames += [
        _frame(f"late{i}", T0 + timedelta(days=200 + 7 * i), detected_objects=["mirror"])
        for i in range(30)
    ]
    extractor = VisualFrameExtractor(vocabulary_until=T0 + timedelta(days=120))
    observations = ObservationAdapter([extractor]).transform(None, visual_evidence={"frames": frames})

    signal_ids = {obs.signal_id for obs in observations}
    assert "ritual.obj.kitchen_table" in signal_ids
    assert "ritual.obj.mirror" not in signal_ids  # sonradan çıkan etiket baseline'da yoktu


# --- 7) Shortcode çapraz doğrulaması ---------------------------------------


def test_frame_with_shortcode_mismatch_is_rejected() -> None:
    diagnostics = AdapterDiagnostics()
    frame = _frame("DYFi2elsbxR", T0, shortcode="DYFi2elsbxR")  # shortcode 2026'da oluştu
    observations = ObservationAdapter().transform(
        None, visual_evidence={"frames": [frame]}, diagnostics=diagnostics
    )

    assert observations == []
    assert diagnostics.shortcode_mismatch_refs == ["DYFi2elsbxR"]
    assert any("shortcode_timestamp_mismatch" in warning for warning in diagnostics.warnings)


def test_frame_with_consistent_shortcode_passes() -> None:
    real_time = datetime(2026, 9, 22, 9, 5, tzinfo=timezone.utc)
    frame = _frame("ok", real_time, shortcode="DdlX2SNhT3y")
    observations = ObservationAdapter().transform(None, visual_evidence={"frames": [frame]})

    assert observations
    assert all(obs.timestamp == real_time for obs in observations)


# --- 8) Metin ekseni --------------------------------------------------------


def test_silent_caption_does_not_fake_zero_density() -> None:
    posts = ["", "Gelecekte yapacağım diye planlıyorum"]
    times = [_iso(T0), _iso(T0 + timedelta(days=1))]
    observations = ObservationAdapter([TextLinguisticExtractor()]).transform(_profile(posts, times))

    silent = [obs for obs in observations if obs.signal_id == "text.is_silent_caption"]
    assert sorted(obs.value for obs in silent) == [0.0, 1.0]
    densities = [obs for obs in observations if obs.signal_id == "text.future_agency_density"]
    assert len(densities) == 1  # sessiz caption için ölçüm YOK (uydurma 0.0 yok)


def test_future_and_regret_densities_are_computed() -> None:
    posts = ["Yarın başlayacağım, hedefim bu", "keşke artık boşver"]
    times = [_iso(T0), _iso(T0 + timedelta(days=1))]
    observations = ObservationAdapter([TextLinguisticExtractor()]).transform(_profile(posts, times))

    future = {obs.timestamp: obs.value for obs in observations if obs.signal_id == "text.future_agency_density"}
    regret = {obs.timestamp: obs.value for obs in observations if obs.signal_id == "text.regret_exhaustion_density"}
    assert future[T0] > 0.0
    assert regret[T0] == 0.0
    assert future[T0 + timedelta(days=1)] == 0.0
    assert regret[T0 + timedelta(days=1)] > 0.0


# --- 9) Wave-1 zaman serisi -------------------------------------------------


def test_frequency_samples_are_read_as_series() -> None:
    frequency_map = {
        "samples": [
            {"t": _iso(T0), "energy": 3.0, "post_count": 2},
            {"t": _iso(T0 + timedelta(days=1)), "energy": 1.0, "post_count": 1},
            {"energy": 9.0},  # tarihsiz örnek seriye girmez
        ]
    }
    diagnostics = AdapterDiagnostics()
    observations = ObservationAdapter([FrequencyWaveExtractor()]).transform(
        None, frequency_map=frequency_map, diagnostics=diagnostics
    )

    assert sorted(obs.value for obs in observations if obs.signal_id == "wave.energy") == [1.0, 3.0]
    assert any("undated_wave_sample" in warning for warning in diagnostics.warnings)


# --- 10) Kronoloji ----------------------------------------------------------


def test_observations_are_chronological() -> None:
    posts = ["a", "b", "c"]
    times = [_iso(T0 + timedelta(days=off)) for off in (2, 0, 1)]
    observations = ObservationAdapter().transform(_profile(posts, times))

    timestamps = [obs.timestamp for obs in observations]
    assert timestamps == sorted(timestamps)


# --- Shortcode ile matematiksel zaman doğrulaması (gönderi düzeyi) ----------


def test_post_shortcode_confirms_declared_time() -> None:
    """``CYoNoBYMJrS`` → 2022-01-12; beyan edilen tarih tutuyorsa gönderi geçer."""
    profile = {
        "posts": [{"text": "bugün", "shortcode": "CYoNoBYMJrS"}],
        "post_times": ["2022-01-12T12:00:00+00:00"],
    }
    diagnostics = AdapterDiagnostics()
    posts = align_platform_posts(profile, diagnostics, now=NOW)

    assert len(posts) == 1
    assert diagnostics.shortcode_mismatch_refs == []


def test_post_shortcode_mismatch_rejects_shifted_post() -> None:
    """Tarih 2026 diyor, medya kimliği 2022 → paralel dizi kayması yakalanır."""
    profile = {
        "posts": [{"text": "bugün", "shortcode": "CYoNoBYMJrS"}],
        "post_times": ["2026-01-12T12:00:00+00:00"],
    }
    diagnostics = AdapterDiagnostics()
    posts = align_platform_posts(profile, diagnostics, now=NOW)

    assert posts == []
    assert diagnostics.shortcode_mismatch_refs == ["post_0000"]
    assert any("post_shortcode_timestamp_mismatch" in w for w in diagnostics.warnings)


def test_post_shortcode_can_be_read_from_permalink() -> None:
    profile = {
        "posts": [{"text": "bugün", "permalink": "https://www.instagram.com/p/CYoNoBYMJrS/"}],
        "post_times": ["2026-01-12T12:00:00+00:00"],
    }
    diagnostics = AdapterDiagnostics()
    assert align_platform_posts(profile, diagnostics, now=NOW) == []
    assert diagnostics.shortcode_mismatch_refs == ["post_0000"]
