import logging

logger = logging.getLogger(__name__)
import contextvars
import hashlib
import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from functools import lru_cache
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Iterator, List, Mapping, Optional, Type, TypeVar

import httpcore
# [AUDIT 2026-10-08 · E-GÖZ1-3] `from httpx import ...` — satır başı `import httpx`
# bypass kalıbı burası dahil hiçbir ürün dosyasında kalmaz. İstenen isimler
# açıkça alınır; istemci üretimi merkezi fabrikadan (build_secure_client) geçer.
from httpx import AsyncHTTPTransport, URL
from httpcore._backends.auto import AutoBackend
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from pathlib import Path
from agent_core.services.response_cache import build_cache_from_env
from agent_core.services.task_routing_resolver import resolve_task_chain
from agent_core.services.token_compressor import compress_prompt, CompressionLevel

_RTK_POLICY_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "rtk_policy.json"
_RTK_SAFE_DEFAULT: dict[str, Any] = {
    "enabled": False,
    "default_level": "conservative",
    "bypass": {"tasks": [], "agents": []},
}

T = TypeVar("T", bound=BaseModel)

# --------------------------------------------------------------------------- #
# 9Router / legacy taşıma sözleşmesi (BOSS-1 dürüstlük düzeltmesi)
#
# Tek gerçek kaynak burasıdır. README ".env" bölümü ile kod AYNI isimleri okur:
#   1) NINEROUTER_*           → yerel 9Router hub'ı (birincil, önerilen)
#   2) PINEAL_LLM_*           → README'nin tarihsel adı (uyumluluk takma adı)
#   3) OPENROUTER_*           → bulut OpenRouter (son çare)
# Kanıt zinciri (telemetri "provider") hangi taşımanın gerçekten kullanıldığını
# yazar: yerel hub ise "9router", bulut isim uzayı ise "openrouter". Önceden her
# hâlükârda "openrouter" yazılıyordu; operatör trafiği yerel hub'a alsa bile
# kanıt yanlış okuyordu.
# --------------------------------------------------------------------------- #
NINEROUTER_DEFAULT_BASE_URL = "http://127.0.0.1:20128/v1"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})


def provider_label_for_endpoint(base_url: str, *, explicit_local: bool = False) -> str:
    """Taşıma etiketi: operatörün kendi hub'ı → '9router', bulut isim uzayı → 'openrouter'.

    Amaç yalancı telemetriyi bitirmek: ajan çağrıları legacy taşımadan geçtiğinde
    kanıt zincirine YANLIŞ "openrouter" yazılıyordu. Kural:
      * NINEROUTER_*/PINEAL_LLM_* açıkça tanımlıysa → operatör kendi hub'ını seçti → '9router'
      * adres loopback ise → yerel hub → '9router'
      * aksi hâlde → 'openrouter' (bulut)
    """
    if explicit_local:
        return "9router"
    host = ""
    try:
        host = (URL(base_url).host or "").lower()
    except Exception:
        host = ""
    return "9router" if host in _LOOPBACK_HOSTS else "openrouter"


# [BOSS-4] Model ailesi çözümü: "hiçbir model kendi ürettiği çıktıyı
# onaylayamaz" kuralı bu eşlemeyle uygulanır (jüri koltuğu düşürme).
_FAMILY_TOKENS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("anthropic", ("claude", "anthropic")),
    ("google", ("gemini", "google", "palm")),
    ("xai", ("grok", "x-ai")),
    ("openai", ("gpt", "openai", "o1", "o3", "oss")),
    ("deepseek", ("deepseek",)),
    ("zhipu", ("glm", "z-ai")),
    ("poolside", ("laguna", "poolside")),
    ("upstage", ("solar", "upstage")),
    ("inclusion", ("ling", "inclusion")),
    ("qwen", ("qwen", "alibaba")),
    ("nvidia", ("nemotron", "nvidia")),
    ("meta", ("llama", "meta")),
    ("mistral", ("mistral", "mixtral")),
)


# Jüri koltuklarının aile kimliği: rota adı tek başına yetmez ("open" hangi
# üretici?). Açıkça yazılır; "open_weights" bilinçli olarak nötr gruptur —
# hiçbir frontier üreticinin kendi çıktısını onaylamasına izin vermez.
_ROUTE_FAMILY_HINTS: dict[str, str] = {
    "pineal-juror-google": "google",
    "pineal-juror-claude": "anthropic",
    "pineal-juror-open": "open_weights",
}


def model_family(model: str | None) -> str:
    """Model/rota adından üretici ailesini çıkarır (bilinmiyorsa 'unknown')."""
    token = (model or "").strip().lower()
    if not token:
        return "unknown"
    if token in _ROUTE_FAMILY_HINTS:
        return _ROUTE_FAMILY_HINTS[token]
    for family, needles in _FAMILY_TOKENS:
        if any(needle in token for needle in needles):
            return family
    return "unknown"


def resolve_legacy_endpoint() -> tuple[str, Optional[str], str]:
    """(base_url, api_key, provider_label) — ilk tanımlı kanal kazanır."""
    ninerouter_url = os.getenv("NINEROUTER_BASE_URL")
    pineal_url = os.getenv("PINEAL_LLM_BASE_URL")
    explicit_local = bool(ninerouter_url or pineal_url)
    base_url = (
        ninerouter_url
        or pineal_url
        or os.getenv("OPENROUTER_BASE_URL")
        or "https://openrouter.ai/api/v1"
    )
    api_key = (
        os.getenv("NINEROUTER_API_KEY")
        or os.getenv("PINEAL_LLM_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
    )
    return base_url.rstrip("/"), api_key, provider_label_for_endpoint(base_url, explicit_local=explicit_local)


class _PinnedNetworkBackend:
    """Connect one verified hostname to one pre-resolved address."""

    def __init__(self, hostname: str, address: str):
        self._hostname = hostname.rstrip(".").lower()
        self._address = address
        self._backend = AutoBackend()

    async def connect_tcp(self, host, port, **kwargs):
        if host.rstrip(".").lower() != self._hostname:
            raise OSError("PINNED_ROUTE_HOST_MISMATCH")
        return await self._backend.connect_tcp(self._address, port, **kwargs)

    async def connect_unix_socket(self, path, **kwargs):
        raise OSError("PINNED_ROUTE_UNIX_SOCKET_FORBIDDEN")

    async def sleep(self, seconds):
        await self._backend.sleep(seconds)


class _PinnedAsyncHTTPTransport(AsyncHTTPTransport):
    """httpx transport that preserves TLS SNI while preventing DNS rebinding."""

    def __init__(self, hostname: str, address: str):
        super().__init__(retries=0)
        self._pool = httpcore.AsyncConnectionPool(
            network_backend=_PinnedNetworkBackend(hostname, address),
            retries=0,
        )


@dataclass(frozen=True)
class LLMChatResult:
    """One OpenAI-compatible response bound to its immutable gateway call id."""

    call_id: str
    response: Any = field(repr=False)


@dataclass(frozen=True)
class GatewayRoute:
    """One authorized OpenAI-compatible transport selected by the router."""

    connection_id: str
    provider_id: str
    model: str
    base_url: str
    api_key: Optional[str] = field(default=None, repr=False)
    local: bool = False
    hostname: Optional[str] = None
    pinned_address: Optional[str] = None
    host_header: Optional[str] = None
    input_per_million_usd: Optional[float] = None
    output_per_million_usd: Optional[float] = None
    # FINAL-SPEC: liste fiyatı ayrı taşınır (ör. Nous indirimi listeden farklı);
    # spend accounting daima effective (input/output_per_million) kullanır.
    list_input_per_million_usd: Optional[float] = None
    list_output_per_million_usd: Optional[float] = None

    @property
    def pricing(self) -> Optional[dict[str, float]]:
        if self.input_per_million_usd is None or self.output_per_million_usd is None:
            return None
        return {
            "in": self.input_per_million_usd,
            "out": self.output_per_million_usd,
        }


@dataclass(frozen=True)
class LLMChatStream:
    """A prefetched provider stream bound to one immutable gateway call id."""

    call_id: str
    chunks: AsyncIterator[Any] = field(repr=False)


@dataclass
class LLMCallScope:
    """Task-local collector used to bind call records to one agent execution.

    Context variables are copied per asyncio task, so concurrent agents sharing a
    gateway cannot consume each other's records. The records live in the scope as
    well as in the bounded diagnostic ``call_log``; evidence never relies on a
    mutable global log slice.
    """

    task_id: Optional[str]
    agent_id: Optional[str]
    records: List[dict[str, Any]] = field(default_factory=list)

    @property
    def call_ids(self) -> List[str]:
        return [record["call_id"] for record in self.records]


_active_call_scope: contextvars.ContextVar[Optional[LLMCallScope]] = contextvars.ContextVar(
    "llm_call_scope", default=None
)

# FINAL-SPEC F-4: zincirin KAYNAĞI telemetriye yazılır — matrix mi, task
# fallback mi, yoksa sessiz ENV emergency override'u mu. Default: matrix.
_active_chain_source: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "llm_chain_source", default=None
)

_active_task_hint: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "llm_task_hint", default=None
)
_active_agent_hint: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "llm_agent_hint", default=None
)

# (b'') davranış turu kararı (2. ajan mühürlü): ajânın tier'ı zincir veri-
# modeline gömülmez; variant katmanına contextvar ile taşınır.
# - get_agent_chain SET EDER (agent_tiers.json'dan; reset YOK — overwrite
#   disiplini: her resolve yazar, son yazan kazanır; ajan tanınmıyorsa
#   "unknown"). Üç çağrıcı da (capable_chain, snapshot, Aspasia inspector)
#   bu yüzden otomatik doğru tier'ı kurar — aspasia/ dosyasına dokunulmaz.
# - agent_route_variants OKUR; FAZ-2-ENFORCE kararını FAZ-1'de DENETİM izine
#   yazar ama UYGULAMAZ (FAZ-1'de üretim davranışı birebir korunur).
# - effective_routing_snapshot kendi döngüsü için save/restore yapar (kalıntı
#   bırakmaz; M-C3); _log_call tier'ı chain_source yanına yazar (stale olursa
#   GÖRÜNÜR olur — sessiz yanlışlık yasak).
_AGENT_TIER_VALUES: frozenset[str] = frozenset({"heavy", "vision", "simple", "verify", "jury"})
_active_agent_tier: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "llm_agent_tier", default=None
)

class SpendCapExceeded(RuntimeError):
    """P2-MALİYET: canlı harcama üst limiti aşıldı — daha fazla çağrı reddedilir."""


class ProviderEmptyResponseError(RuntimeError):
    """Sağlayıcı 200 döndürdü ama `choices` BOŞTU — transport/semantic hata.

    [FIX #10] Ayrı bir istisna tipi: query_json'un parse-tamir bloğu
    ``except ValueError`` ile bu hatayı "bozuk JSON" sanıp ikinci bir
    ÜCRETLİ repair çağrısı tetikliyordu (modülün kendi sözleşmesi: "Repair
    is scoped to parse/schema failures only"). RuntimeError tabanlı olduğu
    için parse-tamir bloğu onu yakalayamaz; hata doğrudan yükselir.
    Yeniden denenebilirlik değişmedi: _is_retryable_error bilinmeyen
    tiplerde default (True) koluna düşer, ValueError ile aynı davranış.
    """


# Errors that must never trigger a chain fallback: they are configuration or
# policy rejections, not transient upstream conditions.
_FALLBACK_GUARD_MARKERS = (
    "spend cap",
    "spend_cap",
    "unknown_pricing",
    "paid_escalation",
    "model unavailable",
    "local_provider_unavailable",
    "non_retryable",
    "circuit",
    "real_llm_call_not_executed",
    "llm_key_missing",
    "llm api key rejected",
    # FINAL-SPEC #27: provider'in sessiz model ikamesi reddi bir TRANSPORT
    # hatası değil politika kararıdır — zincir/merdiven devam ettirilmez.
    "model_substitution_denied",
)

# MP-ROUTING: Gerçek çok sağlayıcılı yürütme. Ajan zincirlerindeki çıplak
# slug'lar artık salt "OpenRouter'a gitsin" varsayımıyla çevrilmez; aynı
# model doğrudan sağlayıcı API'sinde (kendi base_url/anahtar/kota/fiyat)
# mevcut ve politika kapılarından geçiyorsa maliyet merdiveni önce onu
# önerir. OpenRouter havuzun SANTRALİ değil, bir üyesidir.
# FAZ 3: liste 4 girdiden katalogdaki TUM openai_chat uzak saglayicilara
# acildi. Kume keyfi degil: routed_chat._OPTIONAL_OPENAI_CHAT_CONNECTIONS
# ile ayni saglayicilar + ayni env adlari (tek sozlesme, iki yol) arti
# katalogdaki diger openai_chat uzak saglayicilar. *-local ve base_url'suz
# girdiler anahtar istemez (tasiyici degiller). openai/anthropic/xai/cohere/
# azure listede YOK: tasiyicilari openai_chat degil (tani destegi ayri is);
# anahtarlari route_diagnostics'te gorunur (transport_unsupported).
# google-gemini BURADA: Google'in resmi OpenAI-uyumlu endpoint'i
# (.../v1beta/openai/) katalogda openai_chat isaretli; sifir yeni transport
# koduyla ayni AsyncOpenAI tasmasi kullanilir.
# FAZ-2-P4 (2026-09-08, sahip onayi): google-gemini-backup AYNI endpoint'in
# 2. anahtari (GEMINI_BACKUP_API_KEY) — 429/limit durumunda merdiven otomatik
# backup key'e duser (ayni model, ayri kontenjan). Vertex (GEMINI_VERTEX_TOKEN)
# ayri base/protokol ister -> diagnostic'ta kalir (canli dogrulama sonrasi eklenir).
_AGENT_DIRECT_PROVIDER_KEYS: tuple[tuple[str, str], ...] = (
    ("groq", "GROQ_API_KEY"),
    ("deepseek", "DEEPSEEK_API_KEY"),
    ("cerebras", "CEREBRAS_API_KEY"),
    ("nous-research", "NOUS_API_KEY"),
    ("mistral", "MISTRAL_API_KEY"),
    ("together", "TOGETHER_API_KEY"),
    ("fireworks", "FIREWORKS_API_KEY"),
    ("alibaba-dashscope", "DASHSCOPE_API_KEY"),
    ("sambanova", "SAMBANOVA_API_KEY"),
    ("nvidia-nim", "NVIDIA_API_KEY"),
    ("huggingface", "HUGGINGFACE_API_KEY"),
    ("deepinfra", "DEEPINFRA_API_KEY"),
    ("perplexity", "PERPLEXITY_API_KEY"),
    ("google-gemini", "GEMINI_API_KEY"),
    ("google-gemini-backup", "GEMINI_BACKUP_API_KEY"),
)

# FAZ 3: tasiyicisi openai_chat olmayan uzak saglayicilar. Rota TEKLIF
# EDILMEZ (transport yok); anahtarlari yalniz route_diagnostics'te
# "gorunur" (key_present + transport_unsupported) — operator envanterinin
# akibetini tek ekranda gorur, sessiz yutma olmaz.
_DIAGNOSTIC_ONLY_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("openai", "OPENAI_API_KEY"),
    ("anthropic", "ANTHROPIC_API_KEY"),
    ("xai", "XAI_API_KEY"),
    ("cohere", "COHERE_API_KEY"),
    ("azure-openai", "AZURE_OPENAI_API_KEY"),
    # FAZ 3-EK: operator envanterindeki ek anahtarlar. iflow = ozel ag
    # gecidi (baz URL/protokol bilinmeden rota TEKLIF EDILMEZ); vertex
    # gemini (GEMINI_VERTEX_TOKEN) farkli base/protokol ister — rotasyon
    # canli dogrulama sonrasi eklenir (FAZ-2-P4). Hepsi tani ekraninda
    # GORUNUR (sessiz yutma yok).
    ("iflow", "IFLOW_API_KEY"),
    ("google-gemini-vertex", "GEMINI_VERTEX_TOKEN"),
)

_KNOWN_PROVIDER_KEY_IDS: frozenset = frozenset(
    [pid for pid, _ in _AGENT_DIRECT_PROVIDER_KEYS]
    + [pid for pid, _ in _DIAGNOSTIC_ONLY_PROVIDERS]
)


def _attested_provider_models(provider_id: str) -> tuple[str, ...]:
    """FAZ 3: operator beyanli model listesi (PINEAL_PROVIDER_MODELS_*).

    Katalog `models` bos olan bir saglayiciya operator, sundugunu BILDIGI
    model ID'lerini beyan eder: PINEAL_PROVIDER_MODELS_TOGETHER="m1,m2".
    Bu bir katalog iddiasi DEGIL, operator beyanidir (kendi anahtari,
    kendi kotasi); firewall (paid-escalation) + spend-cap + kota kapilari
    aynen gecerlidir. Uydurma katalog girdisi yazilmaz.
    """
    env_name = "PINEAL_PROVIDER_MODELS_" + provider_id.upper().replace("-", "_")
    raw = os.getenv(env_name, "")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


class ModelSubstitutionDeniedError(RuntimeError):
    """ROUTING-HARDENING: reddin结构化 kimligi (requested/actual) exception ile
    tasinir; boylece call_log kaydi provider'in dondurdugu modeli FIELD olarak
    tutar (eskiden sadece error-string'deydi). RuntimeError subclass'idir —
    mevcut `pytest.raises(RuntimeError, match=...)` sozlesmeleri bozulmaz."""

    def __init__(self, message: str, *, requested: str, actual: str):
        super().__init__(message)
        self.requested = requested
        self.actual = actual


def _failure_reason(exc: BaseException) -> str:
    """Map an upstream failure to the FINAL telemetry ``fallback_reason``."""
    status = getattr(exc, "status_code", None)
    err = str(exc).lower()
    if status == 429 or "429" in err or "rate limit" in err:
        if any(marker in err for marker in ("quota", "insufficient", "credit")):
            return "429_QUOTA_EXHAUSTED"
        return "429_RATE_LIMITED"
    if status == 408 or "timeout" in err or "timed out" in err:
        return "TIMEOUT"
    if isinstance(status, int) and 500 <= status < 600:
        return "SERVER_ERROR"
    if status == 404 or "model_not_found" in err or "model unavailable" in err:
        return "MODEL_UNAVAILABLE"
    if any(marker in err for marker in ("connection", "connect", "refused", "reset")):
        return "NETWORK_FAILURE"
    return type(exc).__name__.upper()


def _is_fallback_allowed(
    exc: BaseException, *, json_mode: bool, route_scoped: bool = False
) -> bool:
    """Decide whether a chain may move to the next model after ``exc``.

    Fallback is allowed for transient transport errors (timeout,
    connection, 408/429/5xx), upstream 401/auth failures **on a specific
    route**, and — in JSON mode — for genuine parse/schema failures. Auth on
    the master (route-less) key, spend-cap, unknown-pricing, paid-escalation,
    and model-unavailable rejections are guarded.

    ``route_scoped``: hata belirli bir sağlayıcı rotasından mı geldi
    (``route is not None``)? [RÖNTGEN 2026-09-23] Eskiden 401 koşulsuz
    "geçici" sayılıyordu: OpenRouter MASTER anahtarı reddedildiğinde zincir
    sıradaki 3 modeli de aynı geçersiz anahtarla deniyordu (ölçüldü: 3 çağrı).
    Oysa `_is_retryable_error` 401/403'ü zaten KALICI sınıflandırıyor — iki
    sınıflandırıcı çelişiyordu. Master anahtar hatası artık anında yükselir.
    """
    err = str(exc).lower()
    if isinstance(exc, SpendCapExceeded):
        return False
    if "in_flight" in err or "in-flight" in err:
        return True
    if any(marker in err for marker in _FALLBACK_GUARD_MARKERS):
        return False
    if any(marker in err for marker in ("high demand", "overloaded")):
        return True
    if any(marker in err for marker in ("401", "unauthorized", "invalid_api_key")):
        # Rota-kapsamlı auth hatası: o sağlayıcının KENDİ anahtarı geçersiz —
        # başka taşıyıcı/rota gerçekten çalışabilir. Rota yoksa (master
        # OpenRouter anahtarı) aynı anahtar zincirdeki tüm modeller için
        # geçersizdir: düşmek yalnız zaman/kota yakar ve kök nedeni gizler.
        return route_scoped
    if json_mode and isinstance(exc, (ValueError, TypeError, KeyError)):
        return True
    return LLMGateway._is_retryable_error(exc)


class LLMGateway:
    # [BOSS-4] Çapraz jüri paneli: bu koltuklar bağımsız hakemdir; üreten
    # ajanın ailesiyle aynı olan koltuk karar anında düşürülür.
    JURY_PANEL_AGENTS: tuple[str, ...] = (
        "pineal_juror_google",
        "pineal_juror_claude",
        "pineal_juror_open",
    )

    MODEL_REGISTRY = {
        "solar_pro4": "upstage/solar-pro4",
        "ling_3_flash": "inclusionai/ling-3.0-flash",
        "deepseek_v4_flash": "deepseek/deepseek-v4-flash",
        "glm_5_2": "z-ai/glm-5.2",
        "deepseek_v4_pro": "deepseek/deepseek-v4-pro",
        "gemini_3_7_flash": "google/gemini-3.7-flash",
        "claude_sonnet_5": "anthropic/claude-sonnet-5",
        "grok_4_6": "x-ai/grok-4.6",
        # FAZ-2 (sahip Q2 + 2. ajan izin listesi): simple tier'a bağlanan canlı-
        # teyitli free modeller. gpt-oss-120b: groq (tam) direct free; laguna
        # :free: nous direct free (canlı prefix'li yazım). Not: Cerebras
        # gpt-oss-120b free katmanı 2026-07-21'de kapatıldı (araştırma
        # 2026-09-08) — o rota artık ücretli (ROUTES'a bak).
        "gpt_oss_120b": "openai/gpt-oss-120b",
        "laguna_s_2_1_free": "poolside/laguna-s-2.1:free",
        # FAZ-2-P3 (sahip onayı 2026-09-08): resonance_synthesizer'a Luna
        # atandı. ROUTES'ta nous-research indirimli kanalı + OR legacy aynı
        # $0.20/$1.20'de; MODEL_PRICING legacy accounting için eklendi.
        "gpt_5_6_luna": "openai/gpt-5.6-luna",
        # 9Router Canlı Rotaları (4 İş Koridoru + 3 Jüri Koltuğu)
        "pineal_deep_reasoning": "pineal-deep-reasoning",
        "pineal_general_reasoning": "pineal-general-reasoning",
        "pineal_fast_extract": "pineal-fast-extract",
        "pineal_vision": "pineal-vision",
        "pineal_juror_google": "pineal-juror-google",
        "pineal_juror_claude": "pineal-juror-claude",
        "pineal_juror_open": "pineal-juror-open",
        "pineal_truth_lane": "pineal-truth-lane",
        "pineal_vision_lane": "pineal-vision-lane",
        "pineal_intelligence_lane": "pineal-intelligence-lane",
    }

    MODEL_PRICING = {
        # 9Router yerel yönlendirici hatları (yerel proxy — fatura 0 / harici kota)
        "pineal-deep-reasoning": {"in": 0.0, "out": 0.0},
        "pineal-general-reasoning": {"in": 0.0, "out": 0.0},
        "pineal-fast-extract": {"in": 0.0, "out": 0.0},
        "pineal-vision": {"in": 0.0, "out": 0.0},
        "pineal-juror-google": {"in": 0.0, "out": 0.0},
        "pineal-juror-claude": {"in": 0.0, "out": 0.0},
        "pineal-juror-open": {"in": 0.0, "out": 0.0},
        "pineal-truth-lane": {"in": 0.0, "out": 0.0},
        "pineal-vision-lane": {"in": 0.0, "out": 0.0},
        "pineal-intelligence-lane": {"in": 0.0, "out": 0.0},
        # Fiyatlar 2026-09-08'de OpenRouter kataloğundan doğrulandı (promo/listed,
        # cached-effective değil). Kaynak: /api/v1/models + model sayfaları.
        # Not: solar-pro4/ling-3.0-flash promo 2026-09-10'a kadar; sonrası 0.12/0.24 ve
        # daha yükseğe döner — `OPENROUTER_MAX_SPEND_USD` bu tabloyu baz alır.
        "upstage/solar-pro4": {"in": 0.03, "out": 0.12},
        "inclusionai/ling-3.0-flash": {"in": 0.021, "out": 0.063},
        # 2026-09-08 araştırma düzeltmesi: OR kataloğu deepseek-v4-flash'i
        # $0.09/$0.18 gösteriyor (eski $0.0679/$0.168 iki tarafla da uyuşmuyordu).
        "deepseek/deepseek-v4-flash": {"in": 0.09, "out": 0.18},
        "z-ai/glm-5.2": {"in": 0.3276, "out": 1.03},
        "deepseek/deepseek-v4-pro": {"in": 0.4679, "out": 0.9358},
        "google/gemini-3.7-flash": {"in": 0.75, "out": 3.75},
        # 2026-09-02 karar matrisi: Sonnet 5 $2/$10 (promo), Grok 4.6 $2/$6.
        # 2026-09-08 notu: Sonnet 5 promo'su 31.08.2026'da sona erdi; Anthropic
        # liste $3/$15'e taşındı. OR passthrough ve Nous kanalı ($1.6/$8,
        # ROUTES) canlıda yeniden teyit edilmeden bu tablo değiştirilmez —
        # CI canlı-kontrol (verify_openrouter_catalog) teyitten sonra güncellenir.
        "anthropic/claude-sonnet-5": {"in": 2.0, "out": 10.0},
        "x-ai/grok-4.6": {"in": 2.0, "out": 6.0},
        # FAZ-2-P3: resonance_synthesizer → Luna ($0.20/$1.20, OR canlı fiyat).
        "openai/gpt-5.6-luna": {"in": 0.2, "out": 1.2},
        # FAZ-2-P3 (Cerebras free katmanı kapandı): gpt-oss-120b free kanalı
        # Groq; OR-legacy ÜCRETLİ yol accounting'i burada kayıtlı (free kanal
        # teklif edilemezse OR'a düşen çağrı UNKNOWN_PRICING ile kırılmasın —
        # eski cerebras-free yedek bu boşluğu gizliyordu).
        "openai/gpt-oss-120b": {"in": 0.15, "out": 0.60},
        # live_llm_gate.py varsayılan hakemi (OPENROUTER_JUDGE_MODEL). Guard bunu
        # fiyatsız görüp gate'i UNKNOWN_PRICING ile düşürüyordu — eklendi.
        "openai/gpt-5.6-sol-pro": {"in": 2.0, "out": 10.0},
        # FAZ-2 free model accounting record
        "poolside/laguna-s-2.1:free": {"in": 0.0, "out": 0.0},
    }
    
    # Defaults follow the 2026-09-02 decision matrix (retired promo slugs are
    # NOT the bare-env fallback). Operators may still override via env.
    TIER_1_MODEL = os.getenv("OPENROUTER_TIER_1_MODEL", MODEL_REGISTRY["claude_sonnet_5"])
    TIER_2_MODEL = os.getenv("OPENROUTER_TIER_2_MODEL", MODEL_REGISTRY["deepseek_v4_flash"])
    DEFAULT_VISION_MODEL = os.getenv("OPENROUTER_VISION_MODEL", MODEL_REGISTRY["gemini_3_7_flash"])

    CHAINS = {
        "depth": [MODEL_REGISTRY["claude_sonnet_5"], MODEL_REGISTRY["deepseek_v4_pro"], MODEL_REGISTRY["gemini_3_7_flash"]],
        "vision": [MODEL_REGISTRY["gemini_3_7_flash"], MODEL_REGISTRY["grok_4_6"]],
        "dialogue": [MODEL_REGISTRY["claude_sonnet_5"], MODEL_REGISTRY["gemini_3_7_flash"]],
        "fast": [MODEL_REGISTRY["deepseek_v4_flash"], MODEL_REGISTRY["gemini_3_7_flash"]],
    }
    # Agent policies make specialist selection explicit while retaining a
    # bounded, capability-compatible failover chain.
    # Karar matrisi: Passion/Cognitive/Audit hızlı & ucuz katmana çekildi,
    # Friction/HumanBehavior/Aspasia/Lilith yüksek akıl katmanında.
    AGENT_CHAINS = {
        # FAZ-2-P3 (sahip onayı 2026-09-08, araştırma): cognitive_profiler
        # ton/karmaşıklık/mizah profili — hamaliye-ağırlıklı: Groq free
        # (gpt-oss-120b) birincil, ucuz deepseek-v4-flash yedek. Gemini
        # birincillikten çekildi (veri hamallığında frontier/paid yakılmaz).
        "cognitive_profiler": [
            MODEL_REGISTRY["gpt_oss_120b"],
            MODEL_REGISTRY["gemini_3_7_flash"],
            MODEL_REGISTRY["deepseek_v4_flash"],
        ],
        "friction_detector": [MODEL_REGISTRY["claude_sonnet_5"], MODEL_REGISTRY["gemini_3_7_flash"], MODEL_REGISTRY["deepseek_v4_pro"]],
        # [RÖNTGEN 2026-09-23] simple tier = free-only (FAZ-2 ENFORCE, sahip Q2).
        # Zincirdeki `google/gemini-3.7-flash` basamağı ÇALIŞAMAZ: tier kapısı
        # onu `simple_non_free` gerekçesiyle reddediyor (ölçüldü: 0 rota teklifi).
        # Yani RUNBOOK üç basamaklı bir merdiven belgelerken ortadaki basamak
        # hiçbir koşulda koşmuyordu — ölü rota silindi.
        "passion_mapper": [
            MODEL_REGISTRY["gpt_oss_120b"],
            MODEL_REGISTRY["laguna_s_2_1_free"],
        ],
        # FAZ-2-P3 (sahip onayı 2026-09-08, araştırma): resonance_synthesizer
        # ilk-temas metni üretimi — OR/nous $0.20/$1.20 Luna birincil
        # (kalite 77, claude'dan ~10× ucuz); claude-sonnet-5 yedek kalır.
        "resonance_synthesizer": [
            MODEL_REGISTRY["gpt_5_6_luna"],
            MODEL_REGISTRY["gemini_3_7_flash"],
            MODEL_REGISTRY["claude_sonnet_5"],
        ],
        "vision_analyzer": [MODEL_REGISTRY["gemini_3_7_flash"], MODEL_REGISTRY["grok_4_6"]],
        "autonomous_verifier": [MODEL_REGISTRY["claude_sonnet_5"], MODEL_REGISTRY["gemini_3_7_flash"], MODEL_REGISTRY["grok_4_6"]],
        # [BOSS-4] Jüri koltukları: her biri TEK rotaya bağlanır, böylece
        # çapraz jüri kuralı (üreten aile panelden düşer) deterministik kalır.
        "pineal_juror_google": [MODEL_REGISTRY["pineal_juror_google"]],
        "pineal_juror_claude": [MODEL_REGISTRY["pineal_juror_claude"]],
        "pineal_juror_open": [MODEL_REGISTRY["pineal_juror_open"]],
        # [RÖNTGEN 2026-09-23] aynı gerekçe: simple tier'da paid gemini
        # basamağı ölüydü (tier kapısı reddediyordu). Free-only zincir geri kuruldu.
        "autonomous_verifier_extract": [
            MODEL_REGISTRY["gpt_oss_120b"],
            MODEL_REGISTRY["laguna_s_2_1_free"],
        ],
        "osint_investigator": [MODEL_REGISTRY["gemini_3_7_flash"], MODEL_REGISTRY["grok_4_6"], MODEL_REGISTRY["deepseek_v4_pro"]],
        "aspasia": [MODEL_REGISTRY["claude_sonnet_5"], MODEL_REGISTRY["gemini_3_7_flash"]],
        # [RÖNTGEN 2026-09-23] simple tier: ölü paid basamak kaldırıldı
        # (yukarıdaki passion_mapper notuyla aynı gerekçe).
        "lilith_growth": [
            MODEL_REGISTRY["gpt_oss_120b"],
            MODEL_REGISTRY["laguna_s_2_1_free"],
        ],
        "authenticity_auditor": [
            MODEL_REGISTRY["deepseek_v4_flash"],
            MODEL_REGISTRY["gemini_3_7_flash"],
            MODEL_REGISTRY["claude_sonnet_5"],
        ],
        "depth_analyst": [
            MODEL_REGISTRY["claude_sonnet_5"],
            MODEL_REGISTRY["deepseek_v4_pro"],
            MODEL_REGISTRY["gemini_3_7_flash"],
        ],
        # FAZ-2-P3 (sahip onayı): human_behavior Groq free (gpt-oss-120b)
        # birincil — research: OpenCV ön-işlem görseli zaten çözüyor; paid
        # claude birincillik bitti (task_routing delta aynı zinciri taşır).
        "human_behavior": [MODEL_REGISTRY["gpt_oss_120b"], MODEL_REGISTRY["gemini_3_7_flash"]],
        "mirror_truth": [MODEL_REGISTRY["claude_sonnet_5"], MODEL_REGISTRY["gemini_3_7_flash"]],
        "pattern_interrupt": [
            MODEL_REGISTRY["gpt_oss_120b"],
            MODEL_REGISTRY["laguna_s_2_1_free"],
        ],
    }
    # 9Router yerel proxy aktifken (127.0.0.1:20128) ajanların kullandığı kanonik hatlar
    NINEROUTER_AGENT_CHAINS = {
        "mirror_truth": ["pineal-general-reasoning", "pineal-deep-reasoning"],
        "autonomous_verifier": ["pineal-general-reasoning", "pineal-fast-extract"],
        "human_behavior": ["pineal-general-reasoning", "pineal-fast-extract"],
        "passion_mapper": ["pineal-fast-extract", "pineal-general-reasoning"],
        "friction_detector": ["pineal-general-reasoning", "pineal-fast-extract"],
        "cognitive_profiler": ["pineal-general-reasoning", "pineal-fast-extract"],
        "pattern_interrupt": ["pineal-fast-extract", "pineal-general-reasoning"],
        "resonance_synthesizer": ["pineal-general-reasoning", "pineal-deep-reasoning"],
        "vision_analyzer": ["pineal-vision", "pineal-general-reasoning"],
        "osint_investigator": ["pineal-general-reasoning", "pineal-fast-extract"],
        "authenticity_auditor": ["pineal-vision", "pineal-general-reasoning"],
        "depth_analyst": ["pineal-general-reasoning", "pineal-deep-reasoning"],
        "autonomous_verifier_extract": ["pineal-fast-extract", "pineal-general-reasoning"],
        "lilith_growth": ["pineal-fast-extract", "pineal-general-reasoning"],
        "aspasia": ["pineal-general-reasoning", "pineal-deep-reasoning"],
        "shadow_executor": ["pineal-general-reasoning", "pineal-deep-reasoning"],
        "interpreter": ["pineal-general-reasoning", "pineal-fast-extract"],
        "pineal_juror_google": ["pineal-juror-google"],
        "pineal_juror_claude": ["pineal-juror-claude"],
        "pineal_juror_open": ["pineal-juror-open"],
    }
    # FAZ-2 notu: simple-tier ajan zincirleri (autonomous_verifier_extract,
    # lilith_growth, pattern_interrupt, passion_mapper) canlı-teyitli free
    # modellere bağlandı (sahip Q2: tek-tip [gpt-oss-120b, laguna-s-2.1:free]).
    # ENFORCE simple=free-only bu zincirlerle uyumludur; paid taşıma isteyen
    # simple zincir FAZ-2 kilidinde KIRMIZI olur (M-C1-full).
    TASK_CAPABILITIES = {
        "vision": frozenset({"chat", "vision"}),
        "depth": frozenset({"chat"}),
        "dialogue": frozenset({"chat"}),
        "fast": frozenset({"chat"}),
    }
    AGENT_CAPABILITIES = {
        "vision_analyzer": frozenset({"chat", "vision"}),
        "cognitive_profiler": frozenset({"chat"}),
        "friction_detector": frozenset({"chat"}),
        "passion_mapper": frozenset({"chat"}),
        "resonance_synthesizer": frozenset({"chat"}),
        "autonomous_verifier": frozenset({"chat"}),
        "authenticity_auditor": frozenset({"chat"}),
        "depth_analyst": frozenset({"chat"}),
    }
    VISION_MODELS = frozenset({
        MODEL_REGISTRY["gemini_3_7_flash"],
        MODEL_REGISTRY["claude_sonnet_5"],
        MODEL_REGISTRY["grok_4_6"],
        MODEL_REGISTRY["pineal_vision_lane"],
        MODEL_REGISTRY["pineal_vision"],
    })

    LOCAL_DEFAULT_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")
    LOCAL_DEFAULT_MODEL = os.getenv("LOCAL_LLM_MODEL", "dolphin-llama3:latest")

    def get_chain(self, task: str) -> List[str]:
        env_var = f"OPENROUTER_CHAIN_{task.upper()}"
        if os.getenv(env_var):
            return [m.strip() for m in os.getenv(env_var).split(",") if m.strip()]
        if "20128" in self.openrouter_base_url:
            t = task.lower()
            if t == "vision":
                return ["pineal-vision", "pineal-general-reasoning"]
            if t == "depth":
                return ["pineal-general-reasoning", "pineal-deep-reasoning"]
            if t == "fast":
                return ["pineal-fast-extract", "pineal-general-reasoning"]
            return ["pineal-general-reasoning", "pineal-deep-reasoning"]
        return self.CHAINS.get(task.lower(), [self.TIER_1_MODEL, self.TIER_2_MODEL])

    def get_agent_chain(self, agent_name: str | None, task: str) -> List[str]:
        # (b'') kural 1: tier BU fonksiyonun içinde set edilir (tek satır,
        # reset YOK — token-dance değeri silerdi). Overwrite disiplini: her
        # resolve yazar; ajan yoksa None, tiers.json'da tanınmıyorsa "unknown"
        # (-> heavy-eşdeğeri + tier_unresolved telemetri). env_override dahil
        # HER dal yazımdan sonra döner, bu yüzden set en başta tek noktadadır.
        tier: Optional[str] = None
        if agent_name:
            entry = self._load_agent_tiers().get(agent_name)
            candidate = entry.get("tier") if isinstance(entry, dict) else None
            tier = candidate if candidate in _AGENT_TIER_VALUES else "unknown"
        _active_agent_tier.set(tier)
        if agent_name:
            env_var = f"OPENROUTER_AGENT_CHAIN_{agent_name.upper()}"
            if os.getenv(env_var):
                # FINAL-SPEC F-4: matrix DEFAULT SoT'tur; ENV yalnızca açık
                # operasyon/acil override'ıdır ve telemetride işaretlenir.
                _active_chain_source.set("env_override")
                return [m.strip() for m in os.getenv(env_var).split(",") if m.strip()]
            if "20128" in self.openrouter_base_url and agent_name in self.NINEROUTER_AGENT_CHAINS:
                _active_chain_source.set("9router_canonical")
                return self.NINEROUTER_AGENT_CHAINS[agent_name]
            # STEP-1 TASK ROUTING: config-driven delta over AGENT_CHAINS.
            # Precedence: env (above) > task_routing > agent_matrix > task_chain.
            routed = resolve_task_chain(
                agent_name, task, valid_keys=frozenset(self.MODEL_REGISTRY.keys())
            )
            if routed is not None:
                _active_chain_source.set("task_routing")
                return [self.MODEL_REGISTRY[key] for key in routed]
            if agent_name in self.AGENT_CHAINS:
                _active_chain_source.set("agent_matrix")
                return self.AGENT_CHAINS[agent_name]
        _active_chain_source.set("task_chain")
        return self.get_chain(task)

    def required_capabilities(
        self,
        *,
        task: str = "depth",
        agent_name: Optional[str] = None,
        images: Optional[List[str]] = None,
    ) -> frozenset[str]:
        capabilities: set[str] = {"chat"}
        capabilities.update(self.TASK_CAPABILITIES.get(task.lower(), ()))
        if agent_name:
            capabilities.update(self.AGENT_CAPABILITIES.get(agent_name, ()))
        if images:
            capabilities.add("vision")
        return frozenset(capabilities)

    def model_satisfies(self, model: str, capabilities: frozenset[str]) -> bool:
        if "vision" in capabilities:
            return model in self.VISION_MODELS
        return True

    def capable_chain(
        self,
        *,
        task: str,
        agent_name: Optional[str] = None,
        images: Optional[List[str]] = None,
    ) -> List[str]:
        required = self.required_capabilities(
            task=task, agent_name=agent_name, images=images
        )
        chain = [
            model
            for model in self.get_agent_chain(agent_name, task)
            if self.model_satisfies(model, required)
        ]
        if not chain:
            raise RuntimeError(
                f"NO_CAPABLE_MODEL: no model in {agent_name or task} chain "
                f"satisfies {sorted(required)}"
            )
        return chain

    def effective_routing_snapshot(self) -> dict[str, Any]:
        """Salt-okunur routing snapshotu: registry + çözünmüş zincirler + rotalar + tierler.

        Routing bilgisinin TEK makine-okunur ağzı. `scripts/generate_routing_shadows.py`
        ve kontrat testleri buradan beslenir; üretim yolları (query_chain vb.) bu metodu
        ÇAĞIRMAZ (sıfır davranış etkisi).

        Sözleşme (test ile kilitli):
        - task="depth" ile çözülür; listelenen ajanlarda katman atfı task-bağımsızdır
          (env/routing/matrix dalları task'a bakmaz).
        - `_active_chain_source` ve `_active_agent_tier` side-effect'leri
          save/restore ile yutulur (M-C3: döngü sonrası tier kalıntısı bırakmaz).
        - Tier ihlalleri BİLGİLENDİRME amaçlıdır (v1): CI kırmaz, RUNBOOK'ta render edilir.
        """
        from agent_core.services.task_routing_resolver import load_task_routing

        tiers = self._load_agent_tiers()
        routing_table = load_task_routing()
        routed = {
            k
            for k, v in routing_table.items()
            if not k.startswith("_") and k != "schema_version" and isinstance(v, list)
        }
        agents = sorted(set(self.AGENT_CHAINS) | routed)
        reverse = {v: k for k, v in self.MODEL_REGISTRY.items()}

        token = _active_chain_source.set(_active_chain_source.get())
        tier_token = _active_agent_tier.set(_active_agent_tier.get())
        try:
            agent_rows = {}
            for agent in agents:
                chain = self.get_agent_chain(agent, "depth")
                source = _active_chain_source.get() or "task_chain"
                keys = [reverse.get(m) for m in chain]
                agent_rows[agent] = {
                    "chain": list(chain),
                    "chain_keys": keys if all(keys) else None,
                    "source": source,
                }
        finally:
            # (b''): tier da chain_source gibi yutulur — snapshot 18 ajanı
            # resolve eder; son yazanın tier'ı çağrıcı context'ine SIZMAMALI.
            _active_agent_tier.reset(tier_token)
            _active_chain_source.reset(token)

        try:
            from agent_core.services import final_routing_policy as pol

            routes = {
                key: {"tier": spec.tier, "in": spec.input_per_million_usd, "out": spec.output_per_million_usd}
                for key, spec in pol.ROUTES.items()
            }
            free_ids = {spec.model for spec in pol.ROUTES.values() if spec.tier == "free"}
        except Exception:
            routes, free_ids = {}, set()

        return {
            "schema_version": 1,
            "registry": dict(self.MODEL_REGISTRY),
            "agents": agent_rows,
            "routes": routes,
            "tiers": tiers,
            "tier_violations": self._snapshot_tier_violations(agent_rows, tiers, free_ids),
        }

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_agent_tiers() -> dict[str, Any]:
        """agent_tiers.json intent tablosu (yoksa/bozuksa {} — snapshot çökmez).

        ⚡ Bolt: Cached parsed static configuration file to prevent blocking the
        event loop with synchronous file I/O operations on every call.
        """
        override = os.getenv("PINEAL_AGENT_TIERS_PATH", "").strip()
        path = Path(override) if override else Path(__file__).resolve().parent.parent.parent / "config" / "agent_tiers.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeDecodeError):
            return {}
        tiers = data.get("tiers") if isinstance(data, dict) else None
        return tiers if isinstance(tiers, dict) else {}

    @staticmethod
    def _snapshot_tier_violations(
        agent_rows: dict[str, dict[str, Any]], tiers: dict[str, Any], free_ids: set[str]
    ) -> list[dict[str, str]]:
        """Tier intent vs çözünmüş zincir — v1 sezgiseller (bilgilendirme, CI kırmaz)."""
        FRONTIER_KEYS = {"claude_sonnet_5", "deepseek_v4_pro", "grok_4_6"}
        out: list[dict[str, str]] = []
        for agent, row in agent_rows.items():
            entry = tiers.get(agent)
            if not isinstance(entry, dict) or entry.get("tier") not in _AGENT_TIER_VALUES:
                out.append({"agent": agent, "rule": "untiered", "detail": "tiers dosyasında karşılığı yok"})
                continue
            tier, chain, keys = entry["tier"], row["chain"], row["chain_keys"] or []
            if tier == "simple" and not (set(chain) & set(free_ids)):
                out.append(
                    {"agent": agent, "rule": "simple_without_free", "detail": f"zincirde bedava-rota modeli yok: {chain}"}
                )
            if tier == "vision" and (not chain or chain[0] not in LLMGateway.VISION_MODELS):
                out.append(
                    {"agent": agent, "rule": "vision_first_not_capable", "detail": f"ilk model vision-eligible değil: {chain[:1]}"}
                )
            if tier == "heavy" and not (set(keys) & FRONTIER_KEYS):
                out.append(
                    {"agent": agent, "rule": "heavy_without_frontier", "detail": f"zincirde frontier (claude/pro/grok) yok: {chain}"}
                )
        return out

    def __init__(self):
        # BOSS-1: tek sözleşme — NINEROUTER_* > PINEAL_LLM_* > OPENROUTER_*
        self.openrouter_base_url, self.api_key, self.transport_provider = resolve_legacy_endpoint()
        self.local_base_url = self.LOCAL_DEFAULT_URL
        self.local_model = self.LOCAL_DEFAULT_MODEL
        self.request_timeout_seconds = min(
            45.0,
            max(0.1, self._env_float("LLM_REQUEST_TIMEOUT_SECONDS", 45.0)),
        )
        self.use_local = os.getenv("USE_LOCAL_LLM", "false").lower() == "true"
        self.client = None
        self.local_client = None
        self._routed_clients: dict[tuple[str, str, str], Any] = {}
        self.failure_count = 0
        self.circuit_open = False
        self.circuit_opened_at = 0.0
        self.live_unlocked = False
        self.total_cost = 0.0
        # P2-MALİYET: kümülatif harcama ve sert üst limit
        self.spend_usd = 0.0
        self.spend_cap_usd = self._env_float("OPENROUTER_MAX_SPEND_USD", 0.0)
        self.max_output_tokens = max(1, int(self._env_float("OPENROUTER_MAX_OUTPUT_TOKENS", 4096)))
        self.image_token_reserve = max(0, int(self._env_float("OPENROUTER_IMAGE_TOKEN_RESERVE", 8192)))
        self._budget_lock = threading.Lock()
        self._reserved_spend_usd = 0.0
        self._budget_reservations: dict[str, float] = {}
        # MP-ROUTING: agent-path provider quota pre-checks (lazy, policy-backed)
        self._agent_governor = None
        # (b'') FAZ-1: tier-gate denetim izi (bounded; FAZ-2-ENFORCE kararları
        # FAZ-1'de UYGULANMAZ, yalnız yazılır). Okuma: tier_audit_trail().
        self._tier_audit_trail: list[dict[str, Any]] = []
        # FAZ 3: oda-ornekli saglayici anahtarlari (vault -> bellek). Ayni
        # saglayicinin env anahtarini ezer (oda izolasyonu; api_key ile ayni
        # sozlesme). Degerler HICBIR zaman loglanmaz/telemetriye yazilmaz.
        self._provider_keys: dict[str, str] = {}
        # ROUTING-HARDENING: kisa omurlu saglayici-saglik devresi. Tek kacak
        # veri yapi DEGIL: yalniz GEICICI tasima hatalari sayilir (policy
        # redleri sayilmaz), sure dolunca kendiliginden sifirlanir, cap'li
        # anahtar sayisi = bilinen provider'lar. Env: PINEAL_PROVIDER_...
        self._provider_fail_streak: dict[str, int] = {}
        self._provider_block_until: dict[str, float] = {}
        # RTK: RAM-cached singleton policy
        self._rtk_policy_cache: dict[str, Any] | None = None
        # [017]: PINEAL_ALLOW_UNPRICED_MODELS=1 ile yapılan takipsiz çağrı sayacı
        self.unpriced_calls = 0
        # Bounded diagnostic history. Agent evidence is populated from a
        # task-local LLMCallScope, never by slicing this shared list.
        self.call_log: List[dict[str, Any]] = []
        self._rebuild()
        self.cache = build_cache_from_env()

    @contextmanager
    def capture_calls(self, task_id: Optional[str], agent_id: Optional[str]) -> Iterator[LLMCallScope]:
        """Bind subsequent calls to a task/agent and collect their exact records."""
        scope = LLMCallScope(task_id=task_id, agent_id=agent_id)
        token = _active_call_scope.set(scope)
        try:
            yield scope
        finally:
            _active_call_scope.reset(token)

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _log_call(
        self,
        kind: str,
        model: str,
        provider: str,
        *,
        call_id: Optional[str] = None,
        started_at: Optional[str] = None,
        cache_hit: bool = False,
        attempt: int = 0,
        duration_ms: int = 0,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        cost_usd: float = 0.0,
        error: Optional[str] = None,
        requested_model: Optional[str] = None,
        fallback_reason: Optional[str] = None,
        quota_status: Optional[str] = None,
        extras: Optional[Mapping[str, Any]] = None,
        captured_scope: Optional[LLMCallScope] = None,
    ) -> dict[str, Any]:
        """Append one JSON-serializable record for a logical gateway call.

        The FINAL telemetry contract requires the requested/actual model split
        and the reason for any silent-looking model change. ``model`` remains
        the executed (actual) model for backwards compatibility; consumers of
        the new contract read ``requested_model``/``actual_model``.
        """
        scope = captured_scope or _active_call_scope.get()
        finished_at = self._utc_now()
        record: dict[str, Any] = {
            "call_id": call_id or str(uuid.uuid4()),
            "task_id": scope.task_id if scope else None,
            "agent_id": scope.agent_id if scope else None,
            "kind": kind,
            "model": model,
            "requested_model": requested_model if requested_model is not None else model,
            "actual_model": model,
            "provider": provider,
            "attempt": attempt,
            # Compatibility for existing telemetry consumers; ``attempt`` is
            # the canonical production contract field.
            "attempts": attempt,
            "cache_hit": cache_hit,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": float(cost_usd),
            "started_at": started_at or finished_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "fallback_reason": fallback_reason,
            "quota_status": quota_status,
            "error": error,
            # Compatibility alias retained while API/UI consumers migrate.
            "at": finished_at,
        }
        chain_source = _active_chain_source.get()
        if chain_source:
            record["chain_source"] = chain_source
        # (b''): kararlarda kullanılan tier her çağrı kaydına yazılır (stale
        # olursa GÖRÜNÜR olur). Değer yoksa (ajan dışı çağrı) alan hiç yazılmaz.
        agent_tier = _active_agent_tier.get()
        if agent_tier:
            record["agent_tier"] = agent_tier
        if extras:
            record.update({k: v for k, v in extras.items() if v is not None})
        self.call_log.append(record)
        if len(self.call_log) > 500:
            del self.call_log[: len(self.call_log) - 500]
        if scope is not None:
            scope.records.append(record.copy())
        return record

    def annotate_call(self, call_id: str, **fields: Any) -> None:
        """Merge bounded telemetry fields into every record of one logical call."""
        allowed = {"requested_model", "actual_model", "fallback_reason", "quota_status"}
        updates = {key: value for key, value in fields.items() if key in allowed and value is not None}
        if not updates:
            return
        for record in self.call_log:
            if record.get("call_id") == call_id:
                record.update(updates)
        scope = _active_call_scope.get()
        if scope is not None:
            for record in scope.records:
                if record.get("call_id") == call_id:
                    record.update(updates)

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, str(default)))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _usage_tokens(usage: Any) -> Optional[tuple[int, int]]:
        """Return trustworthy token counts, rejecting missing or malformed usage."""
        if usage is None:
            return None
        missing = object()
        prompt_tokens = getattr(usage, "prompt_tokens", missing)
        completion_tokens = getattr(usage, "completion_tokens", missing)
        if (
            prompt_tokens is missing
            or completion_tokens is missing
            or not isinstance(prompt_tokens, int)
            or not isinstance(completion_tokens, int)
            or isinstance(prompt_tokens, bool)
            or isinstance(completion_tokens, bool)
        ):
            return None
        if prompt_tokens < 0 or completion_tokens < 0:
            return None
        total_tokens = getattr(usage, "total_tokens", missing)
        if total_tokens is not missing:
            fields_set = getattr(usage, "model_fields_set", None)
            total_was_explicit = fields_set is None or "total_tokens" in fields_set
            if not total_was_explicit and (total_tokens is None or total_tokens == 0):
                total_tokens = missing
            if total_tokens is not missing and (
                not isinstance(total_tokens, int)
                or isinstance(total_tokens, bool)
                or total_tokens <= 0
            ):
                return None
        if prompt_tokens + completion_tokens <= 0:
            return None
        return prompt_tokens, completion_tokens

    def _usage_cost(
        self,
        model: str,
        usage: Any,
        pricing: Optional[Mapping[str, float]] = None,
    ) -> float:
        """Return observed provider cost from token usage without mutating state."""
        import logging
        tokens = self._usage_tokens(usage)
        if tokens is None:
            return 0.0
        rates = pricing or self.MODEL_PRICING.get(model)
        if rates is None:
            logging.warning("SPEND: fiyati bilinmeyen model, harcama takip edilemiyor: %s", model)
            return 0.0
        prompt_tokens, completion_tokens = tokens
        return (
            prompt_tokens * rates["in"] + completion_tokens * rates["out"]
        ) / 1_000_000.0

    def _account_spend(self, model: str, usage: Any) -> float:
        """Account observed usage atomically (compatibility entry point)."""
        cost = self._usage_cost(model, usage)
        with self._budget_lock:
            self.spend_usd += cost
            self.total_cost += cost
        return cost

    def _maximum_call_cost(
        self,
        model: str,
        prompt: str,
        system_prompt: Optional[str],
        images: Optional[List[str]],
        pricing: Optional[Mapping[str, float]] = None,
    ) -> float:
        """Conservative reservation based on bounded output and UTF-8 input bytes."""
        rates = pricing or self.MODEL_PRICING[model]
        # A tokenizer cannot consume more tokens than the encoded input bytes;
        # reserve extra message framing and a configurable image allowance.
        prompt_bytes = len(prompt.encode("utf-8")) + len((system_prompt or "").encode("utf-8"))
        prompt_tokens = prompt_bytes + 64 + self.image_token_reserve * len(images or [])
        return (
            prompt_tokens * rates["in"] + self.max_output_tokens * rates["out"]
        ) / 1_000_000.0

    def _maximum_chat_cost(
        self,
        model: str,
        request_payload: dict[str, Any],
        max_tokens: int,
        pricing: Optional[Mapping[str, float]] = None,
    ) -> float:
        """Conservatively reserve a structured chat request before dispatch."""
        rates = pricing or self.MODEL_PRICING[model]
        encoded = json.dumps(
            request_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        image_parts = 0
        for message in request_payload.get("messages", []):
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, list):
                image_parts += sum(isinstance(part, dict) and part.get("type") == "image_url" for part in content)
        prompt_tokens = len(encoded) + 64 + self.image_token_reserve * image_parts
        return (prompt_tokens * rates["in"] + max_tokens * rates["out"]) / 1_000_000.0

    def _reserve_budget(self, call_id: str, amount: float) -> None:
        """Atomically reserve worst-case cost before any paid provider call."""
        with self._budget_lock:
            projected = self.spend_usd + self._reserved_spend_usd + amount
            if self.spend_cap_usd > 0 and projected > self.spend_cap_usd:
                raise SpendCapExceeded(self._cap_message_locked(projected=projected))
            self._budget_reservations[call_id] = amount
            self._reserved_spend_usd += amount

    def _release_budget(self, call_id: str) -> None:
        """Release a reservation after failure, rejection, or cancellation."""
        with self._budget_lock:
            amount = self._budget_reservations.pop(call_id, 0.0)
            self._reserved_spend_usd = max(0.0, self._reserved_spend_usd - amount)

    def _settle_budget(
        self,
        call_id: str,
        model: str,
        usage: Any,
        pricing: Optional[Mapping[str, float]] = None,
    ) -> float:
        """Replace a reservation with observed or conservative accounted cost."""
        usage_is_trustworthy = self._usage_tokens(usage) is not None
        observed_cost = self._usage_cost(model, usage, pricing)
        with self._budget_lock:
            reserved = self._budget_reservations.pop(call_id, 0.0)
            self._reserved_spend_usd = max(0.0, self._reserved_spend_usd - reserved)
            # A paid response without trustworthy usage must not erase its spend
            # reservation and silently reopen capacity under the hard cap.
            cost = reserved if reserved > 0 and not usage_is_trustworthy else observed_cost
            if reserved > 0 and not usage_is_trustworthy:
                import logging

                logging.warning(
                    "Provider returned missing or invalid usage; retaining full "
                    "reserved cost as spend"
                )
            self.spend_usd += cost
            self.total_cost += cost
        return cost

    def _cap_exceeded(self) -> bool:
        if self.spend_cap_usd <= 0:
            return False
        with self._budget_lock:
            return self.spend_usd + self._reserved_spend_usd >= self.spend_cap_usd

    def _cap_message_locked(self, *, projected: Optional[float] = None) -> str:
        committed = self.spend_usd
        reserved = self._reserved_spend_usd
        value = projected if projected is not None else committed + reserved
        return (
            f"OPENROUTER_SPEND_CAP_EXCEEDED: committed=${committed:.6f}, "
            f"reserved=${reserved:.6f}, projected=${value:.6f}, "
            f"cap=${self.spend_cap_usd:.6f} (OPENROUTER_MAX_SPEND_USD)."
        )

    def _cap_message(self) -> str:
        with self._budget_lock:
            return self._cap_message_locked()

    def budget_status(self) -> dict[str, float | int]:
        """Return an atomic telemetry snapshot of committed and reserved spend."""
        with self._budget_lock:
            return {
                "spend_usd": self.spend_usd,
                "reserved_usd": self._reserved_spend_usd,
                "cap_usd": self.spend_cap_usd,
                "active_reservations": len(self._budget_reservations),
            }

    def _pricing_guard(
        self,
        model: str,
        *,
        kind: str,
        pricing: Optional[Mapping[str, float]] = None,
    ) -> None:
        """[017] fix: fiyatı bilinmeyen model için ÜCRETLİ canlı çağrı varsayılan
        olarak REDDEDİLİR. Eski davranış yalnızca uyarı loglayıp harcamayı 0
        sayıyordu; bu, bilinmeyen modelle spend cap'in sessiz bypass'ı demekti.

        Açık kabul: PINEAL_ALLOW_UNPRICED_MODELS=1 (takipsiz maliyet bilinçli
        seçimdir; unpriced_calls sayacı gözlemlenebilirlikte raporlanır).
        """
        if pricing is not None or model in self.MODEL_PRICING:
            return
        if os.getenv("PINEAL_ALLOW_UNPRICED_MODELS", "0") == "1":
            self.unpriced_calls += 1
            import logging
            logging.warning(
                "SPEND: fiyatı bilinmeyen modele açıkça izin verildi "
                "(PINEAL_ALLOW_UNPRICED_MODELS=1): %s", model,
            )
            return
        msg = (
            f"UNKNOWN_PRICING: '{model}' için fiyat kaydı yok; harcama takip edilemez "
            "ve spend cap bypass edilemez. MODEL_PRICING'e fiyat ekleyin veya "
            "PINEAL_ALLOW_UNPRICED_MODELS=1 ile takipsiz maliyeti açıkça kabul edin."
        )
        raise RuntimeError(msg)

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        """[018] fix: retry yalnızca GEÇİCİ hata sınıflarına uygulanır.

        Retryable:   timeout, bağlantı hatası/reset, 408, 429, 5xx
        Non-retryable: 400/401/403/404/422, geçersiz istek, model yok,
                     bağlam limiti, spend cap (ayrı ele alınır)
        Bilinmeyen durumlar mevcut davranışı (retry) korur.
        """
        try:
            from openai import APIConnectionError, APITimeoutError
            if isinstance(exc, (APITimeoutError, APIConnectionError)):
                return True
        except Exception as exc:
            logger.warning(
                "[_is_retryable_error] beklenmeyen hata (Exception) yutulmadı — iz bırakıldı: %s", exc, exc_info=True
            )

        err = str(exc).lower()
        if "in_flight" in err or "in-flight" in err:
            return True

        status = getattr(exc, "status_code", None)
        if isinstance(status, int):
            return status in (408, 429) or 500 <= status < 600

        if any(m in err for m in (
            "timeout", "timed out", "connection", "connect", "refused",
            "reset", "10061", "429", "rate limit", "rate_limit",
            "502", "503", "504", "internal server error",
        )):
            return True
        if any(m in err for m in (
            "400", "403", "404", "422", "invalid_request", "invalid request",
            "model_not_found", "context_length", "unauthorized", "invalid_api_key",
        )):
            return False
        return True

    @staticmethod
    def _is_strict_retryable_error(exc: Exception) -> bool:
        """Retry only errors known to be transient on new gateway surfaces."""
        try:
            from openai import APIConnectionError, APITimeoutError

            if isinstance(exc, (APITimeoutError, APIConnectionError)):
                return True
        except Exception as exc:
            logger.warning(
                "[_is_strict_retryable_error] beklenmeyen hata (Exception) yutulmadı — iz bırakıldı: %s", exc, exc_info=True
            )
        if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
            return True
        status = getattr(exc, "status_code", None)
        return isinstance(status, int) and (status in (408, 429) or 500 <= status < 600)

    @staticmethod
    def _model_substitution_allowed(requested: str, actual: str) -> bool:
        from agent_core.services.final_routing_policy import model_substitution_allowed

        return model_substitution_allowed(requested, actual)

    def _annotate_most_recent(self, model: str, **fields: Any) -> None:
        """Annotate the latest failed record for ``model`` (best-effort)."""
        allowed = {"fallback_reason", "quota_status"}
        updates = {key: value for key, value in fields.items() if key in allowed and value is not None}
        if not updates:
            return
        for record in reversed(self.call_log):
            if record.get("model") == model and record.get("error"):
                record.update(updates)
                return

    def set_key(self, key: str, unlock_live: bool = False):
        self.api_key = key
        if unlock_live:
            self.live_unlocked = True
        self.failure_count = 0
        self.circuit_open = False
        self.circuit_opened_at = 0.0
        self._rebuild()

    def set_provider_key(self, provider_id: str, key: str) -> None:
        """FAZ 3: oda-ornekli dogrudan-saglayici anahtari (vault -> bellek).

        env'deki ayni saglayici anahtarini ezer. Bilinmeyen provider_id ->
        ValueError (sessiz yutma yok; cagiran loglar). Bos key -> kayit
        silinir (env'ye geri donulur).
        """
        pid = (provider_id or "").strip().lower()
        if pid not in _KNOWN_PROVIDER_KEY_IDS:
            raise ValueError(f"unknown provider_id for direct key: {provider_id!r}")
        if key and key.strip():
            self._provider_keys[pid] = key.strip()
        else:
            self._provider_keys.pop(pid, None)

    def clear_provider_key(self, provider_id: str) -> None:
        """FAZ 3: oda anahtarini sil (env'ye geri donulur)."""
        self._provider_keys.pop((provider_id or "").strip().lower(), None)

    def _provider_api_key(self, provider_id: str, key_env: str) -> str:
        """FAZ 3: anahtar cozumleme — once oda (vault), sonra env."""
        inst = self._provider_keys.get(provider_id, "").strip()
        if inst:
            return inst
        return os.getenv(key_env, "").strip()

    def _provider_key_source(self, provider_id: str, key_env: str) -> str:
        """FAZ 3: tani icin anahtar kaynagi (deger ASLA dondurulmez)."""
        if self._provider_keys.get(provider_id, "").strip():
            return "instance"
        if os.getenv(key_env, "").strip():
            return "env"
        return "none"

    def set_local_config(self, base_url: str = None, model_name: str = None, active: bool = True):
        if base_url:
            self.local_base_url = base_url
        if model_name:
            self.local_model = model_name
        self.use_local = active
        self._rebuild()

    def _rebuild(self):
        if self.api_key:
            default_headers = {"X-9Router-Token-Saver": "off"} if "20128" in self.openrouter_base_url else None
            self.client = AsyncOpenAI(
                base_url=self.openrouter_base_url,
                api_key=self.api_key,
                default_headers=default_headers,
                max_retries=0,
            )
        # Local client (Ollama/LM Studio/vLLM)
        try:
            self.local_client = AsyncOpenAI(
                base_url=self.local_base_url,
                api_key="ollama",
                max_retries=0,
            )
        except Exception:
            self.local_client = None

    def _quota_governor(self):
        if self._agent_governor is None:
            from agent_core.services.quota_governor import QuotaGovernor

            self._agent_governor = QuotaGovernor.from_policy()
        return self._agent_governor

    def _record_route_attempt(self, route: GatewayRoute, response: Any = None, *, success: bool) -> None:
        """Keep the agent-path quota governor aware of routed transports."""
        try:
            governor = self._quota_governor()
            usage = getattr(response, "usage", None) if response is not None else None
            # Provider-agrega pencere ("*"): status(provider) ayni kabi okur;
            # per-model pencere provider seviyesindeki merdiven skip'inde gorunmez.
            if success:
                governor.record_success(
                    route.provider_id,
                    "*",
                    prompt_tokens=(
                        int(getattr(usage, "prompt_tokens", 0) or 0) if usage is not None else None
                    ),
                    completion_tokens=(
                        int(getattr(usage, "completion_tokens", 0) or 0) if usage is not None else None
                    ),
                )
            else:
                governor.record_failure(route.provider_id, "*")
        except Exception as exc:
            logger.warning(
                "[_record_route_attempt] beklenmeyen hata (Exception) yutulmadı — iz bırakıldı: %s", exc, exc_info=True
            )

    def _route_cooldown_remaining(self, provider_id: str) -> float:
        return max(0.0, self._provider_block_until.get(provider_id, 0.0) - time.monotonic())

    def _note_route_health(self, provider_id: str, *, ok: bool) -> None:
        if ok:
            self._provider_fail_streak.pop(provider_id, None)
            self._provider_block_until.pop(provider_id, None)
            return
        try:
            threshold = max(1, int(os.getenv("PINEAL_PROVIDER_FAILURE_THRESHOLD", "3")))
            cooldown = max(1, int(os.getenv("PINEAL_PROVIDER_COOLDOWN_SECONDS", "60")))
        except ValueError:
            threshold, cooldown = 3, 60
        streak = self._provider_fail_streak.get(provider_id, 0) + 1
        if streak >= threshold:
            self._provider_fail_streak[provider_id] = 0
            self._provider_block_until[provider_id] = time.monotonic() + cooldown
        else:
            self._provider_fail_streak[provider_id] = streak

    def provider_health(self) -> dict[str, float]:
        """Read-only: kalan cooldown saniyeleri (Aspasia denetim satirlari icin)."""
        return {p: round(r, 1) for p, r in
                ((p, self._route_cooldown_remaining(p)) for p in list(self._provider_block_until))
                if r > 0}

    @staticmethod
    def _tier_route_decision(
        tier: Optional[str],
        *,
        free: bool,
        discounted: bool,
        escalation_enabled: bool,
    ) -> dict[str, Any]:
        """(b'') FAZ-2-ENFORCE semantiğinde TEK rota kararı (saf, uygulanmaz).

        FAZ-1 DENETİM bu kararı izine yazar; FAZ-2 filtresi aynı kararı
        uygular. Kurallar: simple -> yalnız free; heavy/vision/verify/unknown
        -> free ve indirimli izin (liste-fiyat ödemek için escalation gerekir);
        unknown tier -> heavy-eşdeğeri + ``tier_unresolved`` işareti.
        """
        unresolved = tier == "unknown"
        family = tier if tier in _AGENT_TIER_VALUES else "unknown"
        if family != "simple":
            family = "heavy"  # vision/verify/heavy/unknown: heavy ailesi
        if free:
            return {
                "decision": "allow", "reason": "free_transport", "would_deny": False,
                "tier_unresolved": unresolved, "price_class": "free",
            }
        if family == "simple":
            return {
                "decision": "would_deny", "reason": "simple_non_free", "would_deny": True,
                "tier_unresolved": unresolved,
                "price_class": "discounted" if discounted else "list",
            }
        if discounted:
            return {
                "decision": "allow", "reason": "heavy_discounted", "would_deny": False,
                "tier_unresolved": unresolved, "price_class": "discounted",
            }
        if escalation_enabled:
            return {
                "decision": "allow", "reason": "heavy_listed_escalated", "would_deny": False,
                "tier_unresolved": unresolved, "price_class": "list",
            }
        return {
            "decision": "would_deny", "reason": "heavy_listed_gate", "would_deny": True,
            "tier_unresolved": unresolved, "price_class": "list",
        }

    @staticmethod
    def _tier_variant_sort_key(
        tier: Optional[str], *, is_legacy_or: bool, price_sum: float
    ) -> tuple[float | int, ...]:
        """(b'') FAZ-2 sıralama mekanizması (FAZ-1'de kilitlenir, UYGULANMAZ).

        vision: doğrudan taşımalar OpenRouter legacy'den ÖNCE (fiyat
        eşitliğini beklemeden) — direct-first. Diğer tier'lar/None: bugünkü
        maliyet merdiveni birebir korunur (fiyat, sonra legacy-ayraç).
        """
        if tier == "vision":
            return (1 if is_legacy_or else 0, price_sum)
        return (price_sum, 1 if is_legacy_or else 0)

    def _cheaper_direct_available(self, model: str) -> bool:
        """(FAZ-2.1) OR-legacy liste-fiyat kapatma kapısı.

        True: model için ``final_routing_policy.ROUTES`` içinde İNDİRİMLİ bir
        direct spec var (liste fiyatı < listelenen fiyat), o provider'ın
        anahtarı kurulu ve provider cooldown'da değil -> daha ucuz kanal
        MEVCUT; OR-legacy (liste fiyatı) bu durumda escalation ister.
        False: daha ucuz kanal yok (yalnız-kanal) -> legacy koşulsuz kalır.
        """
        from agent_core.services import final_routing_policy as pol

        for spec in pol.ROUTES.values():
            if not (spec.model == model or model.endswith(f"/{spec.model}")):
                continue
            if spec.list_input_per_million_usd is None:
                continue
            if not (
                spec.input_per_million_usd
                < spec.list_input_per_million_usd
            ):
                continue
            for provider_id, key_env in _AGENT_DIRECT_PROVIDER_KEYS:
                if spec.provider != provider_id:
                    continue
                if not self._provider_api_key(provider_id, key_env):
                    continue
                if self._route_cooldown_remaining(provider_id) > 0:
                    continue
                return True
        return False

    def agent_route_variants(self, model: str,
                              required: frozenset[str] = frozenset()) -> "list[Optional[GatewayRoute]]":
        """MP-ROUTING: cost ladder for ONE chain model across providers.

        Returns ordered transports for ``model``: direct-provider routes whose
        credentials exist, whose model the catalog actually serves, and which
        pass the FINAL policy gates (MODEL@PROVIDER must not be unknown-paid
        unless PINEAL_ALLOW_PAID_ESCALATION=1; exhausted quotas are skipped),
        followed by the legacy OpenRouter transport (``None``). Sorted by
        effective cost: free → cheap → priced → (OpenRouter at its own price).
        With no direct credentials configured this returns ``[None]``, so the
        default production behavior is byte-for-byte the legacy path.
        """
        from types import SimpleNamespace
        from agent_core.services import final_routing_policy as pol

        def _price_sum(pricing: "Optional[dict[str, float]]") -> float:
            if not pricing:
                return float("inf")
            return float(pricing.get("in") or 0.0) + float(pricing.get("out") or 0.0)

        # 9Router kombo rotaları doğrudan 9Router hub'ı üzerinden çalışır
        if model.startswith("pineal-"):
            return [None]

        # (b''): tier contextvar'ı — agent_route_variants OKUR. None ise
        # (ajan bağlamı yok) mekanizma tümüyle devre dışı: bugünkü davranış,
        # denetim izi YOK. Set: get_agent_chain (bu dosya dışından da).
        tier = _active_agent_tier.get()

        variants: list = []
        # (b'') FAZ-2: simple-tier ENFORCE bir taşımayı reddedip merdiven boş
        # kalırsa [] DÖNER — `or [None]` yedeği DENY'i sessizce bypass etmemeli
        # (enforce-bypass yasağı; mühür kriteri 4).
        tier_denied_transport = False
        has_or_transport = self.client is not None or self.use_local
        if has_or_transport:
            legacy_denied = False
            if tier is not None:
                # (b'') OR-legacy liste-fiyat kapatması (FAZ-2.1, komutan emri
                # 2026-09-08): audit kararı (would_deny) ile ENFORCE filtresi
                # aynı satırdan döner.
                #   simple        -> non-free legacy teklif EDİLMEZ (FAZ-2).
                #   heavy ailesi  -> modelin DAHA UCUZ indirimli direct kanalı
                #     KURULUYSA (anahtar + ROUTES indirim spec'i) liste fiyatı
                #     legacy yalnız PINEAL_ALLOW_PAID_ESCALATION=1 ile teklif
                #     edilir; daha ucuz kanal YOKSA (yalnız-kanal, örn. gemini
                #     OR-legacy tek taşıma) legacy koşulsuz kalır — kestirme
                #     kapatma heavy/vision ajanlarını kırmaz (only_channel).
                free_legacy = pol.is_free(model)
                if free_legacy:
                    gate_context = "free"
                elif tier == "simple":
                    gate_context = "simple_non_free"
                elif self._cheaper_direct_available(model):
                    gate_context = "cheaper_direct_available"
                else:
                    gate_context = "only_channel"
                decision = self._tier_route_decision(
                    tier, free=free_legacy, discounted=False,
                    escalation_enabled=(
                        pol.paid_escalation_enabled()
                        or gate_context == "only_channel"
                    ),
                )
                decision["gate_context"] = gate_context
                self._record_tier_decision(
                    tier=tier, model=model, provider=self.transport_provider, legacy=True,
                    decision=decision,
                )
                legacy_denied = bool(decision["would_deny"])
            if legacy_denied:
                tier_denied_transport = True
            else:
                variants.append((_price_sum(self.MODEL_PRICING.get(model)), 1, None))
        try:
            from agent_core.services.provider_manager import (
                ProviderProtocol,
                QuotaStatus,
                load_builtin_catalog,
            )

            catalog = load_builtin_catalog()
        except Exception:
            if not variants and tier_denied_transport:
                return []  # ENFORCE: deny'i `[None]` yedeği bypass etmez
            return [item[2] for item in variants] or [None]

        for provider_id, key_env in _AGENT_DIRECT_PROVIDER_KEYS:
            api_key = self._provider_api_key(provider_id, key_env)
            if not api_key:
                continue
            # ROUTING-HARDENING: gecici-tasima-hatasi devresi — ardisik transient
            # hatali provider kisa sureligine merdivenden duser; sure kendiligin-
            # den dolar. POLICY REDETLERI SAYILMAZ (yalniz transport hatasi).
            if self._route_cooldown_remaining(provider_id) > 0:
                continue
            try:
                provider = catalog.get_provider(provider_id)
            except Exception:
                continue
            if provider.protocol is not ProviderProtocol.OPENAI_CHAT or not provider.base_url:
                continue
            matched = None
            for candidate in provider.models:
                if not getattr(candidate, "enabled", True):
                    continue
                if candidate.id == model or model.endswith(f"/{candidate.id}"):
                    matched = candidate
                    break
            if matched is None:
                # FAZ 3: katalogda eslesme yoksa operator beyanina bakilir
                # (PINEAL_PROVIDER_MODELS_*). Beyan, eslesme kurali disinda
                # HICBIR kapiyi atlamaz (firewall/cap/kota aynen gecerli).
                for attested_id in _attested_provider_models(provider_id):
                    if attested_id == model or model.endswith(f"/{attested_id}"):
                        matched = SimpleNamespace(id=attested_id, pricing=None)
                        break
            if matched is None:
                continue
            # MODEL@PROVIDER kimliği: policy kataloğu fiyatın gerçek kaynağı;
            # katalogda listelenmemiş/ücretli rota fail-closed escalation ister.
            # (b'') FAZ-2 (sahip Q1 kararı): aynı _tier_route_decision UYGULANIR.
            # - simple: free-only ENFORCE — would_deny rota teklif edilmez.
            # - heavy ailesi (heavy/vision/verify/unknown): İNDİRİMLİ direct
            #   kanala escalation env'siz izin (relax); liste-fiyat/frontier
            #   direct bugünkü firewall kapısından geçer (değişmedi).
            # - Denetim izi (tier_audit_trail) her karar için yazılmaya devam eder.
            spec_pre = pol.ROUTES.get(f"{matched.id}@{provider_id}")
            enforce_skip = False
            if tier is not None:
                if spec_pre is not None:
                    route_free = spec_pre.is_free()
                    route_discounted = bool(
                        spec_pre.list_input_per_million_usd is not None
                        and spec_pre.input_per_million_usd
                        < spec_pre.list_input_per_million_usd
                    )
                else:
                    # Katalogda eşleşen ama ROUTES'u olmayan rota: fail-closed
                    # paid kabul edilir (indirim bilgisi yok -> discounted=False).
                    route_free = pol.is_free(matched.id, provider_id)
                    route_discounted = False
                decision = self._tier_route_decision(
                    tier, free=route_free, discounted=route_discounted,
                    escalation_enabled=pol.paid_escalation_enabled(),
                )
                self._record_tier_decision(
                    tier=tier, model=matched.id, provider=provider_id,
                    legacy=False, decision=decision,
                )
                if tier == "simple" and decision["would_deny"]:
                    enforce_skip = True
            if enforce_skip:
                tier_denied_transport = True
                continue  # ENFORCE: simple -> yalnız free (sahip Q1)
            if pol.is_paid(matched.id, provider_id) and not pol.paid_escalation_enabled():
                # FAZ-2 relax (sahip Q1): heavy ailesinin İNDİRİMLİ direct
                # kanalı escalation env'siz çalışır; liste fiyatı/frontier
                # rota firewall'da kalmaya devam eder.
                discounted_channel = bool(
                    tier not in (None, "simple")
                    and spec_pre is not None
                    and spec_pre.list_input_per_million_usd is not None
                    and spec_pre.input_per_million_usd
                    < spec_pre.list_input_per_million_usd
                )
                if not discounted_channel:
                    continue
            pricing: "Optional[dict[str, float]]" = None
            list_pricing: "Optional[dict[str, float]]" = None
            spec = pol.ROUTES.get(f"{matched.id}@{provider_id}")
            if (spec is not None and required
                    and not required.issubset(spec.capabilities)):
                # ROUTING-HARDENING: gorev/ajan kapasite gereksinimi (orn. tools,
                # vision) route'un ROUTES.capabilities beyaniyla DOGRULANIR;
                # beyan yetersizse rota teklif edilmez (gorev sonradan kirilmasin).
                continue
            if spec is not None:
                pricing = {
                    "in": spec.input_per_million_usd,
                    "out": spec.output_per_million_usd,
                }
                if spec.list_input_per_million_usd is not None:
                    list_pricing = {
                        "in": spec.list_input_per_million_usd,
                        "out": spec.list_output_per_million_usd,
                    }
            elif getattr(matched, "pricing", None) is not None and matched.pricing.known:
                pricing = {
                    "in": matched.pricing.input_per_million_usd,
                    "out": matched.pricing.output_per_million_usd,
                }
            if pricing is None and self.spend_cap_usd > 0:
                continue  # capsiz cüzdan: fiyatı izlenemeyen rota teklif edilmez
            try:
                st = self._quota_governor().status(provider_id)
                # governor.status() dogrudan enum donerir; .status attribute
                # tasiyen snapshot turleriyle de uyumlu kalir.
                if getattr(st, "status", st) is QuotaStatus.EXHAUSTED:
                    continue
            except Exception as exc:
                logger.warning(
                    "[agent_route_variants] beklenmeyen hata (Exception) yutulmadı — iz bırakıldı: %s", exc, exc_info=True
                )
            variants.append((
                _price_sum(pricing),
                0,
                GatewayRoute(
                    connection_id=f"agent-{provider_id}",
                    provider_id=provider_id,
                    model=matched.id,
                    base_url=str(provider.base_url).rstrip("/"),
                    api_key=api_key,
                    input_per_million_usd=None if pricing is None else pricing["in"],
                    output_per_million_usd=None if pricing is None else pricing["out"],
                    list_input_per_million_usd=None if list_pricing is None else list_pricing["in"],
                    list_output_per_million_usd=None if list_pricing is None else list_pricing["out"],
                ),
            ))
        variants.sort(key=lambda item: (item[0], item[1]))
        if not variants and tier_denied_transport:
            # (b'') FAZ-2: ENFORCE (simple free-only) TÜM taşımaları reddetti —
            # BOŞ merdiven döner; `or [None]` yedeği deny'i sessizce bypass
            # etmemeli (zincir bu modeli atlar, tüm modeler reddedilirse
            # zincir tükenir -> hata görünür olur, sessiz liste-fiyat kaçağı yok).
            return []
        return [item[2] for item in variants] or [None]

    def _record_tier_decision(
        self,
        *,
        tier: Optional[str],
        model: str,
        provider: str,
        legacy: bool,
        decision: dict[str, Any],
    ) -> None:
        """(b'') Sınırlı denetim izine tek FAZ-2 kararı yazar (davranışı değiştirmez)."""
        entry: dict[str, Any] = {
            "tier": tier,
            "model": model,
            "route_key": f"{model}@openrouter" if legacy else f"{model}@{provider}",
            "provider": (self.transport_provider if legacy else provider),
            "decision": decision["decision"],
            "reason": decision["reason"],
            "would_deny": bool(decision.get("would_deny")),
            "tier_unresolved": bool(decision.get("tier_unresolved")),
            "price_class": decision.get("price_class"),
            "gate_context": decision.get("gate_context"),
        }
        agent_hint = _active_agent_hint.get()
        if agent_hint:
            entry["agent"] = agent_hint
        self._tier_audit_trail.append(entry)
        if len(self._tier_audit_trail) > 500:
            del self._tier_audit_trail[: len(self._tier_audit_trail) - 500]

    def tier_audit_trail(self, *, limit: Optional[int] = None) -> list[dict[str, Any]]:
        """(b'') Salt-okunur denetim izi: her rota için FAZ-2 kararı + tier.

        FAZ-1'de kararlar UYGULANMAZ (üretim yolu değişmez); iz, FAZ-2'nin
        neleri engelleyeceğini önden görünür kılar. Sıra: kayıt sırası.
        """
        rows = list(self._tier_audit_trail)
        return rows[-limit:] if limit else rows

    def route_diagnostics(self, model: str, required: frozenset[str] = frozenset()) -> dict[str, Any]:
        """FAZ 3: model icin havuz gorunurlugu (salt-okunur tani).

        agent_route_variants ile AYNI kapi sirasini izler; her saglayici icin
        karar + neden dondurur. Secret DEGER asla icermez (varlik/kaynak
        boolean'lari only). Tutarlilik kilidi: offered kumesi variants ile
        birebir eslesir (tests/unit/test_multi_provider_routing.py).

        Neden kodlari: no_key | cooldown | no_catalog | transport_unsupported |
        model_not_served | paid_firewall | capability | unpriced_with_cap |
        exhausted | offered.
        """
        from agent_core.services import final_routing_policy as pol
        from agent_core.services.provider_manager import ProviderProtocol, QuotaStatus

        try:
            from agent_core.services.provider_manager import load_builtin_catalog
            catalog = load_builtin_catalog()
        except Exception:
            catalog = None

        offered: list[dict[str, Any]] = []
        skipped: dict[str, dict[str, Any]] = {}

        def _key_info(provider_id: str, key_env: str) -> dict[str, Any]:
            source = self._provider_key_source(provider_id, key_env)
            return {"key_present": source != "none", "key_source": source}

        # Legacy tasima (None rota): OpenRouter istemcisi veya yerel model.
        has_or = self.client is not None or self.use_local
        if has_or:
            offered.append({
                "route_key": f"{model}@{self.transport_provider}", "provider": self.transport_provider,
                "model": model, "priced": model in self.MODEL_PRICING,
                "via": self.transport_provider if self.client is not None else "local",
            })
        else:
            skipped[self.transport_provider] = {
                "reason": "no_key",
                **_key_info(
                    self.transport_provider,
                    "NINEROUTER_API_KEY" if self.transport_provider == "9router" else "OPENROUTER_API_KEY",
                ),
            }

        for provider_id, key_env in _AGENT_DIRECT_PROVIDER_KEYS:
            info = _key_info(provider_id, key_env)
            if not info["key_present"]:
                skipped[provider_id] = {"reason": "no_key", **info}
                continue
            if self._route_cooldown_remaining(provider_id) > 0:
                skipped[provider_id] = {"reason": "cooldown", **info}
                continue
            provider = None
            if catalog is not None:
                try:
                    provider = catalog.get_provider(provider_id)
                except Exception:
                    provider = None
            if provider is None:
                skipped[provider_id] = {"reason": "no_catalog", **info}
                continue
            if provider.protocol is not ProviderProtocol.OPENAI_CHAT or not provider.base_url:
                skipped[provider_id] = {"reason": "transport_unsupported", **info}
                continue
            matched_id: Optional[str] = None
            matched_source = "catalog"
            for candidate in provider.models:
                if not getattr(candidate, "enabled", True):
                    continue
                if candidate.id == model or model.endswith(f"/{candidate.id}"):
                    matched_id = candidate.id
                    break
            if matched_id is None:
                for attested_id in _attested_provider_models(provider_id):
                    if attested_id == model or model.endswith(f"/{attested_id}"):
                        matched_id = attested_id
                        matched_source = "attested"
                        break
            if matched_id is None:
                skipped[provider_id] = {"reason": "model_not_served", **info}
                continue
            if pol.is_paid(matched_id, provider_id) and not pol.paid_escalation_enabled():
                skipped[provider_id] = {"reason": "paid_firewall", **info}
                continue
            spec = pol.ROUTES.get(f"{matched_id}@{provider_id}")
            if spec is not None and required and not required.issubset(spec.capabilities):
                skipped[provider_id] = {"reason": "capability", **info}
                continue
            priced = spec is not None
            if not priced:
                for candidate in provider.models:
                    if getattr(candidate, "id", None) == matched_id:
                        cp = getattr(candidate, "pricing", None)
                        priced = cp is not None and bool(getattr(cp, "known", False))
                        break
            if not priced and self.spend_cap_usd > 0:
                skipped[provider_id] = {"reason": "unpriced_with_cap", **info}
                continue
            try:
                st = self._quota_governor().status(provider_id)
                if getattr(st, "status", st) is QuotaStatus.EXHAUSTED:
                    skipped[provider_id] = {"reason": "exhausted", **info}
                    continue
            except Exception as exc:
                logger.warning(
                    "[route_diagnostics] beklenmeyen hata (Exception) yutulmadı — iz bırakıldı: %s", exc, exc_info=True
                )
            offered.append({
                "route_key": f"{matched_id}@{provider_id}", "provider": provider_id,
                "model": matched_id, "priced": priced, "source": matched_source,
            })

        # Tasiyicisiz saglayicilar: yalniz gorunurluk (asla offered degil).
        for provider_id, key_env in _DIAGNOSTIC_ONLY_PROVIDERS:
            skipped[provider_id] = {
                "reason": "transport_unsupported",
                **_key_info(provider_id, key_env),
            }

        return {"model": model, "offered": offered, "skipped": skipped,
                "pool_size": len(offered), "openrouter_offered": has_or}

    def _get_rtk_policy(self) -> dict[str, Any]:
        """RAM-cached singleton okuma — provider_health ile birebir aynı model.
        
        Disk yalnızca ilk çağrıda (lazy) okunur, sonrası RAM'den servis edilir.
        Fail-open: Dosya yoksa/bozuksa _RTK_SAFE_DEFAULT (enabled=False) döner.
        """
        if self._rtk_policy_cache is not None:
            return self._rtk_policy_cache

        policy = {
            "enabled": False,
            "default_level": "conservative",
            "bypass": {"tasks": [], "agents": []},
        }
        try:
            with open(_RTK_POLICY_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            policy = {
                "enabled": bool(loaded.get("enabled", False)),
                "default_level": loaded.get("default_level", "conservative"),
                "bypass": {
                    "tasks": list(loaded.get("bypass", {}).get("tasks", [])),
                    "agents": list(loaded.get("bypass", {}).get("agents", [])),
                },
            }
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            import logging
            logging.warning("RTK_POLICY_LOAD_FAILED: %s; RTK devre dışı (fail-open).", exc)
            self._rtk_policy_cache = dict(_RTK_SAFE_DEFAULT)
            return self._rtk_policy_cache

        env_enabled = os.getenv("PINEAL_RTK_ENABLED")
        if env_enabled is not None:
            policy["enabled"] = env_enabled.strip().lower() in ("1", "true", "yes")

        for env_var, bypass_key in (
            ("PINEAL_RTK_BYPASS_TASKS", "tasks"),
            ("PINEAL_RTK_BYPASS_AGENTS", "agents"),
        ):
            raw = os.getenv(env_var, "")
            if raw.strip():
                extra = {t.strip() for t in raw.split(",") if t.strip()}
                policy["bypass"][bypass_key] = list(set(policy["bypass"][bypass_key]) | extra)

        self._rtk_policy_cache = policy
        return policy

    def should_bypass_rtk(self, *, task: Optional[str] = None, agent_name: Optional[str] = None) -> bool:
        """Task veya agent_name bypass listesindeyse sıkıştırma uygulanmaz."""
        policy = self._get_rtk_policy()
        if not policy.get("enabled", False):
            return True
        if task and task in policy.get("bypass", {}).get("tasks", []):
            return True
        if agent_name and agent_name in policy.get("bypass", {}).get("agents", []):
            return True
        return False

    def _apply_rtk_compression(
        self,
        text: str,
        *,
        task: Optional[str] = None,
        agent_name: Optional[str] = None,
    ) -> str:
        """HTTP çağrısından hemen önce metni sıkıştırır (fail-open)."""
        try:
            if self.should_bypass_rtk(task=task, agent_name=agent_name):
                return text

            policy = self._get_rtk_policy()
            level = CompressionLevel(policy.get("default_level", "conservative"))
            return compress_prompt(text, level)
        except Exception as exc:
            import logging
            logging.warning("RTK_COMPRESSION_FAILED: %s; using uncompressed text (fail-open).", exc)
            return text

    def _compress_chat_messages(
        self,
        messages: List[dict[str, Any]],
        *,
        task: Optional[str] = None,
        agent_name: Optional[str] = None,
    ) -> List[dict[str, Any]]:
        """Yalnızca text içeriğine dokunur, image_url veya diğer part'ları aynen korur."""
        result: List[dict[str, Any]] = []
        for msg in messages:
            new_msg = dict(msg)
            content = new_msg.get("content")

            if isinstance(content, str):
                new_msg["content"] = self._apply_rtk_compression(
                    content, task=task, agent_name=agent_name
                )
            elif isinstance(content, list):
                new_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        new_part = dict(part)
                        new_part["text"] = self._apply_rtk_compression(
                            part.get("text", ""), task=task, agent_name=agent_name
                        )
                        new_parts.append(new_part)
                    else:
                        new_parts.append(part)
                new_msg["content"] = new_parts

            result.append(new_msg)
        return result

    def _client_for_route(self, route: GatewayRoute):
        """Build/cache transport clients without moving network I/O out of the gateway."""
        credential_fingerprint = hashlib.sha256(
            (route.api_key or "").encode("utf-8")
        ).hexdigest()
        cache_key = (route.connection_id, route.base_url, credential_fingerprint)
        if (
            not route.local
            and self.client is not None
            and route.provider_id == "openrouter"
            and route.base_url.rstrip("/") == self.openrouter_base_url.rstrip("/")
            and (not route.api_key or route.api_key == self.api_key)
        ):
            return self.client
        client = self._routed_clients.get(cache_key)
        if client is None:
            http_client = None
            if route.hostname and route.pinned_address:
                # Merkezi fabrika: varsayılan timeout/limits uygulanır;
                # transport-level DNS pinning (rebinding'e karşı) korunur.
                from agent_core.utils.security import build_secure_client

                http_client = build_secure_client(
                    transport=_PinnedAsyncHTTPTransport(
                        route.hostname,
                        route.pinned_address,
                    ),
                    follow_redirects=False,
                    trust_env=False,
                )
            client = AsyncOpenAI(
                base_url=route.base_url,
                api_key=route.api_key or "not-needed",
                default_headers=(
                    {"Host": route.host_header} if route.host_header else None
                ),
                http_client=http_client,
                max_retries=0,
            )
            if len(self._routed_clients) >= 128:
                self._routed_clients.pop(next(iter(self._routed_clients)))
            self._routed_clients[cache_key] = client
        return client

    async def query(
        self,
        prompt: str,
        temperature: float = 0.7,
        tier: int = 1,
        model: str = None,
        system_prompt: str = None,
        images: Optional[List[str]] = None,
        route: Optional[GatewayRoute] = None,
        task: Optional[str] = None,
        agent_name: Optional[str] = None,
    ) -> str:
        """Execute one logical LLM call and emit exactly one call-id record.

        Retries retain the same ``call_id``. Task/agent ownership comes from
        ``capture_calls`` and is therefore isolated across concurrent asyncio
        tasks sharing this gateway.
        """
        import asyncio
        import logging

        call_id = str(uuid.uuid4())
        started_at = self._utc_now()
        t0 = time.monotonic()

        is_local_request = bool(
            (model and any(marker in model.lower() for marker in ("local", "ollama", "127.0.0.1")))
            or self.use_local
        )
        pricing: Optional[dict[str, float]] = None
        if is_local_request:
            selected_model = self.local_model if (not model or model == "local") else model
            provider = "local"
        elif route is not None:
            selected_model = route.model
            provider = route.provider_id
            pricing = route.pricing
        else:
            if "20128" in self.openrouter_base_url and not model:
                selected_model = (
                    "pineal-vision" if images
                    else ("pineal-deep-reasoning" if tier == 1 else "pineal-fast-extract")
                )
            else:
                selected_model = (
                    os.getenv("OPENROUTER_VISION_MODEL", self.DEFAULT_VISION_MODEL)
                    if images and not model
                    else model or (self.TIER_1_MODEL if tier == 1 else self.TIER_2_MODEL)
                )
            provider = self.transport_provider
        # Capture the model the caller actually asked for before any fallback
        # reassignment, so telemetry can always explain requested != actual.
        requested_model = selected_model if route is None else (model or route.model)
        # FINAL-SPEC: provider rotasının kimliği + effective/list fiyat ayrımı
        # telemetriye backward-compatible ek alan olarak yazılır.
        route_extras: Optional[dict[str, Any]] = None
        if route is not None:
            route_extras = {
                "route_key": f"{route.model}@{route.provider_id}",
                "pricing_in_per_million_usd": route.input_per_million_usd,
                "pricing_out_per_million_usd": route.output_per_million_usd,
            }
            if route.list_input_per_million_usd:
                route_extras["list_pricing_in_per_million_usd"] = route.list_input_per_million_usd
                route_extras["list_pricing_out_per_million_usd"] = route.list_output_per_million_usd
                if route.input_per_million_usd is not None:
                    route_extras["discount_pct"] = round(
                        (1.0 - route.input_per_million_usd / route.list_input_per_million_usd) * 100.0,
                        1,
                    )
        logical_cost_usd = 0.0

        def log_call(
            *,
            error: Optional[str] = None,
            attempt: int = 0,
            cache_hit: bool = False,
            prompt_tokens: Optional[int] = None,
            completion_tokens: Optional[int] = None,
            cost_usd: Optional[float] = None,
            record_provider: Optional[str] = None,
            extras: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            return self._log_call(
                "query",
                selected_model,
                record_provider or provider,
                call_id=call_id,
                started_at=started_at,
                cache_hit=cache_hit,
                attempt=attempt,
                duration_ms=int((time.monotonic() - t0) * 1000),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=logical_cost_usd if cost_usd is None else cost_usd,
                error=error,
                requested_model=requested_model,
                # merge: cagrinin ekledigi structured alanlar route_extras'i EZMEZ
                extras=({**(route_extras or {}), **extras}
                        if extras is not None else route_extras),
            )

        # Routed attempts use provider-scoped state; the legacy circuit guards
        # only the single-transport compatibility path (mirrors chat_completion).
        if route is None and self.circuit_open:
            if time.time() - getattr(self, "circuit_opened_at", 0.0) > 60.0:
                self.circuit_open = False
                self.failure_count = 0
            else:
                log_call(error="CIRCUIT_OPEN", record_provider="circuit_breaker")
                raise RuntimeError("Circuit breaker ACIK - LLM servisi durduruldu (60s bekleme devrede)")

        if is_local_request:
            target_client = self.local_client or AsyncOpenAI(base_url=self.local_base_url, api_key="ollama")
        elif route is not None:
            if (
                os.getenv("LIVE_LLM_E2E") != "1"
                and os.getenv("PINEAL_ROUTER_LIVE") != "1"
                and not getattr(self, "live_unlocked", False)
            ):
                log_call(error="REAL_LLM_CALL_NOT_EXECUTED")
                raise RuntimeError(
                    "REAL_LLM_CALL_NOT_EXECUTED: routed transport canlı kapalı "
                    "(LIVE_LLM_E2E=1 veya PINEAL_ROUTER_LIVE=1 gerekir)."
                )
            target_client = self._client_for_route(route)
        else:
            if os.getenv("LIVE_LLM_E2E") != "1" and not getattr(self, "live_unlocked", False):
                log_call(error="REAL_LLM_CALL_NOT_EXECUTED")
                raise RuntimeError(
                    "REAL_LLM_CALL_NOT_EXECUTED: Canlı LLM çağrıları kapalı. "
                    "Açmak için: (1) Kasa'ya API anahtarı girin (oturum boyunca açılır), veya "
                    "(2) .env dosyasına OPENROUTER_API_KEY yazıp LIVE_LLM_E2E=1 yapıp sunucuyu yeniden başlatın."
                )
            if not self.client:
                log_call(error="LLM_KEY_MISSING")
                raise RuntimeError(
                    "LLM anahtari yok. Vault veya .env ile OPENROUTER_API_KEY enjekte et veya Local LLM seç."
                )
            target_client = self.client

        # RTK Compression (ephemeral on outbound prompt, preserves images & memory)
        scope = _active_call_scope.get()
        task_hint = (
            task
            or _active_task_hint.get()
            or (scope.task_id if scope else None)
            or (getattr(route, "task", None) if route else None)
        )
        agent_hint = (
            agent_name
            or _active_agent_hint.get()
            or (scope.agent_id if scope else None)
            or (getattr(route, "agent_name", None) if route else None)
        )
        compressed_prompt = self._apply_rtk_compression(prompt, task=task_hint, agent_name=agent_hint)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if images:
            content = [{"type": "text", "text": compressed_prompt}]
            content += [{"type": "image_url", "image_url": {"url": url}} for url in images]
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": compressed_prompt})

        cache_key = None
        if (
            not images
            and not is_local_request
            and route is None
            and self.cache
            and self.cache.is_cachable(prompt, images)
        ):
            cache_key = self.cache.make_key(
                prompt=prompt,
                model=selected_model,
                system_prompt=system_prompt,
                temperature=temperature,
            )
            # [AUDIT P0-6] sqlite erişimi SENKRONdur; event loop üzerinde
            # çalıştırılırsa tüm API donar (ölçülen 30.7 ms / 300 okuma).
            cached = await asyncio.to_thread(self.cache.get, cache_key)
            if cached is not None:
                log_call(cache_hit=True, record_provider="cache")
                return cached

        budget_reserved = False
        if not is_local_request:
            try:
                self._pricing_guard(selected_model, kind="query", pricing=pricing)
            except RuntimeError:
                log_call(error="UNKNOWN_PRICING")
                raise
            if pricing is not None or selected_model in self.MODEL_PRICING:
                reservation = self._maximum_call_cost(
                    selected_model,
                    prompt,
                    system_prompt,
                    images,
                    pricing,
                )
                try:
                    self._reserve_budget(call_id, reservation)
                    budget_reserved = True
                except SpendCapExceeded:
                    log_call(error="OPENROUTER_SPEND_CAP_EXCEEDED")
                    raise
            elif self.spend_cap_usd > 0 and os.getenv("PINEAL_ALLOW_UNPRICED_MODELS", "0") != "1":
                log_call(error="UNKNOWN_PRICING_FOR_SPEND_CAP")
                raise RuntimeError(
                    "UNKNOWN_PRICING_FOR_SPEND_CAP: unpriced models cannot run while a spend cap is active"
                )

        # Routed transport: one HTTP attempt per route; the provider cost
        # ladder / chain itself is the fallback mechanism (mirrors UnifiedRouter
        # lease semantics). Legacy OpenRouter keeps its bounded same-provider retry.
        max_retries = 1 if route is not None else 3
        for attempt_index in range(max_retries):
            attempt = attempt_index + 1
            try:
                # A malformed but billed provider response may have settled the
                # previous reservation. Every subsequent paid attempt must
                # reserve again before another request can leave the process.
                if (
                    not is_local_request
                    and (pricing is not None or selected_model in self.MODEL_PRICING)
                    and not budget_reserved
                ):
                    reservation = self._maximum_call_cost(
                        selected_model, prompt, system_prompt, images, pricing
                    )
                    self._reserve_budget(call_id, reservation)
                    budget_reserved = True
                response = await target_client.chat.completions.create(
                    model=selected_model,
                    temperature=temperature,
                    messages=messages,
                    stream=False,
                    timeout=self.request_timeout_seconds,
                    max_tokens=self.max_output_tokens,
                )
                # FINAL-SPEC #27: sessiz ikame firewall'u TUM tasmalarda
                # gecerli — provider (OpenRouter dahil) istenen model yerine
                # baska bir model dondurduyse bu asla kabul edilmez.
                actual_model = getattr(response, "model", None)
                if actual_model and not self._model_substitution_allowed(
                    selected_model, str(actual_model)
                ):
                    # Tek log: except blogindeki non-retryable dal yazacak;
                    # buradan sadece marka'lı hata yukseltilir.
                    raise ModelSubstitutionDeniedError(
                        f"MODEL_SUBSTITUTION_DENIED: requested '{selected_model}' "
                        f"but provider returned '{actual_model}'",
                        requested=selected_model,
                        actual=str(actual_model),
                    )
                if route is not None:
                    self._record_route_attempt(route, response, success=True)
                else:
                    self.failure_count = 0
                usage = getattr(response, "usage", None)
                cost_usd = 0.0
                if not is_local_request:
                    # Settle observed provider usage before parsing the body.
                    # Otherwise a malformed paid response could be retried as
                    # though no billable request had occurred.
                    cost_usd = self._settle_budget(call_id, selected_model, usage, pricing)
                    logical_cost_usd += cost_usd
                    budget_reserved = False
                choices = getattr(response, "choices", None) or []
                if not choices or not getattr(choices[0], "message", None):
                    # [FIX #10] Transport hatası: query_json bunu parse
                    # hatası sanıp ücretli repair'a girmesin.
                    raise ProviderEmptyResponseError(
                        f"Provider returned empty choices from model '{selected_model}'"
                    )
                content = getattr(choices[0].message, "content", "") or ""

                if cache_key and content:
                    try:
                        # [AUDIT P0-6] yazma da thread'e devredilir (bkz. get).
                        await asyncio.to_thread(self.cache.put, cache_key, content)
                    except Exception as cache_error:
                        # A cache write must never retry an already billed call.
                        logging.warning("LLM response cache write failed: %s", cache_error)
                resolved_model_str = str(actual_model) if actual_model else None
                resolved_provider_str = (
                    resolved_model_str.split("/")[0]
                    if resolved_model_str and "/" in resolved_model_str
                    else None
                )
                log_call(
                    attempt=attempt,
                    prompt_tokens=(
                        int(getattr(usage, "prompt_tokens", 0) or 0) if usage is not None else None
                    ),
                    completion_tokens=(
                        int(getattr(usage, "completion_tokens", 0) or 0) if usage is not None else None
                    ),
                    cost_usd=(
                        None
                        if "20128" in self.openrouter_base_url
                        else logical_cost_usd
                    ),
                    extras={
                        "resolved_model": resolved_model_str,
                        "resolved_provider": resolved_provider_str,
                        "requested_route": selected_model,
                        "token_saver_mode": "off",
                        "cost_note": (
                            "antigravity_oauth_quota"
                            if "20128" in self.openrouter_base_url
                            else None
                        ),
                    },
                )
                return content
            except asyncio.CancelledError:
                if budget_reserved:
                    self._release_budget(call_id)
                    budget_reserved = False
                log_call(error="CANCELLED", attempt=attempt)
                raise
            except SpendCapExceeded:
                if budget_reserved:
                    self._release_budget(call_id)
                    budget_reserved = False
                log_call(error="OPENROUTER_SPEND_CAP_EXCEEDED", attempt=attempt)
                raise
            except Exception as exc:
                error_text = str(exc).lower()
                if route is not None:
                    self._record_route_attempt(route, success=False)
                is_connection_error = any(
                    marker in error_text for marker in ("connection", "connect", "refused", "10061")
                )

                if is_local_request and is_connection_error:
                    if os.getenv("ALLOW_LOCAL_TO_CLOUD_FALLBACK", "false").lower() != "true":
                        log_call(error="LOCAL_PROVIDER_UNAVAILABLE", attempt=attempt)
                        raise RuntimeError(
                            "LOCAL_PROVIDER_UNAVAILABLE: Yerel model erişilemedi; "
                            "bulut fallback'i açıkça yetkilendirilmedi."
                        ) from exc
                    if self.client:
                        logging.warning(
                            "Yetkili provider fallback: local %s → cloud %s",
                            selected_model,
                            self.TIER_1_MODEL,
                        )
                        target_client = self.client
                        selected_model = self.TIER_1_MODEL
                        is_local_request = False
                        provider = self.transport_provider
                        try:
                            self._pricing_guard(selected_model, kind="query")
                        except RuntimeError:
                            log_call(error="UNKNOWN_PRICING", attempt=attempt)
                            raise
                        reservation = self._maximum_call_cost(
                            selected_model, prompt, system_prompt, images
                        )
                        try:
                            self._reserve_budget(call_id, reservation)
                            budget_reserved = True
                        except SpendCapExceeded:
                            log_call(error="OPENROUTER_SPEND_CAP_EXCEEDED", attempt=attempt)
                            raise
                        continue

                is_auth_error = any(
                    marker in error_text for marker in ("401", "unauthorized", "invalid_api_key")
                )
                if is_auth_error:
                    if budget_reserved:
                        self._release_budget(call_id)
                        budget_reserved = False
                    logging.error("LLM Gateway authentication error: %s", exc)
                    log_call(error="AUTH_FAILED", attempt=attempt)
                    raise RuntimeError(f"LLM API Key rejected: {exc}") from exc

                if "model_substitution_denied" in error_text:
                    # FINAL-SPEC #27: ikame reddi ic retry de zincir fallback'i
                    # de tetiklemez; rezervasyon iade, kayit tek, hata yukselir.
                    if budget_reserved:
                        self._release_budget(call_id)
                        budget_reserved = False
                    # #34: kayit, hangi modelin hangisiyle ikame edilmek
                    # istendigini tek basina aciklayabilmeli (detay kaybolmasin).
                    # ROUTING-HARDENING: provider'in dondurdugu model ayrica
                    # STRUCTURED actual_model alani olarak yazilir (spec #10).
                    log_call(
                        error=f"MODEL_SUBSTITUTION_DENIED::{str(exc)[:200]}",
                        attempt=attempt,
                        extras={
                            "actual_model": getattr(exc, "actual", None),
                            "requested_model": getattr(exc, "requested", None),
                        },
                    )
                    raise

                if not self._is_retryable_error(exc):
                    if budget_reserved:
                        self._release_budget(call_id)
                        budget_reserved = False
                    logging.error("LLM Gateway non-retryable error (%s): %s", type(exc).__name__, exc)
                    log_call(error=f"NON_RETRYABLE::{type(exc).__name__}", attempt=attempt)
                    raise

                if attempt_index < max_retries - 1:
                    backoff = 2 ** attempt_index
                    logging.warning(
                        "LLM Bağlantı/Gecikme Hatası (deneme %s/%s), %ss içinde tekrar deneniyor... %s",
                        attempt,
                        max_retries,
                        backoff,
                        exc,
                    )
                    try:
                        await asyncio.sleep(backoff)
                    except asyncio.CancelledError:
                        if budget_reserved:
                            self._release_budget(call_id)
                            budget_reserved = False
                        log_call(error="CANCELLED", attempt=attempt)
                        raise
                    continue

                if budget_reserved:
                    self._release_budget(call_id)
                    budget_reserved = False
                self.failure_count += 1
                if self.failure_count > 5:
                    self.circuit_open = True
                    self.circuit_opened_at = time.time()
                log_call(error=type(exc).__name__, attempt=attempt)
                raise

    async def chat_completion(
        self,
        *,
        messages: List[dict[str, Any]],
        model: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        stop: Any = None,
        tools: Optional[List[dict[str, Any]]] = None,
        tool_choice: Any = None,
        response_format: Optional[dict[str, Any]] = None,
        seed: Optional[int] = None,
        user: Optional[str] = None,
        route: Optional[GatewayRoute] = None,
        task: Optional[str] = None,
        agent_name: Optional[str] = None,
    ) -> LLMChatResult:
        """Execute a non-streaming OpenAI chat request under gateway controls.

        This is the compatibility transport boundary: arbitrary conversation and
        tool shapes are preserved, while this gateway remains the only owner of
        call identity, retries, circuit state, spend reservations, and capture.
        """
        import asyncio
        import logging

        if not isinstance(model, str) or not model.strip():
            raise ValueError("model is required")
        if not messages:
            raise ValueError("at least one message is required")
        selected_model = route.model if route is not None else self.MODEL_REGISTRY.get(model, model)
        is_local_request = route.local if route is not None else bool(self.use_local)
        if route is None and is_local_request and selected_model == "local":
            selected_model = self.local_model
        provider = route.provider_id if route is not None else (
            "local" if is_local_request else self.transport_provider
        )
        pricing = route.pricing if route is not None else None
        effective_max_tokens = self.max_output_tokens if max_tokens is None else max_tokens
        if effective_max_tokens < 1 or effective_max_tokens > self.max_output_tokens:
            raise ValueError(f"max_tokens must be between 1 and gateway cap {self.max_output_tokens}")

        scope = _active_call_scope.get()
        task_hint = (
            task
            or _active_task_hint.get()
            or (scope.task_id if scope else None)
            or (getattr(route, "task", None) if route else None)
        )
        agent_hint = (
            agent_name
            or _active_agent_hint.get()
            or (scope.agent_id if scope else None)
            or (getattr(route, "agent_name", None) if route else None)
        )
        outbound_messages = self._compress_chat_messages(messages, task=task_hint, agent_name=agent_hint)

        request_payload: dict[str, Any] = {
            "model": selected_model,
            "messages": outbound_messages,
            "max_tokens": effective_max_tokens,
        }
        optional_parameters = {
            "temperature": temperature,
            "top_p": top_p,
            "stop": stop,
            "tools": tools,
            "tool_choice": tool_choice,
            "response_format": response_format,
            "seed": seed,
            "user": user,
        }
        request_payload.update({key: value for key, value in optional_parameters.items() if value is not None})

        call_id = str(uuid.uuid4())
        started_at = self._utc_now()
        started_monotonic = time.monotonic()
        logical_cost_usd = 0.0
        requested_model = model

        def log_call(
            *,
            error: Optional[str] = None,
            attempt: int = 0,
            prompt_tokens: Optional[int] = None,
            completion_tokens: Optional[int] = None,
            cost_usd: Optional[float] = None,
            fallback_reason: Optional[str] = None,
            quota_status: Optional[str] = None,
            extras: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            return self._log_call(
                "chat.completions",
                selected_model,
                provider,
                call_id=call_id,
                started_at=started_at,
                attempt=attempt,
                duration_ms=int((time.monotonic() - started_monotonic) * 1000),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=logical_cost_usd if cost_usd is None else cost_usd,
                error=error,
                requested_model=requested_model,
                fallback_reason=fallback_reason,
                quota_status=quota_status,
                extras=extras,
            )

        # Routed calls use provider-scoped circuits in UnifiedRouter. The legacy
        # gateway circuit remains only for the single-provider compatibility path.
        if route is None and self.circuit_open:
            if time.time() - self.circuit_opened_at > 60.0:
                self.circuit_open = False
                self.failure_count = 0
            else:
                log_call(error="CIRCUIT_OPEN")
                raise RuntimeError("LLM_CIRCUIT_OPEN")

        if route is not None:
            if (
                not is_local_request
                and os.getenv("LIVE_LLM_E2E") != "1"
                and os.getenv("PINEAL_ROUTER_LIVE") != "1"
                and not self.live_unlocked
            ):
                log_call(error="REAL_LLM_CALL_NOT_EXECUTED")
                raise RuntimeError("REAL_LLM_CALL_NOT_EXECUTED")
            target_client = self._client_for_route(route)
        elif is_local_request:
            target_client = self.local_client
            if target_client is None:
                log_call(error="LOCAL_PROVIDER_UNAVAILABLE")
                raise RuntimeError("LOCAL_PROVIDER_UNAVAILABLE")
        else:
            if os.getenv("LIVE_LLM_E2E") != "1" and not self.live_unlocked:
                log_call(error="REAL_LLM_CALL_NOT_EXECUTED")
                raise RuntimeError("REAL_LLM_CALL_NOT_EXECUTED")
            if self.client is None:
                log_call(error="LLM_KEY_MISSING")
                raise RuntimeError("LLM_KEY_MISSING")
            target_client = self.client

        budget_reserved = False
        if not is_local_request:
            try:
                self._pricing_guard(
                    selected_model,
                    kind="chat.completions",
                    pricing=pricing,
                )
            except RuntimeError:
                log_call(error="UNKNOWN_PRICING")
                raise
            if pricing is not None or selected_model in self.MODEL_PRICING:
                reservation = self._maximum_chat_cost(
                    selected_model,
                    request_payload,
                    effective_max_tokens,
                    pricing,
                )
                try:
                    self._reserve_budget(call_id, reservation)
                    budget_reserved = True
                except SpendCapExceeded:
                    log_call(error="OPENROUTER_SPEND_CAP_EXCEEDED")
                    raise
            elif self.spend_cap_usd > 0:
                log_call(error="UNKNOWN_PRICING_FOR_SPEND_CAP")
                raise RuntimeError("UNKNOWN_PRICING_FOR_SPEND_CAP")

        # A unified AttemptLease maps to exactly one provider HTTP attempt.
        # Legacy mode retains its existing bounded same-provider retry behavior.
        max_retries = 1 if route is not None else 3
        for attempt_index in range(max_retries):
            attempt = attempt_index + 1
            try:
                response = await target_client.chat.completions.create(
                    **request_payload,
                    timeout=self.request_timeout_seconds,
                )
                # Provider default-model override firewall: the provider must
                # never silently substitute a different model than requested.
                if route is not None:
                    actual_model = getattr(response, "model", None)
                    if actual_model and not self._model_substitution_allowed(
                        selected_model, str(actual_model)
                    ):
                        if budget_reserved:
                            self._release_budget(call_id)
                            budget_reserved = False
                        error = (
                            f"MODEL_SUBSTITUTION_DENIED: requested "
                            f"'{selected_model}' but provider returned "
                            f"'{actual_model}'"
                        )
                        # ROUTING-HARDENING: tek log — yapılandırılmış
                        # requested/actual kaydı dış except yazar (spec #10)
                        raise ModelSubstitutionDeniedError(
                            error, requested=selected_model, actual=str(actual_model)
                        )
                if route is None:
                    self.failure_count = 0
                usage = getattr(response, "usage", None)
                if not is_local_request:
                    logical_cost_usd = self._settle_budget(
                        call_id,
                        selected_model,
                        usage,
                        pricing,
                    )
                    budget_reserved = False
                usage_tokens = self._usage_tokens(usage)
                prompt_tokens = usage_tokens[0] if usage_tokens is not None else None
                completion_tokens = usage_tokens[1] if usage_tokens is not None else None
                log_call(
                    attempt=attempt,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=logical_cost_usd,
                )
                return LLMChatResult(call_id=call_id, response=response)
            except asyncio.CancelledError:
                if budget_reserved:
                    self._release_budget(call_id)
                log_call(error="CANCELLED", attempt=attempt)
                raise
            except SpendCapExceeded:
                if budget_reserved:
                    self._release_budget(call_id)
                log_call(error="OPENROUTER_SPEND_CAP_EXCEEDED", attempt=attempt)
                raise
            except Exception as exc:
                retryable = self._is_strict_retryable_error(exc)
                if retryable and attempt_index < max_retries - 1:
                    try:
                        await asyncio.sleep(2**attempt_index)
                    except asyncio.CancelledError:
                        if budget_reserved:
                            self._release_budget(call_id)
                        log_call(error="CANCELLED", attempt=attempt)
                        raise
                    continue
                if budget_reserved:
                    self._release_budget(call_id)
                    budget_reserved = False
                if retryable and route is None:
                    self.failure_count += 1
                    if self.failure_count > 5:
                        self.circuit_open = True
                        self.circuit_opened_at = time.time()
                if isinstance(exc, ModelSubstitutionDeniedError):
                    # ROUTING-HARDENING: tek, yapılandırılmış red kaydı —
                    # interface/telemetry regex'e hiç düşmeden okusun (spec #10)
                    log_call(
                        error=f"MODEL_SUBSTITUTION_DENIED::{str(exc)[:200]}",
                        attempt=attempt,
                        extras={
                            "actual_model": getattr(exc, "actual", None),
                            "requested_model": getattr(exc, "requested", selected_model),
                        },
                    )
                    raise
                logging.error(
                    "OpenAI-compatible gateway request failed (%s)",
                    type(exc).__name__,
                )
                log_call(error=type(exc).__name__, attempt=attempt)
                raise

        raise AssertionError("unreachable chat completion retry state")

    async def start_chat_stream(
        self,
        *,
        messages: List[dict[str, Any]],
        model: str,
        route: GatewayRoute,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        stop: Any = None,
        response_format: Optional[dict[str, Any]] = None,
        seed: Optional[int] = None,
        user: Optional[str] = None,
        stream_options: Optional[dict[str, Any]] = None,
    ) -> LLMChatStream:
        """Start one routed HTTP stream and prefetch its first SSE chunk.

        Unified routing gives every lease exactly one provider request. Failure
        before this method returns is therefore eligible for router fallback;
        errors after the prefetched chunk are surfaced as interruptions and can
        never switch provider mid-stream.
        """
        import asyncio

        if not messages:
            raise ValueError("at least one message is required")
        selected_model = route.model
        effective_max_tokens = self.max_output_tokens if max_tokens is None else max_tokens
        if effective_max_tokens < 1 or effective_max_tokens > self.max_output_tokens:
            raise ValueError(f"max_tokens must be between 1 and gateway cap {self.max_output_tokens}")
        if (
            not route.local
            and os.getenv("LIVE_LLM_E2E") != "1"
            and os.getenv("PINEAL_ROUTER_LIVE") != "1"
            and not self.live_unlocked
        ):
            raise RuntimeError("REAL_LLM_CALL_NOT_EXECUTED")

        request_payload: dict[str, Any] = {
            "model": selected_model,
            "messages": messages,
            "max_tokens": effective_max_tokens,
            "stream": True,
        }
        optional_parameters = {
            "temperature": temperature,
            "top_p": top_p,
            "stop": stop,
            "response_format": response_format,
            "seed": seed,
            "user": user,
            "stream_options": stream_options,
        }
        request_payload.update({
            key: value for key, value in optional_parameters.items() if value is not None
        })

        call_id = str(uuid.uuid4())
        started_at = self._utc_now()
        started_monotonic = time.monotonic()
        captured_scope = _active_call_scope.get()
        pricing = route.pricing
        budget_reserved = False
        reservation = 0.0

        def log_call(
            *,
            error: Optional[str] = None,
            usage: Any = None,
            cost_usd: float = 0.0,
        ) -> None:
            usage_tokens = self._usage_tokens(usage)
            self._log_call(
                "chat.completions.stream",
                selected_model,
                route.provider_id,
                call_id=call_id,
                started_at=started_at,
                attempt=1,
                duration_ms=int((time.monotonic() - started_monotonic) * 1000),
                prompt_tokens=usage_tokens[0] if usage_tokens else None,
                completion_tokens=usage_tokens[1] if usage_tokens else None,
                cost_usd=cost_usd,
                error=error,
                requested_model=model,
                captured_scope=captured_scope,
            )

        if not route.local:
            try:
                self._pricing_guard(
                    selected_model,
                    kind="chat.completions.stream",
                    pricing=pricing,
                )
            except RuntimeError:
                log_call(error="UNKNOWN_PRICING")
                raise
            if pricing is not None or selected_model in self.MODEL_PRICING:
                reservation = self._maximum_chat_cost(
                    selected_model,
                    request_payload,
                    effective_max_tokens,
                    pricing,
                )
                try:
                    self._reserve_budget(call_id, reservation)
                    budget_reserved = True
                except SpendCapExceeded:
                    log_call(error="OPENROUTER_SPEND_CAP_EXCEEDED")
                    raise
            elif self.spend_cap_usd > 0:
                log_call(error="UNKNOWN_PRICING_FOR_SPEND_CAP")
                raise RuntimeError("UNKNOWN_PRICING_FOR_SPEND_CAP")

        target_client = self._client_for_route(route)
        try:
            upstream = await target_client.chat.completions.create(
                **request_payload,
                timeout=self.request_timeout_seconds,
            )
            first_chunk = await anext(upstream)
        except asyncio.CancelledError:
            if budget_reserved:
                self._release_budget(call_id)
            log_call(error="CANCELLED")
            raise
        except Exception as exc:
            if budget_reserved:
                self._release_budget(call_id)
            log_call(error=type(exc).__name__)
            raise

        async def chunks() -> AsyncIterator[Any]:
            settled = False
            observed_usage = None

            def observe(chunk: Any) -> None:
                nonlocal observed_usage
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    observed_usage = usage

            def finalize(error: Optional[str]) -> None:
                nonlocal settled
                if settled:
                    return
                settled = True
                cost = 0.0
                if not route.local:
                    cost = self._settle_budget(
                        call_id,
                        selected_model,
                        observed_usage,
                        pricing,
                    )
                log_call(error=error, usage=observed_usage, cost_usd=cost)

            try:
                observe(first_chunk)
                yield first_chunk
                async for chunk in upstream:
                    observe(chunk)
                    yield chunk
            except asyncio.CancelledError:
                finalize("CANCELLED")
                raise
            except Exception as exc:
                finalize(f"STREAM_INTERRUPTED::{type(exc).__name__}")
                raise
            else:
                finalize(None)
            finally:
                finalize("STREAM_CLOSED")

        return LLMChatStream(call_id=call_id, chunks=chunks())

    def extract_json(self, text: str) -> dict:
        """Markdown fence ve etiketleri temizleyip JSON ayıklar."""
        text = (text or "").strip()
        if not text:
            raise ValueError("Boş metin; JSON ayıklanamaz.")
        
        # 1. Kod blokları varsa önce onları dene
        if "```json" in text:
            blocks = [b.split("```")[0].strip() for b in text.split("```json")[1:]]
            for b in reversed(blocks):
                try:
                    return json.loads(b)
                except Exception as exc:
                    logger.warning(
                        "[extract_json] beklenmeyen hata (Exception) yutulmadı — iz bırakıldı: %s", exc, exc_info=True
                    )
        elif "```" in text:
            blocks = [b.split("```")[0].strip() for b in text.split("```")[1:]]
            for b in reversed(blocks):
                try:
                    return json.loads(b)
                except Exception as exc:
                    logger.warning(
                        "[extract_json] beklenmeyen hata (Exception) yutulmadı — iz bırakıldı: %s", exc, exc_info=True
                    )

        # 2. Doğrudan parse dene
        try:
            return json.loads(text)
        except Exception as exc:
            logger.warning(
                "[extract_json] beklenmeyen hata (Exception) yutulmadı — iz bırakıldı: %s", exc, exc_info=True
            )

        # 3. Metin içindeki tüm JSON nesnelerini tara
        decoder = json.JSONDecoder()
        start = 0
        found_objs = []
        while start < len(text):
            pos = text.find('{', start)
            if pos == -1:
                break
            try:
                obj, end_idx = decoder.raw_decode(text[pos:])
                if isinstance(obj, dict):
                    found_objs.append(obj)
                start = pos + max(1, end_idx)
            except Exception:
                start = pos + 1

        if found_objs:
            for obj in reversed(found_objs):
                if "$defs" not in obj and "properties" not in obj:
                    return obj
            return found_objs[-1]

        raise ValueError(f"JSON Ayrıştırma Hatası | Orijinal metin: {text[:100]}...")

    def _coerce_to_schema(self, parsed_data: Any, schema: Type[T]) -> T:
        if not isinstance(parsed_data, dict):
            raise ValueError(f"Beklenen JSON nesnesi (dict), alınan: {type(parsed_data)}")
        
        # Eğer model 'properties' altına sarmaladıysa unwrap yap
        if "properties" in parsed_data and hasattr(schema, "model_fields") and "properties" not in schema.model_fields:
            props = parsed_data["properties"]
            if isinstance(props, dict):
                sample_val = next(iter(props.values()), None)
                if not isinstance(sample_val, dict) or "type" not in sample_val:
                    parsed_data = props

        # Eğer model sınıf ismi altına sarmaladıysa unwrap yap
        root_key = getattr(schema, "__name__", "")
        if root_key and root_key in parsed_data and isinstance(parsed_data[root_key], dict):
            parsed_data = parsed_data[root_key]

        # Alan seviyesinde unwrap (LLM {field: {title: ..., default: ...}} dönerse)
        cleaned = dict(parsed_data)
        if hasattr(schema, "model_fields"):
            for field_name, field_info in schema.model_fields.items():
                if field_name in cleaned and isinstance(cleaned[field_name], dict):
                    inner = cleaned[field_name]
                    if "default" in inner:
                        cleaned[field_name] = inner["default"]
                    elif "value" in inner:
                        cleaned[field_name] = inner["value"]
                    elif "const" in inner:
                        cleaned[field_name] = inner["const"]
                    elif "description" in inner and len(inner) == 1:
                        cleaned[field_name] = inner["description"]
        parsed_data = cleaned

        return schema.model_validate(parsed_data)

    async def query_json(self, prompt: str, schema: Type[T], temperature: float = 0.7, tier: int = 1, model: str = None, images: Optional[List[str]] = None, route: Optional[GatewayRoute] = None, task: Optional[str] = None, agent_name: Optional[str] = None) -> T:
        """LLM'den sorgu atar, beklenen JSON formatını (Pydantic schema) tamir mekanizmasıyla garanti eder.

        Repair is scoped to parse/schema failures only. Transport, auth, spend-cap,
        cancellation, and other non-JSON errors are re-raised immediately so a
        broken upstream call is never disguised as a second paid repair attempt.
        """
        full_prompt = (
            f"{prompt}\n\n"
            f"Lütfen çıktını SADECE aşağıdaki JSON formatına uygun DOLDURULMUŞ JSON verisi olarak ver. Markdown etiketi kullanma, hiçbir ek açıklama yapma:\n"
            f"{json.dumps(schema.model_json_schema(), ensure_ascii=False)}"
        )
        
        selected_model = model or (self.TIER_1_MODEL if tier == 1 else self.TIER_2_MODEL)
        response_text = ""
        try:
            response_text = await self.query(full_prompt, temperature, tier=tier, model=selected_model, images=images, route=route, task=task, agent_name=agent_name)
            parsed_data = self.extract_json(response_text)
            return self._coerce_to_schema(parsed_data, schema)
        except (ValueError, ValidationError, TypeError, KeyError, json.JSONDecodeError) as err:
            # 1 Kez Repair (Tamir) İsteği — yalnız JSON/şema hatalarında.
            repair_prompt = (
                f"Önceki çıktın geçerli bir doldurulmuş JSON verisi değildi veya şemaya uymadı ({err}). "
                f"Lütfen SADECE şu şemaya uygun DOLDURULMUŞ veriyi JSON olarak döndür (şema etiketlerini değil, gerçek veriyi yaz):\n{json.dumps(schema.model_json_schema(), ensure_ascii=False)}\n"
                f"DİKKAT: Eksik veri varsa uydurma kelimeler veya sahte skorlar YAZMA. Sadece var olanları yerleştir.\n"
                f"Eklediğin bozuk çıktı şuydu:\n{response_text[:200]}"
            )
            repair_text = await self.query(repair_prompt, temperature, tier=tier, model=selected_model, images=images, route=route, task=task, agent_name=agent_name)
            parsed_data = self.extract_json(repair_text)
            return self._coerce_to_schema(parsed_data, schema)

    async def query_chain(
        self,
        prompt: str,
        task: str = "depth",
        temperature: float = 0.7,
        system_prompt: str = None,
        images: Optional[List[str]] = None,
        agent_name: Optional[str] = None,
    ) -> str:
        """Görev bazlı model zincirini çalıştırır.

        Yalnızca GEÇİCİ hatalarda (timeout/connection/408/429/5xx) zincirdeki
        sıradaki modele düşer. AUTH, spend cap, unknown pricing, paid
        escalation, model unavailable ve policy-deny hataları düşmez.

        FINAL-SPEC F-1: ``agent_name`` verilirse zincir AGENT_CHAINS'ten çözülür
        (matrix = default SoT) ve her model provider merdiveniyle yürür.
        """
        import logging
        chain = self.capable_chain(task=task, agent_name=agent_name, images=images)
        required_caps = self.required_capabilities(
            task=task, agent_name=agent_name, images=images
        )
        last_exception = None
        t_token = _active_task_hint.set(task) if task else None
        a_token = _active_agent_hint.set(agent_name) if agent_name else None

        try:
            for model in chain:
                # MP-ROUTING: sağlayıcı merdiveni (free → indirimli → OpenRouter),
                # sonra zincirdeki sıradaki model.
                for route in self.agent_route_variants(model, required=required_caps):
                    tried = route.model if route is not None else model
                    try:
                        result = await self.query(
                            prompt=prompt,
                            temperature=temperature,
                            model=model,
                            system_prompt=system_prompt,
                            images=images,
                            route=route,
                        )
                        if route is not None:
                            # ROUTING-HARDENING: basarili tasima devreyi sifirlar.
                            self._note_route_health(route.provider_id, ok=True)
                        return result
                    except Exception as e:
                        if not _is_fallback_allowed(
                            e, json_mode=False, route_scoped=route is not None
                        ):
                            self._annotate_most_recent(tried, fallback_reason=_failure_reason(e))
                            raise
                        if route is not None:
                            # yalniz GECICI transport hatasi streak'e sayilir
                            self._note_route_health(route.provider_id, ok=False)
                        last_exception = e
                        self._annotate_most_recent(tried, fallback_reason=_failure_reason(e))
                        logging.warning(
                            f"Model zincirinde geçici hata [{task} -> {model}"
                            f"@{route.provider_id if route is not None else 'openrouter'}]: {e}. "
                            f"Sıradaki rota/model deneniyor..."
                        )
                        continue

            if last_exception:
                raise last_exception
            raise RuntimeError(f"Zincirdeki tüm modeller tükendi ({task})")
        finally:
            if t_token is not None:
                _active_task_hint.reset(t_token)
            if a_token is not None:
                _active_agent_hint.reset(a_token)

    async def query_json_chain(
        self,
        prompt: str,
        schema: Type[T],
        task: str = "depth",
        temperature: float = 0.7,
        images: Optional[List[str]] = None,
        agent_name: Optional[str] = None,
    ) -> T:
        """Görev bazlı model zinciri ile şemalı JSON sorgusu yapar.

        Yalnızca GEÇİCİ hatalarda (timeout/connection/408/429/5xx) veya gerçek
        JSON parse/schema başarısızlığında zincirdeki sıradaki modele düşer.
        AUTH, spend cap, unknown pricing, paid escalation, model unavailable ve
        policy-deny hataları "JSON tamiri" bahanesiyle ikinci çağrıya dönüşmez.
        """
        import logging
        chain = self.capable_chain(task=task, agent_name=agent_name, images=images)
        required_caps = self.required_capabilities(
            task=task, agent_name=agent_name, images=images
        )
        last_exception = None
        t_token = _active_task_hint.set(task) if task else None
        a_token = _active_agent_hint.set(agent_name) if agent_name else None

        try:
            for model in chain:
                # MP-ROUTING: önce bu MODELİN sağlayıcı merdiveni denenir
                # (free → indirimli → OpenRouter); geçici hata sonraki taşımayı
                # dener, taşımalar bitince zincirdeki sonraki MODELE düşülür.
                for route in self.agent_route_variants(model, required=required_caps):
                    tried = route.model if route is not None else model
                    try:
                        result = await self.query_json(
                            prompt=prompt,
                            schema=schema,
                            temperature=temperature,
                            model=model,
                            images=images,
                            route=route,
                        )
                        if route is not None:
                            self._note_route_health(route.provider_id, ok=True)
                        return result
                    except Exception as e:
                        if not _is_fallback_allowed(
                            e, json_mode=True, route_scoped=route is not None
                        ):
                            self._annotate_most_recent(tried, fallback_reason=_failure_reason(e))
                            raise
                        if route is not None:
                            # ROUTING-HARDENING: yalniz GECICI transport hatasi sayilir
                            self._note_route_health(route.provider_id, ok=False)
                        last_exception = e
                        self._annotate_most_recent(tried, fallback_reason=_failure_reason(e))
                        logging.warning(
                            f"JSON zincirinde hata [{task} -> {model}"
                            f"@{route.provider_id if route is not None else 'openrouter'}]: {e}. "
                            f"Sıradaki rota/model deneniyor..."
                        )
                        continue

            if last_exception:
                raise last_exception
            raise RuntimeError(f"JSON Zincirindeki tüm modeller tükendi ({task})")
        finally:
            if t_token is not None:
                _active_task_hint.reset(t_token)
            if a_token is not None:
                _active_agent_hint.reset(a_token)
