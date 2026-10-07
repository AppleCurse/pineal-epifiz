"""FINAL-KARAR-MATRIX - production routing policy
Fail-closed by construction, not by data.

Invariants:
- UNKNOWN MODEL/PRICE/PROVIDER/UNVERIFIED -> DENY
- UNKNOWN QUOTA != INF, never unlimited
- Canonical key = model@provider everywhere
- verification_status defaults to unverified (opt-in)
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple

logger = logging.getLogger("pineal.routing")

class PaidEscalationDenied(RuntimeError):
    pass

class UnknownModelDenied(RuntimeError):
    pass

class UnknownQuotaDenied(RuntimeError):
    pass

QUOTA_UNKNOWN = None  # sentinel, must never be treated as inf/unlimited

@dataclass(frozen=True)
class RouteSpec:
    model: str
    provider: str
    tier: str  # free, paid, frontier
    input_per_million_usd: float
    output_per_million_usd: float
    context_window: int | None = None
    capabilities: frozenset[str] = frozenset({"chat"})
    verification_status: str = "unverified"  # FIX #1: default unverified, force opt-in
    list_input_per_million_usd: float | None = None
    list_output_per_million_usd: float | None = None
    note: str = ""

    def __post_init__(self):
        # both-or-neither for list pricing
        li = self.list_input_per_million_usd
        lo = self.list_output_per_million_usd
        if (li is None) ^ (lo is None):
            raise ValueError(f"list pricing must be both set or both None for {self.model}@{self.provider}")
        if self.verification_status not in ("verified", "unverified", "validating", "discovered"):
            raise ValueError(f"invalid verification_status {self.verification_status}")

    def is_free(self) -> bool:
        return self.tier == "free" and self.input_per_million_usd == 0.0 and self.output_per_million_usd == 0.0

    def effective_pricing(self) -> Tuple[float, float]:
        return (self.input_per_million_usd, self.output_per_million_usd)


QUOTAS: Dict[str, Dict[str, int | None]] = {
    "groq": {"rpm": 30, "rpd": 14400, "tpm": QUOTA_UNKNOWN, "tpd": QUOTA_UNKNOWN},
    # Cerebras açık free katmanı 2026-07-21'de kapatıldı; kalan kota değerleri
    # muhafazakâr tavan olarak korunur (paid üretim kotası canlıda doğrulanmadı —
    # UNKNOWN != INF kuralı gereği tavan hiçbir zaman 'limitsiz' sayılmaz).
    "cerebras": {"rpm": 5, "tpm": 30000, "tpd": 1_000_000, "rpd": QUOTA_UNKNOWN},
}

def quota_limit(provider: str, dim: str) -> int:
    """FIX #5: enforce UNKNOWN QUOTA != INF. Fail-closed: unknown -> raise."""
    v = QUOTAS.get(provider, {}).get(dim, QUOTA_UNKNOWN)
    if v is None:
        # Raise to force explicit handling; caller cannot silently treat as unlimited
        raise UnknownQuotaDenied(f"UNKNOWN_QUOTA: {provider}.{dim} is UNKNOWN, not unlimited")
    return v

def quota_limit_or_zero(provider: str, dim: str) -> int:
    """Conservative helper for governors that want 0 when unknown."""
    try:
        return quota_limit(provider, dim)
    except UnknownQuotaDenied:
        return 0

# Canonical key = model@provider
def _canonical_key(model: str, provider: str) -> str:
    return f"{model}@{provider}"

ROUTES: Dict[str, RouteSpec] = {
    "openai/gpt-oss-120b@groq": RouteSpec("openai/gpt-oss-120b", "groq", "free", 0.0, 0.0, 131072, frozenset({"chat","streaming","tools"}), "verified", note="Groq 30 RPM / 14400 RPD"),
    # FAZ-2-P3 (araştırma 2026-09-08, sahip onayı): Cerebras açık free katmanı
    # 21.07.2026'da kapatıldı; gpt-oss-120b artık yalnız ücretli ($0.35/$0.75).
    # Eski "free 0.0/0.0" kaydı canlı gerçeğe aykırıydı (fatura riski) —
    # PAID'e çekildi; ücretsiz alternatif Groq free kanalıdır (aynı model).
    # Not: model kimliği catalog'daki cerebras yazımıyla aynı kalır ("gpt-oss-120b",
    # openai/ öneksiz) — is_free/model-eşleme bu yüzden bozulmaz.
    "gpt-oss-120b@cerebras": RouteSpec("gpt-oss-120b", "cerebras", "paid", 0.35, 0.75, 131072, frozenset({"chat","streaming"}), "verified", note="Cerebras free katmanı kapandı 2026-07-21; paid $0.35/$0.75"),
    # FAZ-2 canlı-katalog düzeltmesi (2. ajan mühürlü izin): prefix'ler canlı
    # OpenRouter yazımıyla birebir (poolside/…, inclusionai/…); eski dots
    # önizleme modeli canlıda YOK -> ölü kayıt yasak, SİLİNDİ.
    "poolside/laguna-s-2.1:free@nous-research": RouteSpec("poolside/laguna-s-2.1:free", "nous-research", "free", 0.0, 0.0, 262144, frozenset({"chat","streaming","tools"}), "verified"),
    "poolside/laguna-xs-2.1:free@nous-research": RouteSpec("poolside/laguna-xs-2.1:free", "nous-research", "free", 0.0, 0.0, 262144, frozenset({"chat","streaming","tools"}), "verified"),
    "inclusionai/ling-3.0-flash-fin:free@nous-research": RouteSpec("inclusionai/ling-3.0-flash-fin:free", "nous-research", "free", 0.0, 0.0, 262144, frozenset({"chat","streaming","tools"}), "verified"),
    "stepfun/step-3.7-flash@nous-research": RouteSpec("stepfun/step-3.7-flash", "nous-research", "paid", 0.20, 1.15, 262144, frozenset({"chat","streaming","vision","tools","video"}), "verified"),
    "upstage/solar-pro4@nous-research": RouteSpec("upstage/solar-pro4", "nous-research", "paid", 0.03, 0.12, 524288, frozenset({"chat","streaming","tools"}), "verified"),
    "meituan/longcat-2.0@nous-research": RouteSpec("meituan/longcat-2.0", "nous-research", "paid", 0.30, 1.20, 1_048_576, frozenset({"chat","streaming","tools"}), "verified"),
    "openai/gpt-5.6-luna@nous-research": RouteSpec("openai/gpt-5.6-luna", "nous-research", "paid", 0.20, 1.20, 400000, frozenset({"chat","streaming","tools"}), "verified", 1.00, 6.00, "Nous 80% discount vs $1/$6"),
    # FAZ-2-P3 notu (araştırma 2026-09-08): Sonnet 5'in OR liste promosu
    # ($2/$10) 31.08.2026'da sona erdi, liste $3/$15'e taşındı. Nous kanalı
    # $1.60/$8.00 (eski %20 indirim) hâlâ canlı mı — CI canlı-kontrol
    # (scripts/verify_openrouter_catalog.py) teyit eder; teyitsiz sabit
    # değiştirilmez (list değeri 2.00/10.00 = arşivlenen promo).
    "anthropic/claude-sonnet-5@nous-research": RouteSpec("anthropic/claude-sonnet-5", "nous-research", "paid", 1.60, 8.00, 1_048_576, frozenset({"chat","streaming","vision","tools","reasoning"}), "verified", 2.00, 10.00, "Nous 20% discount vs archived $2/$10 promo (liste 31.08.2026'da $3/$15'e taşındı)"),
    "google/gemini-3.7-flash@openrouter": RouteSpec("google/gemini-3.7-flash", "openrouter", "paid", 0.75, 3.75, 1_048_576, frozenset({"chat","streaming","vision","tools"}), "verified"),
    # FAZ-2-P4 (2026-09-08, sahip onayı): Google resmi OpenAI-uyumlu endpoint
    # (generativelanguage .../v1beta/openai/). Model kimliği Google'in kendi
    # adı (öneksiz "gemini-3.7-flash"); gateway model eşleşmesi OR'daki
    # "google/gemini-3.7-flash" ile endswith yoluyla çakışır. Fiyat OR liste
    # ($0.75/$3.75) — AI Studio free tier'i CANLI teyit bekler; teyit sonrası
    # free kayda çevrilir (Cerebras dersi: teyitsiz free yazılmaz). Backup =
    # aynı endpoint, 2. anahtar (429/limit → otomatik rotasyon).
    "gemini-3.7-flash@google-gemini": RouteSpec("gemini-3.7-flash", "google-gemini", "paid", 0.75, 3.75, 1_048_576, frozenset({"chat","streaming","vision","tools"}), "verified", note="Google direkt; free-tier canlı teyit bekler"),
    "gemini-3.7-flash@google-gemini-backup": RouteSpec("gemini-3.7-flash", "google-gemini-backup", "paid", 0.75, 3.75, 1_048_576, frozenset({"chat","streaming","vision","tools"}), "verified", note="429 sonrası backup key (aynı endpoint)"),
    "openai/gpt-5.6-sol-pro@openrouter": RouteSpec("openai/gpt-5.6-sol-pro", "openrouter", "frontier", 2.00, 10.00, 1_048_576, frozenset({"chat","streaming","tools","reasoning"}), "verified", note="Frontier explicit"),
    # 9Router yerel rotaları (v0.5.81 local proxy 127.0.0.1:20128)
    "pineal-deep-reasoning@openrouter": RouteSpec("pineal-deep-reasoning", "openrouter", "free", 0.0, 0.0, 1_048_576, frozenset({"chat","streaming","tools","reasoning"}), "verified", note="9Router deep reasoning combo"),
    "pineal-general-reasoning@openrouter": RouteSpec("pineal-general-reasoning", "openrouter", "free", 0.0, 0.0, 1_048_576, frozenset({"chat","streaming","tools"}), "verified", note="9Router general reasoning combo"),
    "pineal-fast-extract@openrouter": RouteSpec("pineal-fast-extract", "openrouter", "free", 0.0, 0.0, 131072, frozenset({"chat","streaming","tools"}), "verified", note="9Router fast extract combo"),
    "pineal-vision@openrouter": RouteSpec("pineal-vision", "openrouter", "free", 0.0, 0.0, 1_048_576, frozenset({"chat","streaming","vision","tools"}), "verified", note="9Router multimodal vision combo"),
    "pineal-juror-google@openrouter": RouteSpec("pineal-juror-google", "openrouter", "free", 0.0, 0.0, 1_048_576, frozenset({"chat","streaming","tools"}), "verified", note="9Router juror google combo"),
    "pineal-juror-claude@openrouter": RouteSpec("pineal-juror-claude", "openrouter", "free", 0.0, 0.0, 1_048_576, frozenset({"chat","streaming","tools"}), "verified", note="9Router juror claude combo"),
    "pineal-juror-open@openrouter": RouteSpec("pineal-juror-open", "openrouter", "free", 0.0, 0.0, 131072, frozenset({"chat","streaming","tools"}), "verified", note="9Router juror open combo"),
    "pineal-deep-reasoning@9router": RouteSpec("pineal-deep-reasoning", "9router", "free", 0.0, 0.0, 1_048_576, frozenset({"chat","streaming","tools","reasoning"}), "verified", note="9Router deep reasoning combo"),
    "pineal-general-reasoning@9router": RouteSpec("pineal-general-reasoning", "9router", "free", 0.0, 0.0, 1_048_576, frozenset({"chat","streaming","tools"}), "verified", note="9Router general reasoning combo"),
    "pineal-fast-extract@9router": RouteSpec("pineal-fast-extract", "9router", "free", 0.0, 0.0, 131072, frozenset({"chat","streaming","tools"}), "verified", note="9Router fast extract combo"),
    "pineal-vision@9router": RouteSpec("pineal-vision", "9router", "free", 0.0, 0.0, 1_048_576, frozenset({"chat","streaming","vision","tools"}), "verified", note="9Router multimodal vision combo"),
    "pineal-juror-google@9router": RouteSpec("pineal-juror-google", "9router", "free", 0.0, 0.0, 1_048_576, frozenset({"chat","streaming","tools"}), "verified", note="9Router juror google combo"),
    "pineal-juror-claude@9router": RouteSpec("pineal-juror-claude", "9router", "free", 0.0, 0.0, 1_048_576, frozenset({"chat","streaming","tools"}), "verified", note="9Router juror claude combo"),
    "pineal-juror-open@9router": RouteSpec("pineal-juror-open", "9router", "free", 0.0, 0.0, 131072, frozenset({"chat","streaming","tools"}), "verified", note="9Router juror open combo"),
}

FORBIDDEN_ALIASES = {"poolside/laguna:free", "laguna:free", "xs:free", "ling:free"}

TASK_GROUPS: Dict[str, List[Tuple[str, str]]] = {
    # FAZ-2-P3 (2026-09-08): Cerebras açık free katmanı kapandığı için tüm
    # free-first kümelerde gpt-oss-120b yalnız Groq free kanalından gelir;
    # Cerebras artık PAID rota olarak ROUTES'ta durur (escalation ile erişilir).
    "general": [("openai/gpt-oss-120b","groq"), ("poolside/laguna-s-2.1:free","nous-research"), ("poolside/laguna-xs-2.1:free","nous-research")],
    "fast": [("openai/gpt-oss-120b","groq"), ("poolside/laguna-s-2.1:free","nous-research"), ("poolside/laguna-xs-2.1:free","nous-research"), ("inclusionai/ling-3.0-flash-fin:free","nous-research")],
    "normal": [("openai/gpt-oss-120b","groq"), ("poolside/laguna-s-2.1:free","nous-research"), ("poolside/laguna-xs-2.1:free","nous-research")],
    "research": [("openai/gpt-oss-120b","groq"), ("poolside/laguna-s-2.1:free","nous-research"), ("poolside/laguna-xs-2.1:free","nous-research"), ("inclusionai/ling-3.0-flash-fin:free","nous-research"), ("stepfun/step-3.7-flash","nous-research"), ("upstage/solar-pro4","nous-research"), ("meituan/longcat-2.0","nous-research"), ("openai/gpt-5.6-luna","nous-research")],
    "deep_reasoning": [("openai/gpt-oss-120b","groq"), ("poolside/laguna-s-2.1:free","nous-research"), ("inclusionai/ling-3.0-flash-fin:free","nous-research"), ("stepfun/step-3.7-flash","nous-research"), ("upstage/solar-pro4","nous-research"), ("meituan/longcat-2.0","nous-research"), ("openai/gpt-5.6-luna","nous-research")],
    "code_fast": [("openai/gpt-oss-120b","groq"), ("poolside/laguna-s-2.1:free","nous-research")],
    "code_expert": [("poolside/laguna-s-2.1:free","nous-research"), ("poolside/laguna-xs-2.1:free","nous-research"), ("inclusionai/ling-3.0-flash-fin:free","nous-research")],
    "long_document": [("inclusionai/ling-3.0-flash-fin:free","nous-research"), ("upstage/solar-pro4","nous-research"), ("meituan/longcat-2.0","nous-research")],
    "repo_scale": [("meituan/longcat-2.0","nous-research")],
    "vision": [("google/gemini-3.7-flash","openrouter"), ("stepfun/step-3.7-flash","nous-research"), ("anthropic/claude-sonnet-5","nous-research")],
    "video": [("stepfun/step-3.7-flash","nous-research")],
    "frontier_daily": [("openai/gpt-5.6-luna","nous-research")],
    "frontier_reasoning": [("anthropic/claude-sonnet-5","nous-research")],
    "frontier_sol_pro": [("openai/gpt-5.6-sol-pro","openrouter")],
}

# FIX #3: import-time integrity check - loud failure on misconfiguration
def _validate_catalog() -> None:
    for task, cands in TASK_GROUPS.items():
        for m, p in cands:
            key = _canonical_key(m, p)
            if key not in ROUTES:
                raise RuntimeError(f"TASK_GROUPS[{task!r}] references unknown route {key}")
            # key/spec mismatch check
            spec = ROUTES[key]
            if spec.model != m or spec.provider != p:
                raise RuntimeError(f"ROUTES[{key!r}] key/spec mismatch: spec has {spec.model}@{spec.provider}")
            if spec.verification_status != "verified":
                raise RuntimeError(f"TASK_GROUPS[{task!r}] references unverified route {key} status={spec.verification_status}")
    for alias in FORBIDDEN_ALIASES:
        if any(s.model == alias for s in ROUTES.values()):
            raise RuntimeError(f"forbidden alias present in ROUTES: {alias}")
    # capability cross-check FIX #7
    for task, cands in TASK_GROUPS.items():
        if task == "vision":
            for m, p in cands:
                spec = ROUTES[_canonical_key(m, p)]
                if "vision" not in spec.capabilities:
                    raise RuntimeError(f"vision task requires vision capability but {spec.model}@{spec.provider} lacks it")
        if task == "video":
            for m, p in cands:
                spec = ROUTES[_canonical_key(m, p)]
                if "video" not in spec.capabilities and "vision" not in spec.capabilities:
                    raise RuntimeError(f"video task requires video/vision capability but {spec.model}@{spec.provider} lacks it")

_validate_catalog()

def paid_escalation_enabled() -> bool:
    return os.getenv("PINEAL_ALLOW_PAID_ESCALATION", "0").strip() == "1"

# FIX #2: fail-closed is_paid/is_free with provider=None
def is_paid(model: str, provider: str | None = None) -> bool:
    matches = [s for s in ROUTES.values() if s.model == model and (provider is None or s.provider == provider)]
    if not matches:
        return True  # unknown -> enters paid firewall -> DENY
    return any(s.tier in ("paid", "frontier") or not s.is_free() for s in matches)

def is_free(model: str, provider: str | None = None) -> bool:
    matches = [s for s in ROUTES.values() if s.model == model and (provider is None or s.provider == provider)]
    return bool(matches) and all(s.is_free() for s in matches)

def assert_known_model(model: str, provider: str) -> RouteSpec:
    if model in FORBIDDEN_ALIASES:
        raise UnknownModelDenied(f"FORBIDDEN_ALIAS_DENIED: {model}")
    key = _canonical_key(model, provider)
    spec = ROUTES.get(key)
    # FIX #3: drop fallback search loop - dead code in deny-path hides bugs
    if not spec:
        raise UnknownModelDenied(f"UNKNOWN_MODEL_DENIED: {provider}/{model} not in verified catalog (key {key})")
    if spec.verification_status != "verified":
        raise UnknownModelDenied(f"MODEL_NOT_VERIFIED: {provider}/{model} status={spec.verification_status}")
    return spec

def assert_executable(model: str, provider: str | None = None, *, explicit: bool = False) -> RouteSpec:
    """FIX #4: simplified canonical-key parsing, no unreachable branches. FIX #1 explicit bypass audited."""
    # Canonical key support
    if provider is None:
        if "@" not in model:
            raise UnknownModelDenied(f"UNKNOWN_PROVIDER_DENIED: provider required for {model}")
        model, provider = model.rsplit("@", 1)

    spec = assert_known_model(model, provider)

    if spec.tier in ("paid", "frontier"):
        # FIX: explicit=True is audited, frontier requires both env and explicit
        if explicit:
            logger.warning(f"PAID_ESCALATION_EXPLICIT_BYPASS: {provider}/{model} tier={spec.tier} explicit=True used")
            if spec.tier == "frontier" and not paid_escalation_enabled():
                raise PaidEscalationDenied(f"FRONTIER_REQUIRES_ENV: {provider}/{model} needs PINEAL_ALLOW_PAID_ESCALATION=1 even with explicit=True")
        if not (explicit or paid_escalation_enabled()):
            raise PaidEscalationDenied(f"PAID_ESCALATION_DENIED: {provider}/{model} tier={spec.tier}")

    return spec

def executable_task_groups(*, allow_paid: bool | None = None) -> Dict[str, List[str]]:
    allow = paid_escalation_enabled() if allow_paid is None else allow_paid
    result: Dict[str, List[str]] = {}
    for task, candidates in TASK_GROUPS.items():
        selected: List[str] = []
        for model, provider in candidates:
            # FIX #3: don't silently swallow - _validate_catalog already ensures key exists, but keep explicit error for safety
            key = _canonical_key(model, provider)
            if key not in ROUTES:
                raise RuntimeError(f"TASK_GROUPS drift: {key} not in ROUTES")
            spec = ROUTES[key]
            if spec.tier in ("paid", "frontier") and not allow:
                continue
            selected.append(key)
        result[task] = selected
    return result

def effective_pricing(model: str, provider: str) -> Tuple[float, float] | None:
    try:
        spec = assert_known_model(model, provider)
        return spec.input_per_million_usd, spec.output_per_million_usd
    except UnknownModelDenied:
        return None

def list_pricing(model: str, provider: str) -> Tuple[float, float] | None:
    try:
        spec = assert_known_model(model, provider)
        if spec.list_input_per_million_usd is not None:
            return spec.list_input_per_million_usd, spec.list_output_per_million_usd
        return spec.input_per_million_usd, spec.output_per_million_usd
    except UnknownModelDenied:
        return None


# --------------------------------------------------------------------------- #
# Integration helpers used by the routed executor / gateway (not part of the
# FINAL reference's public surface, kept here so consumers speak one module).
# --------------------------------------------------------------------------- #
def is_known_route(model: str, provider: str) -> bool:
    """Non-raising predicate: is ``provider/model`` a FINAL-matrix route?"""
    return _canonical_key(model, provider) in ROUTES


def model_substitution_allowed(requested: str, actual: str) -> bool:
    """A provider silently substituting the requested model is never allowed."""
    if not requested or not actual:
        return True
    req = requested.strip().lower()
    act = actual.strip().lower()
    if req == act:
        return True
    # 9Router multi-provider lane combos return member models
    if req.startswith("pineal-") or req.endswith("-lane"):
        return True
    # [RÖNTGEN 2026-09-23] Sağlayıcı-farkı toleransı YALNIZCA iki taraf da
    # "sağlayıcı/model" biçimindeyse geçerlidir: aynı modelin başka bir
    # sağlayıcı kaydından dönmesi ikame değildir
    # (ör. anthropic/gpt-oss-120b -> openai/gpt-oss-120b, 9Router çok-sağlayıcılı
    # şeritler). ÇIPLAK model adı bu toleranstan yararlanamaz: "gpt-oss-120b"
    # yanıtı hangi sağlayıcının hangi ağırlığını çalıştırdığını SÖYLEMEZ — bu
    # sessiz ikamenin açık kapısıydı (eski kod True dönüyordu).
    if "/" in req and "/" in act:
        return req.split("/")[-1] == act.split("/")[-1]
    return False


# === INVARIANTS ===
if __name__ == "__main__":
    import sys
    os.environ.pop("PINEAL_ALLOW_PAID_ESCALATION", None)

    assert is_paid("completely-unknown-model") is True
    assert QUOTA_UNKNOWN is None and QUOTA_UNKNOWN != float("inf")
    for qs in QUOTAS.values():
        for v in qs.values():
            assert v != float("inf")

    assert QUOTAS["groq"]["rpm"] == 30 and QUOTAS["groq"]["rpd"] == 14400
    assert QUOTAS["groq"]["tpm"] is None and QUOTAS["groq"]["tpd"] is None
    assert QUOTAS["cerebras"]["rpm"] == 5 and QUOTAS["cerebras"]["tpm"] == 30000 and QUOTAS["cerebras"]["tpd"] == 1_000_000

    for keys in executable_task_groups(allow_paid=True).values():
        for rk in keys:
            assert "@" in rk and rk in ROUTES

    try:
        assert_executable("unknown-model@unknown-provider")
        sys.exit("MUST DENY unknown")
    except UnknownModelDenied:
        logger.warning('Suppressed exception observed at agent_core/services/final_routing_policy.py:330 (pass)')

    try:
        assert_executable("openai/gpt-5.6-luna@nous-research")
        sys.exit("paid must DENY by default")
    except PaidEscalationDenied:
        logger.warning('Suppressed exception observed at agent_core/services/final_routing_policy.py:336 (pass)')

    # happy paths
    assert assert_executable("openai/gpt-oss-120b", "groq").is_free()
    assert assert_executable("openai/gpt-5.6-luna@nous-research", explicit=True).tier == "paid"

    # forbidden alias
    try:
        assert_known_model("laguna:free", "nous-research")
        sys.exit("forbidden alias must DENY")
    except UnknownModelDenied:
        logger.warning('Suppressed exception observed at agent_core/services/final_routing_policy.py:347 (pass)')

    # no paid leakage
    for keys in executable_task_groups(allow_paid=False).values():
        assert all(ROUTES[k].is_free() for k in keys)
    assert executable_task_groups(allow_paid=False)["frontier_sol_pro"] == []

    print("ALL INVARIANTS PASS - production-ready")
