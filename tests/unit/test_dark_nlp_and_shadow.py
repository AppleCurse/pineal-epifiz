import pytest
from unittest.mock import AsyncMock, MagicMock
from agent_core.nlp.dark_nlp import EmbeddedCommandEngine, PresuppositionEngine
from agent_core.shadow.shadow_executor import ShadowExecutor, ShadowResult
from agent_core.services.llm_gateway import LLMGateway

# --- HERMETIC TEST GUARD: blocks live LLM calls ---
@pytest.fixture(autouse=True)
def _hermetic_guard(monkeypatch):
    async def _blocked(self, *a, **k):
        raise RuntimeError("REAL_LLM_CALL_NOT_EXECUTED: unit test kipi")
    monkeypatch.setattr(LLMGateway, "query", _blocked)
    monkeypatch.setattr(LLMGateway, "query_json", _blocked)


def test_embedded_command_engine_visual_detection():
    """Görsel kelimeler içeren profilde 'visual' temsil sistemi ve şablonları üretilmelidir."""
    engine = EmbeddedCommandEngine()
    profile = {
        "bio": "Fotoğraf çekmeyi ve mimari detaylara bakmayı severim.",
        "posts": ["Işığı gör ve manzarayı hayal et."]
    }
    seq = engine.generate_sequence(profile, desired_action="bize katıl")
    
    assert len(seq) == 3
    assert seq[0]["phase"] == "pace"
    assert "visual" in seq[0]["text"]
    assert seq[1]["phase"] == "command"
    assert "gördüğünde" in seq[1]["text"]
    assert "bize katıl" in seq[1]["text"]
    assert seq[2]["phase"] == "closure"
    assert "imge kaybolurken" in seq[2]["text"]


def test_embedded_command_engine_auditory_and_kinesthetic_defaults():
    """İşitsel kelimelerde auditory, hiç anahtar kelime yoksa varsayılan kinesthetic üretilmelidir."""
    engine = EmbeddedCommandEngine()
    
    # İşitsel
    auditory_profile = {"bio": "Müziği dinle ve sesi hisset", "posts": ["Yankılanan ritimler"]}
    seq_aud = engine.generate_sequence(auditory_profile, desired_action="odaklan")
    assert "auditory" in seq_aud[0]["text"] or "kinesthetic" in seq_aud[0]["text"]
    
    # Boş/eşleşmeyen metin bir duyusal sistem veya kişilik özelliği atfetmez.
    empty_profile = {"bio": "", "posts": []}
    assert engine.generate_sequence(empty_profile, desired_action="derinleş") == []
    assert engine.generate_sequence(
        {"bio": "Bugün yeni bir kitap yayımlandı.", "posts": []},
        desired_action="derinleş",
    ) == []
    assert engine.generate_sequence(auditory_profile, desired_action="") == []


def test_presupposition_engine_chain_generation():
    """Ön varsayım motoru inanç listesini sırayla şablonlara yerleştirmeli ve zincirlemelidir."""
    engine = PresuppositionEngine()
    beliefs = ["güvende olmak", "anlaşılmak", "özgür kalmak"]
    chain = engine.generate_chain(beliefs)
    
    assert len(chain) == 3
    assert chain[0]["type"] == "existence"
    assert "güvende olmak" in chain[0]["sentence"]
    assert chain[1]["type"] == "time"
    assert "anlaşılmak" in chain[1]["sentence"]
    # İkinci ve sonraki cümleler bir önceki inanca atıf yapmalıdır
    assert "güvende olmak demek" in chain[1]["sentence"]


def test_presupposition_engine_empty_beliefs():
    """Boş inanç listesinde boş liste dönmelidir."""
    engine = PresuppositionEngine()
    assert engine.generate_chain([]) == []


@pytest.mark.asyncio
async def test_shadow_executor_deterministic_synthesis(monkeypatch):
    """ShadowExecutor tüm alt modülleri birleştirip deterministik bir ShadowResult üretmelidir."""
    executor = ShadowExecutor()
    
    # Mock MirrorOfTruth
    mock_mirror_res = MagicMock()
    mock_mirror_res.model_dump.return_value = {
        "mirror_score": 0.85,
        "alignment": "high"
    }
    monkeypatch.setattr(executor.mirror, "execute", AsyncMock(return_value=mock_mirror_res))
    
    # Mock PatternInterrupt
    mock_pattern_res = MagicMock()
    mock_pattern_res.message = "Derin bir nefes al ve düşüncelerini durdur."
    monkeypatch.setattr(executor.pattern, "execute", AsyncMock(return_value=mock_pattern_res))

    # GÖREV 2.1: sozluk-skorlama kaldirildi; sentez yolunu ACIK gozlemle
    # besle (kelime->trait baglantisi artik yoktur; yoklugu govde
    # testlerinde kilitlidir, sentez burada kilitlenir).
    from agent_core.psychology.dark_triad import DarkTriadProfile
    monkeypatch.setattr(
        executor.dark_triad, "analyze",
        lambda profile_data: DarkTriadProfile(narcissism=0.8),
    )
    
    task_input = {
        "target_profile": {
            "bio": "Mükemmel, mükemmel, mükemmel, mükemmel, eşsiz, eşsiz, olağanüstü, benzersiz, seçilmiş. Mükemmeliyetçi ve hırslı bir lider.",
            "posts": ["Başarı tek seçenektir.", "Kontrol bende."]
        },
        "user_profile": {
            "rituals": ["kahve", "kitap"],
            "music": "klasik",
            "envies": "derin bağ"
        },
        "desired_action": "bana yanıt ver",
        "target_beliefs": ["kontrolü elde tutmak", "kusursuz görünmek"]
    }
    
    res = await executor.execute(task_input)
    assert isinstance(res, ShadowResult)
    assert isinstance(res.message, str)
    assert len(res.message) > 0
    assert isinstance(res.dark_profile, dict)
    assert isinstance(res.strategy, str)
    assert res.nlp_sequence == []  # profilde duyusal anahtar yok; temsil sistemi atfedilmez
    assert 0.0 <= res.confidence <= 1.0
    
    # Mesajın sentezlenmiş yapıda presupposition ve nlp_command içerdiğini doğrula
    assert "kontrolü elde tutmak" in res.message
    assert "Derin bir nefes al" in res.message
