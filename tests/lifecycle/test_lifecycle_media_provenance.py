"""Medya kökeni kapısı — "sızıntı mı, vitrin mi?" ayrımının kilidi."""

from __future__ import annotations

from agent_core.lifecycle.media_provenance import (
    BACKGROUND_EDGE_FLOOR,
    BACKGROUND_VARIANCE_FLOOR,
    BackgroundStats,
    classify_media,
    measure_background,
)


def _measurable() -> BackgroundStats:
    return BackgroundStats(
        variance=BACKGROUND_VARIANCE_FLOOR * 4,
        edge_density=BACKGROUND_EDGE_FLOOR * 10,
        sampled_pixels=50_000,
    )


def _flat() -> BackgroundStats:
    return BackgroundStats(
        variance=BACKGROUND_VARIANCE_FLOOR / 10,
        edge_density=BACKGROUND_EDGE_FLOOR / 10,
        sampled_pixels=50_000,
    )


def test_synthetic_software_wins_over_everything() -> None:
    provenance = classify_media(
        "m1",
        exif={"Software": "Midjourney v6", "Make": "Canon"},
        caption="harika bir gün",
        background=_measurable(),
    )
    assert provenance.capture_class == "synthetic_or_render"
    assert provenance.feeds_habitat is False
    assert provenance.feeds_somatic is False
    assert provenance.feeds_authored is True


def test_authored_hashtag_marks_composite_even_with_background() -> None:
    provenance = classify_media("m2", caption="yeni işim #digitalart", background=_measurable())
    assert provenance.capture_class == "edited_composite"
    assert provenance.feeds_habitat is False
    assert provenance.feeds_somatic is False
    assert any("authored_tag" in item for item in provenance.evidence)


def test_editor_software_marks_composite() -> None:
    provenance = classify_media("m3", exif={"Software": "Adobe Photoshop 25.0"}, background=_measurable())
    assert provenance.capture_class == "edited_composite"
    assert provenance.feeds_authored is True


def test_measurable_background_is_incidental_and_feeds_habitat() -> None:
    provenance = classify_media("m4", background=_measurable())
    assert provenance.capture_class == "camera_incidental"
    assert provenance.feeds_habitat is True
    assert provenance.feeds_somatic is True


def test_flat_background_is_staged_somatic_only() -> None:
    """Stüdyo/düz fon: yüz gerçektir (somatik OK), arka plan ÖLÇÜLEMEZ (habitat HAYIR)."""
    provenance = classify_media("m5", background=_flat())
    assert provenance.capture_class == "camera_staged"
    assert provenance.has_measurable_background is False
    assert provenance.feeds_somatic is True
    assert provenance.feeds_habitat is False
    assert provenance.feeds_authored is False


def test_no_signal_at_all_is_unknown_and_feeds_nothing() -> None:
    provenance = classify_media("m6")
    assert provenance.capture_class == "unknown"
    assert provenance.feeds_habitat is False
    assert provenance.feeds_somatic is False
    assert provenance.feeds_authored is False
    assert "no_provenance_signal" in provenance.evidence


def test_missing_exif_is_not_fraud_evidence() -> None:
    """Platform görselleri yeniden kodlarken EXIF'i siler: yokluk kanıt değildir."""
    provenance = classify_media("m7", exif={}, background=_measurable())
    assert provenance.capture_class == "camera_incidental"
    assert provenance.feeds_habitat is True


def test_measure_background_fails_closed_without_file() -> None:
    """Dosya okunamıyorsa sayı uydurulmaz (None döner)."""
    assert measure_background("/nonexistent/path/never.jpg") is None
