"""Wiring W1/W2/W3 (frontend): UI yalniz gercek model alanlarini okur.

Svelte test altyapisi olmadigindan kaynak-kontrat kilitleri kullanilir:
eski sahte anahtarlar (night_owl_score, bot_probability, ritual_match_score...)
frontend kaynaginda bir daha GECEMEZ.

[P6 · 2026-10-18] Kontrat artik CANLI frontend ağacına uygulanır.
Ölçüldü: kontratın bağlandığı `UnifiedCompactPanel.svelte` PR #143'te
yenilen arayüzde import edilmiyordu (ölü kod) ve 2026-10-18'de silindi.
Ölü dosyayı koruyan yeşil bir test, üretimde hiçbir şeyi garanti etmiyordu.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
LIVE_SRC = "\n".join(
    path.read_text(encoding="utf-8")
    for path in sorted(FRONTEND_SRC.rglob("*.svelte"))
) + "\n".join(
    path.read_text(encoding="utf-8")
    for path in sorted(FRONTEND_SRC.rglob("*.ts"))
)
I18N_SRC = (REPO_ROOT / "frontend" / "src" / "i18n.ts").read_text(encoding="utf-8")

#: Canlı arayüzün gerçekten okuduğu alanlar (ölçüldü: AtlasPinealCockpit).
REAL_FIELDS = (
    "night_share",
    "peak_hour",
    "median_drift_hours",
    "verdict_code",
    "compatibility_score",
    "recommended_approach",
)

#: Uydurma/eski alanlar — canlı arayüzde BİR YERDE bile geçemez.
FAKE_FIELDS = (
    "night_owl_score",
    "peak_utc_hour",
    "tz_offset_hours_likely",
    "bot_probability",
    "ritual_match_score",
    "playlist_resonance",
    "envy_intensity",
)


def test_frontend_reads_real_timing_keys():
    for field in ("night_share", "peak_hour", "median_drift_hours"):
        assert field in LIVE_SRC, f"canlı arayüz gerçek zaman alanını okumuyor: {field}"


def test_frontend_reads_verdict_code_not_bot_probability():
    assert "verdict_code" in LIVE_SRC
    assert "bot_probability" not in LIVE_SRC


def test_frontend_reads_only_real_resonance_fields():
    for field in ("compatibility_score", "recommended_approach"):
        assert field in LIVE_SRC, f"canlı arayüz gerçek rezonans alanını okumuyor: {field}"


def test_no_fake_fields_anywhere_in_live_frontend():
    """Uydurma alanlar canlı frontend ağacının HİÇBİR yerinde geçemez."""
    offenders = {f: f in LIVE_SRC for f in FAKE_FIELDS if f in LIVE_SRC}
    assert offenders == {}, f"uydurma alan canlı arayüzde: {offenders}"


def test_real_fields_are_actually_used_by_a_live_component():
    """Her 'gerçek alan' en az bir canlı bileşende okunmalı (boş sözleşme yok)."""
    for field in REAL_FIELDS:
        holders = [
            path.name
            for path in sorted(FRONTEND_SRC.rglob("*.svelte"))
            if field in path.read_text(encoding="utf-8")
        ]
        assert holders, f"gerçek alan hiçbir canlı bileşende okunmuyor: {field}"


def test_i18n_uses_real_labels_only():
    assert "verdictHealthy" in I18N_SRC
    assert "verdictInflated" in I18N_SRC
    assert "engagementRateLabel" in I18N_SRC
    assert "resonanceScoreLabel" in I18N_SRC
    assert "approachLabel" in I18N_SRC
    assert "redFlagsLabel" in I18N_SRC
    assert "botProbLabel" not in I18N_SRC
    assert "ritualMatch" not in I18N_SRC
    assert "playlistResonance" not in I18N_SRC
    assert "envyIntensity" not in I18N_SRC
