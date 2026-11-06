"""Karanlık Üçlü (Dark Triad) Kanıt ve Psikodinamik Derinlik Ölçüm Testleri."""

import pytest
from agent_core.psychology.dark_triad import DarkTriadAnalyzer, DarkTriadProfile
from agent_core.shadow.shadow_executor import ShadowExecutor


def test_dark_triad_ordinary_text_remains_unmeasured():
    """Sıradan metinlerde kanıt/derinlik sinyali yoksa trait_scores_measured=False kalmalı ve traitler 0.0 olmalı."""
    analyzer = DarkTriadAnalyzer()
    profile = analyzer.analyze({"bio": "Yazılımcı ve doğa tutkunu.", "posts": ["Kod yazmak harika."]})
    assert profile.trait_scores_measured is False
    assert profile.narcissism == 0.0
    assert profile.machiavellianism == 0.0
    assert profile.psychopathy == 0.0
    assert profile.exploitability == 0.0
    assert profile.evidence_quotes == {}

    strategy = analyzer.generate_strategy(profile)
    assert strategy["vector"] == "unavailable"


def test_dark_triad_with_depth_reaction_formation_measures_narcissism():
    """Tepki oluşturma (reaction formation >= 0.40) narsisizm eğilimini somut alıntıyla ölçer."""
    analyzer = DarkTriadAnalyzer()
    depth = {
        "verdict": "ok",
        "reaction_formation_index": 0.52,
        "channels": {
            "declaration": {"signals": {"repetition_score": 0.1}},
            "rhythm": {"signals": {"n_ruptures": 0, "rupture_kinds": []}},
        },
        "evidence_quotes": ["Ben her zaman en mükemmel standardı kurarım."],
    }
    profile = analyzer.analyze({"bio": "Vitrin mimarı"}, depth=depth)
    assert profile.trait_scores_measured is True
    assert profile.narcissism >= 0.70
    assert "narcissism" in profile.evidence_quotes
    assert len(profile.evidence_quotes["narcissism"]) > 0

    strategy = analyzer.generate_strategy(profile)
    assert strategy["vector"] == "mirroring"
    assert "seçilmiş" in strategy["tactic"].lower() or "özel" in strategy["tactic"].lower()


def test_dark_triad_with_depth_repetition_measures_machiavellianism():
    """Tekrar skoru (repetition_score >= 0.40) makyavelist faydacılık eğilimini ölçer."""
    analyzer = DarkTriadAnalyzer()
    depth = {
        "verdict": "ok",
        "reaction_formation_index": 0.1,
        "channels": {
            "declaration": {"signals": {"repetition_score": 0.48}},
            "rhythm": {"signals": {"n_ruptures": 0, "rupture_kinds": []}},
        },
        "evidence_quotes": ["Güç dengelerini sürekli lehimize çevirmeliyiz."],
    }
    profile = analyzer.analyze({"bio": "Stratejist"}, depth=depth)
    assert profile.trait_scores_measured is True
    assert profile.machiavellianism >= 0.60
    assert "machiavellianism" in profile.evidence_quotes

    strategy = analyzer.generate_strategy(profile)
    assert strategy["vector"] == "alliance"
    assert "çıkar" in strategy["tactic"].lower()


def test_dark_triad_with_depth_rupture_measures_psychopathy():
    """Ritim kırılması (rupture >= 1 veya entropy_jump) psikopati/risk açlığını ölçer."""
    analyzer = DarkTriadAnalyzer()
    depth = {
        "verdict": "ok",
        "reaction_formation_index": 0.1,
        "channels": {
            "declaration": {"signals": {"repetition_score": 0.1}},
            "rhythm": {"signals": {"n_ruptures": 2, "rupture_kinds": ["entropy_jump"]}},
        },
        "evidence_quotes": ["Her an patlamaya hazır bir voltaj taşıyorum."],
    }
    profile = analyzer.analyze({"bio": "Adrenalin arayan"}, depth=depth)
    assert profile.trait_scores_measured is True
    assert profile.psychopathy >= 0.50
    assert "psychopathy" in profile.evidence_quotes

    strategy = analyzer.generate_strategy(profile)
    assert strategy["vector"] == "thrill"
    assert "heyecan" in strategy["tactic"].lower() or "risk" in strategy["tactic"].lower()


def test_dark_triad_with_direct_evidence_quotes():
    """profile_data içindeki doğrudan alıntılar trait skorunu üretir."""
    analyzer = DarkTriadAnalyzer()
    profile_data = {
        "bio": "Kurucu",
        "evidence_quotes": {
            "narcissism": ["Bu sektörde benden daha iyisi yok."],
        },
    }
    profile = analyzer.analyze(profile_data)
    assert profile.trait_scores_measured is True
    assert profile.narcissism == 0.75
    assert profile.exploitability > 0.0
    assert "narcissism" in profile.evidence_quotes


def test_shadow_executor_serializes_unmeasured_as_null_and_measured_as_float():
    """Ölçülmemiş trait'ler API çıktısında null olur, ölçülmüş olanlar sayısal kalır."""
    unmeasured = DarkTriadProfile()
    payload_unmeasured, has_traits, _ = ShadowExecutor._dark_profile_payload(unmeasured)
    assert has_traits is False
    assert payload_unmeasured["narcissism"] is None
    assert payload_unmeasured["machiavellianism"] is None
    assert payload_unmeasured["psychopathy"] is None
    assert payload_unmeasured["exploitability"] is None

    measured = DarkTriadProfile(narcissism=0.75, exploitability=0.6, trait_scores_measured=True)
    payload_measured, has_traits_m, _ = ShadowExecutor._dark_profile_payload(measured)
    assert has_traits_m is True
    assert payload_measured["narcissism"] == 0.75
    assert payload_measured["machiavellianism"] is None
    assert payload_measured["exploitability"] == 0.60
