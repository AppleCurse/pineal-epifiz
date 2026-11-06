"""Epistemik Katman, Model Alanları ve Sınır Durumları Kapsamlı Doğrulama Testleri."""

import math
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_core.services.epistemic import build_epistemic_state, clamp, VERIFICATION, CHANNEL_WEIGHT
from agent_core.services.llm_gateway import LLMGateway
from agent_core.domain.memory_models import PassionProfile, FrictionProfile, CognitiveStyle
from backend.routes.hook_studio import register_hook_studio_routes, HookResult


# ============================================================================
# 1. CLAMP (KELEPÇE) TESTLERİ: ASLA YÜKSELTMEZ, TAVANI AŞMAZ, KENAR DURUMLAR
# ============================================================================

def test_clamp_never_increases_confidence():
    """Tavan 0.9 iken model 0.3 ise kelepçe 0.3 dönmeli (asla yükseltmez)."""
    state = {"input_data_present": True, "confidence_ceiling": 0.9}
    assert clamp(0.3, state) == 0.3
    assert clamp(0.05, state) == 0.05


def test_clamp_caps_confidence_at_ceiling():
    """Model 0.95 iken tavan 0.4 ise kelepçe 0.4'e kırpmalı."""
    state = {"input_data_present": True, "confidence_ceiling": 0.4}
    assert clamp(0.95, state) == 0.40
    assert clamp(0.70, state) == 0.40


def test_clamp_zero_ceiling_returns_zero():
    """Tavan 0.0 iken model ne olursa olsun 0.0 dönmeli."""
    state = {"input_data_present": True, "confidence_ceiling": 0.0}
    assert clamp(0.99, state) == 0.0
    assert clamp(0.50, state) == 0.0


def test_clamp_input_absent_returns_zero():
    """Girdi yoksa (input_data_present=False) sonuç daima 0.0 olmalı."""
    state = {"input_data_present": False, "confidence_ceiling": 0.8}
    assert clamp(0.85, state) == 0.0
    assert clamp(None, {}) == 0.0


def test_clamp_edge_cases_nan_none_inf_invalid():
    """None, NaN, Inf, geçersiz string ve taşma değerleri güvenle 0.0 veya sınıra çekilmeli."""
    state = {"input_data_present": True, "confidence_ceiling": 0.75}
    assert clamp(None, state) == 0.0
    assert clamp("geçersiz", state) == 0.0
    assert clamp(float("nan"), state) == 0.0
    assert clamp(float("inf"), state) == 0.0
    assert clamp(-0.5, state) == 0.0
    # Model 1.4 gibi taşma döndürürse tavana (0.75) kırpılır
    assert clamp(1.4, state) == 0.75


# ============================================================================
# 2. EPİSTEMİK DURUM VE GİRDİ VS KANIT DOĞRULAMA AYRIMI
# ============================================================================

def test_epistemic_empty_payload():
    """Tamamen boş payload: girdi yok, tavan 0, data_confidence=False."""
    state = build_epistemic_state({}, profiles={})
    assert state["input_data_present"] is False
    assert state["data_confidence"] is False
    assert state["confidence_ceiling"] == 0.0
    assert state["channels_used"] == []


def test_epistemic_single_visual_channel():
    """Yalnızca görsel kanıt kanalı: tavan 0.9 olmalı."""
    state = build_epistemic_state({"visual": "görsel analiz verisi"}, profiles={})
    assert state["input_data_present"] is True
    assert state["confidence_ceiling"] == 0.9
    assert "visual" in state["channels_used"]
    # Bağımsız doğrulama olmadıkça data_confidence FALSE kalmalıdır
    assert state["data_confidence"] is False


def test_input_present_does_not_mean_data_confidence():
    """Girdi varlığı (input_data_present) tek başına data_confidence değildir."""
    # Sadece bio girdisi var ama bağımsız kanıt yok -> data_confidence False
    unverified_state = build_epistemic_state(
        {"bio": "Kullanıcı bio bilgisi"},
        profiles={"core_passions": ["Yazılım"]},
        has_verified_proof=False,
    )
    assert unverified_state["input_data_present"] is True
    assert unverified_state["data_confidence"] is False

    # Bağımsız doğrulama mühürlendiğinde -> data_confidence True
    verified_state = build_epistemic_state(
        {"bio": "Kullanıcı bio bilgisi"},
        profiles={"core_passions": ["Yazılım"]},
        has_verified_proof=True,
    )
    assert verified_state["input_data_present"] is True
    assert verified_state["data_confidence"] is True


# ============================================================================
# 3. KAVRAMSAL MODEL VE ALAN EŞLEME TESTLERİ (Doküman & Kod Uyumu)
# ============================================================================

def test_memory_models_support_conceptual_aliases():
    """Dokümantasyondaki ve koddaki alanların her ikisi de Pydantic modellerinde desteklenir."""
    # PassionProfile: passion_anchors <-> core_passions, secondary_interests <-> energizing_topics
    p = PassionProfile(passion_anchors=["Derin Öğrenme"], secondary_interests=["Robotik"])
    assert p.core_passions == ["Derin Öğrenme"]
    assert p.energizing_topics == ["Robotik"]
    assert p.passion_anchors == ["Derin Öğrenme"]
    assert p.secondary_interests == ["Robotik"]

    # FrictionProfile: forbidden_territories <-> boundary_signals / stress_triggers
    f = FrictionProfile(forbidden_territories=["Özel Hayat"])
    assert f.boundary_signals == ["Özel Hayat"]
    assert f.forbidden_territories == ["Özel Hayat"]

    # CognitiveStyle: thinking_style <-> complexity_level
    c = CognitiveStyle(thinking_style="Kavramsal / Analitik")
    assert c.complexity_level == "Kavramsal / Analitik"
    assert c.thinking_style == "Kavramsal / Analitik"


# ============================================================================
# 4. ARKETİP BAZLI KIRMIZI ÇİZGİ KORUMASI / PENETRASYON AYRIMI
# ============================================================================

def test_hook_studio_archetype_rule_separation():
    """authentic_connection kırmızı çizgiyi korur; shadow_hook defansı deler."""
    app = FastAPI()
    mock_gw = MagicMock(spec=LLMGateway)
    captured_prompts = []

    async def mock_query(prompt, **kwargs):
        captured_prompts.append(prompt)
        return HookResult(
            opening_message="Test mesajı",
            opening_topic="Test konusu",
            rationale="Gerekçe",
            archetype="test",
            confidence=0.85,
        )

    mock_gw.query_json_chain = AsyncMock(side_effect=mock_query)

    register_hook_studio_routes(
        app,
        rate_limit=lambda ip, action: True,
        rate_identity=lambda req: "127.0.0.1",
        gateway_provider=lambda: mock_gw,
        get_executor=None,
    )
    client = TestClient(app)

    base_payload = {
        "client_id": "test_room",
        "target_username": "target_user",
        "target_profile": {"bio": "Mimar", "posts": ["Şehir planlama"]},
        "passions": {"core_passions": ["Mimari"]},
        "frictions": {"sensitivities": ["Gürültü"], "stress_triggers": ["Son teslimler"]},
    }

    # 1. authentic_connection: Kırmızı çizgi korumalı olmalı
    client.post("/api/hook/generate", json={**base_payload, "intent": "authentic_connection"})
    auth_prompt = captured_prompts[-1]
    assert "HASSASİYETLERE VE SINIRLARA ASLA BASMA (Kırmızı Çizgi Koruması)" in auth_prompt
    assert "TAKTİKSEL PSİKOLOJİK HEDEFLEME & YARA İZİ" not in auth_prompt

    # 2. shadow_hook: Taktiksel penetrasyon kuralı aktif olmalı
    client.post("/api/hook/generate", json={**base_payload, "intent": "shadow_hook"})
    shadow_prompt = captured_prompts[-1]
    assert "TAKTİKSEL PSİKOLOJİK HEDEFLEME & YARA İZİ" in shadow_prompt
    assert "Karşı tarafın kırmızı çizgilerine ve hassasiyetlerine asla basma" not in shadow_prompt
