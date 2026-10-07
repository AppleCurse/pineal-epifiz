#!/usr/bin/env python3
"""
LILITH CLI - Ultra-Lightweight Social Media Growth & Viral Content Runner.

Bu dosya SADECE komut satırı I/O'su ve kimlik bilgisi çözümlemesi yapar.
Tüm nörobilişsel iş mantığı, formüller ve rapor formatlama
`agent_core.agents.lilith_growth.LilithGrowthAgent` içinde TEK yerde toplanmıştır (DRY).
"""

import sys
import os
import asyncio
import argparse
import json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception as exc:
        print(f"[UYARI] stdout kodlaması ayarlanamadı: {type(exc).__name__}", file=sys.stderr)

from agent_core.agents.lilith_growth import LilithGrowthAgent


def resolve_credentials(model: str) -> tuple[str | None, str | None, str]:
    """Nous / OpenRouter / Vault / .env sırasıyla API anahtarını ve base_url'i çözer."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("[UYARI] python-dotenv yok; .env yüklenmedi", file=sys.stderr)

    base_url = os.getenv("OPENROUTER_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("NOUS_API_KEY") or os.getenv("OPENAI_API_KEY")

    if not api_key and os.path.exists(".pineal_vault.json"):
        try:
            with open(".pineal_vault.json", "r", encoding="utf-8") as vf:
                vdata = json.load(vf)
                api_key = vdata.get("api_key") or vdata.get("openrouter_key") or vdata.get("nous_key")
                if not api_key:
                    # KASA SEMASI: providers.{ad}.api_key (yerel envanter).
                    _provs = vdata.get("providers") if isinstance(vdata.get("providers"), dict) else {}
                    _or_entry = _provs.get("openrouter") or _provs.get("nous_portal") or _provs.get("nous-research")
                    if isinstance(_or_entry, dict):
                        api_key = _or_entry.get("api_key")
                    elif isinstance(_or_entry, str):
                        api_key = _or_entry
        except Exception as exc:
            print(f"[UYARI] kasa anahtarı okunamadı: {type(exc).__name__}", file=sys.stderr)

    if api_key and not base_url:
        if api_key.startswith("sk-nous-"):
            base_url = "https://inference-api.nousresearch.com/v1"
        elif api_key.startswith("sk-or-v1-"):
            base_url = "https://openrouter.ai/api/v1"

    if model == "gpt-4o":
        model = os.getenv("OPENROUTER_TIER_1_MODEL") or "anthropic/claude-sonnet-5"

    return api_key, base_url, model


def build_payload(args: argparse.Namespace) -> dict:
    payload: dict = {"topic": args.topic, "platform": args.platform}

    if args.aspasia_profile and os.path.exists(args.aspasia_profile):
        try:
            with open(args.aspasia_profile, "r", encoding="utf-8") as f:
                aspasia_data = json.load(f)
            payload["target_profile"] = aspasia_data.get("target_profile", {})
            payload["friction_profile"] = aspasia_data.get("friction_profile", {})
            payload["passion_profile"] = aspasia_data.get("passion_profile", {})
            payload["cognitive_style"] = aspasia_data.get("cognitive_style", {})
        except Exception as e:
            print(f"[UYARI] Aspasia profili okunamadı: {e}", file=sys.stderr)

    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Lilith - Viral Social Media Content Engine")
    parser.add_argument("--topic", type=str, default="Yapay Zeka ve Geleceğin Güç Dengesi", help="İçerik konusu")
    parser.add_argument("--platform", type=str, default="x_twitter", help="Platform: x_twitter, instagram, linkedin")
    parser.add_argument("--aspasia_profile", type=str, default=None, help="Aspasia analiz JSON dosyası yolu (opsiyonel)")
    parser.add_argument("--model", type=str, default="gpt-4o", help="Model adı")
    args = parser.parse_args()

    api_key, base_url, model = resolve_credentials(args.model)
    agent = LilithGrowthAgent.from_cli_credentials(api_key=api_key, base_url=base_url, model=model)
    payload = build_payload(args)

    print(f"\n[LILITH] İçerik üretiliyor... (Konu: {args.topic} | Platform: {args.platform})")

    # execute() KENDİ İÇİNDE fallback'i yönetir; burada ayrı bir try/except
    # fallback bloğuna GEREK YOK — tek çıktı tipi (LilithContentPackage) garanti.
    result = asyncio.run(agent.execute(payload))
    print(LilithGrowthAgent.render_console_report(result))


if __name__ == "__main__":
    main()
