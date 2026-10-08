"""Canlı provider doğrulama probu (2026-09-08) — anahtar değerlerini asla loglamaz.

Her OpenAI-uyumlu sağlayıcının /models listesini çeker; katalog (provider_catalog)
ve final_routing_policy.ROUTES ile karşılaştırır. Yalnız OKUMA — LLM çağrısı yok.
"""

import logging

logger = logging.getLogger(__name__)

import json
import os
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning(
            "[<modül>] beklenmeyen hata (Exception) yutulmadı — iz bırakıldı: %s", exc, exc_info=True
        )

import httpx

REPO = Path(__file__).resolve().parents[1]
ENV_PATH = REPO / ".env"


def load_env() -> dict:
    data = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            data[k.strip()] = v.strip()
    return {**os.environ, **data}


ENV = load_env()

# provider_id -> (base_url, env_key)
PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "deepseek": ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "cerebras": ("https://api.cerebras.ai/v1", "CEREBRAS_API_KEY"),
    "nous-research": ("https://inference-api.nousresearch.com/v1", "NOUS_API_KEY"),
    "google-gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "GEMINI_API_KEY",
    ),
    "together": ("https://api.together.xyz/v1", "TOGETHER_API_KEY"),
    "deepinfra": ("https://api.deepinfra.com/v1/openai", "DEEPINFRA_API_KEY"),
    "nvidia-nim": ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY"),
}

CATALOG = json.loads((REPO / "config" / "provider_catalog.json").read_text(encoding="utf-8"))
CATALOG_MODELS = {}
for p in CATALOG.get("providers", []):
    CATALOG_MODELS[p["id"]] = [m.get("id") for m in p.get("models", [])]

sys.path.insert(0, str(REPO))
from agent_core.services import final_routing_policy as pol  # noqa: E402

ROUTES = {}
for key, spec in pol.ROUTES.items():
    ROUTES.setdefault(spec.provider, []).append((spec.model, spec.tier, spec.input_per_million_usd))


def redact(key: str) -> str:
    return f"{key[:4]}...{key[-3:]} ({len(key)} kar)" if key else "(BOŞ)"


def main() -> None:
    print("=" * 78)
    print("CANLI PROVIDER /models DOĞRULAMASI — 2026-09-08")
    print("=" * 78)
    for pid, (base, env_key) in PROVIDERS.items():
        key = ENV.get(env_key, "")
        print(f"\n--- {pid} | anahtar: {redact(key)}")
        if not key:
            print("  ANAHTAR YOK — atlandı")
            continue
        url = base.rstrip("/") + "/models"
        try:
            with httpx.Client(timeout=25, follow_redirects=True) as client:
                r = client.get(url, headers={"Authorization": f"Bearer {key}"})
        except Exception as exc:  # noqa: BLE001
            print(f"  HATA: {type(exc).__name__}: {exc}")
            continue
        if r.status_code != 200:
            body = r.text[:200].replace("\n", " ")
            print(f"  HTTP {r.status_code}: {body}")
            continue
        try:
            payload = r.json()
        except Exception:  # noqa: BLE001
            print(f"  JSON değil (HTTP {r.status_code}), ilk 200: {r.text[:200]}")
            continue
        if isinstance(payload, list):
            raw = payload
        elif isinstance(payload, dict):
            raw = payload.get("data") or payload.get("models") or []
        else:
            raw = []
        ids = sorted({
            (str(m.get("id", "")) if isinstance(m, dict) else str(m)).strip()
            for m in raw
            if (isinstance(m, dict) and m.get("id")) or (isinstance(m, str) and m)
        })
        print(f"  Canlı model sayısı: {len(ids)}")
        catalog = CATALOG_MODELS.get(pid, [])
        routes_here = [m for m, *_ in ROUTES.get(pid, [])]
        print(f"  Katalogda kayıtlı: {len(catalog)} | ROUTES'ta: {len(routes_here)}")
        if ids:
            interesting = [
                i for i in ids
                if any(tok in i for tok in ("gpt-oss", "deepseek", "gemini", "claude", "luna", "laguna", "llama-3.3"))
            ]
            shown = interesting[:15] if interesting else ids[:15]
            print("  İlgili canlı modeller:", ", ".join(shown) or "(filtre boş)")
        # Katalogda olup canlıda olmayanlar (bayat katalog riski)
        stale = [m for m in catalog if m not in ids and m not in ("openai/gpt-oss-120b",)]
        if stale:
            print(f"  ⚠ KATALOG'DA VAR / CANLIDA YOK: {stale[:10]}")
        # ROUTES'ta olup canlıda yok
        stale_r = [m for m in routes_here if m not in ids]
        if stale_r:
            print(f"  ⚠ ROUTES'TA VAR / CANLIDA YOK: {stale_r[:10]}")
        # Canlıda olup katalogda yok (eklenecek adaylar — yalnız ilgili)
        fresh = [i for i in ids if any(tok in i for tok in ("gemini", "gpt-oss", "deepseek", "claude", "luna")) and i not in catalog]
        if fresh:
            print(f"  + CANLIDA VAR / KATALOGDA YOK (aday): {fresh[:10]}")


if __name__ == "__main__":
    main()
