"""Dil hattı uçları — ``/api/language/*`` (status · detect · translate).

[API-BÖLME 2] Bu modül ``backend/api.py`` tek-modül TAVANI yüzünden AYRILDI
(``tests/unit/test_api_monolith_ratchet.py``; kural: yeni satır yerine MODÜL
ÇIKAR — ``docs/reports/API_MONOLITH_SPLIT_PLAN.md`` §4, "düşük bağımlılık"
sırasının ilk adımı). Rotalar ``register_language_routes`` ile ``app``'e
KAYDEDİLİR ve statik mount'tan ÖNCE sıralanır. Bağımlılıklar ENJEKTE edilir:
bu modül ``backend.api``'yi içe aktarmaz, dairesel bağımlılık yoktur.

Uç sözleşmeleri (gövdeler taşınırken DEĞİŞTİRİLMEDİ):
  * ``GET  /api/language/status``    → tespit her zaman yereldir; çeviri motoru
    var mı, kapı açık mı, kanıta işlenen SON ölçüm ne. Uydurma uygunluk yok.
  * ``POST /api/language/detect``    → dil ölçümü omurga (capability) üzerinden;
    sinyal yoksa ``language=unknown`` + sebep döner, etiket UYDURULMAZ;
    kasa kilitliyken tespit de koşmaz (Tüzük Md.4, istisna yok).
  * ``POST /api/language/translate`` → metin YEREL motorda çevrilir; uzak uç
    REDDEDİLİR (``non_local_endpoint``); motor yoksa çeviri üretilmez
    (``available:false`` + sebep), kaynak metin hedef dilmiş gibi DÖNMEZ.

HIZ SINIRI (sözleşme — ``tests/integration/test_language_transport_contract.py`` kilitler):
ÜÇ uç da AYNI kovayı paylaşır: ``language:{client_id}`` · 60 istek/60 sn
(``backend/api.py`` → ``RATE_LIMITS["language"]``). ``client_id``:
``detect``/``translate`` gövdeden, ``status`` ise ``?client_id=`` sorgu
parametresinden alınır (varsayılan ``default``). Aşımda üçü de AYNI gövdeyle 429
döner: ``{"error": {"code": "RATE_LIMITED", ...}}``. Kova paylaşıldığı için bir uçta
harcanan istek diğerlerinin bütçesinden düşer.

KASA MANDALI (vault): ``detect`` ve ``translate`` kilitliyken KOŞMAZ
(``denied_by == "vault"`` — Tüzük Md.4). ``status`` yalnız OKUMA raporudur
(motor var mı, kapı açık mı, son ölçüm ne); kasadan bağımsız çalışır ve bu,
davranış sözleşmesinin parçasıdır — gizli bir istisna değil.

Test: ``tests/integration/test_language_api_faz_d.py`` (davranış),
``tests/integration/test_language_transport_contract.py`` (taşıma sözleşmesi:
hız sınırı paylaşımı · 429 gövdesi · kasa mandalı · 422),
``tests/unit/test_language_detect.py`` (dil ölçümü).
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import Query

from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

__all__ = [
    "LanguageDetectPayload",
    "LanguageTranslatePayload",
    "register_language_routes",
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


def register_language_routes(
    app: Any,
    *,
    rate_limit: Callable[[str, str], bool],
    check_vault_interlock: Callable[[str], bool],
    broadcast_log: Callable[[str, str, str], None],
    flag_env: Callable[[str], bool],
) -> None:
    """``/api/language/*`` uçlarını ``app``'e kaydeder.

    ``check_vault_interlock``: oda kasası açık mı (açık değilse yetenek
    ``vault_locked`` ile reddedilir). ``flag_env``: capability kapısı okuma
    (ör. ``ENABLE_LOCAL_TRANSLATE``) — ``backend/api.py``'deki tek kaynak.
    """

    @app.get("/api/language/status")
    async def api_language_status(
        client_id: str = Query(
            "default",
            min_length=1,
            max_length=128,
            pattern=r"^[A-Za-z0-9_-]+$",
            description="Hız sınırı kovasının istemci kimliği (60 istek/60 sn).",
            examples=["client_ab12cd3"],
        )
    ):
        """[FAZ D · D4] Dil hattının GERÇEK durumu: tespit her zaman yereldir;
        çeviri motoru var mı, kapı açık mı, kanıta işlenen SON ölçüm ne?

        [DENETİM 2026-10-14] Bu uç, modül docstring'inin söz verdiği kovayı
        (``language:{client_id}``) ``detect``/``translate`` ile PAYLAŞIR; modül
        açıklaması üç ucun paylaştığını yazıp burada sınır uygulanmaması
        "yazılanla koşanın ayrışması" kusuruydu. ``client_id`` sorgu
        parametresinden gelir çünkü GET gövdesi yoktur (ön yüz zaten
        ``?client_id=`` gönderiyor).

        Parametre sözleşmesi: 1..128 karakter ve ``^[A-Za-z0-9_-]+$`` — gövde
        modellerindeki (`LanguageRequest.client_id`, ``max_length=128``) sınırın
        aynısıdır ki üç uç aynı kimlikleri kabul etsin. İhlalde 422 döner;
        böylece sorgu dizesi, kova sözlüğüne keyfî biçimde anahtar yazamaz
        (``backend/api.py`` P0-4 kuralı: client_id biçim VE uzunluk doğrulanır).
        """
        if not rate_limit(f"language:{client_id}", "language"):
            return JSONResponse(
                {"error": {"code": "RATE_LIMITED", "message": "Çok fazla dil durumu isteği"}},
                status_code=429,
            )

        from agent_core.services import language, translation

        return {
            "detect": {"available": True, "method": "deterministic_local"},
            "translate": translation.status(),
            "last": language.last_finding(),
        }


    @app.post("/api/language/detect")
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
            enabled_flags={}, vault_locked=not check_vault_interlock(req.client_id), rate_ok=True
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


    @app.post("/api/language/translate")
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
            enabled_flags={GATE: flag_env(GATE)},
            vault_locked=not check_vault_interlock(req.client_id),
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
