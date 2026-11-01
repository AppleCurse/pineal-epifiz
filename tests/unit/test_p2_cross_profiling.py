"""[P2 · DENETİM 2026-10-16] Çapraz profilleme — deterministiklik ve dürüstlük.

Denetim maddesi 11: "deterministik ve kanıtlı eşleştirme yaz: (a) aynı kullanıcı
adı varyantı, (b) bio'daki ortak harici link, (c) socid ortak ID. Her eşleşme
``EvidenceItem``; güven skoru **'kapsam'** etiketiyle, olasılık olarak sunulmadan."

Bu dosya o sözleşmeyi kilitler. Her test, düzeltme geri alınınca KIRMIZIya
dönmelidir (revert-doğrulama).
"""

from __future__ import annotations

import pytest

from agent_core.domain.evidence_models import EvidenceItem
from agent_core.services.cross_profiler import (
    SIGNAL_WEIGHTS,
    CrossProfileCorrelation,
    correlate_profiles,
)


# ─────────────────────────────────────────────────────────────────────────────
# YARDIMCILAR
# ─────────────────────────────────────────────────────────────────────────────
def _target(**overrides):
    tp = {
        "username": "@alice",
        "platform": "instagram",
        "bio": "",
        "detected_urls": [],
    }
    tp.update(overrides)
    return tp


# ─────────────────────────────────────────────────────────────────────────────
# 1. DETERMİNİSTİK SİNYALLER
# ─────────────────────────────────────────────────────────────────────────────
def test_exact_handle_across_platforms_matches():
    """(a) Birebir aynı kullanıcı adı → eşleşme."""
    res = correlate_profiles(
        _target(detected_urls=["https://x.com/alice"])
    )
    assert isinstance(res, CrossProfileCorrelation)
    assert res.cluster_count == 1
    match = res.matches[0]
    assert match.match_method == "exact_handle"
    assert "exact_handle" in match.signals
    assert match.epistemic_type == "inference"


def test_normalized_handle_variant_matches():
    """(a) Nokta/altçizgi varyantı → eşleşme (daha zayıf sinyal)."""
    res = correlate_profiles(
        _target(username="@john.doe", detected_urls=["https://x.com/johndoe"])
    )
    assert res.cluster_count == 1
    assert "normalized_handle" in res.matches[0].signals


def test_bio_cross_link_matches_only_the_exact_url():
    """(b) Biyografideki bağlantı → eşleşme; ALT DİZE eşleşme olmaz."""
    res = correlate_profiles(
        _target(
            username="@main_hero",
            bio="Follow my work on https://github.com/main_hero_codes",
            detected_urls=["https://github.com/main_hero_codes"],
        )
    )
    assert res.cluster_count == 1
    assert "self_declared_link" in res.matches[0].signals


def test_substring_url_in_bio_is_not_a_match():
    """Alt dize eşleşmesi YANLIŞ POZİTİF üretmemeli.

    Biyografi "https://x.com/alicexyz" adresini içeriyor; tespit edilen hesap
    "x.com/alice". Eski kod ("hesabın adresi biyografinin ALT DİZESİ mi?") bu
    ikisini eşleştiriyordu — oysa adresler FARKLI. Doğru davranış: eşleşme yok.
    """
    res = correlate_profiles(
        _target(
            username="@bob",
            bio="bana ulaş: https://x.com/alicexyz",
            detected_urls=["https://x.com/alice"],
        )
    )
    assert res.cluster_count == 0, f"alt dize eşleşmesi üretildi: {res.matches}"


def test_socid_shared_id_matches_two_profiles():
    """(c) socid iki URL'de aynı kimliği okudu → eşleşme."""
    res = correlate_profiles(
        _target(
            username="@alice",
            detected_urls=[
                "https://linkedin.com/in/alice",
                "https://github.com/alice",
            ],
            socid_identities=[
                {"url": "https://linkedin.com/in/alice", "fields": {"user_id": "99123"}},
                {"url": "https://github.com/alice", "fields": {"user_id": "99123"}},
            ],
        )
    )
    assert res.cluster_count >= 1
    assert any("shared_platform_id" in m.signals for m in res.matches)


def test_socid_id_does_not_match_an_unrelated_handle():
    """socid kimlik alanı KULLANICI ADI DEĞİLDİR.

    `user_id=4242` ile başka bir platformdaki `@4242` hesabı eşleşmemeli —
    rastgele çakışma yanlış eşleşme (false positive) üretirdi.
    """
    res = correlate_profiles(
        _target(
            username="@alice",
            detected_urls=[
                "https://linkedin.com/in/alice",
                "https://x.com/4242",
            ],
            socid_identities=[
                {"url": "https://linkedin.com/in/alice", "fields": {"user_id": "4242"}},
            ],
        )
    )
    for m in res.matches:
        assert "4242" not in (m.source_handle, m.target_handle), (
            f"socid id bir kullanıcı adı gibi eşleşti: {m}"
        )


def test_generic_handles_never_match():
    """Jenerik kullanıcı adları (admin/login/...) eşleşme üretmez."""
    res = correlate_profiles(
        _target(username="@admin", detected_urls=["https://x.com/admin"])
    )
    assert res.cluster_count == 0


def test_same_platform_accounts_are_not_cross_matches():
    """Aynı platformdaki iki hesap "çapraz profil" eşleşmesi değildir.

    `x.com` ve `twitter.com` aynı platformdur (ikisi de "x") → ikisi arasında
    eşleşme üretilmez.
    """
    res = correlate_profiles(
        _target(
            username="@alice",
            platform="x",
            detected_urls=[
                "https://twitter.com/alice",
            ],
        )
    )
    assert res.cluster_count == 0, f"aynı platform eşleşmesi üretildi: {res.matches}"


def test_no_signal_no_match():
    """Deterministik sinyal yoksa eşleşme YOK (olasılıksal eşleştirme yok)."""
    res = correlate_profiles(
        _target(username="@alice", detected_urls=["https://x.com/bob"])
    )
    assert res.cluster_count == 0
    assert res.items == []


# ─────────────────────────────────────────────────────────────────────────────
# 2. KAPSAM SKORU: OLASILIK DEĞİL
# ─────────────────────────────────────────────────────────────────────────────
def test_coverage_is_a_scope_score_not_a_probability():
    """Skor "kapsam" etiketli; kanıtın ``confidence`` alanı BOŞ kalır."""
    res = correlate_profiles(
        _target(detected_urls=["https://x.com/alice"])
    )
    match = res.matches[0]
    assert match.confidence_label == "kapsam"
    assert match.coverage == pytest.approx(SIGNAL_WEIGHTS["exact_handle"])

    item = res.items[0]
    assert isinstance(item, EvidenceItem)
    assert item.epistemic_type == "inference"
    assert item.source_engine == "cross_profiler"
    # Alan sözleşmesi: kalibre edilmemiş skor ``confidence`` alanına GİRMEZ.
    assert item.confidence is None
    assert item.source_metrics["coverage_label"] == "kapsam"
    assert item.source_metrics["coverage_is_probability"] is False
    assert item.scope["confidence_label"] == "kapsam"
    # Metin de olasılık gibi sunmaz.
    assert "olasılık DEĞİLDİR" in item.content
    assert "%" not in item.content


def test_signals_accumulate_coverage():
    """Birden çok boyut yandığında kapsam toplanır (belgelenmiş ağırlıklar)."""
    res = correlate_profiles(
        _target(
            username="@main_hero",
            bio="https://github.com/main_hero",
            detected_urls=["https://github.com/main_hero"],
        )
    )
    assert res.cluster_count == 1
    signals = res.matches[0].signals
    assert "self_declared_link" in signals
    assert "exact_handle" in signals
    expected = SIGNAL_WEIGHTS["self_declared_link"] + SIGNAL_WEIGHTS["exact_handle"]
    assert res.matches[0].coverage == pytest.approx(expected)
    assert res.matches[0].coverage <= 1.0


def test_every_match_produces_one_evidence_item():
    """Her eşleşme tam olarak bir ``EvidenceItem`` üretir."""
    res = correlate_profiles(
        _target(
            username="@alice",
            detected_urls=[
                "https://x.com/alice",
                "https://github.com/alice",
            ],
        )
    )
    assert res.cluster_count == len(res.matches) == len(res.items)
    for item in res.items:
        assert item.provenance_refs, "eşleşmenin kaynak adresi kanıtta olmalı"


def test_evidence_reaches_the_canonical_chain():
    """Kanıt zincirine girer (pillar paketi boş olsa bile)."""
    from agent_core.services.pillar_evidence_adapter import adapt_pillar_bundle

    res = correlate_profiles(
        _target(detected_urls=["https://x.com/alice"])
    )
    items = adapt_pillar_bundle(None, extra_items=list(res.items))
    assert len(items) == 1
    assert items[0].source_engine == "cross_profiler"
