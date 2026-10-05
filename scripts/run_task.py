#!/usr/bin/env python3
"""[W4.2] Rust TaskManager -> PinealExecutor standart girişi.

Rust tarafındaki eski zincir iki adımda ölüydü ([001]/[002]/[049]):
önce scraper.py (X-unsupported -> exit 1), sonra var olmayan
rust_bridge_agent. Bu betik o zincirin TEK ve GERÇEK halefidir:

    stdin JSON  ->  platform_registry (tek sahiplik)  ->  kazıma  ->
    PinealExecutor.execute_task  ->  stdout JSON (TaskStatus)

Sözleşme (sahte veri YASAK):
- Girdi (stdin, UTF-8 JSON):
    {"url": str, "rituals": [str], "playlist": [str], "envies": [str],
     "cookie": str (opsiyonel), "scraper_type": str (opsiyonel, yoksayılır —
     platform kararı URL'den registry'de verilir [023])}
- Çıktı (stdout): her durumda TEK JSON nesnesi.
- Çıkış kodları:
    0 = pipeline koştu (TaskStatus üretildi; halted_* dahil dürüst duraklar)
    2 = platform desteklenmiyor / yetki bekleniyor (unsupported_web, x)
    3 = kazıma kanıt üretemedi (InsufficientEvidence)
    4 = iç hata (JSON parse, executor exception)
- Veri stdin'den okunur; ASLA script metnine/komut satırına gömülmez
  ([045]'in enjeksiyon dersi; API anahtarı/command-line sızıntısı yok).
- Loglar stderr'e akar (TaskManager telemetriye taşır).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone

# Betik repo kökünden bağımsız çalışsın: scripts/ -> repo kökü
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _log(level: str, msg: str) -> None:
    print(f"[run_task][{level}] {msg}", file=sys.stderr, flush=True)


def _emit(payload: dict, exit_code: int) -> None:
    print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)
    raise SystemExit(exit_code)


async def main() -> None:
    try:
        req = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as e:
        _emit({"status": "invalid_input", "error": f"stdin JSON değil: {e}"}, 4)

    url = str(req.get("url") or "")
    rituals = [str(r).strip() for r in (req.get("rituals") or []) if str(r).strip()]
    playlist = [str(p).strip() for p in (req.get("playlist") or []) if str(p).strip()]
    envies = [str(e).strip() for e in (req.get("envies") or []) if str(e).strip()]
    cookie = str(req.get("cookie") or "")

    from agent_core.services.platform_registry import (
        build_user_context,
        effective_scraper_type,
        scrape_instagram,
        scrape_x,
    )

    platform = effective_scraper_type(url, req.get("scraper_type"))
    _log("INFO", f"platform kararı: {platform} (url={url or '<yok>'})")
    if url and platform == "unsupported_web":
        _emit({
            "status": "unsupported_platform",
            "platform": "unsupported_web",
            "note": "Tanınmayan platform; tahmine dayalı kazıma yapılmaz ([023]).",
        }, 2)

    payload = {
        **build_user_context(rituals, playlist, envies),
        "target_profile": {"bio": "", "posts": [], "post_times": [], "images": []},
        # [FAZ A] Operatör CLI'si kasa bilmez; omurga durumunu açıkça taşır
        # (ajanlar kasa gerçeğini tahmin etmez, payload'dan okur).
        "policy": {"vault_locked": False},
    }

    if url and platform == "x":
        # [FAZ A · Retina] X artık "yetki bekleyen" bir delik değil: gerçek
        # sensör omurgadan koşar (sensor.x.twscrape). Kanıt üretemezse sahte
        # profil ÜRETİLMEZ; görev dürüstçe durur (exit 3).
        try:
            payload["target_profile"].update(await scrape_x(url, log=_log))
        except Exception as e:
            if "InsufficientEvidenceError" in type(e).__name__:
                _emit({"status": "halted_evidence", "platform": "x",
                       "reason": str(e)[:300]}, 3)
            _log("ERROR", f"X kazıma hatası: {type(e).__name__}: {e}")
            _emit({"status": "scrape_failed", "platform": "x",
                   "error": f"{type(e).__name__}: {e}"[:300]}, 3)
    elif url:
        try:
            payload["target_profile"].update(await scrape_instagram(url, cookie, log=_log))
        except Exception as e:
            if "InsufficientEvidenceError" in type(e).__name__ or "TargetPrivateError" in type(e).__name__:
                _emit({"status": "halted_evidence", "reason": str(e)[:300]}, 3)
            _log("ERROR", f"kazıma hatası: {type(e).__name__}: {e}")
            _emit({"status": "scrape_failed", "error": f"{type(e).__name__}: {e}"[:300]}, 3)

    from agent_core.task_executor import PinealExecutor

    task_id = f"rust_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    executor = PinealExecutor(log_callback=_log)
    # Operatör CLI'si kasa bilmez; omurga politikası payload ile aynıdır.
    try:
        executor.search_engine.set_policy(payload.get("policy") or {})
    except Exception:
        pass
    try:
        status = await executor.execute_task(payload, task_id)
    except Exception as e:
        _log("ERROR", f"executor hatası: {type(e).__name__}: {e}")
        _emit({"status": "failed", "error": f"{type(e).__name__}: {e}"[:300]}, 4)

    # TaskStatus -> JSON (durumlar dürüst: halted_* dahil exit 0; pipeline KOŞTU)
    _emit(status.model_dump(mode="json"), 0)


if __name__ == "__main__":
    asyncio.run(main())
