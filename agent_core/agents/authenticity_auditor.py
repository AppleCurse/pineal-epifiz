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
from pydantic import BaseModel, ConfigDict, Field
from agent_core.services.llm_gateway import LLMGateway
from agent_core.services.upstream_findings import upstream_findings_block
from agent_core.services.confidence import normalize_confidence

logger = logging.getLogger(__name__)

class AuthenticityProfile(BaseModel):
    authenticity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    visual_text_gaps: list[str] = []
    supported_claims: list[str] = []
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    data_confidence: bool = False
    fallback_reason: Optional[str] = "unavailable"

    model_config = ConfigDict(extra="allow")

class AuthenticityAuditorAgent:
    """
    Kullanıcının beyanları (bio/post) ile görsel kanıtlar (fotoğraflardaki nesneler,
    mekanlar, estetik) arasındaki tutarlılığı ve "Özgünlük Boşluğunu" ölçer.
    """

    def __init__(self, llm_gateway: Optional[LLMGateway] = None):
        self.llm_gateway = llm_gateway or LLMGateway()

    async def execute(self, payload: Dict[str, Any]) -> AuthenticityProfile:
        payload = payload if isinstance(payload, dict) else {}
        raw_target = payload.get("target_profile")
        target = raw_target if isinstance(raw_target, dict) else {}
        raw_bio = target.get("bio")
        bio = raw_bio.strip() if isinstance(raw_bio, str) else ""
        raw_posts = target.get("posts", [])
        if isinstance(raw_posts, str):
            raw_posts = [raw_posts]
        posts = (
            [post.strip() for post in raw_posts if isinstance(post, str) and post.strip()]
            if isinstance(raw_posts, (list, tuple))
            else []
        )
        raw_visual = payload.get("visual_evidence")
        visual_evidence = raw_visual if isinstance(raw_visual, dict) else {}
        visual_signal = any(
            (isinstance(visual_evidence.get(key), str) and visual_evidence[key].strip())
            or (
                isinstance(visual_evidence.get(key), (list, tuple))
                and any(isinstance(item, str) and item.strip() for item in visual_evidence[key])
            )
            for key in (
                "detected_objects", "environment_and_places", "activity_signals",
                "aesthetic_style", "visual_evidence_summary",
            )
        )
        upstream_block = upstream_findings_block(payload)

        if not visual_signal or not (bio or posts):
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
            if not isinstance(result, AuthenticityProfile):
                raise TypeError("authenticity_profile_schema_mismatch")
            score, score_valid = normalize_confidence(result.authenticity_score)
            model_confidence, confidence_valid = normalize_confidence(result.confidence)
            has_findings = bool(result.visual_text_gaps or result.supported_claims)
            data_confidence = score_valid and confidence_valid and has_findings and model_confidence > 0.0
            fallback_reason = (
                None if data_confidence
                else "invalid_model_score" if not score_valid or not confidence_valid
                else "insufficient_grounded_evidence"
            )
            return result.model_copy(update={
                "authenticity_score": score if data_confidence else 0.0,
                "confidence": model_confidence if data_confidence else 0.0,
                "data_confidence": data_confidence,
                "fallback_reason": fallback_reason,
            })
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
