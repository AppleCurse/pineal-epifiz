#!/usr/bin/env python3
"""CI verifier for the OpenRouter facts Pineal depends on.

Two independent, deliberately separated checks:

1. **Local catalog contract** (always runs, no network): the pinned
   ``config/provider_catalog.json`` must contain the paid OpenRouter models
   Pineal uses, with the exact FINAL-KARAR-MATRIX prices. This also guards the
   free/paid boundary: a ``:free``-suffixed model must really be priced $0, and
   no model is ever classified free just because OpenRouter lists it.

2. **Live OpenRouter check** (only when ``OPENROUTER_API_KEY`` is set): fetch
   ``/api/v1/models`` and cross-check that the required paid models exist with
   the expected prices. A missing model or a price drift fails the run.

3. **Doğrulanamadı ≠ doğrulandı** (2026-10-14). Canlı kontrol dış bir servise
   bağlıdır; ağ/servis kesintisi bizim kataloğumuz hakkında HİÇBİR ŞEY söylemez.
   Bu yüzden üç hüküm ayrı yazılır:

   * ``FAIL:``   — canlı katalog okundu ve bizim pinlerle ÇELİŞİYOR (kayma). exit 1.
   * ``UNVERIFIED:`` — servise ulaşılamadı (ağ hatası, 5xx/429, gövde çözülemedi).
     Doğrulama YAPILAMADI; exit 0 ama asla "doğrulandı" DENMEZ — CI'da yüksek sesli
     ``::warning`` annotation'ı olarak yüzeye çıkar. Kesinti yüzünden main'i kırmak
     yanlış alarmdır, sessizce geçmek ise sahte yeşildir; doğru cevap ikisinin
     ortası: doğrulanamadığını AÇIKÇA söylemek.
   * ``SKIP:``   — anahtar yok, canlı kontrol hiç denenmedi.

   Bu ayrım 2026-10-14'te yaşandı: aynı ağaç PR'da geçti, merge sonrası main'de
   düştü ve düşüşün SEBEBİ hiçbir yerde okunamadı (betik hata satırlarını
   stderr'e yazıyordu, CI adımı yalnız stdout'u yakalıyordu). Artık her hüküm
   tek satır, makine-okunur ve CI annotation'ına taşınır.

OpenRouter presence/absence is NEVER treated as evidence about the Nous
catalog. Nous facts are owned by the FINAL routing policy and the local
catalog, which this script also verifies separately.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Callable

# Canlı kontrolün sabitleri — kilit testleri tek yerden okur.
_LIVE_MAX_ATTEMPTS = 3
_LIVE_BACKOFF_SECONDS = 1.0
_LIVE_TIMEOUT_SECONDS = 20
# Test enjeksiyonu için: gerçek ağ koşumunda time.sleep, testlerde sahte.
_live_sleep: Callable[[float], None] = time.sleep

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "config" / "provider_catalog.json"

# OpenRouter models Pineal must be able to route through with exact prices
# ($ per 1M tokens, input/output). Verified against the decision matrix.
REQUIRED_OPENROUTTER = {
    "google/gemini-3.7-flash": (0.75, 3.75),
    # [2026-10-14 · canlı teyit] CI'ın canlı çapraz kontrolü sol-pro'yu $2/$10
    # pinliyken $4/$20 olarak okudu (iki ardışık koşuda aynı: main + dal).
    # Depo politikası gereği ("CI canlı-kontrol teyitten sonra güncellenir")
    # pin canlı değere hizalandı; eski değer promosyon dönemine aitti.
    "openai/gpt-5.6-sol-pro": (4.0, 20.0),
    # [2026-10-14 · kapsam genişletmesi] Aşağıdaki üç model harcama sayacının
    # (LLMGateway.MODEL_PRICING) ve TIER_2 varsayılanının taşıdığı modellerdi;
    # fiyatları yalnız "inanç" olarak duruyordu — hiçbir canlı kontrol yoktu.
    # Artık CI her koşuda canlı katalogla karşılaştırır: fark çıkarsa DURUM
    # makine-okunur bir `FAIL:` satırıyla bildirilir ve tablolar ona göre
    # güncellenir (tahminle değil, ölçümle).
    # [2026-10-14 · canlı teyit] Genişletilen kapsam İKİ gerçek sapma daha buldu:
    # depo $0.09/$0.18 ve $0.4679/$0.9358 tutuyordu (2 ondalığa yuvarlanmış/promo
    # dönemi); canlı katalog $0.091/$0.182 ve $0.386976/$0.773952 okudu.
    "deepseek/deepseek-v4-flash": (0.091, 0.182),
    # [2026-10-14 · ikinci ölçüm] $0.95526/$1.91052 okundu; önceki değer
    # $0.386976/$0.773952 idi. Fiyat OYNAK: her koşu ölçer.
    # [2026-10-15 · PR CI 38787820334] $0.395328/$0.790656;
    # [PR CI 38789947274] $0.392022/$0.784044; [38794722007] $0.386976/$0.773952;
    # [38821301808] $0.348174/$0.696348; [38822647324] $0.346434/$0.692868.
    # [2026-10-16 · CI 38833598719 (Faz 1) + 38840573018 (P0) + 38843226709 (main)]
    # Canlı katalog $0.95526/$1.91052'ye DÖNDÜ — ÜÇ bağımsız koşuda birebir aynı
    # ölçüm (promo bitiş/başlangıç salınımı). Ölçülen değere hizalandı
    # (tahminle değil, ölçümle).
    "deepseek/deepseek-v4-pro": (0.95526, 1.91052),
    "anthropic/claude-sonnet-5": (2.0, 10.0),
    # [2026-10-14 · kapsam turu 2] Katalogun `openrouter` bölümünde beyan edilmiş
    # ama hiç canlı kontrol edilmemiş dört kayıt daha: katalog bunların OR fiyatı
    # olduğunu İDDİA ediyor; artık iddia her koşuda sınanır. Ayrıca kodun kendi
    # notu bu ikisinde promosyon bekliyor — "solar-pro4/ling-3.0-flash promo
    # 2026-09-10'a kadar; sonrası 0.12/0.24 ve daha yükseğe döner". Promo bir ay
    # önce bittiğine göre sapma çıkması BEKLENEN sonuçtur; çıkarsa tablo canlı
    # değere hizalanır (tahminle değil, ölçümle).
    # Ölçüm 2026-10-14 (canlı): solar-pro4 $0.09/$0.36 · glm-5.2 $0.04/$7.00 ·
    # deepseek-v4-pro $0.95526/$1.91052. ling-3.0-flash ve grok-4.6 DEĞİŞMEDİ.
    # NOT (kanal farkı): solar-pro4'ün nous indirimli kanalı ROUTES'ta $0.03/$0.12
    # olarak durur — bu pin OR (bulut liste) fiyatını doğrular, nous sözleşmesini
    # değil. İkisi bilinçli olarak farklı kanallardır.
    "upstage/solar-pro4": (0.09, 0.36),
    "inclusionai/ling-3.0-flash": (0.021, 0.063),
    # [2026-10-15 · CI 38662205946] Çıktı son ölçümde $4.40/1M (önceki $7.00).
    # [2026-10-15 · CI 38664381599] Girdi son ölçümde $0.037/1M.
    # [2026-10-15 · CI 38665669314 + 38665674379] Çıktı yeniden $7/1M.
    # [2026-10-15 · PR CI 38787820334] $0.65/$10.00; [38821301808] $0.037/$7.00 per 1M.
    # [2026-10-16 · CI 38833598719 (Faz 1) + 38840573018 (P0) + 38843226709 (main)]
    # Canlı katalog $0.62/$2.42 okundu (girdi 16,8× YÜKSELDİ, çıktı 2,9× DÜŞTÜ);
    # üç koşu birebir aynı. Ölçülen değere hizalandı.
    "z-ai/glm-5.2": (0.62, 2.42),
    "x-ai/grok-4.6": (2.0, 6.0),
}

# ── KAPSAM BOŞLUĞU (dürüstçe adlandırılmış) ──────────────────────────────────
# `LLMGateway.MODEL_PRICING` şu iki modeli ücretlendirir ama bunlar
# `config/provider_catalog.json`'da YOKTUR; katalogda olmadıkları için canlı
# kontrole de alınamazlar (yerel kontrat önce katalog eşleşmesi ister).
# Katalogu sessizce genişletmek "yetkilendirilmiş API" iddiasını büyütmek olurdu;
# onun yerine boşluk AÇIKÇA adlandırılır ve testle dondurulur:
#   * `openai/gpt-5.6-luna`  — nous indirimli kanal + OR legacy aynı $0.20/$1.20
#   * `openai/gpt-oss-120b`  — Groq free kanalı; OR-legacy ücretli yol accounting'i
# Operatör bu ikisini katalogda yetkilendirirse pinleri de eklenir ve doğrulama
# kapsamı kendiliğinden genişler.
UNCOVERED_PRICED_MODELS = frozenset({
    "openai/gpt-5.6-luna",
    "openai/gpt-oss-120b",
})

# Nous FINAL-KARAR-MATRIX facts. These are verified locally, never against
# the OpenRouter catalog. FAZ-2 (2. ajan mühürlü canlı denetim): prefix'ler
# canlı yazımla birebir (poolside/…, inclusionai/…); eski dots önizleme
# modeli canlı katalogda YOK -> listeden düşürüldü (ölü kayıt yasak).
REQUIRED_NOUS_FREE = {
    "poolside/laguna-s-2.1:free",
    "poolside/laguna-xs-2.1:free",
    "inclusionai/ling-3.0-flash-fin:free",
}
REQUIRED_NOUS_PAID = {
    "stepfun/step-3.7-flash": (0.20, 1.15),
    "upstage/solar-pro4": (0.03, 0.12),
    "meituan/longcat-2.0": (0.30, 1.20),
    "openai/gpt-5.6-luna": (0.20, 1.20),
    "anthropic/claude-sonnet-5": (1.60, 8.00),
}


def _load_catalog() -> dict:
    with CATALOG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _catalog_models(catalog: dict) -> dict[str, dict]:
    models: dict[str, dict] = {}
    for provider in catalog.get("providers", []):
        provider_id = provider.get("id", "")
        for model in provider.get("models", []):
            models[f"{provider_id}/{model.get('id', '')}"] = model
    return models


def _pricing(model: dict) -> tuple[float, float]:
    pricing = model.get("pricing") or {}
    return (
        float(pricing.get("input_per_million_usd", 0.0)),
        float(pricing.get("output_per_million_usd", 0.0)),
    )


def verify_local_catalog() -> list[str]:
    """Deterministic local contract checks. Returns a list of failures."""
    failures: list[str] = []
    catalog = _load_catalog()
    if catalog.get("schema_version") != 1:
        failures.append("catalog schema_version must be 1")
        return failures
    models = _catalog_models(catalog)

    for model_id, (expected_in, expected_out) in REQUIRED_OPENROUTTER.items():
        model = models.get(f"openrouter/{model_id}")
        if model is None:
            failures.append(f"openrouter/{model_id}: missing from local catalog")
            continue
        actual_in, actual_out = _pricing(model)
        if abs(actual_in - expected_in) > 1e-9 or abs(actual_out - expected_out) > 1e-9:
            failures.append(
                f"openrouter/{model_id}: price drift "
                f"({actual_in}/{actual_out}) != ({expected_in}/{expected_out})"
            )

    nous_present = any(
        provider.get("id") == "nous-research" for provider in catalog.get("providers", [])
    )
    if not nous_present:
        failures.append("nous-research: provider missing from local catalog")
    else:
        for free_id in REQUIRED_NOUS_FREE:
            model = models.get(f"nous-research/{free_id}")
            if model is None:
                failures.append(f"nous-research/{free_id}: missing free route")
                continue
            actual_in, actual_out = _pricing(model)
            if actual_in != 0.0 or actual_out != 0.0:
                failures.append(f"nous-research/{free_id}: free route is not priced $0")
        for paid_id, (expected_in, expected_out) in REQUIRED_NOUS_PAID.items():
            model = models.get(f"nous-research/{paid_id}")
            if model is None:
                failures.append(f"nous-research/{paid_id}: missing paid route")
                continue
            actual_in, actual_out = _pricing(model)
            if abs(actual_in - expected_in) > 1e-9 or abs(actual_out - expected_out) > 1e-9:
                failures.append(
                    f"nous-research/{paid_id}: price drift "
                    f"({actual_in}/{actual_out}) != ({expected_in}/{expected_out})"
                )

    # Free/paid boundary: a ':free' suffix must be genuinely priced $0 and must
    # not be a retired/incorrect alias in the catalog.
    for canonical, model in models.items():
        if ":free" in canonical:
            actual_in, actual_out = _pricing(model)
            if actual_in != 0.0 or actual_out != 0.0:
                failures.append(f"{canonical}: ':free' suffix but priced > $0")

    # Spec section 13: gemma-3-27b-it:free must NOT be a verified route even if
    # it exists in the general OpenRouter catalog.
    if "nous-research/google/gemma-3-27b-it:free" in models:
        failures.append("nous-research/google/gemma-3-27b-it:free must not be catalogued")
    return failures


def verify_live_openrouter(
    key: str,
    attempts: int = _LIVE_MAX_ATTEMPTS,
    sleep: Callable[[float], None] | None = None,
) -> tuple[list[str], str | None]:
    """Cross-check the live OpenRouter catalog.

    Returns ``(failures, unverified_reason)``:

    * ``failures`` dolu → canlı katalog bizim pinlerle çelişiyor (gerçek kayma).
    * ``unverified_reason`` dolu → servise ulaşılamadı; DOĞRULAMA YAPILMADI.
      İkisi AYNI ANDA dolu olamaz: servis okunamadıysa hüküm verilemez.

    Geçici ağ arızalarında (yük dengeleme, DNS, 5xx) tek denemeyle pes etmek
    yanlış alarm üretirdi; bu yüzden sınırlı sayıda yeniden deneme yapılır.
    """
    if sleep is None:
        sleep = _live_sleep
    last_error = ""
    for attempt in range(1, max(1, attempts) + 1):
        try:
            request = urllib.request.Request(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=_LIVE_TIMEOUT_SECONDS) as response:
                payload = json.load(response)
        except Exception as exc:  # ağ/servis/gövde: hüküm verilemez
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < attempts:
                sleep(_LIVE_BACKOFF_SECONDS * attempt)
            continue

        models = {item.get("id"): item for item in payload.get("data", [])}
        failures: list[str] = []
        for model_id, (expected_in, expected_out) in REQUIRED_OPENROUTTER.items():
            item = models.get(model_id)
            if not item:
                failures.append(f"{model_id}: missing from live OpenRouter catalog")
                continue
            pricing = item.get("pricing", {})
            actual_in = float(pricing.get("prompt", 0))
            actual_out = float(pricing.get("completion", 0))
            if abs(actual_in - expected_in / 1_000_000) > 1e-12:
                failures.append(f"{model_id}: live input price ${actual_in * 1_000_000:g}/1M != ${expected_in:g}/1M")
            if abs(actual_out - expected_out / 1_000_000) > 1e-12:
                failures.append(f"{model_id}: live output price ${actual_out * 1_000_000:g}/1M != ${expected_out:g}/1M")
        return failures, None

    return [], f"live OpenRouter unreachable after {attempts} attempt(s) — {last_error}"


def main() -> int:
    failures = verify_local_catalog()

    key = None
    try:
        import os

        key = os.getenv("OPENROUTER_API_KEY")
    except Exception:  # pragma: no cover - import cannot realistically fail
        key = None

    verified_live = False
    if not key:
        print("SKIP: live OpenRouter check (OPENROUTER_API_KEY not configured)")
    else:
        live_failures, unverified = verify_live_openrouter(key)
        if unverified is not None:
            # Doğrulama YAPILAMADI. Bu bir "geçti" değildir ve öyle sunulmaz.
            print(f"UNVERIFIED: {unverified}")
        else:
            failures.extend(live_failures)
            verified_live = not live_failures

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(
        "PASS: local catalog contract verified"
        + (" + live OpenRouter models verified" if verified_live else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
