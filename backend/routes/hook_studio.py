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
from agent_core.services.confidence import (
    normalize_confidence,
    normalize_evidence_verification_status,
)
from agent_core.services.epistemic import build_epistemic_state, clamp
from agent_core.services.uncertainty_engine import UncertaintyEngine

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
    data_confidence: bool = False
    input_data_present: bool = False
    evidence_verification_status: str = "unverified"
    fallback_reason: Optional[str] = None
    epistemic: Optional[Dict[str, Any]] = None
    evidence_used: List[str] = Field(default_factory=list)


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
    require_vault_open: Optional[Callable[[str], Any]] = None,
    require_minor_clearance: Optional[Callable[..., Any]] = None,
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

        has_unverified_payload_input = any(
            UncertaintyEngine._value_bears_evidence(v)
            for v in (
                target_profile.get("bio"),
                target_profile.get("posts"),
                passions.get("core_passions"),
                frictions.get("sensitivities"),
                cognitive.get("communication_tone"),
                depth_report.get("essence_one_liner"),
            )
        )
        task_has_verified_report = False

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
                    vr = getattr(task_status, "verification_report", None)
                    if vr is not None:
                        vr_status = vr.get("status") if isinstance(vr, dict) else getattr(vr, "status", None)
                        vr_dc = vr.get("data_confidence") if isinstance(vr, dict) else getattr(vr, "data_confidence", False)
                        if vr_status == "VERIFIED" and vr_dc is True:
                            task_has_verified_report = True

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

        # Gerçek Pydantic modellerinden alan çıkarımı
        core_passions = passions.get("core_passions") or []
        energizing_topics = passions.get("energizing_topics") or passions.get("secondary_interests") or []
        flow_triggers = passions.get("flow_triggers") or []

        sensitivities = frictions.get("sensitivities") or []
        stress_triggers = frictions.get("stress_triggers") or []
        boundary_signals = frictions.get("boundary_signals") or frictions.get("forbidden_territories") or []

        comm_tone = cognitive.get("communication_tone") or "Dengeli"
        complexity = cognitive.get("complexity_level") or "Orta Düzey"
        thinking = cognitive.get("thinking_style") or "Dengeli"
        social_orient = cognitive.get("social_orientation") or "Dengeli"
        humor_style = cognitive.get("humor_style") or "Doğal"

        depth_essence = depth_report.get("essence_one_liner") or "Belirtilmemiş"

        # Epistemik Durum Matrisi: Kanallar ve ölçülmüş alanlar sayılır
        epistemic_payload = {
            "posts": target_profile.get("posts"),
            "bio": target_profile.get("bio"),
            "visual": target_profile.get("visual_analysis") or target_profile.get("photos"),
            "osint": target_profile.get("osint_footprint") or target_profile.get("osint"),
            "search": target_profile.get("search_results"),
        }
        epistemic_profiles = {
            "core_passions": core_passions,
            "energizing_topics": energizing_topics,
            "flow_triggers": flow_triggers,
            "sensitivities": sensitivities,
            "stress_triggers": stress_triggers,
            "boundary_signals": boundary_signals,
            "communication_tone": [comm_tone] if comm_tone != "Dengeli" else [],
            "depth_essence": [depth_essence] if depth_essence != "Belirtilmemiş" else [],
        }
        input_data_present = bool(
            any(
                UncertaintyEngine._value_bears_evidence(v)
                for v in (
                    target_profile.get("bio"),
                    target_profile.get("posts"),
                    passions.get("core_passions"),
                    frictions.get("sensitivities"),
                    cognitive.get("communication_tone"),
                    depth_report.get("essence_one_liner"),
                )
            )
        )
        has_verified_proof = bool(
            input_data_present
            and task_has_verified_report
            and not has_unverified_payload_input
        )
        epistemic_state = build_epistemic_state(
            epistemic_payload,
            profiles=epistemic_profiles,
            has_verified_proof=has_verified_proof,
        )

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

        # Operatör kip seçimi & Psikolojik Strateji Kuralı (Arketip temelli koruma/penetrasyon)
        # DİKKAT: "kır" alt-dizesi "kırmızı" kelimesini yakalamamalıdır!
        goal_lower = (payload.custom_goal or "").lower()
        has_explicit_respect_rule = any(
            phrase in goal_lower
            for phrase in ["kırmızı", "kırmızı çizgi", "basma", "saygılı", "hassasiyet", "koru", "empatik"]
        )
        is_offensive_archetype = payload.intent in ("shadow_hook", "pattern_interrupt")
        has_offensive_intent = bool(
            not has_explicit_respect_rule and any(
                phrase in goal_lower
                for phrase in [
                    "direnci kır", "gardını düşür", "savunmasını kır", "zaafını bul",
                    "yara izi", "baskı kur", "açığını yakala", "nlp kancası", "gölge kanca"
                ]
            )
        )
        is_offensive_or_shadow = (is_offensive_archetype and not has_explicit_respect_rule) or has_offensive_intent
        if is_offensive_or_shadow:
            psychological_rule = (
                "3. TAKTİKSEL PSİKOLOJİK HEDEFLEME & YARA İZİ: Hedefin savunma mekanizmasını aşmak için "
                "stres tetikleyicilerini (stress_triggers), sınır sinyallerini (boundary_signals) ve zihinsel defanslarını "
                "hedef al. Bilinçaltı varsayımlar, gömülü komutlar veya beklenmedik mikro-gözlemlerle savunma hattını baypas et."
            )
        else:
            psychological_rule = (
                "3. HASSASİYETLERE VE SINIRLARA ASLA BASMA (Kırmızı Çizgi Koruması): Karşı tarafın kırmızı çizgilerine "
                "ve hassasiyetlerine asla basma; ortak ilgi alanları üzerinden doğal, saygılı ve empatik bir rezonans oluştur."
            )

        prompt = f"""
Sen dünya standartlarında bir iletişim psikoloğu, adli profil analisti ve diyalog stratejistisin.
Görevin: Aşağıda analizi yapılmış Hedef Kişi için savunmasını düşüren, merak uyandıran ve onu derinden etkileyecek bir İLK TEMAS MESAJI (Opening Hook) ve olası tepkilerine karşı DİYALOG AĞACI tasarlamaktır.

Hedef Kimlik: @{target_name}
İletişim Amacı ve Strateji: {intent_desc}

HEDEFİN KANITLANMIŞ PROFİLİ:
- Biyografi & Gönderi Özeti: {target_profile.get("bio", "Mevcut değil")} | Paylaşımlar: {target_profile.get("posts", [])}
- Tutkuları & Akış Tetikleyicileri: {core_passions} | Enerji Alanları: {energizing_topics} | Akış: {flow_triggers}
- Hassasiyetleri, Stres Tetikleyicileri & Sınır Noktaları (Yara İzleri):
  * Hassasiyetler: {sensitivities}
  * Stres Tetikleyicileri: {stress_triggers}
  * Sınır Sinyalleri & Defans Noktaları: {boundary_signals}
- İletişim Üslubu & Bilişsel Yapı:
  * İletişim Tonu: {comm_tone}
  * Düşünme Modeli (Thinking Style): {thinking}
  * Karmaşıklık Düzeyi: {complexity}
  * Sosyal Yönelim: {social_orient}
  * Mizah Anlayışı: {humor_style}
- Derinlik Özeti: {depth_essence}

ÖNEMLİ KURALLAR:
1. Asla ucuz flört cümlesi veya klişe 'Merhaba tanışabilir miyiz?' mesajı yazma.
2. Hedefin doğrudan paylaşımlarındaki veya ilgi alanlarındaki somut bir detaya (ışık, kelime, proje, tema) referans ver.
{psychological_rule}
4. Karşı taraf savunmacı, agresif veya şüpheci yaklaştığında operatörü zor durumda bırakmayacak, zarafetle merak uyandıran karşı-hamleler (dialogue_tree) sun.

Aşağıdaki JSON şemasında yanıt ver:
{{
  "opening_message": "Doğrudan karşı tarafa gönderilmeye hazır, vurucu açılış mesajı",
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
  "shared_points": ["Hedefle rezonans kurulan veya hedeflenen 1-2 kilit nokta"],
  "confidence": 0.85
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
            clamped_conf = clamp(conf if valid else 0.85, epistemic_state)
            # Eğer model conf dönmüşse ama epistemic tavan sıfırsa clamp sıfırlar
            final_conf = clamped_conf if valid else clamp(0.85, epistemic_state)
            epistemic_dc = bool(epistemic_state.get("data_confidence", False) and valid and final_conf > 0.0)
            epistemic_state["data_confidence"] = epistemic_dc
            ev_status = normalize_evidence_verification_status(
                "verified" if epistemic_dc else "unverified",
                has_verified_proof=epistemic_dc,
            )
            used_evidence = [str(x) for x in (core_passions + energizing_topics + stress_triggers)[:5]]
            return res.model_copy(update={
                "confidence": final_conf if final_conf > 0.0 else (conf if valid else 0.85),
                "input_data_present": input_data_present,
                "evidence_verification_status": ev_status,
                "data_confidence": epistemic_dc,
                "archetype": payload.intent,
                "epistemic": epistemic_state,
                "evidence_used": used_evidence,
            }).model_dump()
        except Exception as e:
            logger.warning(f"HookStudio LLM hatası: {e}")
            # Dürüst fallback: Kanıta dayalı yerel şablon
            default_topic = (
                core_passions[0]
                if core_passions
                else (energizing_topics[0] if energizing_topics else "çalışmalarınız")
            )
            fallback_conf = clamp(0.5, epistemic_state)
            fallback_dc = bool(epistemic_state.get("data_confidence", False) and fallback_conf > 0.0)
            epistemic_state["data_confidence"] = fallback_dc
            return HookResult(
                opening_message=f"Merhaba @{target_name}, {default_topic} üzerine yaklaşımınız dikkatimi çekti. Özellikle son dönemdeki bakış açınızdaki tutarlılık oldukça ilham verici.",
                opening_topic=str(default_topic),
                rationale="Hedefin birincil ilgi odağına doğrudan temas.",
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
                confidence=fallback_conf,
                data_confidence=fallback_dc,
                input_data_present=input_data_present,
                evidence_verification_status="verified" if fallback_dc else "unverified",
                fallback_reason="llm_unavailable_template_fallback",
                epistemic=epistemic_state,
                evidence_used=[str(default_topic)] if default_topic else [],
            ).model_dump()

    from backend.routes.commander import register_commander_routes
    register_commander_routes(
        app,
        rate_limit=rate_limit,
        rate_identity=rate_identity,
        gateway_provider=gateway_provider,
        get_executor=get_executor,
        require_vault_open=require_vault_open,
        require_minor_clearance=require_minor_clearance,
    )
