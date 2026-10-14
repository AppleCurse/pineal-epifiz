"""Gerçeklik (özgünlük) denetçisi — beyan ile görsel kanıt arasındaki tutarlılık.

Hedefin bio/post metinlerinde BEYAN ettiği kimlik ile fotoğraflardan çıkarılan
SOMUT görsel kanıtlar (nesne, mekân, eylem, estetik) karşılaştırılır ve
"özgünlük boşluğu" ölçülür. Çıktı ``AuthenticityProfile``: authenticity_score,
visual_text_gaps, supported_claims, confidence.

Dürüstlük sözleşmesi: görsel kanıt ya da beyan yoksa skor UYDURULMAZ; ajan
``confidence=0.0`` ve ``fallback_reason="insufficient_evidence"`` döner. Diğer
ajanların doğrulanmamış bulguları prompt'a yalnız
``agent_core.services.upstream_findings`` bloğu üzerinden girer (tek kaynak).

Tüketici: ``agent_core/task_executor.py`` 360° zinciri.
Test: ``tests/unit/test_authenticity_auditor.py``.
"""

import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, ConfigDict
from agent_core.services.llm_gateway import LLMGateway
from agent_core.services.upstream_findings import upstream_findings_block

logger = logging.getLogger(__name__)

class AuthenticityProfile(BaseModel):
    authenticity_score: float = 1.0  # 0.0 (tamamen kurgu/çelişkili) - 1.0 (tamamen sahici)
    visual_text_gaps: list[str] = []
    supported_claims: list[str] = []
    confidence: float = 1.0

    model_config = ConfigDict(extra="allow")

class AuthenticityAuditorAgent:
    """
    Kullanıcının beyanları (bio/post) ile görsel kanıtlar (fotoğraflardaki nesneler,
    mekanlar, estetik) arasındaki tutarlılığı ve "Özgünlük Boşluğunu" ölçer.
    """

    def __init__(self, llm_gateway: Optional[LLMGateway] = None):
        self.llm_gateway = llm_gateway or LLMGateway()

    async def execute(self, payload: Dict[str, Any]) -> AuthenticityProfile:
        target = payload.get("target_profile", {})
        bio = target.get("bio", "")
        posts = target.get("posts", [])
        visual_evidence = payload.get("visual_evidence", {})
    # [BOSS-9] Diğer ajanların doğrulanmamış bulguları prompt'a referans olarak girer
    # (tek kaynak: agent_core.services.upstream_findings); boşsa metin boş kalır.
        upstream_block = upstream_findings_block(payload)

        if not visual_evidence or not (bio or posts):
            return AuthenticityProfile(
                authenticity_score=0.0,
                visual_text_gaps=[],
                supported_claims=[],
                confidence=0.0,
                data_confidence=False,
                fallback_reason="insufficient_evidence"
            )

        posts_text = "\n".join([f"- {p}" for p in posts[:10]]) if posts else "Gönderi metni bulunamadı."
        visual_text = f"""
- Nesneler: {visual_evidence.get('detected_objects', [])}
- Mekanlar: {visual_evidence.get('environment_and_places', [])}
- Eylemler: {visual_evidence.get('activity_signals', [])}
- Estetik: {visual_evidence.get('aesthetic_style', '')}
"""

        prompt = f"""
Aşağıda bir kişinin beyanları (biyografi ve gönderi metinleri) ile onun paylaştığı 
fotoğraflardan çıkarılmış SOMUT görsel kanıtlar yer almaktadır.

Görev: Metinsel iddialar ile görsel gerçeklik arasındaki tutarlılığı hesaplamak.
- Kişi "minimalist" olduğunu iddia edip lüks/kaotik ortamlar mı paylaşıyor? (Çelişki)
- Doğayı sevdiğini söyleyip sadece kapalı mekan veya stüdyo fotoğrafı mı var? (Çelişki)
- İddia ettiği mesleği veya hobileri görsellerde somut olarak yer alıyor mu? (Destekleyici)

Hedef Biyografi:
"{bio}"

Son Paylaşımlar / Metinler:
{posts_text}

Görsel Kanıtlar (Fotoğraflarda Görülenler):
{visual_text}

{upstream_block}

JSON formatında yanıt ver:
{{
    "authenticity_score": 0.85, 
    "visual_text_gaps": ["Çelişen noktaların kısa açıklaması", "varsa"],
    "supported_claims": ["Görselle kanıtlanan beyanlar"],
    "confidence": 0.90
}}
"""
        try:
            result = await self.llm_gateway.query_json_chain(
                prompt=prompt,
                schema=AuthenticityProfile,
                task="depth",
                temperature=0.2,
                agent_name="authenticity_auditor"
            )
            return result
        except Exception as e:
            logger.warning("AuthenticityAuditor LLM hatası: %s", e)
            return AuthenticityProfile(
                authenticity_score=0.0,
                visual_text_gaps=[],
                supported_claims=[],
                confidence=0.0,
                data_confidence=False,
                fallback_reason="llm_unavailable"
            )
