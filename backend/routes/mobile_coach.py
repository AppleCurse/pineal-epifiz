"""Mobil danışman (koç) köprüsü — ``POST /api/mobile/coach``.

[2026-10-23] Neden var?
    Android uygulaması Aspasia koç sohbetini doğrudan
    ``generativelanguage.googleapis.com`` adresine gönderiyordu:
    LLM anahtarı cihazda duruyor, kasa/maliyet/kota/telemetri kapıları
    atlanıyor ve modele giden sistem istemi denetlenemiyordu.

    Bu uç istemi SUNUCUDA kurar (``agent_core.aspasia.mobile_coach``), yanıtı
    tek ağ geçidinden (``LLMGateway``) geçirir ve hangi modelin kullanıldığını
    raporlar. İstemci "system prompt" GÖNDEREMEZ; yalnız yapılandırılmış
    bağlam gönderir ve beyaz liste dışı anahtarlar yanıtta
    ``dropped_context_fields`` olarak görünür (sessiz yutma yok).

Neden ayrı modül?
    ``backend/api.py`` tek-modül tavanı (``tests/unit/test_api_monolith_ratchet.py``)
    yeni satır yerine MODÜL ÇIKARMAYI zorunlu kılar. Bağımlılıklar ENJEKTE
    edilir: bu modül ``backend.api``'yi içe aktarmaz (dairesel bağımlılık yok).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

__all__ = ["MobileCoachPayload", "register_mobile_coach_routes"]


class MobileCoachPayload(BaseModel):
    """Mobil danışman isteği — serbest istem YOK, yalnız yapılandırılmış bağlam."""

    client_id: str = Field(default="mobile", max_length=64)
    user_message: str = Field(min_length=1, max_length=4000)
    language: str = Field(default="tr", max_length=8)
    model_override: Optional[str] = Field(default=None, max_length=120)
    profile_context: Optional[Dict[str, Any]] = None
    hypotheses: List[Dict[str, Any]] = Field(default_factory=list, max_length=12)
    image_data: Optional[str] = Field(default=None, max_length=8_000_000)


def register_mobile_coach_routes(
    app: Any,
    *,
    rate_limit: Callable[[str, str], bool],
    rate_identity: Callable[[Request], str],
    gateway_provider: Callable[[], Any],
) -> None:
    """``/api/mobile/coach`` ucunu ``app``'e kaydeder.

    ``gateway_provider``: TEK ağ geçidini verir (Aspasia'nın ``LLMGateway``'i).
    İkinci bir LLM yolu açılmaz — bütçe/kota/ikame telemetrisi aynı yerden akar.
    """

    @app.post("/api/mobile/coach")
    async def mobile_coach(payload: MobileCoachPayload, request: Request):
        """Koç yanıtı: istem sunucuda kurulur, model gateway'den geçer.

        Dönen ``source``/``model`` alanları kaynağı GİZLEMEZ. Gateway hatası
        sessizce yutulmaz: istemci hata sınıfını ve sebebini görür, kendi
        geri düşüşünü (Gemini) açıkça etiketler.
        """
        if not rate_limit(f"mobile_coach:{rate_identity(request)}", "aspasia"):
            return JSONResponse(
                {"error": {"code": "RATE_LIMITED", "message": "Danışman yoğun; kısa bir mola verin."}},
                status_code=429,
            )

        from agent_core.aspasia.mobile_coach import (
            build_system_prompt,
            build_user_message,
            sanitize_context,
        )

        # Beyaz liste: istemci "system_prompt"/"instructions" gönderirse modele
        # ULAŞMAZ. Düşen anahtarlar sessizce yutulmaz — yanıtta raporlanır.
        accepted_context = sanitize_context(payload.profile_context)
        dropped_context = sorted(set(payload.profile_context or {}) - set(accepted_context))
        system_prompt = build_system_prompt(
            language=payload.language,
            profile_context=accepted_context,
            hypotheses=payload.hypotheses,
        )
        user_message = build_user_message(
            payload.user_message, has_image=bool(payload.image_data)
        )

        gateway = gateway_provider()
        if gateway is None:
            return JSONResponse(
                {"error": {"code": "GATEWAY_UNAVAILABLE", "message": "Model ağ geçidi yüklenemedi"}},
                status_code=503,
            )

        try:
            if payload.model_override:
                answer = await gateway.query(
                    prompt=user_message,
                    system_prompt=system_prompt,
                    temperature=0.4,
                    tier=1,
                    model=payload.model_override,
                    images=[payload.image_data] if payload.image_data else None,
                )
                model_label = payload.model_override
            else:
                answer = await gateway.query_chain(
                    prompt=user_message,
                    task="dialogue",
                    temperature=0.4,
                    system_prompt=system_prompt,
                    agent_name="aspasia",
                    images=[payload.image_data] if payload.image_data else None,
                )
                model_label = "chain:aspasia"
        except Exception as exc:
            # Sessiz yutma yok: istemci hangi sınıf hatayla düştüğünü görür.
            return JSONResponse(
                {
                    "error": {
                        "code": "COACH_UNAVAILABLE",
                        "message": "Model yanıtı alınamadı.",
                        "reason": f"{type(exc).__name__}: {str(exc)[:160]}",
                    }
                },
                status_code=502,
            )

        text = (answer or "").strip()
        if not text:
            return JSONResponse(
                {"error": {"code": "EMPTY_ANSWER", "message": "Model boş yanıt döndürdü."}},
                status_code=502,
            )

        return {
            "answer": text,
            "source": "backend",
            "model": model_label,
            "language": payload.language,
            "context_fields": sorted(accepted_context),
            "dropped_context_fields": dropped_context,
        }
