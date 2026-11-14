#!/usr/bin/env python3
"""PINEAL EPİFİZ — Canlıya Alma (Production) Yapılandırma ve Doğrulama Aracı.

Bu betik GO_LIVE.md'de belirtilen 3 ana blocker'ı otomatik olarak çözer:
1. PINEAL_ENV=production ve kriptografik PINEAL_TOKEN (>=32 karakter) üretir.
2. PINEAL_OPERATOR_TOKENS (ayrışmış oda sahipliği için) üretir.
3. OPENROUTER_MAX_SPEND_USD=50.0 (fail-closed tavan) değerini ayarlar.
4. Cloudflare için BACKEND_ORIGIN secret komutunu hazır eder.
5. security_posture() kapı fonksiyonunu çalıştırarak açılış sağlığını doğrular.
"""
from __future__ import annotations

import os
import pathlib
import secrets
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def generate_tokens() -> tuple[str, str, str]:
    root_token = secrets.token_urlsafe(36)
    admin_token = secrets.token_urlsafe(32)
    operator_token = secrets.token_urlsafe(32)
    return root_token, admin_token, operator_token


def create_production_env(backend_origin: str = "https://pineal-backend.up.railway.app", spend_cap: float = 50.0) -> dict[str, str]:
    root_token, admin_token, op_token = generate_tokens()
    prod_env_path = ROOT / ".env.production"

    env_content = f"""# ==============================================================================
# PINEAL-HERETIC v3.0 — PRODUCTION ORTAM DEĞİŞKENLERİ
# Üretilme zamanı: otomatik üretim kapısı
# ==============================================================================

# 1. Ortam ve Kimlik Doğrulama Kapısı (FAIL-CLOSED)
PINEAL_ENV=production
PINEAL_REQUIRE_AUTH=true
PINEAL_TOKEN={root_token}

# 2. Çok Operatörlü Oda Sahipliği (Oda sızıntısını önler)
PINEAL_OPERATOR_TOKENS=admin:{admin_token},operator:{op_token}

# 3. Harcama Tavanı (Sınırsız fatura kilidi - fail-closed)
OPENROUTER_MAX_SPEND_USD={spend_cap:.2f}

# 4. LLM ve Model Seçimi
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_TIER_1_MODEL=anthropic/claude-sonnet-5
OPENROUTER_TIER_2_MODEL=deepseek/deepseek-v4-flash
LLM_REQUEST_TIMEOUT_SECONDS=45
LIVE_LLM_E2E=1

# 5. Dış Kaynak Kapıları
ENABLE_CROSS_PLATFORM=true
ENABLE_MAIGRET=true
ENABLE_HOLEHE=true
ENABLE_CRAWL4AI=true
ENABLE_SCRAPLING=true
ENABLE_X_SENSOR=true
ENABLE_IG_SECONDARY=true
ENABLE_REPORT_FACTORY=true

# 6. Cloudflare & CORS İzinleri
PINEAL_ALLOWED_ORIGINS=https://pineal-frontend.pages.dev,https://pineal-clean.workers.dev
BACKEND_ORIGIN={backend_origin}

# 7. E-posta Brifing Servisi
PINEAL_EMAIL_ENABLED=0
"""
    prod_env_path.write_text(env_content, encoding="utf-8")

    return {
        "PINEAL_TOKEN": root_token,
        "ADMIN_TOKEN": admin_token,
        "OPERATOR_TOKEN": op_token,
        "OPENROUTER_MAX_SPEND_USD": str(spend_cap),
        "BACKEND_ORIGIN": backend_origin,
        "PROD_FILE": str(prod_env_path),
    }


def verify_security_posture(prod_tokens: dict[str, str]) -> bool:
    os.environ["PINEAL_ENV"] = "production"
    os.environ["PINEAL_REQUIRE_AUTH"] = "true"
    os.environ["PINEAL_TOKEN"] = prod_tokens["PINEAL_TOKEN"]
    os.environ["PINEAL_OPERATOR_TOKENS"] = f"admin:{prod_tokens['ADMIN_TOKEN']}"
    os.environ["OPENROUTER_MAX_SPEND_USD"] = prod_tokens["OPENROUTER_MAX_SPEND_USD"]

    try:
        from agent_core.utils.security import security_posture, SecurityConfigurationError
        posture = security_posture()
        print("\n[OK] security_posture() doğrulandı:")
        print(f"     Ortam: {posture['environment']}")
        print(f"     Kimlik Durumu: {posture['auth_state']}")
        print(f"     Uyarı Kodu: {posture['warning_code']}")
        return True
    except SecurityConfigurationError as e:
        print(f"\n[FAIL] Güvenlik kapısı reddetti: {e}")
        return False
    except Exception as e:
        print(f"\n[FAIL] Beklenmeyen hata: {e}")
        return False


def main():
    print("=" * 60)
    print("PINEAL EPİFİZ — CANLIYA ALMA HAZIRLIK ARACI")
    print("=" * 60)

    backend_origin = sys.argv[1] if len(sys.argv) > 1 else "https://pineal-backend.up.railway.app"
    data = create_production_env(backend_origin=backend_origin)

    print(f"\n1. .env.production oluşturuldu: {data['PROD_FILE']}")
    print(f"   - PINEAL_TOKEN: {data['PINEAL_TOKEN'][:8]}...{data['PINEAL_TOKEN'][-6:]} (36 byte)")
    print(f"   - admin token:  {data['ADMIN_TOKEN'][:8]}...{data['ADMIN_TOKEN'][-6:]}")
    print(f"   - operator tok: {data['OPERATOR_TOKEN'][:8]}...{data['OPERATOR_TOKEN'][-6:]}")
    print(f"   - Harcama Sınırı: ${data['OPENROUTER_MAX_SPEND_USD']} / oturum")

    verified = verify_security_posture(data)
    if not verified:
        sys.exit(1)

    print("\n2. CLOUDFLARE İÇİN GEREKLİ KOMUTLAR:")
    print("   Eğer Cloudflare Pages veya Workers kullanıyorsanız terminalden şunu çalıştırın:")
    print(f"   npx wrangler secret put BACKEND_ORIGIN")
    print(f"   (İstendiğinde şu adresi yapıştırın: {backend_origin})")
    print("\n   Veya Pages için:")
    print(f"   npx wrangler pages secret put BACKEND_ORIGIN")
    print("=" * 60)


if __name__ == "__main__":
    main()
