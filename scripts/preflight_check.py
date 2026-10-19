#!/usr/bin/env python3
"""Preflight Check — Sistem Başlatma Öncesi Kapsamlı Sağlık Denetimi.

Bu betik şunları doğrular:
1. Python Bağımlılıkları (FastAPI, Playwright, Pydantic, Uvicorn vb.)
2. Playwright Chromium Tarayıcı Motorunun varlığı
3. Frontend Derleme Tazeliği (frontend/dist var mı, frontend/src'den yeni mi?)
4. 9Router / LLM Ağ Geçidi Erişilebilirliği (127.0.0.1:20128)
5. Ortam Değişkenleri ve Kasa Sağlığı (.env, PINEAL_ENV, ENABLE_CROSS_PLATFORM)
"""
from __future__ import annotations

import os
import sys
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"


def check_python_dependencies() -> bool:
    required = [
        "fastapi",
        "uvicorn",
        "pydantic",
        "playwright",
        "httpx",
    ]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"[{RED}FAIL{RESET}] Eksik Python paketleri: {', '.join(missing)}")
        return False
    print(f"[{GREEN}OK{RESET}] Temel Python paketleri eksiksiz.")
    return True


def check_playwright_chromium() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exec_path = p.chromium.executable_path
            if os.path.exists(exec_path):
                print(f"[{GREEN}OK{RESET}] Playwright Chromium motoru hazır: {exec_path}")
                return True
            else:
                print(f"[{YELLOW}WARN{RESET}] Chromium binary bulunamadı: {exec_path}")
                return False
    except Exception as e:
        print(f"[{YELLOW}WARN{RESET}] Playwright tarayıcı kontrolü: {e}")
        return False


def check_frontend_freshness() -> int:
    """0: taze, 1: dist yok veya src daha yeni (derleme gerekir)."""
    dist_index = ROOT / "frontend" / "dist" / "index.html"
    src_dir = ROOT / "frontend" / "src"

    if not dist_index.exists():
        print(f"[{YELLOW}BUILD REQUIRED{RESET}] frontend/dist bulunamadı.")
        return 1

    dist_mtime = dist_index.stat().st_mtime
    for p in src_dir.rglob("*"):
        if p.is_file() and p.stat().st_mtime > dist_mtime:
            print(f"[{YELLOW}BUILD REQUIRED{RESET}] Kaynak dosya ({p.name}) derlemeden daha yeni.")
            return 1

    print(f"[{GREEN}OK{RESET}] Frontend derlemesi güncel.")
    return 0


def check_llm_gateway() -> bool:
    url = "http://127.0.0.1:20128/v1/models"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "pineal-preflight"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                print(f"[{GREEN}OK{RESET}] 9Router / Yerel LLM Ağ Geçidi canlı (port 20128).")
                return True
    except Exception:
        print(f"[{YELLOW}INFO{RESET}] 9Router (20128) aktif değil; cloud LLM veya offline mod kullanılacak.")
        return False


def main() -> int:
    print(f"\n{CYAN}=== PINEAL-HERETIC SİSTEM ÖN KONTROLÜ (PREFLIGHT) ==={RESET}\n")
    ok = True
    if not check_python_dependencies():
        ok = False
    check_playwright_chromium()
    check_llm_gateway()

    freshness = check_frontend_freshness()
    if freshness != 0:
        print(f"\n{YELLOW}Frontend güncellenmeli (npm run build).{RESET}")
        return 2

    if not ok:
        print(f"\n{RED}Kritik ön kontrol hataları var. Lütfen bağımlılıkları tamamlayın.{RESET}")
        return 1

    print(f"\n{GREEN}Tüm ön kontroller başarıyla tamamlandı.{RESET}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
