"""Varsayılan sinyal semantiği — toleransın TEK beyan yeri.

Kural: burada hiçbir kişi, hesap, şehir, cinsiyet veya belirli nesne adı yoktur.
Yalnız ÖLÇÜM TÜRLERİ ve birimleri vardır (``ritual.obj.*`` gibi joker
aileler). Hangi nesnenin/mekânın ritüel sayılacağını kod değil, kişinin kendi
verisindeki frekans belirler (bkz. ``observation_adapter.VisualFrameExtractor``).

Tolerans gerekçeleri (uydurma değil, birim):
    * ``timing.post_hour``     → 1.0 saat: bir saatlik kayma uyku düzeninde
      anlamlıdır, 10 dakikalık kayma değildir. Dairesel (period=24).
    * ``timing.is_night_post`` → 0.5: ikili sinyalde 0→1 kırılmadır.
    * ``text.word_count``      → 5 kelime: caption uzunluğu gürültülüdür.
    * ``media.is_authored_or_staged`` → 0.5: üretim biçimi ikili sinyal.
    * ``habitat.person_count`` → 1 kişi.
    * ``gaze.head_pitch``      → 5 derece: kamera açısı gürültüsü ~±3°.
    * ``gaze.ear_mean``        → 0.03: göz açıklığı oranı ölçüm hatası.
    * ``strata.drift.*``       → 0.3: pillar'ın kendi drift_ratio ölçeği.

Tüketici: ``agent_core.lifecycle.baseline_builder.build_baseline``.
Test: ``tests/lifecycle/test_lifecycle_baseline.py``.
"""

from __future__ import annotations

from agent_core.lifecycle.baseline_builder import SignalRegistry, SignalSpec

__all__ = ["DEFAULT_SPECS", "default_registry"]

DEFAULT_SPECS: list[SignalSpec] = [
    # --- Zamanlama (target_profile["post_times"]) ---
    SignalSpec("timing.post_hour", kind="circular", min_meaningful_delta=1.0, circular_period=24.0),
    SignalSpec("timing.is_night_post", kind="binary", min_meaningful_delta=0.5),
    SignalSpec("timing.inter_post_days", kind="continuous", min_meaningful_delta=1.0),
    # --- Metin / dilsel ufuk (target_profile["posts"]) ---
    SignalSpec("text.word_count", kind="count", min_meaningful_delta=5.0),
    SignalSpec("text.is_silent_caption", kind="binary", min_meaningful_delta=0.5),
    SignalSpec("text.future_agency_density", kind="ratio", min_meaningful_delta=0.5),
    SignalSpec("text.regret_exhaustion_density", kind="ratio", min_meaningful_delta=0.5),
    # --- Üretim biçimi (TÜM tarihli karelerde ölçülür) ---
    SignalSpec("media.is_incidental_life", kind="binary", min_meaningful_delta=0.5),
    SignalSpec("media.is_authored_or_staged", kind="binary", min_meaningful_delta=0.5),
    SignalSpec("visual.object_richness", kind="count", min_meaningful_delta=1.0),
    # --- Yayınlanan karenin ölçülen özellikleri (0..1 normalize) -------------
    # Toleranslar ölçüm gürültüsüne göre: 8 puanlık parlaklık/doygunluk farkı
    # JPEG yeniden kodlama ve otomatik pozlamayla açıklanabilir; 12 puan
    # açıklanamaz. Bunlar EDİTORYAL eksendir, "oda/ışık" iddiası değildir.
    SignalSpec("media.frame_brightness", kind="continuous", min_meaningful_delta=0.08),
    SignalSpec("media.frame_saturation", kind="continuous", min_meaningful_delta=0.08),
    SignalSpec("media.frame_contrast", kind="continuous", min_meaningful_delta=0.10),
    SignalSpec("media.frame_edge_density", kind="continuous", min_meaningful_delta=0.05),
    SignalSpec("media.frame_colorfulness", kind="continuous", min_meaningful_delta=0.10),
    # --- Akış ritüelleri (sözlük VERİDEN çıkar, kodda liste yok) ---
    SignalSpec("ritual.obj.*", kind="binary", min_meaningful_delta=0.5),
    SignalSpec("ritual.place.*", kind="binary", min_meaningful_delta=0.5),
    # --- Habitat (YALNIZCA camera_incidental + ölçülebilir arka plan) ---
    SignalSpec("habitat.is_daylight", kind="binary", min_meaningful_delta=0.5),
    SignalSpec("habitat.is_dark_lowkey", kind="binary", min_meaningful_delta=0.5),
    SignalSpec("habitat.person_count", kind="count", min_meaningful_delta=1.0),
    SignalSpec("habitat.is_solitary", kind="binary", min_meaningful_delta=0.5),
    # --- Somatik / bakış (kurgu-montaj karelerde ÜRETİLMEZ) ---
    SignalSpec("gaze.ear_mean", kind="continuous", min_meaningful_delta=0.03),
    SignalSpec("gaze.head_pitch", kind="continuous", min_meaningful_delta=5.0),
    SignalSpec("gaze.duchenne_contraction", kind="ratio", min_meaningful_delta=0.10),
    SignalSpec("gaze.engagement", kind="ratio", min_meaningful_delta=0.10),
    # --- Pillar Wave-1 zaman serisi (frequency_map["samples"]) ---
    SignalSpec("wave.energy", kind="continuous", min_meaningful_delta=0.05),
    SignalSpec("wave.post_count", kind="count", min_meaningful_delta=1.0),
    # --- Pillar Strata ön-hesaplanmış kayması (erken/geç karşılaştırması) ---
    SignalSpec("strata.drift.*", kind="continuous", min_meaningful_delta=0.3),
]


def default_registry() -> SignalRegistry:
    """Her çağrıda temiz registry döner (paylaşılan mutasyon yok)."""
    return SignalRegistry(DEFAULT_SPECS)
