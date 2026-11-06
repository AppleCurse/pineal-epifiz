"""Forensic [017]/[018]: data_score kanıt kalitesini yansıtmalı.

Kurallar:
- "Alan dolu" tek başına 1.0 DEĞİLDİR; placeholder ibareler ("bulunamadı",
  "veri yok", "bilinmiyor", "n/a", "unknown"...) kanıt sayılmaz.
- Metadata alanları (model/provider/süre/token/...) veri kalitesi oranını
  ŞİŞİREMEZ.
- Uzunluk/eleman sayısı yine de confidence üretmez (P1-B2 sözleşmesi korunur).
"""
from pydantic import BaseModel

from agent_core.domain.memory_models import CognitiveStyle, PassionProfile
from agent_core.services.uncertainty_engine import UncertaintyEngine


class DummyResult(BaseModel):
    name: str = ""
    evidence: list = []
    extra: int | None = None
    confidence: float = 0.8


class MetadataResult(BaseModel):
    name: str = "gerçek veri"
    evidence: list = ["kanıt"]
    extra: int = 1
    model: str = "x/y"
    provider: str = "openrouter"
    usage: dict = {"tokens": 1}
    duration_ms: int = 5
    confidence: float = 0.8


class PlaceholderOnlyResult(BaseModel):
    name: str = "veri yok"
    evidence: list = ["n/a"]
    extra: int | None = None
    confidence: float = 0.8


def test_placeholder_strings_are_zero_evidence():
    engine = UncertaintyEngine()
    for marker in ("bilinmiyor", "veri yok", "n/a", "-", "unknown", "sonuç yok"):
        assert engine._score_field_value(marker, empty_list_penalty=0.12) == 0.0, marker
    # 7-pillar deterministik yetersiz-veri notları da kanıt DEĞİLDİR
    for note in (
        "SEISMOS: 0 gönderi < min 5.",
        "VOID: 0 token < min 40.",
        "GRAVITY: Yetersiz gönderi veya meta veri.",
        "KEY: Tüm motorlar yetersiz veri döndü — sentez yapılamadı.",
    ):
        assert engine._score_field_value(note, empty_list_penalty=0.12) == 0.0, note
    # Gerçek tamamlanma notu kanıttır
    assert engine._score_field_value(
        "KEY: Sentez tamamlandı · güven=0.80 · 6/6 motor aktif.",
        empty_list_penalty=0.12,
    ) == 1.0
    # Uzunluk hâlâ skor üretmez
    assert engine._score_field_value("a", empty_list_penalty=0.12) == 1.0
    assert engine._score_field_value("x" * 200, empty_list_penalty=0.12) == 1.0


def test_placeholder_lists_are_not_evidence():
    engine = UncertaintyEngine()
    # Tamamı placeholder -> sıfır kanıt
    assert engine._score_field_value(
        ["veri yok", "bulunamadı"], empty_list_penalty=0.12
    ) == 0.0
    # Karışık -> kanıt oranı (uzunluk değil, ANLAM)
    assert engine._score_field_value(
        ["gerçek veri", "veri yok"], empty_list_penalty=0.12
    ) == 0.5
    # Tamamı gerçek -> sabit 1.0 (eleman sayısı/uzunluk fark etmez)
    assert engine._score_field_value(["a"], empty_list_penalty=0.12) == 1.0
    assert engine._score_field_value(["x" * 300], empty_list_penalty=0.12) == 1.0
    assert engine._score_field_value([], empty_list_penalty=0.12) == 0.12


def test_placeholder_dicts_are_not_evidence():
    engine = UncertaintyEngine()
    assert engine._score_field_value(
        {"type": "unknown", "defense": "unknown"}, empty_list_penalty=0.12
    ) == 0.0
    assert engine._score_field_value(
        {"type": "agresif", "reason": "yok"}, empty_list_penalty=0.12
    ) == 0.4
    assert engine._score_field_value(
        {"type": "agresif", "reason": "gerçek"}, empty_list_penalty=0.12
    ) == 0.8


def test_cognitive_defaults_with_fake_high_confidence_are_suspicious():
    """[018] düzeltmesi: LLM 'unknown' şablonunu doldurup confidence=0.9
    verse bile bu KANIT değildir; profil pas geçemez."""
    engine = UncertaintyEngine()
    fabricated = CognitiveStyle(confidence=0.9, data_confidence=True)
    report = engine.evaluate(fabricated, "cognitive_profiler")
    assert report.is_suspicious, report.reason
    # is_empty dalı sözleşmesi: 0.1 (sahte yüksek LLM güveni geçersizdir)
    assert report.confidence == 0.1, report.confidence
    assert report.data_score == 0.0, report.data_score


def test_real_cognitive_profile_passes():
    engine = UncertaintyEngine()
    real = CognitiveStyle(
        communication_tone="analitik",
        complexity_level="teknik",
        thinking_style="rasyonel-mantıksal",
        humor_style="kuru mizah",
        social_orientation="gözlemci",
        confidence=0.9,
        data_confidence=True,
    )
    report = engine.evaluate(real, "cognitive_profiler")
    assert not report.is_suspicious, report.reason
    assert report.confidence == 0.9, report.confidence


def test_metadata_fields_do_not_inflate_data_score():
    """[017] düzeltmesi: model/provider/süre/token alanları oranı
    şişiremez ve boş veriyi kurtaramaz."""
    engine = UncertaintyEngine()
    plain = DummyResult(name="gerçek", evidence=["kanıt"], extra=1)
    with_meta = MetadataResult(
        name="gerçek", evidence=["kanıt"], extra=1, confidence=0.8
    )
    plain_meta = with_meta.model_dump()
    # metadata alanlı ve alansız model aynı skoru üretmeli
    score_plain, _ = engine.calculate_data_score(
        plain.model_dump(), "test_agent"
    )
    score_meta, breakdown_meta = engine.calculate_data_score(
        plain_meta, "test_agent"
    )
    assert score_plain == score_meta == 1.0
    assert set(breakdown_meta["metadata_excluded"]) >= {
        "model", "provider", "usage", "duration_ms"
    }

    # Placeholder-only profil metadata eklense de 1.0'a çıkamaz
    placeholder = PlaceholderOnlyResult(name="veri yok", evidence=["n/a"], extra=None)
    total_placeholder = placeholder.model_dump()
    total_placeholder["model"] = "x/y"
    score_fake, _ = engine.calculate_data_score(total_placeholder, "test_agent")
    assert score_fake == 0.0, score_fake


def test_weighted_placeholder_lists_drop_data_score():
    """Ağırlıklı yolda placeholder-şişkin listeler kanıt sayılmaz."""
    engine = UncertaintyEngine()
    inflated = PassionProfile(
        core_passions=["veri yok"],
        energizing_topics=["bulunamadı"],
        flow_triggers=[],
        sentiment_polarity=0.5,
        evidence_quotes=["n/a"],
        confidence=0.9,
        data_confidence=True,
    )
    report = engine.evaluate(inflated, "passion_mapper")
    assert report.is_suspicious, report.reason
    assert report.confidence < 0.70, report.confidence
    # breakdown kanıt kalitesini açıkça raporlar
    field_entry = report.breakdown["core_passions"]
    assert field_entry["evidence_bearing"] is False
    assert field_entry["score"] == 0.0


def test_is_empty_uses_evidence_quality_not_field_presence():
    """Dolu görünen ama placeholder içeren profil 'is_empty' sayılır."""
    engine = UncertaintyEngine()
    report = engine.evaluate(
        PlaceholderOnlyResult(name="veri yok", evidence=["n/a"], extra=None),
        "test_agent",
    )
    assert report.is_suspicious, report.reason
    assert report.confidence == 0.1, report.confidence
