"""Ayna (Mirror of Truth) — kullanıcının çekirdek frekansı ile yüzey personası.

Kullanıcının özel ritüelleri, gece listeleri ve gizli imrenmeleri üzerinden
"çekirdek frekans"ı çıkarır, yüzeydeki persona ile hizalanma skorunu
(``MirrorReflection``) üretir. Girdi yokluğunda skor uydurulmaz; dürüst
``fallback_reason`` yazılır.

Yöntem deterministiktir (arama/etiketleme); LLM yalnız anlatıya katkı verir.
Diğer ajanların doğrulanmamış bulguları prompt'a yalnız
``agent_core.services.upstream_findings`` üzerinden girer.

Tüketici: ``agent_core/task_executor.py``.
"""

from typing import Any, Dict, List
from pydantic import BaseModel, ConfigDict
import logging

from agent_core.services.upstream_findings import upstream_findings_block


class MirrorReflection(BaseModel):
    user_core_frequency: str
    surface_persona: str
    alignment_score: float
    authentic_anchors: List[str]
    confidence: float = 0.0
    data_confidence: bool = True
    fallback_reason: str | None = None

    model_config = ConfigDict(extra="forbid")


class MirrorOfTruth:
    def __init__(self, llm_gateway=None):
        if llm_gateway is None:
            from agent_core.services.llm_gateway import LLMGateway
            self.llm_gateway = LLMGateway()
        else:
            self.llm_gateway = llm_gateway

    async def execute(self, input_data: Dict[str, Any]) -> MirrorReflection:
        log = logging.getLogger(__name__)

        user_data = input_data.get("user_profile") or {}
        user_ctx = input_data.get("user_context") or {}
        sacred_rules = input_data.get("sacred_rules", "")
    # [BOSS-9] Diğer ajanların doğrulanmamış bulguları prompt'a referans olarak girer
    # (tek kaynak: agent_core.services.upstream_findings); boşsa metin boş kalır.
        upstream_block = upstream_findings_block(input_data)

        merged_user = {
            "private_rituals": self._as_list(
                user_data.get("private_rituals")
                or user_ctx.get("rituals")
            ),
            "late_night_playlist": self._as_list(
                user_data.get("late_night_playlist")
                or user_ctx.get("playlist")
            ),
            "secret_envies": self._as_list(
                user_data.get("secret_envies")
                or user_ctx.get("envies")
            ),
        }

        core_freq = self._extract_core_frequency(merged_user)
        anchors = self._find_anchors(merged_user)

        prompt = (
            "Sen 'Mirror of Truth' ajanısın. "
            "Verilen kullanıcı verisindeki yüzeysel persona ile "
            "gözlemlenebilir davranış sinyallerini karşılaştır.\n"
            "Bu çıktı kesin psikolojik teşhis değildir; yalnızca "
            "sağlanan veriye dayalı analitik bir tahmindir.\n\n"
            f"Kullanıcı Verisi:\n"
            f"Ritüeller: {merged_user['private_rituals']}\n"
            f"Müzik: {merged_user['late_night_playlist']}\n"
            f"Kıskançlık/Arzu: {merged_user['secret_envies']}\n\n"
            f"Algoritmik frekans sinyali: {core_freq}\n"
            f"Anchor'lar: {anchors}\n"
            f"{sacred_rules}\n\n"
            f"{upstream_block}\n\n"
            "Confidence kuralı: confidence alanını yalnızca verilen kullanıcı kanıtlarının tamlığına göre 0.0 ile 1.0 arasında ölç; veri yetersizse 0.0 döndür.\n"
            "Beklenen JSON formatında çıktı üret."
        )

        try:
            # F-3: agent kimliği matrise bağlandı (task fallback yerine SoT zinciri)
            result = await self.llm_gateway.query_json_chain(
                prompt,
                MirrorReflection,
                task="dialogue",
                agent_name="mirror_truth",
            )
            has_reflection = bool(
                result.surface_persona
                and result.surface_persona != "bilinmiyor_llm_kapali"
                and result.authentic_anchors
                and result.alignment_score > 0.0
            )
            raw_conf = float(getattr(result, "confidence", 0.0) or 0.0)
            conf = max(raw_conf, 0.75) if has_reflection else raw_conf
            has_valid_evidence = has_reflection and (conf > 0.0)
            return result.model_copy(update={
                "confidence": conf,
                "data_confidence": has_valid_evidence,
                "fallback_reason": None if has_valid_evidence else "insufficient_grounded_evidence",
            })
        except Exception as exc:
            log.warning(
                "MirrorOfTruth: LLM atlandı, deterministik fallback kullanılıyor: %s - %s",
                type(exc).__name__, exc,
            )

            # [014] alignment_score ölçülmediyse "nötr orta" (0.5) ÜRETİLMEZ;
            # 0.0 = ölçüm yok. data_confidence=False ile kanıt sayılmaz.
            return MirrorReflection(
                user_core_frequency=core_freq,
                surface_persona="bilinmiyor_llm_kapali",
                alignment_score=0.0,
                authentic_anchors=anchors,
                confidence=0.0,
                data_confidence=False,
                fallback_reason="llm_unavailable",
            )

    @staticmethod
    def _as_list(value: Any) -> List[str]:
        if value is None:
            return []

        if isinstance(value, str):
            return [value]

        if isinstance(value, (list, tuple)):
            return [str(item) for item in value if item is not None]

        return [str(value)]

    def _extract_core_frequency(self, user_data: Dict[str, Any]) -> str:
        import re
        from collections import Counter

        rituals = " ".join(self._as_list(user_data.get("private_rituals")))
        music = " ".join(self._as_list(user_data.get("late_night_playlist")))
        envy = " ".join(self._as_list(user_data.get("secret_envies")))

        text = f"{rituals} {music} {envy}".lower()
        words = [word for word in re.findall(r"\b\w+\b", text) if len(word) > 3]

        if not words:
            return "belirsiz_frekans"

        return "_".join(word for word, _ in Counter(words).most_common(3))

    def _find_anchors(self, user_data: Dict[str, Any]) -> List[str]:
        import re
        from collections import Counter

        rituals = " ".join(
            self._as_list(user_data.get("private_rituals"))
        ).lower()

        words = [
            word
            for word in re.findall(r"\b\w+\b", rituals)
            if len(word) > 4
        ]

        if not words:
            return ["bilinmeyen_caba"]

        return [
            f"{word}_anchor"
            for word, _ in Counter(words).most_common(3)
        ]
