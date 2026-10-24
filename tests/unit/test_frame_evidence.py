"""Tarihli kare kanıtı — zamanı olmayan görselden zaman serisi UYDURULMAZ.

Kilitlenen iddialar:
    * gönderi/görsel/zaman paralel dizileri hizasızsa kare ÜRETİLMEZ,
    * indirilemeyen/çözülemeyen görsel "yokluk" değildir: kayıt yok, sebep var,
    * yerel ölçüm deterministik ve anlamlı (karanlık < aydınlık, dokulu > düz),
    * ``capture_class`` kanıtsız ``unknown`` kalır → habitat/bakış KAPALI,
    * kare özellikleri ``media.frame_*`` (editoryal) eksenine gider, oda
      yorumuna değil.
"""

from __future__ import annotations

import asyncio
import base64
import io
from datetime import datetime, timedelta, timezone

from PIL import Image

from agent_core.lifecycle.observation_adapter import ObservationAdapter
from agent_core.lifecycle.visual_frames import VisualFrameRecord
from agent_core.services.frame_evidence import (
    collect_frames,
    decode_image,
    measure_frame_features,
    select_frame_candidates,
)

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
T0 = datetime(2022, 3, 1, tzinfo=timezone.utc)


def _solid(rgb: tuple[int, int, int], size: int = 64) -> Image.Image:
    return Image.new("RGB", (size, size), rgb)


def _textured(size: int = 64) -> Image.Image:
    image = Image.new("RGB", (size, size), (128, 128, 128))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            value = 255 if (x // 4 + y // 4) % 2 == 0 else 0
            pixels[x, y] = (value, value, value)
    return image


def _profile(count: int = 3) -> dict:
    return {
        "posts": [f"gönderi {index}" for index in range(count)],
        "post_times": [(T0 + timedelta(days=30 * index)).isoformat() for index in range(count)],
        "images": [f"https://cdn.example.com/{index}.jpg" for index in range(count)],
        "post_evidence_types": ["platform_post"] * count,
    }


def _png_b64(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# --- Seçim (fail-closed) ----------------------------------------------------


def test_parallel_array_mismatch_yields_no_frame() -> None:
    profile = _profile()
    profile["images"] = profile["images"][:2]

    candidates, problems = select_frame_candidates(profile, now=NOW)

    assert candidates == []
    assert any("parallel_array_mismatch" in problem for problem in problems)


def test_missing_images_is_reported_not_invented() -> None:
    candidates, problems = select_frame_candidates({"posts": ["a"], "post_times": [""]}, now=NOW)
    assert candidates == []
    assert "images_missing" in problems


def test_undated_post_is_skipped() -> None:
    profile = _profile()
    profile["post_times"][1] = ""

    candidates, problems = select_frame_candidates(profile, now=NOW)

    assert [candidate.post_ref for candidate in candidates] == ["post_0000", "post_0002"]
    assert any("undated_post[1]" in problem for problem in problems)


def test_non_platform_rows_are_excluded() -> None:
    profile = _profile()
    profile["post_evidence_types"][0] = "search_snippet"

    candidates, problems = select_frame_candidates(profile, now=NOW)

    assert all(candidate.post_ref != "post_0000" for candidate in candidates)
    assert any("non_platform_post[0]" in problem for problem in problems)


def test_future_timestamp_is_rejected() -> None:
    profile = _profile()
    profile["post_times"][2] = (NOW + timedelta(days=30)).isoformat()

    candidates, problems = select_frame_candidates(profile, now=NOW)

    assert [candidate.post_ref for candidate in candidates] == ["post_0000", "post_0001"]
    assert any("future_timestamp[2]" in problem for problem in problems)


def test_frame_ids_are_deterministic() -> None:
    first, _ = select_frame_candidates(_profile(), now=NOW)
    second, _ = select_frame_candidates(_profile(), now=NOW)

    assert [c.frame_id for c in first] == [c.frame_id for c in second]
    assert all(c.frame_id.startswith("fr_") and len(c.frame_id) == 23 for c in first)


def test_budget_sampling_keeps_first_and_last() -> None:
    profile = _profile(count=40)
    candidates, problems = select_frame_candidates(profile, max_frames=8, now=NOW)

    assert len(candidates) == 8
    assert candidates[0].post_ref == "post_0000"
    assert candidates[-1].post_ref == "post_0039"
    assert any("frame_budget_applied" in problem for problem in problems)
    assert [c.observed_at for c in candidates] == sorted(c.observed_at for c in candidates)


# --- Yerel ölçüm ------------------------------------------------------------


def test_dark_image_measures_darker_than_bright_image() -> None:
    dark = measure_frame_features(_solid((12, 12, 16)))
    bright = measure_frame_features(_solid((235, 235, 235)))

    assert dark is not None and bright is not None
    assert dark.brightness < 0.1 < 0.9 < bright.brightness
    assert dark.to_dict()["brightness"] < bright.to_dict()["brightness"]


def test_texture_raises_edge_density() -> None:
    flat = measure_frame_features(_solid((128, 128, 128)))
    textured = measure_frame_features(_textured())

    assert flat is not None and textured is not None
    assert textured.edge_density > flat.edge_density
    assert flat.has_background_structure is False
    assert textured.has_background_structure is True


def test_measurement_is_deterministic() -> None:
    image = _textured()
    assert measure_frame_features(image).to_dict() == measure_frame_features(image).to_dict()


def test_undecodable_bytes_are_not_measured() -> None:
    assert decode_image(b"not an image") is None
    assert measure_frame_features(None) is None


# --- Toplama ----------------------------------------------------------------


def _fetch_from(mapping: dict[str, dict]):
    async def _fetch(url: str) -> dict:
        return mapping.get(url, {"status": "failed", "reason": "not_found"})

    return _fetch


def test_collected_frame_satisfies_visual_frame_contract() -> None:
    profile = _profile(count=2)
    mapping = {
        profile["images"][0]: {
            "status": "downloaded",
            "b64": _png_b64(_solid((240, 240, 240))),
            "sha256": "abc123",
            "bytes": 100,
        },
        profile["images"][1]: {
            "status": "downloaded",
            "b64": _png_b64(_solid((10, 10, 12))),
            "sha256": "def456",
            "bytes": 100,
        },
    }

    collection = asyncio.run(collect_frames(profile, fetch=_fetch_from(mapping), now=NOW))

    assert len(collection.frames) == 2
    for payload in collection.frames:
        record = VisualFrameRecord.model_validate(payload)
        assert record.data_confidence is True
        # Kanıt yok: gerçek/kurgu ayrımı bu kademede YAPILMAZ.
        assert record.capture_class == "unknown"
        assert record.lighting == "unknown"
        assert record.detected_objects == []  # uydurulmaz
        assert record.visual_stats is not None
        assert record.post_ref and record.source_sha256
    assert collection.diagnostics["measured_count"] == 2


def test_change_points_target_measured_frames_only() -> None:
    """İkinci kademe yalnız ölçülmüş kareleri hedefler; indeksler deterministik."""
    profile = _profile(count=3)
    mapping = {
        profile["images"][0]: {"status": "downloaded", "b64": _png_b64(_solid((240, 240, 240)))},
        profile["images"][1]: {"status": "failed", "reason": "http_404"},
        profile["images"][2]: {"status": "downloaded", "b64": _png_b64(_solid((10, 10, 12)))},
    }

    first = asyncio.run(collect_frames(profile, fetch=_fetch_from(mapping), now=NOW))
    second = asyncio.run(collect_frames(profile, fetch=_fetch_from(mapping), now=NOW))

    frame_ids = [frame["frame_id"] for frame in first.frames]
    points = first.diagnostics["change_point_frame_ids"]
    assert first.diagnostics["change_points"] == second.diagnostics["change_points"]
    assert points == second.diagnostics["change_point_frame_ids"]
    assert points[0] == frame_ids[0] and points[-1] == frame_ids[-1]
    # Değişim noktaları YALNIZ var olan kareleri gösterir.
    assert set(points) <= set(frame_ids)
    # Ölçülemeyen kare indekse sıkışmaz: sıra korunur, boşluk atlanmaz.
    assert first.diagnostics["measured_count"] == len(frame_ids) == 2


def test_failed_download_produces_no_frame_but_a_reason() -> None:
    profile = _profile(count=1)
    collection = asyncio.run(
        collect_frames(
            profile,
            fetch=_fetch_from({profile["images"][0]: {"status": "failed", "reason": "ssrf_blocked"}}),
            now=NOW,
        )
    )

    assert collection.frames == []
    assert any("ssrf_blocked" in problem for problem in collection.problems)
    assert collection.diagnostics["measured_count"] == 0


def test_fetch_exception_is_contained() -> None:
    async def _boom(url: str):
        raise RuntimeError("network down")

    collection = asyncio.run(collect_frames(_profile(count=1), fetch=_boom, now=NOW))

    assert collection.frames == []
    assert any("fetch_error" in problem for problem in collection.problems)


def test_corrupt_payload_is_not_counted_as_a_frame() -> None:
    profile = _profile(count=1)
    collection = asyncio.run(
        collect_frames(
            profile,
            fetch=_fetch_from({profile["images"][0]: {"status": "downloaded", "b64": "zzz"}}),
            now=NOW,
        )
    )

    assert collection.frames == []
    assert any("measurement_failed" in problem for problem in collection.problems)


def test_budget_timeout_keeps_partial_result_honest() -> None:
    profile = _profile(count=2)

    async def _slow(url: str) -> dict:
        await asyncio.sleep(5)
        return {"status": "downloaded", "b64": _png_b64(_solid((100, 100, 100)))}

    collection = asyncio.run(collect_frames(profile, fetch=_slow, now=NOW, budget_seconds=0.05))

    assert collection.frames == []
    assert collection.diagnostics["budget_exceeded"] is True
    assert "download_budget_exceeded" in collection.problems


def test_no_candidates_is_explicit() -> None:
    empty = asyncio.run(collect_frames({"posts": [], "post_times": []}, fetch=_fetch_from({}), now=NOW))
    assert empty.frames == []
    assert "images_missing" in empty.problems

    undated = asyncio.run(
        collect_frames(
            {"posts": ["a"], "post_times": [""], "images": ["https://cdn.example.com/a.jpg"]},
            fetch=_fetch_from({}),
            now=NOW,
        )
    )
    assert undated.frames == []
    assert "no_dated_frame_candidate" in undated.problems


# --- Adaptör: editoryal eksen, oda iddiası DEĞİL ---------------------------


def test_visual_stats_feed_media_axis_only() -> None:
    payload = {
        "frame_id": "fr_test",
        "observed_at": (T0).isoformat(),
        "capture_class": "unknown",
        "has_measurable_background": True,
        "visual_stats": {
            "brightness": 0.2,
            "saturation": 0.3,
            "contrast": 0.6,
            "edge_density": 0.4,
            "colorfulness": 0.5,
        },
        "post_ref": "post_0000",
    }

    observations = ObservationAdapter().transform(None, visual_evidence={"frames": [payload]})
    signal_ids = {observation.signal_id for observation in observations}

    # Ölçüm taşınır…
    assert {
        "media.frame_brightness",
        "media.frame_saturation",
        "media.frame_contrast",
        "media.frame_edge_density",
        "media.frame_colorfulness",
    } <= signal_ids
    # …ama kanıtsız provenance yüzünden mekân/bakış ekseni AÇILMAZ.
    assert not [signal_id for signal_id in signal_ids if signal_id.startswith("habitat.")]
    assert not [signal_id for signal_id in signal_ids if signal_id.startswith("gaze.")]
    # Ritüel sözlüğü de boş: nesne etiketi ölçülmedi.
    assert not [signal_id for signal_id in signal_ids if signal_id.startswith("ritual.")]
