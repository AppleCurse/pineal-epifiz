#!/usr/bin/env python3
"""preflight_9router.py — Pineal 9Router Canlı Doğrulama ve Sağlık Testi.

Bu script:
1. 9Router yerel servisinin (127.0.0.1:20128) ayakta olduğunu denetler.
2. 4 İş Koridoru + 3 Jüri Koltuğuna canlı ping atar, 200 OK ve gecikmeleri doğrular.
3. Multimodal görsel desteğini (base64) test eder.
4. Çıktıyı JSON olarak raporlar ve hata durumunda exit code != 0 döner (CI uyumlu).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import httpx
except ImportError:
    print("HATA: httpx kütüphanesi gerekli (pip install httpx)")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError as exc:
    logger.debug(
        "[<modül>] ImportError — atlandı (beklenen/opsiyonel, iz bırakıldı): %s", exc
    )

# BOSS-1: ön denetim ile çalışma zamanı AYNI çözümleyiciyi kullanır. Önceden
# preflight PINEAL_LLM_API_KEY'i ilk sırada okuyor, gateway ise o adı hiç
# okumuyordu; yeşil bir preflight farklı bir kanalı doğrulamış olabiliyordu.
try:
    from agent_core.services.llm_gateway import (  # type: ignore
        NINEROUTER_DEFAULT_BASE_URL,
        resolve_legacy_endpoint,
    )
except Exception:  # pragma: no cover - script tek başına da çalışabilsin
    NINEROUTER_DEFAULT_BASE_URL = "http://127.0.0.1:20128/v1"

    def resolve_legacy_endpoint():  # type: ignore
        return (
            os.getenv("NINEROUTER_BASE_URL") or os.getenv("PINEAL_LLM_BASE_URL") or NINEROUTER_DEFAULT_BASE_URL,
            os.getenv("NINEROUTER_API_KEY") or os.getenv("PINEAL_LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY"),
            "9router",
        )

_configured_base_url, API_KEY, TRANSPORT_LABEL = resolve_legacy_endpoint()
# Preflight 9Router hub'ını denetler: operatör uzak bir hub adresi verdiyse ona
# uyar, hiçbir şey verilmemişse yerel varsayılana düşer.
BASE_URL = (
    _configured_base_url
    if TRANSPORT_LABEL == "9router"
    else os.getenv("NINEROUTER_BASE_URL") or NINEROUTER_DEFAULT_BASE_URL
)

ROUTES = [
    "pineal-deep-reasoning",
    "pineal-general-reasoning",
    "pineal-fast-extract",
    "pineal-vision",
    "pineal-juror-google",
    "pineal-juror-claude",
    "pineal-juror-open",
]

# 1x1 kırmızı PNG base64
RED_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def run_preflight() -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
        "X-9Router-Token-Saver": "off",
    }
    client = httpx.Client(timeout=30.0)
    results: dict[str, Any] = {
        "timestamp_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "base_url": BASE_URL,
        "transport_label": TRANSPORT_LABEL,
        "api_key_source": (
            "NINEROUTER_API_KEY" if os.getenv("NINEROUTER_API_KEY")
            else "PINEAL_LLM_API_KEY" if os.getenv("PINEAL_LLM_API_KEY")
            else "OPENROUTER_API_KEY" if os.getenv("OPENROUTER_API_KEY")
            else "none"
        ),
        "routes": {},
        "all_ok": True,
    }

    print(f"=== PINEAL 9ROUTER PREFLIGHT ({results['timestamp_utc']} UTC) ===")
    print(f"Uç Nokta: {BASE_URL}")

    for route in ROUTES:
        t0 = time.perf_counter()
        payload = {
            "model": route,
            "messages": [{"role": "user", "content": 'Say {"status":"ready"}'}],
            "max_tokens": 15,
        }
        try:
            resp = client.post(f"{BASE_URL}/chat/completions", json=payload, headers=headers)
            elapsed = time.perf_counter() - t0
            ok = resp.status_code == 200
            results["routes"][route] = {
                "status_code": resp.status_code,
                "latency_s": round(elapsed, 2),
                "ok": ok,
            }
            if not ok:
                results["all_ok"] = False
                print(f"[FAIL {resp.status_code}] {route:28s} ({elapsed:.2f}s): {resp.text[:80]}")
            else:
                print(f"[OK 200]   {route:28s} ({elapsed:.2f}s)")
        except Exception as e:
            results["all_ok"] = False
            results["routes"][route] = {"error": str(e), "ok": False}
            print(f"[ERROR]    {route:28s}: {e}")

    # Multimodal test
    print("\n--- Multimodal Görsel Testi (pineal-vision) ---")
    t0 = time.perf_counter()
    vision_payload = {
        "model": "pineal-vision",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What color is this pixel? Answer in one word."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{RED_PNG}"}},
                ],
            }
        ],
        "max_tokens": 10,
    }
    try:
        resp = client.post(f"{BASE_URL}/chat/completions", json=vision_payload, headers=headers)
        elapsed = time.perf_counter() - t0
        ok = resp.status_code == 200
        results["vision_multimodal"] = {
            "status_code": resp.status_code,
            "latency_s": round(elapsed, 2),
            "ok": ok,
        }
        if ok:
            print(f"[OK 200]   pineal-vision (multimodal base64) ({elapsed:.2f}s)")
        else:
            results["all_ok"] = False
            print(f"[FAIL {resp.status_code}] pineal-vision (multimodal): {resp.text[:80]}")
    except Exception as e:
        results["all_ok"] = False
        results["vision_multimodal"] = {"error": str(e), "ok": False}
        print(f"[ERROR]    pineal-vision (multimodal): {e}")

    return results


if __name__ == "__main__":
    report = run_preflight()
    report_file = ROOT / "reports" / "9router_preflight_latest.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapor kaydedildi: {report_file.relative_to(ROOT)}")
    if not report["all_ok"]:
        print("\nSONUÇ: PREFLIGHT BAŞARISIZ!")
        sys.exit(1)
    print("\nSONUÇ: TÜM ROTALAR %100 CANLI VE DOĞRULANDI.")
    sys.exit(0)
