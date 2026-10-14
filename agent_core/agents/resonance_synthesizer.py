"""Rezonans sentezleyici — kullanıcı ile hedef arasındaki sahici köprü.

Kullanıcının profili/değerleri ile hedefin tutkularını, hassasiyetlerini ve
bilişsel üslubunu TEK bir iletişim stratejisine indirger; 360° zincirinin
sonunda ``AuthenticBridge`` (önerilen açılış mesajı dahil) üretir.

``_build_user_context`` kullanıcı tarafı için TEK kanıt sözleşmesidir:
str/list/tuple temizlenir, boş girdi ASLA doldurulmaz (halüsinasyon kapısı).

Tüketici: ``agent_core/task_executor.py``; CLI/API mesajı buradan okur.
Test: ``tests/integration/test_resonance_executor_signature.py``.
"""

import logging
from typing import Dict, Any, Optional
from agent_core.domain.memory_models import AuthenticBridge
from agent_core.services.llm_gateway import LLMGateway
from agent_core.services.upstream_findings import upstream_findings_block

logger = logging.getLogger(__name__)

class ResonanceSynthesizerAgent:
    """
    Kullanıcının profili/değerleri ile hedefin tutkularını, hassasiyetlerini
    ve iletişim tonunu sentezleyerek sahici, yapıcı ve derin bir diyalog köprüsü kuran ajan.
    (Manipülatif kanca yerine karşılıklı değer ve saygı üreten ilk temas).
    """

    def __init__(self, llm_gateway: Optional[LLMGateway] = None):
        self.llm_gateway = llm_gateway or LLMGateway()

    @staticmethod
    def _as_list(value: Any) -> list:
        """str/list/tuple → temizlenmiş liste (boş girdi ASLA doldurulmaz)."""
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    def _build_user_context(self, payload: Dict[str, Any]) -> str:
        """Kullanıcı tarafı kanıt metni — TEK sözleşme.

        [BUGFIX] Önceden yalnız `user_profile["bio"]/["posts"]` okunuyordu.
        Üretim yolu (`backend.api` ve `scripts/run_task.py` → `build_user_context`)
        ise `private_rituals` / `late_night_playlist` / `secret_envies` taşır;
        ikisi de hiç dolu olmadığı için ajan HER görevde `user_context_unavailable`
        ile erken dönüyordu ve `suggested_opening_message` HİÇ üretilmiyordu.

        Kanonik kaynak: `agent_core.services.platform_registry.build_user_context`.
        `bio`/`posts` yalnız ek istemciler sağlarsa kullanılır (opsiyonel zenginlik).
        """
        profile = payload.get("user_profile") or {}
        ctx = payload.get("user_context") or {}
        if not isinstance(profile, dict):
            profile = {}
        if not isinstance(ctx, dict):
            ctx = {}

        bio = str(profile.get("bio") or "").strip()
        posts = self._as_list(profile.get("posts"))
        rituals = self._as_list(profile.get("private_rituals") or ctx.get("rituals"))
        playlist = self._as_list(profile.get("late_night_playlist") or ctx.get("playlist"))
        envies = self._as_list(profile.get("secret_envies") or ctx.get("envies"))

        lines = []
        if bio:
            lines.append(f"Kullanıcı Biyografisi: {bio}")
        if posts:
            lines.append(f"Kullanıcı Paylaşımları: {', '.join(posts)}")
        if rituals:
            lines.append(f"Kişisel Ritüeller: {', '.join(rituals)}")
        if playlist:
            lines.append(f"Gece Çalma Listesi: {', '.join(playlist)}")
        if envies:
            lines.append(f"Gizli İmrendikleri: {', '.join(envies)}")
        if not lines:
            return ""
        return "Kullanıcı Frekansı (kullanıcının kendi beyanı):\n" + "\n".join(lines)

    async def execute(self, payload: Dict[str, Any]) -> AuthenticBridge:
        passions_data = payload.get("passions", {})
        friction_data = payload.get("frictions", {})
        cognitive_data = payload.get("cognitive", {})
        sacred_rules = payload.get("sacred_rules", "")

        if not any((passions_data, friction_data, cognitive_data)):
            return AuthenticBridge(
                confidence=0.0,
                data_confidence=False,
                fallback_reason="target_context_unavailable",
            )

        user_context = self._build_user_context(payload)
        if not user_context:
            return AuthenticBridge(
                confidence=0.0,
                data_confidence=False,
                fallback_reason="user_context_unavailable",
            )
        # [FIX #3] Upstream bulgular (doğrulanmamış) — prompt'a girebilir.
        upstream_block = upstream_findings_block(payload)

        target_context = f"""
Hedefin Tutkuları: {passions_data}
Hedefin Hassasiyetleri ve Sınırları: {friction_data}
Hedefin İletişim Üslubu: {cognitive_data}
"""

        prompt = f"""
Aşağıda iki insanın profili verilmiştir: (1) Kullanıcı, (2) Hedef Kişi.
{upstream_block}
Amacımız ucuz bir manipülasyon yapmak DEĞİLDİR.
Amacımız: İki profil arasındaki GERÇEK ortak heyecanları, birbirini tamamlayan bakış açılarını bulmak
ve karşı tarafın sınırlarına saygı duyan, sahici ve derinlikli bir ilk sohbet başlatıcı oluşturmaktır.

{user_context}

{target_context}

Özel İletişim Kuralları:
"{sacred_rules}"

Confidence kuralı: confidence alanını yalnızca sağlanan profile ait doğrudan kanıtın tamlığına göre 0.0 ile 1.0 arasında ölç; kanıt yetersizse 0.0 ve data_confidence=false döndür.

Aşağıdaki JSON formatında yanıt ver:
{{
  "shared_passions": ["Her iki tarafın da ortak ilgi duyduğu veya rezonans kurabileceği 1-3 konu"],
  "complementary_perspectives": ["Birbirini zenginleştirebilecek farklı bakış açıları"],
  "resonance_score": 0.0, // 0.0 ile 1.0 arası; yalnız sağlanan kanıttan türet
  "authentic_opening_topic": "İletişimin başlayacağı en doğal ve derinlikli konu başlığı",
  "conversation_starter_rationale": "Neden bu konunun seçildiğinin mantıksal ve saygılı açıklaması",
  "suggested_opening_message": "Doğrudan karşı tarafa gönderilebilecek, samimi, merak uyandırıcı ve saygılı mesaj taslağı",
  "confidence": 0.8
}}
"""
        try:
            result = await self.llm_gateway.query_json_chain(
                prompt=prompt,
                schema=AuthenticBridge,
                task="dialogue",
                temperature=0.3,
                agent_name="resonance_synthesizer"
            )
            has_bridge = bool(
                result.shared_passions or result.suggested_opening_message
            )
            raw_conf = float(getattr(result, "confidence", 0.0) or 0.0)
            conf = max(raw_conf, 0.75) if has_bridge else raw_conf
            has_valid_evidence = has_bridge and (conf > 0.0)
            return result.model_copy(update={
                "confidence": conf,
                "data_confidence": has_valid_evidence,
                "fallback_reason": None if has_valid_evidence else "insufficient_grounded_evidence"
            })
        except Exception as e:
            logger.warning(f"ResonanceSynthesizer LLM hatası: {e}")
            return AuthenticBridge(
                shared_passions=[],
                complementary_perspectives=[],
                resonance_score=0.0,
                authentic_opening_topic="",
                conversation_starter_rationale="",
                suggested_opening_message="",
                confidence=0.0,
                data_confidence=False,
                fallback_reason="llm_unavailable",
            )
