"""İlk Temas & Etkileme Kancası Stüdyosu — ``POST /api/hook/generate``.

[2026-10-24] Neden var?
    Hedefin 360° analizi (tutkular, hassasiyetler, bilişsel üslup, adli kanıtlar)
    tamamlandıktan sonra operatörün nihai hedefi karşı tarafa doğrudan
    ulaşmak ve savunmasını düşüren, sahici merak uyandıran bir ilk temas
    kurmaktır ("onu etkileyecek bir mesaj").

    Bu modül, hedefin kanıtlanmış bilişsel yapısına ve operatörün seçtiği
    veya girdiği özel iletişim amacına göre (iş birliği, doğal tanışma,
    entelektüel kanca, kalıp kırıcı veya serbest hedef) hedefe özel açılış
    mesajı ve 3 dallı diyalog ağacı (savunmacı/agresif/meraklı tepkilere karşı
    saygılı ve akılcı karşı-hamleler) üretir.

Neden ayrı modül?
    ``backend/api.py`` tek-modül tavanı (``tests/unit/test_api_monolith_ratchet.py``)
    korunur. Bağımlılıklar enjekte edilir; bu modül ``backend.api``'yi içe
    aktarmaz.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agent_core.services.llm_gateway import LLMGateway
from agent_core.services.confidence import normalize_confidence

logger = logging.getLogger(__name__)

__all__ = ["HookStudioPayload", "register_hook_studio_routes"]


class DialogueBranch(BaseModel):
    scenario: str
    target_reaction: str
    our_counter_move: str


class HookResult(BaseModel):
    opening_message: str
    opening_topic: str
    rationale: str
    archetype: str
    dialogue_tree: List[DialogueBranch] = []
    shared_points: List[str] = []
    confidence: float = 0.8
    data_confidence: bool = True
    fallback_reason: Optional[str] = None


class HookStudioPayload(BaseModel):
    client_id: str = Field(default="default", max_length=64)
    task_id: Optional[str] = Field(default=None, max_length=128)
    intent: str = Field(default="authentic_connection", max_length=64)
    custom_goal: Optional[str] = Field(default=None, max_length=2000)
    target_username: Optional[str] = Field(default=None, max_length=128)
    target_profile: Optional[Dict[str, Any]] = None
    passions: Optional[Dict[str, Any]] = None
    frictions: Optional[Dict[str, Any]] = None
    cognitive: Optional[Dict[str, Any]] = None
    depth_report: Optional[Dict[str, Any]] = None


ARCHETYPES = [
    {
        "id": "authentic_connection",
        "title": "Sahici Rezonans",
        "icon": "🤝",
        "description": "Hedefin gerçek tutkularına ve dünya görüşüne saygılı, samimi ve derin bağ kurucu ilk temas.",
    },
    {
        "id": "business_collab",
        "title": "İş / Ortaklık Teklifi",
        "icon": "💼",
        "description": "Zamanına saygı duyan, ortak katma değere odaklanan, profesyonel ve merak uyandıran iş teklifi.",
    },
    {
        "id": "intellectual_collab",
        "title": "Entelektüel Kanca",
        "icon": "💡",
        "description": "Hedefin paylaştığı bir fikir veya ayrıntı üzerinden zihnini kışkırtan, derinlikli soru.",
    },
    {
        "id": "pattern_interrupt",
        "title": "Kalıp Kırıcı Soru",
        "icon": "⚡",
        "description": "Klasik tanışma kalıplarını yıkan, hedefte 'bunu nereden fark etti?' dedirten mikro-gözlem.",
    },
    {
        "id": "shadow_hook",
        "title": "Gölge & NLP Kancası",
        "icon": "🌑",
        "description": "Bilinçaltı varsayımlar ve gömülü komutlarla savunma mekanizmasını baypas eden stratejik mesaj.",
    },
    {
        "id": "custom",
        "title": "Özel Operasyonel Amaç",
        "icon": "🎯",
        "description": "Operatörün serbest metin olarak yazdığı özel amaca tam uyarlanmış nokta atışı mesaj.",
    },
]


def register_hook_studio_routes(
    app: Any,
    *,
    rate_limit: Callable[[str, str], bool],
    rate_identity: Callable[[Request], str],
    gateway_provider: Callable[[], Any],
    get_executor: Optional[Callable[[str], Any]] = None,
) -> None:
    @app.get("/api/hook/archetypes")
    async def list_archetypes():
        """Desteklenen kanca arke tiplerini listeler."""
        return {"archetypes": ARCHETYPES}

    @app.post("/api/hook/generate")
    async def generate_hook(payload: HookStudioPayload, request: Request):
        """Hedefin bilişsel profiline ve operatörün niyetine göre açılış kancası ve diyalog ağacı üretir."""
        ip = rate_identity(request)
        if not rate_limit(ip, "hook_generate"):
            return JSONResponse(
                {"error": {"code": "RATE_LIMITED", "message": "Çok fazla kanca isteği. Lütfen bekleyin."}},
                status_code=429,
            )

        # 1. Profil verilerini topla (payload doğrudan taşıyabilir veya task_id üzerinden çekilebilir)
        target_profile = dict(payload.target_profile or {})
        passions = dict(payload.passions or {})
        frictions = dict(payload.frictions or {})
        cognitive = dict(payload.cognitive or {})
        depth_report = dict(payload.depth_report or {})

        if get_executor is not None and payload.client_id:
            try:
                executor = get_executor(payload.client_id)
                # Aktif veya son görevin durumunu yokla
                task_status = None
                if payload.task_id and hasattr(executor, "tasks") and payload.task_id in executor.tasks:
                    task_status = executor.tasks[payload.task_id]
                elif hasattr(executor, "last_status") and executor.last_status:
                    task_status = executor.last_status

                if task_status is not None:
                    holistic = getattr(task_status, "holistic_profile", None)
                    if holistic:
                        if not passions and getattr(holistic, "passions", None):
                            p = holistic.passions
                            passions = p.model_dump() if hasattr(p, "model_dump") else dict(p)
                        if not frictions and getattr(holistic, "frictions", None):
                            f = holistic.frictions
                            frictions = f.model_dump() if hasattr(f, "model_dump") else dict(f)
                        if not cognitive and getattr(holistic, "cognitive", None):
                            c = holistic.cognitive
                            cognitive = c.model_dump() if hasattr(c, "model_dump") else dict(c)
                    if not target_profile and getattr(task_status, "target_profile", None):
                        target_profile = dict(task_status.target_profile)
                    if not depth_report and getattr(task_status, "depth_report", None):
                        d = task_status.depth_report
                        depth_report = d.model_dump() if hasattr(d, "model_dump") else dict(d)
            except Exception as e:
                logger.debug(f"Hook studio executor durumu okuma hatası: {e}")

        # Kanıt kontrolü
        has_evidence = any((
            target_profile.get("bio"),
            target_profile.get("posts"),
            passions.get("core_passions"),
            frictions.get("sensitivities"),
            cognitive.get("communication_tone"),
            depth_report.get("essence_one_liner"),
        ))

        # Gateway temini
        gw = gateway_provider()
        if gw is None or not isinstance(gw, LLMGateway):
            gw = LLMGateway()

        # Niyet açıklaması
        intent_desc = "Doğal ve samimi ilk temas; merak uyandırmak"
        for arch in ARCHETYPES:
            if arch["id"] == payload.intent:
                intent_desc = arch["description"]
                break

        if payload.intent == "custom" and payload.custom_goal:
            intent_desc = f"Operatörün Özel Hedefi: {payload.custom_goal.strip()}"
        elif payload.custom_goal:
            intent_desc += f" | Ek Operatör Notu: {payload.custom_goal.strip()}"

        target_name = (
            payload.target_username
            or target_profile.get("username")
            or "Hedef Kişi"
        )

        prompt = f"""
Sen dünya standartlarında bir iletişim psikoloğu, adli profil analisti ve diyalog stratejistisin.
Görevin: Aşağıda analizi yapılmış Hedef Kişi için savunmasını düşüren, merak uyandıran ve onu derinden etkileyecek bir İLK TEMAS MESAJI (Opening Hook) ve olası tepkilerine karşı DİYALOG AĞACI tasarlamaktır.

Hedef Kimlik: @{target_name}
İletişim Amacı ve Strateji: {intent_desc}

HEDEFİN KANITLANMIŞ PROFİLİ:
- Biyografi & Gönderi Özeti: {target_profile.get("bio", "Mevcut değil")} | Paylaşımlar: {target_profile.get("posts", [])}
- Tutkuları & İlgi Alanları: {passions.get("core_passions", [])} | Yan Tutkular: {passions.get("secondary_interests", [])}
- Hassasiyetleri & Kırmızı Çizgileri: {frictions.get("sensitivities", [])} | Kaçındığı Konular: {frictions.get("forbidden_territories", [])}
- İletişim Üslubu & Tonu: {cognitive.get("communication_tone", "Dengeli")} | Düşünce Tarzı: {cognitive.get("thinking_style", "Analitik/Sezgisel")}
- Derinlik Özeti: {depth_report.get("essence_one_liner", "Belirtilmemiş")}

ÖNEMLİ KURALLAR:
1. Asla ucuz flört cümlesi veya klişe 'Merhaba tanışabilir miyiz?' mesajı yazma.
2. Hedefin doğrudan paylaşımlarındaki veya ilgi alanlarındaki somut bir detaya (ışık, kelime, proje, tema) referans ver.
3. Karşı tarafın kırmızı çizgilerine ve hassasiyetlerine asla basma.
4. Karşı taraf savunmacı, agresif veya şüpheci yaklaştığında operatörü zor durumda bırakmayacak, zarafetle merak uyandıran karşı-hamleler (dialogue_tree) sun.

Aşağıdaki JSON şemasında yanıt ver:
{{
  "opening_message": "Doğrudan karşı tarafa gönderilmeye hazır, vurucu ve saygılı ilk açılış mesajı",
  "opening_topic": "Konunun odaklandığı ana başlık",
  "rationale": "Bu mesajın hedefin psikolojisinde neden işe yaradığının stratejik gerekçesi",
  "archetype": "{payload.intent}",
  "dialogue_tree": [
    {{
      "scenario": "savunmaci",
      "target_reaction": "Hedefin şüpheci tepkisi (örn: 'Beni nereden tanıyorsun?')",
      "our_counter_move": "Operatörün saygılı ve zekice yanıtı"
    }},
    {{
      "scenario": "agresif",
      "target_reaction": "Hedefin soğuk/ters tepkisi (örn: 'Vaktim yok.')",
      "our_counter_move": "Operatörün zarafetle geri çekilip merak bırakan yanıtı"
    }},
    {{
      "scenario": "merakli",
      "target_reaction": "Hedefin ilgili tepkisi (örn: 'O detayı nasıl fark ettin?')",
      "our_counter_move": "Diyaloğu derinleştiren devam sorusu"
    }}
  ],
  "shared_points": ["Hedefle rezonans kurulan 1-2 kilit nokta"],
  "confidence": 0.92
}}
"""
        try:
            res = await gw.query_json_chain(
                prompt=prompt,
                schema=HookResult,
                task="dialogue",
                temperature=0.35,
                agent_name="hook_studio",
            )
            conf, valid = normalize_confidence(getattr(res, "confidence", None))
            return res.model_copy(update={
                "confidence": conf if valid else 0.85,
                "data_confidence": has_evidence,
                "archetype": payload.intent,
            }).model_dump()
        except Exception as e:
            logger.warning(f"HookStudio LLM hatası: {e}")
            # Dürüst fallback: Kanıta dayalı yerel şablon
            default_topic = (
                passions.get("core_passions", ["paylaşımlarınız"])[0]
                if passions.get("core_passions")
                else "çalışmalarınız"
            )
            return HookResult(
                opening_message=f"Merhaba @{target_name}, {default_topic} üzerine yaklaşımınız dikkatimi çekti. Özellikle son dönemdeki bakış açınızdaki tutarlılık oldukça ilham verici.",
                opening_topic=str(default_topic),
                rationale="Hedefin birincil ilgi odağına saygılı ve doğrudan temas.",
                archetype=payload.intent,
                dialogue_tree=[
                    DialogueBranch(
                        scenario="savunmaci",
                        target_reaction="Beni nereden buldunuz?",
                        our_counter_move="Alanınızdaki üretimleri ve paylaşımlarınızı incelerken denk geldim, yapıcı bir merakla selam vermek istedim.",
                    ),
                    DialogueBranch(
                        scenario="agresif",
                        target_reaction="İlgilenmiyorum.",
                        our_counter_move="Anlayışla karşılıyorum, çalışmalarınızda başarılar dilerim.",
                    ),
                    DialogueBranch(
                        scenario="merakli",
                        target_reaction="Teşekkürler, hangi çalışma ilginizi çekti?",
                        our_counter_move="Özellikle detaylardaki titizliğiniz ve özgün perspektifiniz; bu konuda ne zamandır çalışıyorsunuz?",
                    ),
                ],
                shared_points=[str(default_topic)],
                confidence=0.5,
                data_confidence=False,
                fallback_reason="llm_unavailable_template_fallback",
            ).model_dump()
