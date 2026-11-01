"""ResonanceSynthesizer — kullanıcı bağlamı sözleşmesi.

[BOSS-3] Röntgen bulgusu: ajan `user_profile["bio"]/["posts"]` okuyordu; üretim
yolu ise `private_rituals` / `late_night_playlist` / `secret_envies` taşıyor
(`platform_registry.build_user_context`). Sonuç: her görevde
`user_context_unavailable` ile erken dönüş → `suggested_opening_message` HİÇ
üretilmiyordu. Bu dosya testleri ÜRETİM ŞEKLİYLE yazar; şekil ayrışırsa kızar.
"""

from unittest.mock import AsyncMock, MagicMock

from agent_core.agents.resonance_synthesizer import ResonanceSynthesizerAgent
from agent_core.domain.memory_models import AuthenticBridge
from agent_core.services.llm_gateway import LLMGateway
from agent_core.services.platform_registry import build_user_context

# Üretim yolu: backend.api.api_initiate ve scripts/run_task.py bu yardımcıyı
# kullanır. Testler de aynı yardımcıyı çağırır → sözleşme tek kaynaktan gelir.
PRODUCTION_USER_SECTIONS = build_user_context(
    ["Gece okumaları", "felsefe"],
    ["neşet ertaş"],
    ["derin bağ kurmak"],
)


def _gateway(return_value=None, side_effect=None):
    gateway = MagicMock(spec=LLMGateway)
    gateway.query_json_chain = AsyncMock(return_value=return_value, side_effect=side_effect)
    return gateway


def _target_context():
    return {
        "passions": {"core_passions": ["Sokak Fotoğrafçılığı"]},
        "frictions": {"sensitivities": ["Yüzeysellik"]},
        "cognitive": {"communication_tone": "samimi"},
        "sacred_rules": "Ucuz manipülasyon yapma, sahici ol.",
    }


async def test_production_payload_reaches_the_llm():
    """ÜRETİM şekli (ritüel/çalma listesi/imrendikler) ajanı çalıştırmalı."""
    gateway = _gateway(return_value=AuthenticBridge(
        shared_passions=["Mimari Estetik"],
        complementary_perspectives=["Işık ve Gölge Yorumları"],
        resonance_score=0.92,
        authentic_opening_topic="Kentsel Dönüşümde Estetik Detaylar",
        conversation_starter_rationale="İki taraf da görsel kompozisyona önem veriyor.",
        suggested_opening_message="Merhaba! Son paylaşımınızdaki ışık açısı çok etkileyiciydi.",
        confidence=0.95,
    ))
    agent = ResonanceSynthesizerAgent(llm_gateway=gateway)

    result = await agent.execute({**PRODUCTION_USER_SECTIONS, **_target_context()})

    assert gateway.query_json_chain.await_count == 1, (
        "üretim şekliyle ajan LLM'e hiç gitmedi (eski bio/posts sözleşmesi kırığı)"
    )
    assert result.suggested_opening_message, "ilk temas mesajı üretilmedi"
    assert result.data_confidence is True

    prompt = gateway.query_json_chain.await_args.kwargs["prompt"]
    assert "Kişisel Ritüeller" in prompt
    assert "Gece Çalma Listesi" in prompt
    assert "Gizli İmrendikleri" in prompt


async def test_user_context_string_form_is_also_accepted():
    """`user_context` (metin biçimi) tek başına da yeterli olmalı."""
    sections = {"user_context": {"rituals": "çay, kitap", "playlist": "caz", "envies": ""}}
    gateway = _gateway(return_value=AuthenticBridge(confidence=0.9, resonance_score=0.5, suggested_opening_message="Merhaba"))
    agent = ResonanceSynthesizerAgent(llm_gateway=gateway)

    result = await agent.execute({**sections, **_target_context()})

    assert gateway.query_json_chain.await_count == 1
    assert result.suggested_opening_message == "Merhaba"


async def test_optional_bio_and_posts_are_still_supported():
    """Ek istemciler bio/posts sağlarsa kullanılır (kaldırılmadı, genişletildi)."""
    gateway = _gateway(return_value=AuthenticBridge(confidence=0.9, suggested_opening_message="Merhaba"))
    agent = ResonanceSynthesizerAgent(llm_gateway=gateway)

    await agent.execute({
        "user_profile": {"bio": "Görsel hikaye anlatıcısı.", "posts": ["Işığın peşinde."]},
        **_target_context(),
    })

    prompt = gateway.query_json_chain.await_args.kwargs["prompt"]
    assert "Kullanıcı Biyografisi: Görsel hikaye anlatıcısı." in prompt
    assert "Işığın peşinde." in prompt


async def test_empty_user_evidence_returns_honest_fallback():
    """Boş kullanıcı verisi uydurulmaz: dürüst fallback + LLM çağrısı YOK."""
    gateway = _gateway(return_value=AuthenticBridge(confidence=0.9))
    agent = ResonanceSynthesizerAgent(llm_gateway=gateway)

    result = await agent.execute({
        "user_profile": {"private_rituals": [], "late_night_playlist": [], "secret_envies": []},
        "user_context": {"rituals": "", "playlist": "", "envies": ""},
        **_target_context(),
    })

    assert isinstance(result, AuthenticBridge)
    assert result.confidence == 0.0
    assert result.data_confidence is False
    assert result.fallback_reason == "user_context_unavailable"
    assert gateway.query_json_chain.await_count == 0


async def test_missing_target_context_returns_target_fallback():
    gateway = _gateway(return_value=AuthenticBridge(confidence=0.9))
    agent = ResonanceSynthesizerAgent(llm_gateway=gateway)

    result = await agent.execute(PRODUCTION_USER_SECTIONS)

    assert result.fallback_reason == "target_context_unavailable"
    assert gateway.query_json_chain.await_count == 0


async def test_llm_failure_surfaces_as_llm_unavailable():
    gateway = _gateway(side_effect=RuntimeError("LLM Hatası"))
    agent = ResonanceSynthesizerAgent(llm_gateway=gateway)

    result = await agent.execute({**PRODUCTION_USER_SECTIONS, **_target_context()})

    assert result.confidence == 0.0
    assert result.data_confidence is False
    assert result.fallback_reason == "llm_unavailable"
    assert result.suggested_opening_message == ""


async def test_outreach_intent_without_user_rituals_produces_opening_message():
    """Kullanıcı kişisel ritüel vermese bile iletişim hedefiyle açılış kancası üretilmelidir."""
    gateway = _gateway(return_value=AuthenticBridge(
        shared_passions=["Sokak Fotoğrafçılığı"],
        complementary_perspectives=["Görsel Dil"],
        resonance_score=0.88,
        authentic_opening_topic="Sokak Estetiği",
        conversation_starter_rationale="Hedefin tutkularına odaklanıldı.",
        suggested_opening_message="Fotoğraflarınızdaki ışık dengesi çok etkileyici.",
        confidence=0.9,
    ))
    agent = ResonanceSynthesizerAgent(llm_gateway=gateway)

    result = await agent.execute({
        "user_profile": {"private_rituals": [], "late_night_playlist": [], "secret_envies": []},
        "user_context": {"rituals": "", "playlist": "", "envies": ""},
        "outreach_intent": "Doğal ve samimi ilk temas; fotoğraflarından yola çıkarak merak uyandırmak",
        **_target_context(),
    })

    assert gateway.query_json_chain.await_count == 1
    assert result.suggested_opening_message == "Fotoğraflarınızdaki ışık dengesi çok etkileyici."
    assert result.data_confidence is True
    prompt = gateway.query_json_chain.await_args.kwargs["prompt"]
    assert "İletişim Hedefi & Niyeti" in prompt
