"""Shortcode → zaman: tarih uydurmanın değil, tarihi ÇÜRÜTMENİN aracı."""

from __future__ import annotations

from datetime import datetime, timezone

from agent_core.lifecycle.ig_time import (
    decode_ig_shortcode_utc,
    shortcode_from_url,
    shortcode_time_drift_hours,
)


def test_known_shortcodes_decode_to_source_dates() -> None:
    first = decode_ig_shortcode_utc("CYoNoBYMJrS")
    last = decode_ig_shortcode_utc("DdlX2SNhT3y")

    assert first is not None and (first.year, first.month, first.day) == (2022, 1, 12)
    assert last is not None and (last.year, last.month, last.day) == (2026, 9, 22)


def test_decode_is_monotonic_with_media_id() -> None:
    """Instagram medya ID'si monotondur: sıra ile tarih sırası çelişemez."""
    ordered = ["CYoNoBYMJrS", "DXjAl2HDDjb", "DdlX2SNhT3y"]
    decoded = [decode_ig_shortcode_utc(item) for item in ordered]
    assert all(item is not None for item in decoded)
    assert decoded[0] < decoded[1] < decoded[2]


def test_decode_rejects_garbage() -> None:
    assert decode_ig_shortcode_utc("") is None
    assert decode_ig_shortcode_utc("a") is None
    assert decode_ig_shortcode_utc("!!!!!!!!!!!!") is None
    assert decode_ig_shortcode_utc(None) is None  # type: ignore[arg-type]


def test_shortcode_from_url() -> None:
    assert shortcode_from_url("https://www.instagram.com/p/CYoNoBYMJrS/") == "CYoNoBYMJrS"
    assert shortcode_from_url("https://www.instagram.com/reel/DdlX2SNhT3y/?utm=1") == "DdlX2SNhT3y"
    assert shortcode_from_url("https://example.com/p/CYoNoBYMJrS/") is None


def test_drift_computation() -> None:
    honest = datetime(2022, 1, 12, 11, 27, tzinfo=timezone.utc)
    drift = shortcode_time_drift_hours(honest, "CYoNoBYMJrS")
    assert drift is not None and drift < 0.1

    fabricated = datetime(2026, 1, 1, tzinfo=timezone.utc)
    big_drift = shortcode_time_drift_hours(fabricated, "CYoNoBYMJrS")
    assert big_drift is not None and big_drift > 48


def test_unverifiable_shortcode_returns_none() -> None:
    assert shortcode_time_drift_hours(datetime(2022, 1, 1, tzinfo=timezone.utc), "!!") is None
