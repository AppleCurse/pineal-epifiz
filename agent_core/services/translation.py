"""FAZ D · D4 — ÇEVİRİ: ses ve dinlemeyle AYNI kural — metin makineden çıkmaz.

Yerellik kuralı (tartışmasız, ``adapters_voice`` ile birebir aynı):
    * Motor, ``PINEAL_TRANSLATE_URL`` ile gösterilen YEREL bir uç (yalnız
      ``127.0.0.1`` / ``localhost`` / ``[::1]``) ya da yerel bir CLI'dır
      (``PINEAL_TRANSLATE_CMD``, varsayılan: ``trans`` — translate-shell).
    * Uzak bir adres verilirse ``non_local_endpoint`` ile REDDEDİLİR.
    * Motor yoksa çeviri ÜRETİLMEZ: ``available=False`` + makine-okunur
      sebep. Uydurma çeviri yoktur; kaynak metin hedef dil gibi DÖNMEZ.

Çeviri, tespitin ÜSTÜNE kurulur: kaynak dil önce ölçülür (``language.detect``);
ölçüm sonucu motora iletilir ve çıktıya yazılır (hangi dilden çevrildiği
gizlenmez). Tespit ayrı, çeviri ayrı dürüstlük taşır.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict

from agent_core.services.language import LanguageFinding, detect_language

__all__ = [
    "TranslationResult",
    "resolve_engine",
    "translate_text",
    "GATE",
    "MAX_TEXT_CHARS",
]

#: Yetenek kapısı (PolicyKernel ENABLE_* sözlüğü).
GATE = "ENABLE_LOCAL_TRANSLATE"

#: Çeviri motoruna sınırsız metin gönderilmez (maliyet + hafıza).
MAX_TEXT_CHARS = 2000

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]", "0:0:0:0:0:0:0:1"})

_CLI_TIMEOUT = 30.0


class TranslationResult(BaseModel):
    """Tek çeviri denemesinin dürüst sonucu (uydurma metin yok)."""

    available: bool = False
    reason: str = ""
    text: str = ""
    source_language: str = ""
    source_confidence: float = 0.0
    target_language: str = ""
    engine: str = ""
    chars: int = 0
    machine_note: str = ""

    model_config = ConfigDict(extra="forbid")


def _local_translate_endpoint() -> tuple:
    """(url, '') ya da ('', sebep): çeviri ucu da YALNIZ yerel olabilir."""
    url = os.getenv("PINEAL_TRANSLATE_URL", "").strip()
    if not url:
        return "", "no_local_endpoint"
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in _LOCAL_HOSTS:
        return "", "non_local_endpoint"
    if parsed.scheme not in {"http", "https"}:
        return "", "bad_endpoint_scheme"
    return url, ""


def resolve_engine() -> tuple:
    """(motor, '') ya da ('', sebep). Öncelik: yerel uç → yerel CLI.

    Sebep sözlüğü (makine-okunur, dürüst):
        non_local_endpoint — uç TANIMLI ama uzak: sert ret, CLI'ye düşülmez.
        bad_endpoint_scheme — uç tanımlı ama http(s) değil.
        no_engine          — ne uç ne CLI tanımlı/bulundu.
    """
    url_configured = bool(os.getenv("PINEAL_TRANSLATE_URL", "").strip())
    url, reason = _local_translate_endpoint()
    if url:
        return "local_endpoint", ""
    if url_configured:
        # Uç TANIMLI ama kabul edilemez: ret kararı gizlenmez, CLI'ye düşülmez.
        return "", reason
    cmd = os.getenv("PINEAL_TRANSLATE_CMD", "trans").strip() or "trans"
    if shutil.which(cmd):
        return "cli", ""
    return "", "no_engine"


def _clean_text(text: str) -> str:
    return str(text or "").strip()[:MAX_TEXT_CHARS]


async def translate_text(
    text: str,
    target: str = "en",
    *,
    timeout: float = _CLI_TIMEOUT,
) -> TranslationResult:
    """Metni hedef dile çevirir: ÖNCE tespit, SONRA yerel motor.

    Motor yoksa / uç uzaksa / boş çıktı gelirse çeviri ÜRETİLMEZ;
    dürüst ``available=False`` + sebep döner.
    """
    clean = _clean_text(text)
    target_lang = (target or "").strip().lower()[:8]
    if not clean:
        return TranslationResult(available=False, reason="empty_text")
    if not target_lang:
        return TranslationResult(available=False, reason="empty_target")

    finding: LanguageFinding = detect_language(clean)
    base = {
        "source_language": finding.language,
        "source_confidence": finding.confidence,
        "target_language": target_lang,
        "chars": len(clean),
    }

    engine, reason = resolve_engine()
    if not engine:
        return TranslationResult(
            available=False, reason=reason, engine="",
            machine_note="çeviri motoru yok — metin çevrilmeden bırakıldı", **base
        )

    if engine == "local_endpoint":
        translated, engine_reason = await _run_local_endpoint(clean, finding, target_lang, timeout)
    else:
        translated, engine_reason = await _run_cli(clean, finding, target_lang, timeout)

    translated = (translated or "").strip()
    if not translated:
        return TranslationResult(
            available=False, reason=engine_reason or "empty_translation", engine=engine,
            machine_note="motor çeviri üretmedi — uydurma çeviri yok", **base
        )
    if translated == clean:
        # Motor girdiyi olduğu gibi geri verdi: bu çeviri DEĞİLDİR.
        return TranslationResult(
            available=False, reason="engine_echoed_input", engine=engine,
            machine_note="motor metni değiştirmeden döndürdü — çeviri iddia edilmez", **base
        )

    return TranslationResult(
        available=True, reason="", text=translated, engine=engine,
        machine_note=f"çeviri yerel motorda üretildi ({engine})", **base
    )


async def _run_local_endpoint(text: str, finding: LanguageFinding, target: str, timeout: float) -> tuple:
    url, reason = _local_translate_endpoint()
    if not url:
        return "", reason
    try:
        import httpx
    except ImportError:
        return "", "dependency_missing:httpx"

    payload: dict[str, Any] = {"text": text, "target": target}
    if finding.language != "unknown":
        payload["source"] = finding.language
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
    except Exception as exc:  # ağ hatası gizlenmez, sınıflandırılır
        return "", f"endpoint_error:{type(exc).__name__}"

    if response.status_code >= 400:
        return "", f"endpoint_status:{response.status_code}"
    body = response.content.decode("utf-8", "replace").strip()
    if not body:
        return "", "empty_translation"
    # Uç JSON ({"text": ...}) ya da düz metin dönebilir; ikisi de kabul.
    try:
        import json

        data = json.loads(body)
        if isinstance(data, dict):
            candidate = data.get("text") or data.get("translation") or ""
            return str(candidate).strip(), ""
    except ValueError:
        pass
    return body, ""


async def _run_cli(text: str, finding: LanguageFinding, target: str, timeout: float) -> tuple:
    """CLI sözleşmesi: metin STDIN'den girer, çeviri STDOUT'tan okunur.

    Varsayılan ``trans`` (translate-shell) bayt-bayt buna uyar:
    ``trans -b -no-ansi kaynak:hedef``.
    """
    cmd = os.getenv("PINEAL_TRANSLATE_CMD", "trans").strip() or "trans"
    source = finding.language if finding.language != "unknown" else "auto"
    command = [cmd, "-b", "-no-ansi", f"{source}:{target}"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(text.encode("utf-8")), timeout=timeout
        )
    except asyncio.TimeoutError:
        return "", "timeout"
    except (OSError, FileNotFoundError) as exc:
        return "", f"engine_error:{type(exc).__name__}"

    if proc.returncode != 0:
        detail = (stderr or b"").decode("utf-8", "replace").strip()[:160]
        return "", f"translation_failed:{detail or proc.returncode}"
    return (stdout or b"").decode("utf-8", "replace").strip(), ""


def status() -> dict[str, Any]:
    """Çevirinin GERÇEK durumu: motor var mı, kapı ne, uç yerel mi."""
    engine, reason = resolve_engine()
    url_set = bool(os.getenv("PINEAL_TRANSLATE_URL", "").strip())
    return {
        "available": bool(engine),
        "engine": engine or None,
        "reason": reason or None,
        "gate": GATE,
        "url_configured": url_set,
        "max_chars": MAX_TEXT_CHARS,
    }
