"""Dil hattı uçları — ``/api/language/*`` (FAZ D · D4).

``backend/api.py`` tek-modül tavanı (``tests/unit/test_api_monolith_ratchet.py``)
yüzünden AYRILDI; gövdeler değişmeden taşındı. Bağımlılıklar
(``rate_limit``, kasa kapısı, ``broadcast_log``, env bayrağı) ENJEKTE edilir,
böylece bu modül ``backend.api``'yi içe aktarmaz (dairesel bağımlılık yok).
Rotalar ``backend/api.py`` içinde ``app.include_router`` ile, eskiden olduğu
sırada kaydedilir — ``/`` statik mount'undan önce.
"""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

__all__ = [
    "LanguageDetectPayload",
    "LanguageTranslatePayload",
    "make_language_router",
]


class LanguageDetectPayload(BaseModel):
    """[FAZ D · D4] Dil tespiti isteği."""

    text: str = Field(min_length=1, max_length=20000)
    client_id: str = Field(default="default", max_length=128)


class LanguageTranslatePayload(BaseModel):
    """[FAZ D · D4] Yerel çeviri isteği (metin makineden çıkmaz)."""

    text: str = Field(min_length=1, max_length=2000)
    target: str = Field(default="en", min_length=2, max_length=8)
    client_id: str = Field(default="default", max_length=128)


def make_language_router(
    *,
    rate_limit: Callable[[str, str], bool],
    check_vault_interlock: Callable[[str], bool],
    broadcast_log: Callable[[str, str, str], None],
    flag_env: Callable[[str], bool],
) -> APIRouter:
    """Dil uçlarını bağımlılıkları enjekte edilmiş bir ``APIRouter`` olarak üretir."""
    router = APIRouter()
    _check_vault_interlock = check_vault_interlock
    _flag_env = flag_env

    @router.get("/api/language/status")
    async def api_language_status():
        """[FAZ D · D4] Dil hattının GERÇEK durumu: tespit her zaman yereldir;
        çeviri motoru var mı, kapı açık mı, kanıta işlenen SON ölçüm ne?"""
        from agent_core.services import language, translation

        return {
            "detect": {"available": True, "method": "deterministic_local"},
            "translate": translation.status(),
            "last": language.last_finding(),
        }


    @router.post("/api/language/detect")
    async def api_language_detect(req: LanguageDetectPayload):
        """[FAZ D · D4] Metnin dilini ölçer: omurga üzerinden (kasa kapısı dâhil).

        Sinyal yoksa `language=unknown` + sebep döner; etiket UYDURULMAZ.
        Kasa kilitliyken tespit de koşamaz (Tüzük Md.4, istisna yok).
        """
        from agent_core.capabilities.base import CapabilityContext
        from agent_core.capabilities.policy import PolicyState
        from agent_core.capabilities.registry import bootstrap
        from agent_core.capabilities.runner import CapabilityRunner

        if not rate_limit(f"language:{req.client_id}", "language"):
            return JSONResponse(
                {"error": {"code": "RATE_LIMITED", "message": "Çok fazla dil isteği"}},
                status_code=429,
            )

        runner = CapabilityRunner(registry=bootstrap())
        state = PolicyState(
            enabled_flags={}, vault_locked=not _check_vault_interlock(req.client_id), rate_ok=True
        )
        result = await runner.run(
            "extractor.text.language", CapabilityContext(subject=req.text), state=state
        )
        finding = result.payload
        payload = {
            "available": bool(result.available),
            "denied_by": result.denied_by,
            "reason": result.unavailable_reason,
            "language": getattr(finding, "language", "") if result.available else "",
            "confidence": getattr(finding, "confidence", 0.0) if result.available else 0.0,
            "script": getattr(finding, "script", "") if result.available else "",
            "detect_reason": getattr(finding, "reason", None) if result.available else None,
            "chars": getattr(finding, "chars", 0) if result.available else 0,
        }
        if result.denied_by:
            broadcast_log(req.client_id, "WARNING", f"DİL: tespit engellendi — kasa:{result.denied_by}")
        elif payload["language"] == "unknown":
            broadcast_log(req.client_id, "INFO", f"DİL: ölçülemedi — {payload['detect_reason']}")
        else:
            broadcast_log(
                req.client_id,
                "INFO",
                f"DİL: {payload['language']} · güven {payload['confidence']:.2f}",
            )
        return payload


    @router.post("/api/language/translate")
    async def api_language_translate(req: LanguageTranslatePayload):
        """[FAZ D · D4] Metni YEREL motorda çevirir: ses/dinleme ile aynı kural.

        Uzak uç REDDEDİLİR (`non_local_endpoint`); motor yoksa çeviri ÜRETİLMEZ
        (`available:false` + sebep). Kaynak metin hedef dilmiş gibi DÖNMEZ.
        """
        from agent_core.capabilities.base import CapabilityContext
        from agent_core.capabilities.policy import PolicyState
        from agent_core.capabilities.registry import bootstrap
        from agent_core.capabilities.runner import CapabilityRunner
        from agent_core.services.translation import GATE, MAX_TEXT_CHARS, status as _translation_status

        if not rate_limit(f"language:{req.client_id}", "language"):
            return JSONResponse(
                {"error": {"code": "RATE_LIMITED", "message": "Çok fazla çeviri isteği"}},
                status_code=429,
            )

        runner = CapabilityRunner(registry=bootstrap())
        state = PolicyState(
            enabled_flags={GATE: _flag_env(GATE)},
            vault_locked=not _check_vault_interlock(req.client_id),
            rate_ok=True,
        )
        result = await runner.run(
            "extractor.text.translate_local",
            CapabilityContext(subject=req.text[:MAX_TEXT_CHARS], params={"target": req.target}),
            state=state,
        )
        translated = ""
        if result.items:
            translated = result.items[0].content
        payload = {
            "available": bool(result.available and result.items),
            "denied_by": result.denied_by,
            "reason": result.unavailable_reason,
            "text": translated,
            "source_language": result.notes.get("source_language", ""),
            "source_confidence": result.notes.get("source_confidence", 0.0),
            "target_language": req.target,
            "engine": result.notes.get("engine", ""),
        }
        if payload["available"]:
            broadcast_log(
                req.client_id,
                "INFO",
                f"DİL: çeviri tamam — {payload['source_language']} → {req.target} ({payload['engine']})",
            )
        else:
            why = result.denied_by or result.unavailable_reason or _translation_status().get("reason")
            broadcast_log(req.client_id, "WARNING", f"DİL: ÇEVİRİ ÜRETİLEMEDİ — {why}")
        return payload

    return router
