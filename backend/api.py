from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Path, Request, WebSocket
from fastapi.responses import FileResponse
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
from collections import deque
import asyncio
import io
import json
import logging
import importlib
import shutil
import os
import hashlib
import time

logger = logging.getLogger("backend.api")
from datetime import datetime
import sys

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from agent_core.aspasia.aspasia_chief import AspasiaChief
from agent_core.aspasia.interface import AspasiaCommandGateway
from agent_core.chat.dialogue_manager import DialogueManager
from agent_core.scraper.instagram_ghost import InstagramGhostScraper
from agent_core.services import crawl_enricher, socid_enricher
from agent_core.services.browser_session import BrowserSession
from agent_core.services.dependency_health import (
    StartupDependencyError,
    check_startup_dependencies,
)
from agent_core.schemas.telemetry import ErrorHaltEvent, Severity, TaskCancelledEvent
from agent_core.services.routed_chat import (
    RoutingRuntimeError,
    llm_backend_mode_from_env,
    routing_runtime_from_env,
)
from agent_core.services.runtime_status import rust_core_status
from agent_core.services.task_lifecycle import TaskLifecycleRegistry
from agent_core.services.token_optimizer import OptimizationPolicy, TokenOptimizer
from agent_core.services.unified_router import RoutingStrategy
from agent_core.shadow.shadow_executor import ShadowExecutor
from agent_core.utils.security import (
    SecurityConfigurationError,
    redact_structure,
    redact_text,
    safe_child_path,
    security_posture,
    token_matches,
    validate_identifier,
)
from agent_core.task_executor import PinealExecutor, InsufficientEvidenceError
# [FIX #8] Scraper'ın KENDİNE ÖZLÜ InsufficientEvidenceError'ı (başka bir
# Exception hiyerarşisi) da yakalanmalı; ayrı sınıflar olduğundan
# isinstance ile ayrım yapılır, str(type) kontrolü ile değil.
from agent_core.scraper.instagram_ghost import (
    InsufficientEvidenceError as ScraperInsufficientEvidenceError,
)


shadow_executor = ShadowExecutor()
dialogue_manager = DialogueManager()
aspasia_chief = AspasiaChief()
_tool_output_optimizer = TokenOptimizer()

# v5.0 - Redis Pub/Sub + Agent Rack canlı köprüsü
try:
    from agent_core.services.agent_status_tracker import get_tracker, init_tracker, AGENT_DEFINITIONS
    HAS_AGENT_RACK = True
except ImportError:
    HAS_AGENT_RACK = False
    get_tracker = None
    init_tracker = None
    AGENT_DEFINITIONS = []

@asynccontextmanager
async def lifespan(application: FastAPI):
    try:
        startup_health = check_startup_dependencies()
        startup_health["security"] = security_posture()
        application.state.llm_backend_mode = llm_backend_mode_from_env()
        application.state.openai_router = routing_runtime_from_env()
        router_fallback_active = False
        if (
            application.state.llm_backend_mode == "unified"
            and application.state.openai_router is None
        ):
            logger.error("PINEAL_ROUTER_CONFIG is missing or invalid. Falling back to legacy LLM backend, marking health as DEGRADED.")
            application.state.llm_backend_mode = "legacy"
            router_fallback_active = True
        degraded_reasons: list[str] = []
        if router_fallback_active:
            degraded_reasons.append("UNIFIED_ROUTER_CONFIG_MISSING")

        # Production'da harcama tavanı sıfırsa uyarı yüzey
        _is_prod = os.getenv("PINEAL_ENV", "development").strip().lower() in {"production", "prod"}
        try:
            _spend_cap = float(os.getenv("OPENROUTER_MAX_SPEND_USD", "0").strip())
        except ValueError:
            _spend_cap = 0.0
        _spend_unlimited = (_spend_cap == 0.0)
        if _is_prod and _spend_unlimited:
            logger.warning(
                "SPEND_CAP_UNLIMITED: OPENROUTER_MAX_SPEND_USD=0 in production "
                "allows unbounded LLM spending. Set a non-zero cap."
            )
            degraded_reasons.append("SPEND_CAP_UNLIMITED")

        startup_health["spend_cap_usd"] = None if _spend_unlimited else _spend_cap
        startup_health["spend_cap_unlimited"] = _spend_unlimited

        if degraded_reasons:
            startup_health["status"] = "degraded"
            startup_health["degraded_reasons"] = degraded_reasons

        startup_health["components"] = {
            "rust_core": rust_core_status(),
            "llm_router": {
                "backend_mode": application.state.llm_backend_mode,
                "configured": application.state.openai_router is not None,
                "active": application.state.llm_backend_mode == "unified",
                "model_groups": (
                    sorted(application.state.openai_router.model_groups)
                    if application.state.openai_router is not None
                    else []
                ),
            },
        }
        application.state.startup_health = startup_health

        # v5.0 - Redis + Agent Rack init
        if HAS_AGENT_RACK:
            try:
                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                # TEK bus: init_tracker zaten init_redis_bus çağırır; ikinci bir
                # bağlantı açılmasın (önceden 2 istemci açılıyor, biri sızıyordu).
                tracker = await init_tracker(redis_url)
                bus = tracker.redis_bus
                application.state.redis_bus = bus
                transport = "redis" if getattr(bus, "_use_redis", False) else "in-memory"
                logger.info(f"Agent Rack aktif (telemetri taşıyıcı: {transport})")
            except Exception as e:
                logger.warning(f"Agent Rack init hatasi (fallback): {e}")
                application.state.redis_bus = None
        else:
            application.state.redis_bus = None

    except (StartupDependencyError, SecurityConfigurationError) as exc:
        application.state.startup_health = exc.as_dict()
        logger.critical("Startup security/dependency gate failed: %s", exc.error_code)
        raise

    yield
    # Kapanista odalari TEK bir yoldan kapat
    for client_id in list(application.state.rooms):
        room = application.state.rooms.get(client_id)
        if room is not None:
            _close_room(client_id, room)
    application.state.rooms.clear()
    _rooms_last_seen.clear()
    # Redis disconnect
    try:
        if hasattr(application.state, 'redis_bus') and application.state.redis_bus:
            await application.state.redis_bus.disconnect()
    except Exception:
        pass

app = FastAPI(title="PINEAL-HERETIC v3.0.0-rc.1 API", lifespan=lifespan)
app.state.llm_backend_mode = "legacy"
app.state.openai_router = None
app.state.startup_health = {
    "status": "starting",
    "error_code": None,
    "dependencies": [],
    "components": {"rust_core": rust_core_status()},
}


@app.get("/health")
async def health():
    health_status = app.state.startup_health
    status = health_status.get("status")
    # "failed" → 503 (bağımlılık eksik veya security gate açılmamış)
    # "degraded" → 200 (servis çalışıyor ama kısmi; load-balancer geçirir,
    #   monitoring aracı degraded_reasons / error_code ile alarm üretir)
    # "ready" → 200
    # diğer (starting, None) → 503
    if status == "failed":
        return JSONResponse(health_status, status_code=503)
    if status in ("ready", "degraded"):
        return JSONResponse(health_status, status_code=200)
    return JSONResponse(health_status, status_code=503)


# --- CORS (FAZ 3): ayni-origin serviste CORS gereksizdir; disaridan erisim
# istenirse PINEAL_ALLOWED_ORIGINS ile acilir. Varsayilan yalnizca localhost. ---
_default_origins = [
    "http://localhost:8000", "http://127.0.0.1:8000",
    "http://localhost:5173", "http://127.0.0.1:5173",
]
_allowed = os.getenv("PINEAL_ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [o.strip() for o in _allowed.split(",") if o.strip() and o.strip() != "*"] or _default_origins

class BodySizeLimitExceeded(Exception):
    pass


class BodySizeLimitMiddleware:
    """[P0-BOOT-FIX] İstek gövdesi tavanı middleware'i.

    uvicorn 0.52.4'te --limit-max-request-size bayrağı bulunmadığından
    tavan uygulama katmanında enforced edilir.
    Varsayılan: 1048576 bayt (1 MiB), PINEAL_MAX_BODY_BYTES ile geçersiz kılınabilir.
    """

    def __init__(self, app, max_bytes: Optional[int] = None):
        self.app = app
        if max_bytes is not None:
            self.max_bytes = max_bytes
        else:
            try:
                self.max_bytes = int(os.getenv("PINEAL_MAX_BODY_BYTES", "1048576"))
            except ValueError:
                self.max_bytes = 1048576

    def _get_max_bytes(self) -> int:
        try:
            return int(os.getenv("PINEAL_MAX_BODY_BYTES", str(self.max_bytes)))
        except ValueError:
            return self.max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        max_bytes = self._get_max_bytes()

        # 1. Content-Length başlığı kontrolü (erken ret)
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    content_length = int(value.decode("latin-1"))
                    if content_length > max_bytes:
                        await self._send_413(send, max_bytes)
                        return
                except (ValueError, UnicodeDecodeError):
                    pass
                break

        # 2. Akış / Parçalı (chunked) gövde kontrolü
        total_received = 0
        body_size_exceeded = False

        async def limited_receive():
            nonlocal total_received, body_size_exceeded
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                total_received += len(chunk)
                if total_received > max_bytes:
                    body_size_exceeded = True
                    raise BodySizeLimitExceeded()
            return message

        async def tracked_send(message):
            if body_size_exceeded:
                return
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except Exception:
            pass

        if body_size_exceeded:
            await self._send_413(send, max_bytes)

    async def _send_413(self, send, max_bytes: int):
        body = json.dumps({
            "code": "BODY_TOO_LARGE",
            "error": {
                "code": "BODY_TOO_LARGE",
                "message": f"Request body exceeds maximum allowed size of {max_bytes} bytes",
                "max_bytes": max_bytes,
            },
            "max_bytes": max_bytes,
        }).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("latin-1")),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "X-API-Key",
        "Authorization",
        "X-Pineal-Tool-Optimization",
        "X-Pineal-Routing-Strategy",
    ],
    expose_headers=[
        "X-Pineal-Call-ID",
        "X-Pineal-Call-IDs",
        "X-Pineal-Route-ID",
        "X-Pineal-Route-Mode",
        "X-Pineal-Routing-Strategy",
        "X-Pineal-Optimization-Mode",
        "X-Pineal-Optimization-Bytes-Saved",
        "X-Pineal-Optimization-Lossy",
    ],
)
app.add_middleware(BodySizeLimitMiddleware)

# --- Auth (FAZ 3): PINEAL_TOKEN tanimliysa /api/* ve OpenAI uyumlu /v1/*
# kimlik doğrulaması ister. /v1 ayrıca standart Authorization: Bearer biçimini
# kabul eder; bu anahtar hiçbir zaman upstream provider anahtarı olarak kullanılmaz. ---
def _openai_error(message: str, error_type: str, code: str, param: Optional[str] = None) -> dict:
    return {
        "error": {
            "message": message,
            "type": error_type,
            "param": param,
            "code": code,
        }
    }


def _secure_path(request: Request) -> str:
    """Güvenlik kararları için TEK GERÇEK kaynak: ham ASGI path.

    [AUDIT 2026-09-11 P0-1 / CVE-2026-48710 "BadHost", GHSA-86qp-5c8j-p5mr]
    request.url, DOĞRULANMAMIŞ Host header'ından yeniden kurulur: Starlette
    <=1.0.0'da Host içine '/', '?' veya '#' yerleştirilerek request.url.path,
    router'ın dispatch ettiği GERÇEK path'ten farklı gösterilebilir ve
    startswith("/api/") tarzı kontroller atlatılır (ampirik PoC:
    starlette 0.37.2 + Host: x/zzz?y= -> tokensiz istek /api/* ucundan 200 aldı).
    scope["path"] sunucunun aldığı ham yoldur; Host zehirlenmesinden etkilenmez.
    Eksikse boş döner -> hiçbir güvenlik öneki eşleşmez (fail-closed).
    """
    return request.scope.get("path", "")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = _secure_path(request)
    is_api = path.startswith("/api/")
    is_openai = path.startswith("/v1/")
    if (is_api or is_openai) and request.method != "OPTIONS":
        try:
            posture = security_posture()
        except SecurityConfigurationError as exc:
            body = (
                _openai_error(
                    "Secure startup configuration required",
                    "server_error",
                    exc.error_code,
                )
                if is_openai
                else {"error": {"code": exc.error_code, "message": "Secure startup configuration required"}}
            )
            return JSONResponse(body, status_code=503)

        presented_token = request.headers.get("x-api-key")
        if is_openai:
            authorization = request.headers.get("authorization", "")
            scheme, separator, bearer = authorization.partition(" ")
            if separator and scheme.lower() == "bearer" and bearer:
                presented_token = bearer
        if posture["auth_required"] and not token_matches(presented_token):
            body = (
                _openai_error(
                    "Invalid or missing API key",
                    "authentication_error",
                    "invalid_api_key",
                )
                if is_openai
                else {"error": {"code": "UNAUTHORIZED", "message": "X-API-Key gerekli veya hatalı"}}
            )
            return JSONResponse(body, status_code=401)

        identity = presented_token or (request.client.host if request.client else "unknown")
        identity_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        # [AUDIT P1-18a] Hız sınırı kimliği SUNUCUDAN türetilir ve handler'lara
        # buradan aktarılır. Eskiden handler'lar istemcinin gönderdiği
        # client_id'yi anahtar olarak kullanıyordu; client_id her istekte
        # değiştirilince sınır hiç devreye girmiyordu (ölçülen: 200/200 geçti).
        request.state.rate_identity = identity_hash
        if path.startswith("/api/experimental/"):
            if not rate_limit(f"experimental:{identity_hash}", "experimental"):
                return JSONResponse(
                    {"error": {"code": "RATE_LIMITED", "message": "Experimental endpoint rate limit exceeded"}},
                    status_code=429,
                )
        elif is_openai and not rate_limit(f"openai:{identity_hash}", "openai"):
            return JSONResponse(
                _openai_error(
                    "OpenAI-compatible endpoint rate limit exceeded",
                    "rate_limit_error",
                    "rate_limit_exceeded",
                ),
                status_code=429,
            )
        # [AUDIT P1-18b] Genel kova yalnızca MUTASYON yöntemlerine uygulanır.
        # Tek kova tüm yöntemleri paylaşsaydı ucuz GET'ler (telemetri, görev
        # listesi) mutasyonlar için gereken bütçeyi tüketiyordu — ölçülen:
        # 305 GET sonrası aynı kimlik POST'larında erken 429.
        if (
            is_api
            and request.method not in ("GET", "HEAD", "OPTIONS")
            and not rate_limit(f"api:{identity_hash}", "api")
        ):
            return JSONResponse(
                {"error": {"code": "RATE_LIMITED", "message": "API rate limit exceeded"}},
                status_code=429,
            )
    return await call_next(request)


# --- Tutarli hata modeli (FAZ 3) ---
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    body = (
        _openai_error(str(exc.detail), "invalid_request_error", str(exc.status_code))
        if _secure_path(request).startswith("/v1/")
        else {"error": {"code": str(exc.status_code), "message": str(exc.detail)}}
    )
    return JSONResponse(body, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    if not _secure_path(request).startswith("/v1/"):
        return await request_validation_exception_handler(request, exc)
    first_error = exc.errors()[0] if exc.errors() else {}
    location = first_error.get("loc", ())
    param = ".".join(str(part) for part in location if part != "body") or None
    return JSONResponse(
        _openai_error(
            "Invalid chat completion request",
            "invalid_request_error",
            "validation_error",
            param,
        ),
        status_code=422,
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    body = (
        _openai_error("Internal server error", "server_error", "internal_error")
        if _secure_path(request).startswith("/v1/")
        else {"error": {"code": "INTERNAL", "message": type(exc).__name__}}
    )
    return JSONResponse(body, status_code=500)


# --- Basit kayan-pencere rate limit (FAZ 3; ek bagimlilik yok) ---
RATE_LIMITS = {
    # [AUDIT P1-18b] Genel /api/ arka plan kovası. Eskiden /api/vault,
    # /api/override, /api/executor/intervene, /api/tasks*, /api/telemetry,
    # /api/aspasia/state ve /api/scraper/authorize-alternative uçlarında HİÇ
    # hız sınırı yoktu. 300/60sn ölçülerek seçildi: frontend'de polling yok
    # (setInterval sıfır), CI smoke en kötü 30 telemetri isteği atıyor.
    "api": (300, 60),
    "initiate": (5, 60),
    "aspasia": (20, 60),
    "experimental": (10, 60),
    "openai": (60, 60),
    # [FAZ C · C2] Seslendirme: yerel motor da olsa sınırsız istek kabul
    # edilmez (disk + CPU). Ölçülen ihtiyaç: tur başına birkaç cümle.
    "speech": (30, 60),
    # [FAZ D · D3] Medya hattı: indirme + kare kare çözümleme ağır; sınırsız
    # bırakılmaz (disk + CPU + ağ).
    "media": (6, 60),
    # [FAZ D · D5] Rapor fabrikası: PDF/diyagram/video üretimi diski ve CPU'yu
    # kullanır; sınırsız bırakılmaz.
    "report": (10, 60),
    # [FAZ D · D6] Kurum hedefi: theHarvester koşusu ağır (arama motoru
    # zinciri); SEO/kişi modu birkaç HTTP isteği. Sınırsız bırakılmaz.
    "company": (8, 60),
    # [FAZ D · D2] Yerel jüri: her oylama KADAR yerel model çağrısı yapar
    # (koltuk sayısı × istek). Sınırsız bırakmak yerel GPU'yu kilitler.
    "jury": (6, 60),
    # [FAZ D · D4] Dil tespiti/çeviri: tespit saf hesaptır ama çeviri yerel
    # motor çalıştırır; ikisi de sınırsız istek kabul etmez.
    "language": (60, 60),
}  # (request count, window seconds)
class _RateBucket:
    """Kayan pencere olayları + BU kovaya ait pencere süresi.

    [AUDIT P0-5 v3] Pencere kovayla birlikte saklanmak zorunda. Eskiden
    yalnızca deque tutuluyordu ve süpürme "en geniş pencere"yi (tüm
    kovaların maksimumu, 60 sn) kullanmak zorunda kalıyordu: 1 sn'lik bir
    kovadaki anahtar 60 sn boyunca bellekte kalıyordu. Ölçülen: 30.000 tekil
    anahtar, pencere dolmuş, süpürme çalışıyor -> 30.000 kova hâlâ yerinde.
    """

    __slots__ = ("events", "window")

    def __init__(self, window: float):
        self.events: deque = deque()
        self.window = window


_rate_buckets: Dict[str, _RateBucket] = {}


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


# [AUDIT P0-5] defaultdict her erişimde kalıcı bir anahtar yaratıyordu ve hiçbir
# zaman silinmiyordu (ölçülen: 5000 farklı kimlik -> 5000 kalıcı deque).
# identity ya token ya da istemci IP'si olduğundan bu, internete açık bir uçta
# durdurulamaz bir bellek sızıntısıdır. İki savunma eklendi: boşalan kova anında
# geri verilir ve anahtar sayısı sert bir tavanla sınırlanır.
_MAX_RATE_BUCKETS = _bounded_env_int("PINEAL_MAX_RATE_BUCKETS", 100_000, 1_000, 10_000_000)
# [AUDIT P0-5 v2] Süpürme artık ZAMANA da bağlı. Eskiden yalnızca tavan
# aşıldığında çalışıyordu; ölçülen iki kusur:
#   (a) 60.000 tekil anahtar -> 60.000 kalıcı kova / 50.3 MB, hepsinin penceresi
#       dolmuş ama tavana kadar HİÇBİRİ geri kazanılmıyor (P0-2'nin ikizi).
#   (b) tavan aşıldığında süpürme HER yeni istekte çalışıyor ve tüm sözlüğü
#       sorted() ile sıralıyordu -> üretim tavanında ölçülen ~48-57 ms/istek
#       (kendi kendine DoS).
_RATE_SWEEP_INTERVAL_SECONDS = max(1.0, float(
    os.getenv("PINEAL_RATE_SWEEP_INTERVAL_SECONDS", "60")
))
_rate_sweep_deadline = time.monotonic() + _RATE_SWEEP_INTERVAL_SECONDS


def _maybe_sweep_rate_buckets(now: float) -> None:
    """Süresi geldiyse süpür. Her çağrıda tek float karşılaştırması (~50 ns)."""
    global _rate_sweep_deadline
    if now >= _rate_sweep_deadline:
        # Son tarih önce yenilenir: süpürme patlasa bile her istekte yeniden
        # denenmez, maliyet tek bir isteğe yığılmaz.
        _rate_sweep_deadline = now + _RATE_SWEEP_INTERVAL_SECONDS
        _sweep_rate_buckets(now)


def _sweep_rate_buckets(now: float) -> None:
    """Süresi dolmuş kovaları geri kazanır, gerekirse tavanın altına indirir.

    Üç aşama:
      1. Kendi penceresi dolmuş veya boş kovalar silinir — bunları düşürmek
         hiçbir limiti gevşetmez. Pencere KOVADA saklandığı için ayıklama
         kova başına doğrudur (bkz. _RateBucket).
      2. Hâlâ tavandaysa EN ESKİ (LRU) kovalar düşürülür.
      3. HİSTEREZİS: tavan-1'e değil tavanın ~%80'ine inilir. Aksi halde
         süpürme her yeni istekte yeniden tetikleniyordu (ölçülen ~57 ms/istek).
    """
    for key in [
        k for k, b in _rate_buckets.items()
        if not b.events or now - b.events[-1] > b.window
    ]:
        _rate_buckets.pop(key, None)
    target = max(1, _MAX_RATE_BUCKETS - max(1, _MAX_RATE_BUCKETS // 5))
    overflow = len(_rate_buckets) - target
    if overflow > 0:
        oldest = sorted(
            _rate_buckets,
            key=lambda k: _rate_buckets[k].events[-1] if _rate_buckets[k].events else 0.0,
        )
        for key in oldest[:overflow]:
            _rate_buckets.pop(key, None)


# [AUDIT P1-18a] Kimlik yoksa TÜM kimliksiz çağıranlar tek ortak kovayı
# paylaşır. Fail-safe: "kimlik yok -> sınırsız" değil, "kimlik yok -> paylaşımlı
# ve sınırlı". Doğrudan handler çağrısı (test) da sınırsız yol bulamaz.
_UNIDENTIFIED_RATE_IDENTITY = "unidentified"


def _rate_identity(request: Request) -> str:
    """Hız sınırı için sunucudan türetilmiş kimliği döndürür.

    Handler'lar eskiden `req.client_id` kullanıyordu — bu, istemcinin gövdede
    gönderdiği bir alan. Ölçülen: aynı client_id ile 8 istek -> 3/8 429
    (sınır çalışıyor); her istekte farklı client_id -> 200 istek, 0/200 429.
    """
    identity = getattr(getattr(request, "state", None), "rate_identity", None)
    return identity or _UNIDENTIFIED_RATE_IDENTITY


def rate_limit(key: str, bucket: str) -> bool:
    """True = izin ver; False = limit asildi (429)."""
    limit, window = RATE_LIMITS.get(bucket, (999, 1))
    now = time.monotonic()
    _maybe_sweep_rate_buckets(now)
    bucket = _rate_buckets.get(key)
    if bucket is None:
        if len(_rate_buckets) >= _MAX_RATE_BUCKETS:
            _sweep_rate_buckets(now)
        bucket = _rate_buckets[key] = _RateBucket(window)
    elif bucket.window != window:
        bucket.window = window          # RATE_LIMITS çalışma zamanında değişti
    events = bucket.events
    while events and now - events[0] > window:
        events.popleft()
    if len(events) >= limit:
        return False
    # [AUDIT P0-5] Boşalan kova burada silinMEZ: izin verilen her çağrı hemen
    # aşağıdaki append ile anahtarı geri koyardı, yani silme ölü koddu
    # (mutasyon testiyle doğrulandı: satırı kaldırmak hiçbir testi kızartmadı).
    # Geri kazanımın gerçek yolları zaman temelli _maybe_sweep_rate_buckets ve
    # tavan acil-durum süpürmesidir.
    events.append(now)
    return True

app.state.rooms = {}  # client_id -> {"executor": PinealExecutor, "vault": {}, "websockets": set()}

# W5: tarayici yetenegi probu (300sn cache). Telemetri artik import basarisi
# degil, GERCEK capability raporlar (x_scraper / instagram_scraper / browser_installed).
# [FIX] TTL 60sn idi: her 60sn'de bir PLAYWRIGHT SÜRÜCÜSÜ KALKIP
# executable_path'i soruyordu (process spawn + import maliyeti). 300sn'ye
# çakıldı; ayrıca PINEAL_CHROMIUM_PATH set edilmişse playwright'a
# DOKUNMADAN kısa devre edilir (deploy'da yol bizde, prob gereksiz).
_TELEMETRY_CAPABILITY_TTL_S = 300.0
_telemetry_capability = {"ts": 0.0, "value": None}
_telemetry_capability_lock = asyncio.Lock()


async def _scraper_capability() -> dict:
    now = time.monotonic()
    cached = _telemetry_capability["value"]
    if cached is not None and now - _telemetry_capability["ts"] < _TELEMETRY_CAPABILITY_TTL_S:
        return cached
    async with _telemetry_capability_lock:
        cached = _telemetry_capability["value"]
        if cached is not None and time.monotonic() - _telemetry_capability["ts"] < _TELEMETRY_CAPABILITY_TTL_S:
            return cached
        result = {"instagram": False, "browser": False}
        pinned = os.environ.get("PINEAL_CHROMIUM_PATH", "").strip()
        if pinned and os.path.exists(pinned):
            # [FIX] Pinlenmiş executable: sürücü spawn etmeden doğrula.
            result["browser"] = True
            result["instagram"] = True
        else:
            try:
                if InstagramGhostScraper is not None:
                    from playwright.async_api import async_playwright
                    async with async_playwright() as p:
                        exe = p.chromium.executable_path
                        result["browser"] = bool(exe and os.path.exists(exe))
                        result["instagram"] = result["browser"]
            except Exception:
                result = {"instagram": False, "browser": False}
        _telemetry_capability["ts"] = time.monotonic()
        _telemetry_capability["value"] = result
        return result

VAULT_FILE = ".pineal_vault.json"


def _load_vault(vault_file: str = VAULT_FILE) -> dict:
    """[AUDIT P0-3] Kasayı HER ZAMAN bir dict olarak döndürür.

    Eskiden ``json.load`` bir try/except içindeydi ama sonrasındaki
    ``vault.pop(...)`` / ``vault.get(...)`` çağrıları korumasızdı. Dosya bir
    JSON dizisi/null/metin/sayı içerdiğinde (elle düzenleme, yarım kalan yazma)
    ``get_room`` TypeError/AttributeError atıyordu ve get_room HER endpoint'in
    giriş kapısı olduğu için tüm API 500 dönüyordu — üstelik sessizce, log yok.
    """
    if not os.path.exists(vault_file):
        return {}
    try:
        with open(vault_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        logger.warning(
            "VAULT_CORRUPT: %s okunamadı (%s: %s); boş kasa ile devam ediliyor",
            vault_file, type(exc).__name__, exc,
        )
        return {}
    if not isinstance(data, dict):
        logger.error(
            "VAULT_SCHEMA_INVALID: %s bir JSON nesnesi değil (%s); yok sayıldı",
            vault_file, type(data).__name__,
        )
        return {}
    return data


# KASA SEMASI — yerel .pineal_vault.json'daki GERCEK yapi:
#   {"providers": {"<operator-adi>": {"api_key": "..."}, ...}}
# Operator adlandirmasi serbest metindir ("gemini", "nvidia", "deepseek",
# ...); normalize edilip gateway provider ID'sine cevrilir. Degerler ASLA
# loglanmaz/isaretlenmez/dondurulmez — yalniz ID listeleri (ad/adet).
_VAULT_PROVIDER_ALIASES: dict = {
    "groq": "groq",
    "deepseek": "deepseek",
    "cerebras": "cerebras",
    "nousresearch": "nous-research",
    "nous": "nous-research",
    "nousportal": "nous-research",
    "mistral": "mistral",
    "together": "together",
    "fireworks": "fireworks",
    "alibabadashscope": "alibaba-dashscope",
    "dashscope": "alibaba-dashscope",
    "alibaba": "alibaba-dashscope",
    "sambanova": "sambanova",
    "nvidianim": "nvidia-nim",
    "nvidiannim": "nvidia-nim",  # "NVIDIA NIM" yazimi
    "nvidia": "nvidia-nim",
    "nim": "nvidia-nim",
    "huggingface": "huggingface",
    "hf": "huggingface",
    "deepinfra": "deepinfra",
    "perplexity": "perplexity",
    "google": "google-gemini",
    "gemini": "google-gemini",
    "googlegemini": "google-gemini",
    "geminibackup": "google-gemini-backup",
    "googlegeminibackup": "google-gemini-backup",
    "vertex": "google-gemini-vertex",
    "geminivertex": "google-gemini-vertex",
    "googlegeminivertex": "google-gemini-vertex",
    "openai": "openai",
    "anthropic": "anthropic",
    "xai": "xai",
    "grok": "xai",
    "cohere": "cohere",
    "azureopenai": "azure-openai",
    "azure": "azure-openai",
    "iflow": "iflow",
    # OpenRouter ozel: legacy istemci anahtaridir (set_provider_key degil
    # set_key yoluna duser); yalniz top-level `api_key` yoksa yedek olur.
    "openrouter": "openrouter",
    "or": "openrouter",
    "ninerouter": "openrouter",
    "9router": "openrouter",
}


def _normalize_vault_provider_name(name: object) -> str:
    """Kasa operator adini karsilastirilabilir forma indirir (kucuk harf;
    bosluk/tire/alt-cizgi/nokta yoksayilir)."""
    if not isinstance(name, str):
        return ""
    return "".join(ch for ch in name.strip().lower() if ch not in " -_.")


def _extract_vault_provider_keys(vault: dict) -> tuple:
    """Kasa dict'inden saglayici anahtarlarini cikarir (salt-okur ayristirma).

    Kaynaklar (sirasiyla):
      1. `providers.{ad}.api_key` — operator envanteri (GERCEK yerel sema).
         Duz-metin deger (`{"deepseek": "sk-..."}`) uyumluluk icin kabul edilir.
      2. `provider_keys.{pid}` — eski duz sozlesme; ayni dosyada varsa EZER
         (acik override).

    Donus: (uygulanan {pid: key}, openrouter_yedek_key|None,
            {"unknown": [adlar], "malformed": [adlar]}).
    Cagiran, donen ham dict'leri kasadan DUSURMELIDIR (sir hijyeni: degerler
    oda durumunda barinmaz); bu fonksiyon kasa dict'ini DEGISTIRMEZ.
    """
    applied: dict = {}
    openrouter_key = None
    skipped: dict = {"unknown": [], "malformed": []}
    if not isinstance(vault, dict):
        return applied, openrouter_key, skipped
    providers = vault.get("providers")
    if isinstance(providers, dict):
        for raw_name, entry in providers.items():
            norm_name = _normalize_vault_provider_name(raw_name)
            if norm_name in ("sandbox",):
                continue
            if norm_name in ("searchandosint", "searchosint", "searchandall", "search"):
                if isinstance(entry, dict):
                    for sk in ("tavily", "serpapi", "exa"):
                        val = entry.get(sk)
                        if isinstance(val, str) and val.strip():
                            k_name = f"{sk}_key"
                            if not vault.get(k_name):
                                vault[k_name] = val.strip()
                continue
            pid = _VAULT_PROVIDER_ALIASES.get(norm_name)
            if pid is None:
                skipped["unknown"].append(str(raw_name))
                continue
            if isinstance(entry, dict):
                if pid == "google-gemini":
                    prim = entry.get("primary_api_key") or entry.get("api_key")
                    back = entry.get("backup_api_key")
                    vert = entry.get("vertex_token")
                    found_any = False
                    if isinstance(prim, str) and prim.strip():
                        applied["google-gemini"] = prim.strip()
                        found_any = True
                    if isinstance(back, str) and back.strip():
                        applied["google-gemini-backup"] = back.strip()
                        found_any = True
                    if isinstance(vert, str) and vert.strip():
                        applied["google-gemini-vertex"] = vert.strip()
                        found_any = True
                    if not found_any:
                        skipped["malformed"].append(str(raw_name))
                    continue
                key = entry.get("api_key")
            elif isinstance(entry, str):
                key = entry
            else:
                key = None
            if not isinstance(key, str) or not key.strip():
                skipped["malformed"].append(str(raw_name))
                continue
            if pid == "openrouter":
                openrouter_key = key.strip()
            else:
                applied[pid] = key.strip()
    flat = vault.get("provider_keys")
    if isinstance(flat, dict):
        for raw_pid, key in flat.items():
            pid = raw_pid.strip().lower() if isinstance(raw_pid, str) else ""
            if not pid or not isinstance(key, str) or not key.strip():
                skipped["malformed"].append(str(raw_pid))
                continue
            if pid == "openrouter":
                openrouter_key = key.strip()
            else:
                applied[pid] = key.strip()
    return applied, openrouter_key, skipped


# [FORENSIC VAULT-INTERLOCK] Kilit, dosyanın VARLIĞIYLA değil, içindeki GERÇEK
# sır malzemesiyle açılır. Eskiden `_check_vault_interlock` dosya dict'inin
# truthiness'ına bakıyordu: `{"use_local": true}` gibi anahtarsız bir dosya,
# hatta `sk-or-v1-YOUR...` placeholder'ı bile kilidi açıyordu. Artık her bayrak
# kurulum yolu (`get_room`, `/api/vault`) ve dosya denetimi aynı
# `_is_real_key` kapısından geçer; placeholder fail-closed reddedilir.
# Değerler ASLA loglanmaz/döndürülmez — bu yardımcılar yalnızca boolean üretir.
_PLACEHOLDER_KEY_PREFIXES: tuple = ("sk-or-v1-YOUR",)
_PLACEHOLDER_KEY_MARKERS: tuple = (
    "YOUR_", "YOUR-", "YOUR ", "_YOUR",
    "PLACEHOLDER", "EXAMPLE", "CHANGE_ME", "CHANGEME",
    "REPLACE_ME", "REPLACEME", "INSERT_", "SAMPLE_KEY",
)
_SEARCH_CONTAINER_NAMES: frozenset = frozenset({
    "searchandosint", "searchosint", "searchandall", "search",
})


def _is_placeholder_key(value: object) -> bool:
    """Placeholder/örnek anahtar metni mi? (fail-closed sınıflandırıcı)"""
    if not isinstance(value, str):
        return True
    text = value.strip()
    if not text:
        return True
    for prefix in _PLACEHOLDER_KEY_PREFIXES:
        if text.startswith(prefix):
            return True
    upper = text.upper()
    return any(marker in upper for marker in _PLACEHOLDER_KEY_MARKERS)


def _is_real_key(value: object) -> bool:
    """Gerçek sır malzemesi mi? Boş + placeholder reddedilir."""
    return (
        isinstance(value, str)
        and bool(value.strip())
        and not _is_placeholder_key(value)
    )


def _cookie_pool_has_key(value: object) -> bool:
    """Çok satırlı cookie havuzunda en az bir gerçek satır var mı?"""
    if not isinstance(value, str):
        return False
    lines = [line for line in value.splitlines() if line.strip()]
    if not lines:
        return _is_real_key(value)
    return any(_is_real_key(line) for line in lines)


def _vault_file_has_key_material(vault: dict) -> bool:
    """Dosya kasasında GERÇEK anahtar malzemesi var mı? (salt-okur)

    `providers.*`, `provider_keys.*`, top-level `api_key`, arama anahtarları,
    `x_cookie` / `ig_sessionid` taranır. (Interlock `_vault_bears_key_material`
    kullanır; bu yardımcı `/api/vault/status` raporu içindir.)
    """
    if not isinstance(vault, dict) or not vault:
        return False
    if _is_real_key(vault.get("api_key")):
        return True
    for field in ("ig_sessionid", "tavily_key", "serpapi_key", "exa_key"):
        if _is_real_key(vault.get(field)):
            return True
    if _cookie_pool_has_key(vault.get("x_cookie")):
        return True
    providers = vault.get("providers")
    if isinstance(providers, dict):
        for raw_name, entry in providers.items():
            norm_name = _normalize_vault_provider_name(raw_name)
            if norm_name in _SEARCH_CONTAINER_NAMES:
                if isinstance(entry, dict):
                    for sk in ("tavily", "serpapi", "exa"):
                        if _is_real_key(entry.get(sk)):
                            return True
                continue
            if isinstance(entry, dict):
                for key_field in ("primary_api_key", "backup_api_key", "vertex_token", "api_key"):
                    if _is_real_key(entry.get(key_field)):
                        return True
            elif _is_real_key(entry):
                return True
    flat = vault.get("provider_keys")
    if isinstance(flat, dict):
        for _pid, key in flat.items():
            if _is_real_key(key):
                return True
    return False


def _room_vault_unlocked(vault: dict) -> bool:
    """Oda kasası açık mı? Bayraklar YALNIZCA gerçek malzemeyle kurulur
    (`get_room` + `/api/vault` aynı kapıdan geçer), bu yüzden bayraklar
    güvenilirdir. `/api/vault/lock` bayrakları temizler -> kilitli."""
    if not isinstance(vault, dict):
        return False
    if vault.get("or_key") is True:
        return True
    if vault.get("provider_keys_set"):
        return True
    if vault.get("search_keys") is True:
        return True
    if _is_real_key(vault.get("ig_sessionid")):
        return True
    return _cookie_pool_has_key(vault.get("x_cookie"))


# [AUDIT P0-4] Oda kayıt defteri sınırları. client_id istemcinin seçtiği,
# doğrulanmayan bir string olduğu için sınırsız oda = sınırsız PinealExecutor +
# sender task + kuyruk = OOM (ölçülen: 300 farklı client_id -> 300 kalıcı oda).
_MAX_ROOMS = _bounded_env_int("PINEAL_MAX_ROOMS", 512, 1, 1_000_000)
# Üretecin biçimi "client_<7 karakter>"; 64 geniş bir pay bırakır.
_MAX_CLIENT_ID_LENGTH = _bounded_env_int("PINEAL_MAX_CLIENT_ID_LENGTH", 64, 8, 4_096)
# [AUDIT R3] validate_identifier'ın regex'i uzunluk SINIRLAMIYOR
# (^[A-Za-z0-9_-]+$). client_id'ye 64-char tavan eklenmişti; aynı koruma
# task_id giriş noktalarına taşınmadı (ChatPayload.task_id gövdede SINIRSIZ,
# /api/tasks/{task_id}/cancel|halt path param'ı doğrulanmıyordu). Sunucu
# ürettiği task_id 27 karakter (op_YYYYMMDDHHMMSS_<8hex>); 128 geniş paydır.
_MAX_TASK_ID_LENGTH = _bounded_env_int("PINEAL_MAX_TASK_ID_LENGTH", 128, 8, 4_096)
_MAX_TERMINATE_REASON_LENGTH = 500
_ROOM_TTL_SECONDS = float(os.getenv("PINEAL_ROOM_TTL_SECONDS", "1800"))
_rooms_last_seen: Dict[str, float] = {}


class RoomCapacityExceeded(RuntimeError):
    """Eşzamanlı oda tavanı aşıldı; istemciye 503 olarak yansıtılır."""


@app.exception_handler(RoomCapacityExceeded)
async def room_capacity_handler(request: Request, exc: RoomCapacityExceeded):
    """[AUDIT P0-4] Oda tavanı bir hata değil, kasıtlı bir korumadır.

    500 değil 503 döner: istemci (ve yük dengeleyici) bunu "geçici, tekrar
    denenebilir" olarak yorumlar; 500 ile karıştırılıp alarm üretilmez.
    """
    logger.warning("ROOM_CAPACITY_EXCEEDED path=%s", _secure_path(request))
    body = (
        _openai_error("Server room capacity exceeded", "server_error", "room_capacity_exceeded")
        if _secure_path(request).startswith("/v1/")
        else {"error": {"code": "ROOM_CAPACITY_EXCEEDED", "message": str(exc)}}
    )
    return JSONResponse(body, status_code=503)


# [FIX #7] _close_room senkron bir helper (evictor/sweeper'dan await
# edilmez). Browser kapatma async olduğundan detached task + done-callback
# ile garanti edilir; done-callback seti büyütmekten de korur.
_detached_tasks: set = set()


def _detach_browser_close(sess) -> None:
    async def _runner() -> None:
        try:
            await sess.close()
        except Exception:
            logger.warning("ODA KAPANIYOR: browser session kapatma hatası", exc_info=True)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # loop yoksa (sync context): evictor zaten loop içinden çağrılır
    t = loop.create_task(_runner())
    _detached_tasks.add(t)
    t.add_done_callback(_detached_tasks.discard)


def _close_room(client_id: str, room: dict) -> None:
    """Bir odayı kapatır: sender task, görev task'leri ve browser kapanır."""
    sender = room.get("sender_task")
    if sender is not None and not sender.done():
        sender.cancel()
    for mission in (room.get("mission_tasks") or {}).values():
        if not mission.done():
            mission.cancel()
    # [FIX #7] [026] Zombie Chromium: oda evict edilince görev cancel
    # edilirdi ama BrowserSession KALIYORDU (Chromium process'i sızıyordu).
    # Şimdi room'dan alınıp detached task ile kapatılır.
    sess = room.pop("browser", None)
    if sess is not None:
        _detach_browser_close(sess)
    # Not: aktif WebSocket'i olan bir oda _evict_rooms tarafından zaten
    # atlanır; burada soket kapatmaya çalışmak (close() bir coroutine'dir)
    # await edilemeyeceği için yapılmaz.
    app.state.rooms.pop(client_id, None)
    _rooms_last_seen.pop(client_id, None)


def _evict_rooms(now: float) -> int:
    """Boşta kalmış odaları geri kazanır. Aktif görevi/bağlantısı olan dokunulmaz."""
    if now - getattr(_evict_rooms, "_last_sweep", 0.0) < 5.0:
        return 0
    _evict_rooms._last_sweep = now
    evicted = 0
    for client_id in list(app.state.rooms):
        room = app.state.rooms.get(client_id)
        if room is None:
            continue
        if room.get("mission_tasks") or room.get("websockets"):
            continue
        if now - _rooms_last_seen.get(client_id, now) < _ROOM_TTL_SECONDS:
            continue
        _close_room(client_id, room)
        evicted += 1
    if evicted:
        logger.info("ROOM_EVICTION: %s boşta kalmış oda kapatıldı", evicted)
    return evicted


def get_room(client_id: str) -> dict:
    # [AUDIT P0-4] client_id bir güvenlik sınırıdır: biçim VE uzunluk
    # doğrulanır. validate_identifier'ın regex'i uzunluk sınırlamadığı için
    # (^[A-Za-z0-9_-]+$) 5 KB'lık bir client_id kabul ediliyordu; her biri
    # kalıcı bir sözlük anahtarı + tam bir oda demek.
    if not client_id or len(client_id) > _MAX_CLIENT_ID_LENGTH:
        raise HTTPException(status_code=400, detail="INVALID_CLIENT_ID")
    try:
        validate_identifier(client_id, field="client_id")
    except ValueError:
        raise HTTPException(status_code=400, detail="INVALID_CLIENT_ID") from None
    now = time.monotonic()
    _evict_rooms(now)
    _rooms_last_seen[client_id] = now
    if client_id not in app.state.rooms:
        if len(app.state.rooms) >= _MAX_ROOMS:
            raise RoomCapacityExceeded(
                f"ROOM_CAPACITY_EXCEEDED: {_MAX_ROOMS} eşzamanlı oda sınırına ulaşıldı"
            )
        executor = PinealExecutor(
            log_callback=lambda lvl, msg: sync_log(client_id, lvl, msg),
            emit_event_callback=lambda evt: sync_event(client_id, evt),
            snapshot_callback=lambda s: sync_snapshot(client_id, s)
        )
        # Otomatik Kasa (.pineal_vault.json / .env) yüklemesi
        vault = _load_vault()

        # KASA SEMASI: `providers.{ad}.api_key` (operator envanteri) + eski
        # duz `provider_keys` (ayni dosyada varsa ezer). Ham dict'ler odada
        # BARINMAZ: okunur okunmaz dusurulur (sir hijyeni), yalniz uygulanan/
        # atlanan ID listeleri isaretlenir (deger asla).
        file_provider_keys, file_or_key, file_skipped = _extract_vault_provider_keys(vault)
        vault.pop("providers", None)
        vault.pop("provider_keys", None)

        # Check if local 9router proxy is configured
        is_9router = "20128" in os.getenv("OPENROUTER_BASE_URL", "")
        ninerouter_key = os.getenv("NINEROUTER_API_KEY") or os.getenv("PINEAL_LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY")

        if is_9router and ninerouter_key and ninerouter_key.startswith("sk-pineal"):
            api_key = ninerouter_key
        else:
            api_key = vault.pop("api_key", None) or file_or_key or os.getenv("OPENROUTER_API_KEY")

        # [FORENSIC VAULT-INTERLOCK] Yalnızca GERÇEK anahtar bayrak kurar;
        # placeholder (`sk-or-v1-YOUR...` ve türevleri) fail-closed reddedilir.
        if _is_real_key(api_key):
            executor.llm_gateway.set_key(api_key)
            if shadow_executor is not None:
                shadow_executor.llm_gateway.set_key(api_key)
            if dialogue_manager is not None:
                dialogue_manager.llm.set_key(api_key)
            vault["or_key"] = True

        # Export direct keys to environment for underlying SDKs
        # [FORENSIC VAULT-INTERLOCK] Placeholder ortama YAZILMAZ (env kirliliği yok).
        if _is_real_key(file_provider_keys.get("google-gemini")):
            os.environ.setdefault("GEMINI_API_KEY", file_provider_keys["google-gemini"])
        if _is_real_key(file_provider_keys.get("google-gemini-backup")):
            os.environ.setdefault("GEMINI_BACKUP_API_KEY", file_provider_keys["google-gemini-backup"])

        # FAZ 3: dosyadan yuklenen dogrudan-saglayici anahtarlari (yukarida
        # parse edildi; ham dict'ler odadan dusuruldu). Yalniz oda executor
        # gateway'ine uygulanir (/api/vault'in aksine shadow/dialogue
        # kapsanmaz — dosya yuklemesi oda-scoped'tur).
        if file_provider_keys:
            applied = []
            for provider_id, provider_key in file_provider_keys.items():
                # [FORENSIC VAULT-INTERLOCK] Placeholder dosyadan bile gelse
                # havuza girmez; atlanan ID dürüstçe raporlanır (sir DEĞERİ asla).
                if not _is_real_key(provider_key):
                    file_skipped["malformed"].append(str(provider_id))
                    continue
                try:
                    executor.llm_gateway.set_provider_key(provider_id, provider_key)
                    applied.append(str(provider_id))
                except (ValueError, AttributeError):
                    file_skipped["unknown"].append(str(provider_id))
            if applied:
                vault["provider_keys_set"] = sorted(set(applied))
        if file_skipped["unknown"] or file_skipped["malformed"]:
            vault["provider_keys_skipped"] = {
                "unknown": sorted(set(file_skipped["unknown"])),
                "malformed": sorted(set(file_skipped["malformed"])),
            }
            logger.warning(
                "VAULT_PROVIDERS_SKIPPED: unknown=%s malformed=%s",
                vault["provider_keys_skipped"]["unknown"],
                vault["provider_keys_skipped"]["malformed"],
            )

        tavily = vault.get("tavily_key") or os.getenv("TAVILY_API_KEY")
        # [FIX] .env.example/SearchEngine "SERPAPI_API_KEY" kullanır; eski
        # "SERPAPI_KEY" yalnızca geriye uyumluluk için ikincil okunur.
        serpapi = vault.get("serpapi_key") or os.getenv("SERPAPI_API_KEY") or os.getenv("SERPAPI_KEY")
        exa = vault.get("exa_key") or os.getenv("EXA_API_KEY")
        # [FORENSIC VAULT-INTERLOCK] Placeholder arama anahtarları ne ortama
        # yazılır ne bayrak kurar (fail-closed).
        if not _is_real_key(tavily):
            tavily = None
        if not _is_real_key(serpapi):
            serpapi = None
        if not _is_real_key(exa):
            exa = None
        if tavily:
            os.environ.setdefault("TAVILY_API_KEY", tavily)
        if serpapi:
            os.environ.setdefault("SERPAPI_API_KEY", serpapi)
        if exa:
            os.environ.setdefault("EXA_API_KEY", exa)
        if tavily or serpapi or exa:
            executor.search_engine.set_keys(tavily=tavily, serpapi=serpapi, exa=exa)
            vault["search_keys"] = True
        # Vault explicit value wins; otherwise honour USE_LOCAL_LLM env
        # (do not treat missing key as False when env says true).
        if "use_local" in vault:
            use_local = bool(vault.get("use_local"))
        else:
            use_local = os.getenv("USE_LOCAL_LLM", "false").lower() == "true"
        executor.llm_gateway.use_local = use_local

        app.state.rooms[client_id] = {
            "executor": executor,
            "vault": vault,
            "websockets": set(),
            "logs": [],
            # ASPASIA PROMOTION: ayni kisi + denetim arayuzu + tek yazma kanali.
            # Komut dispatch'i /api/initiate'in kullandigi GERCEK görev akisina
            # baglidir; ikinci bir orchestrator yoktur.
            "aspasia": (AspasiaChief(
                llm_gateway=executor.llm_gateway,
                command_gateway=AspasiaCommandGateway(
                    dispatch=_aspasia_command_dispatch,
                    gateway=executor.llm_gateway,
                ),
                executor=executor,
            ) if AspasiaChief else None),
            "queue": asyncio.Queue(maxsize=2000),
            "sender_task": None,
            "mission_tasks": {},
            "lifecycle": TaskLifecycleRegistry(),
            "telemetry_delivery": {
                "state": "NORMAL",
                "dropped_messages_total": 0,
                "dropped_event_count": 0,
                "dropped_by_kind": {},
                # [BOSS-11] Çerçeve hataları aynı sözleşmede (şema sabit kalsın).
                "frame_errors_total": 0,
                "frame_errors_by_kind": {},
            },
        }
        # FIFO gonderici: tum log/event/snapshot/result mesajlari sirayla iletilir.
        try:
            loop = asyncio.get_running_loop()
            app.state.rooms[client_id]["sender_task"] = loop.create_task(
                _room_sender(app.state.rooms[client_id])
            )
        except RuntimeError:
            pass
    _prune_room_stale_state(app.state.rooms[client_id])  # [AUDIT R1]
    return app.state.rooms[client_id]

def get_executor(client_id: str) -> PinealExecutor:
    return get_room(client_id)["executor"]

def get_vault(client_id: str) -> dict:
    return get_room(client_id)["vault"]


def _room_browser(room: dict) -> BrowserSession:
    """Oda başına tek canlı tarayıcı (lazy)."""
    sess = room.get("browser")
    if sess is None:
        sess = BrowserSession()
        room["browser"] = sess
    return sess


class OpenAIChatCompletionPayload(BaseModel):
    """Supported, bounded subset of the OpenAI chat-completions request."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1, max_length=256)
    messages: list[dict[str, Any]] = Field(min_length=1, max_length=1024)
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    top_p: Optional[float] = Field(default=None, ge=0, le=1)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    max_completion_tokens: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    stop: Any = None
    tools: Optional[list[dict[str, Any]]] = Field(default=None, max_length=128)
    tool_choice: Any = None
    response_format: Optional[dict[str, Any]] = None
    seed: Optional[int] = None
    user: Optional[str] = Field(default=None, max_length=256)
    n: int = Field(default=1, ge=1, le=1)
    stream: bool = False
    stream_options: Optional[dict[str, Any]] = None

    @model_validator(mode="after")
    def validate_protocol_shape(self):
        if self.max_tokens is not None and self.max_completion_tokens is not None:
            raise ValueError("max_tokens and max_completion_tokens are mutually exclusive")
        allowed_roles = {"system", "developer", "user", "assistant", "tool", "function"}
        for message in self.messages:
            if not isinstance(message, dict) or message.get("role") not in allowed_roles:
                raise ValueError("every message requires a supported role")
        encoded = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > 1_048_576:
            raise ValueError("chat completion request exceeds 1 MiB")
        return self


def _openai_gateway():
    return get_executor("openai-compatible").llm_gateway


def _tool_optimization_policy(request: Request) -> tuple[str, OptimizationPolicy]:
    requested = request.headers.get("x-pineal-tool-optimization")
    mode = (requested or os.getenv("PINEAL_TOOL_OPTIMIZATION", "disabled")).strip().lower()
    if mode in {"disabled", "off", "none"}:
        return "disabled", OptimizationPolicy()
    if mode == "safe":
        return "safe", OptimizationPolicy(enabled=True)
    if mode == "lossy":
        return "lossy", OptimizationPolicy(
            enabled=True,
            engine_ids=(
                "strip-ansi",
                "compact-json",
                "collapse-repeated-lines",
                "head-tail",
            ),
            allow_lossy=True,
        )
    raise ValueError("tool optimization mode must be disabled, safe, or lossy")


def _routing_strategy(request: Request) -> RoutingStrategy:
    requested = request.headers.get("x-pineal-routing-strategy")
    value = (requested or os.getenv("PINEAL_ROUTING_STRATEGY", "auto")).strip().lower()
    try:
        return RoutingStrategy(value)
    except ValueError as exc:
        raise ValueError("unknown Pineal routing strategy") from exc


@app.get("/v1/models")
async def openai_models():
    gateway = _openai_gateway()
    now = int(time.time())
    models: dict[str, str] = {}
    routed = app.state.openai_router
    if app.state.llm_backend_mode == "unified" and routed is not None:
        models.update({
            model_id: "pineal-router"
            for model_id in routed.executable_models(gateway)
        })
    else:
        cloud_enabled = gateway.client is not None and (
            os.getenv("LIVE_LLM_E2E") == "1" or gateway.live_unlocked
        )
        if cloud_enabled:
            models.update({model_id: "openrouter" for model_id in gateway.MODEL_PRICING})
        if gateway.use_local and gateway.local_client is not None:
            models[gateway.local_model] = "local"
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": now,
                "owned_by": owner,
            }
            for model_id, owner in sorted(models.items())
        ],
    }


def _stream_chunk_dict(chunk: Any) -> dict[str, Any]:
    if hasattr(chunk, "model_dump"):
        value = chunk.model_dump(mode="json", exclude_none=True)
    elif isinstance(chunk, dict):
        value = chunk
    else:
        raise ValueError("invalid upstream stream chunk")
    if not isinstance(value, dict):
        raise ValueError("invalid upstream stream chunk")
    return value


def _openai_streaming_response(
    routed_stream,
    *,
    call_ids: tuple[str, ...],
    optimization_mode: str,
    optimization_bytes_saved: int,
    optimization_lossy: bool,
) -> StreamingResponse:
    async def event_source():
        chunks = routed_stream.stream.chunks
        try:
            async for chunk in chunks:
                data = json.dumps(
                    _stream_chunk_dict(chunk),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            raise
        except Exception:
            error = _openai_error(
                "The selected provider stream was interrupted after output began",
                "server_error",
                "stream_interrupted",
            )
            yield "data: " + json.dumps(error, separators=(",", ":")) + "\n\n"
        finally:
            # [AUDIT] Üretici (HTTP connection pool / websocket) kapanmazsa
            # her istekte bir bağlantı sızar; aclose() idiomatic kapanış.
            aclose = getattr(chunks, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except Exception:
                    pass
        yield "data: [DONE]\n\n"

    plan = routed_stream.plan
    headers = {
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
        "X-Pineal-Call-ID": routed_stream.stream.call_id,
        "X-Pineal-Call-IDs": ",".join(call_ids),
        "X-Pineal-Route-ID": plan.route_id,
        "X-Pineal-Route-Mode": plan.mode.value,
        "X-Pineal-Routing-Strategy": plan.strategy.value,
        "X-Pineal-Optimization-Mode": optimization_mode,
        "X-Pineal-Optimization-Bytes-Saved": str(optimization_bytes_saved),
        "X-Pineal-Optimization-Lossy": str(optimization_lossy).lower(),
    }
    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers=headers,
    )


@app.post("/v1/chat/completions")
async def openai_chat_completions(payload: OpenAIChatCompletionPayload, request: Request):
    from agent_core.services.llm_gateway import SpendCapExceeded

    if payload.stream and app.state.llm_backend_mode != "unified":
        return JSONResponse(
            _openai_error(
                "Streaming requires PINEAL_LLM_BACKEND=unified",
                "invalid_request_error",
                "streaming_requires_unified_backend",
                "stream",
            ),
            status_code=400,
        )
    if payload.stream and payload.tools:
        return JSONResponse(
            _openai_error(
                "Streaming tool calls are not enabled",
                "invalid_request_error",
                "streaming_tools_not_supported",
                "tools",
            ),
            status_code=400,
        )

    try:
        optimization_mode, optimization_policy = _tool_optimization_policy(request)
    except ValueError as exc:
        return JSONResponse(
            _openai_error(
                str(exc),
                "invalid_request_error",
                "invalid_optimization_mode",
            ),
            status_code=400,
        )
    try:
        routing_strategy = _routing_strategy(request)
    except ValueError as exc:
        return JSONResponse(
            _openai_error(
                str(exc),
                "invalid_request_error",
                "invalid_routing_strategy",
            ),
            status_code=400,
        )
    optimized = _tool_output_optimizer.optimize(
        {"messages": payload.messages, "tools": payload.tools},
        optimization_policy,
    )
    optimized_messages = optimized.body["messages"]
    optimized_tools = optimized.body["tools"]
    lossy_applied = any(
        engine_id in {"collapse-repeated-lines", "head-tail"}
        and savings.applications > 0
        for engine_id, savings in optimized.stats.engine_savings.items()
    )

    gateway = _openai_gateway()
    routed = app.state.openai_router
    effective_max_tokens = payload.max_tokens or payload.max_completion_tokens
    route_plan = None
    call_ids: tuple[str, ...] = ()
    try:
        with gateway.capture_calls(
            task_id=_new_task_id(),
            agent_id="openai-compatible",
        ) as call_scope:
            if app.state.llm_backend_mode == "unified":
                if routed is None:
                    raise RoutingRuntimeError("unified router is not configured")
                if not routed.handles(payload.model):
                    raise RoutingRuntimeError(
                        f"unknown unified model group: {payload.model}"
                    )
                if payload.stream:
                    routed_stream = await routed.start_chat_stream(
                        gateway,
                        messages=optimized_messages,
                        model=payload.model,
                        strategy=routing_strategy,
                        temperature=payload.temperature,
                        max_tokens=effective_max_tokens,
                        top_p=payload.top_p,
                        stop=payload.stop,
                        response_format=payload.response_format,
                        seed=payload.seed,
                        user=payload.user,
                        stream_options=payload.stream_options,
                    )
                    stream_call_ids = tuple(call_scope.call_ids)
                    if routed_stream.stream.call_id not in stream_call_ids:
                        stream_call_ids += (routed_stream.stream.call_id,)
                    return _openai_streaming_response(
                        routed_stream,
                        call_ids=stream_call_ids,
                        optimization_mode=optimization_mode,
                        optimization_bytes_saved=optimized.stats.bytes_saved,
                        optimization_lossy=lossy_applied,
                    )
                routed_result = await routed.chat_completion(
                    gateway,
                    messages=optimized_messages,
                    model=payload.model,
                    strategy=routing_strategy,
                    temperature=payload.temperature,
                    max_tokens=effective_max_tokens,
                    top_p=payload.top_p,
                    stop=payload.stop,
                    tools=optimized_tools,
                    tool_choice=payload.tool_choice,
                    response_format=payload.response_format,
                    seed=payload.seed,
                    user=payload.user,
                )
                result = routed_result.result
                route_plan = routed_result.plan
            else:
                result = await gateway.chat_completion(
                    messages=optimized_messages,
                    model=payload.model,
                    temperature=payload.temperature,
                    max_tokens=effective_max_tokens,
                    top_p=payload.top_p,
                    stop=payload.stop,
                    tools=optimized_tools,
                    tool_choice=payload.tool_choice,
                    response_format=payload.response_format,
                    seed=payload.seed,
                    user=payload.user,
                )
            call_ids = tuple(call_scope.call_ids)
    except SpendCapExceeded:
        return JSONResponse(
            _openai_error(
                "Configured spend cap would be exceeded",
                "insufficient_quota",
                "spend_cap_exceeded",
            ),
            status_code=429,
        )
    except ValueError as exc:
        return JSONResponse(
            _openai_error(str(exc), "invalid_request_error", "invalid_request"),
            status_code=400,
        )
    except RuntimeError as exc:
        code = str(exc).split(":", 1)[0]
        if code.startswith("UNKNOWN_PRICING"):
            status_code = 400
            message = "Requested model has no verified pricing record"
            error_type = "invalid_request_error"
        else:
            status_code = 503
            message = "Configured LLM provider is unavailable"
            error_type = "server_error"
        return JSONResponse(
            _openai_error(message, error_type, code.lower()),
            status_code=status_code,
        )
    except Exception as exc:
        upstream_status = getattr(exc, "status_code", None)
        if upstream_status in {400, 404, 408, 413, 422, 429}:
            status_code = upstream_status
            error_type = "rate_limit_error" if upstream_status == 429 else "invalid_request_error"
        else:
            status_code = 502
            error_type = "server_error"
        return JSONResponse(
            _openai_error(
                "Upstream provider rejected the chat completion request",
                error_type,
                f"upstream_{upstream_status or 'error'}",
            ),
            status_code=status_code,
        )

    response = result.response
    if hasattr(response, "model_dump"):
        body = response.model_dump(mode="json", exclude_none=True)
    elif isinstance(response, dict):
        body = response
    else:
        return JSONResponse(
            _openai_error("Invalid upstream response", "server_error", "invalid_upstream_response"),
            status_code=502,
        )
    response_headers = {
        "Cache-Control": "no-store",
        "X-Pineal-Call-ID": result.call_id,
        "X-Pineal-Call-IDs": ",".join(call_ids),
        "X-Pineal-Optimization-Mode": optimization_mode,
        "X-Pineal-Optimization-Bytes-Saved": str(optimized.stats.bytes_saved),
        "X-Pineal-Optimization-Lossy": str(lossy_applied).lower(),
    }
    if route_plan is not None:
        response_headers.update({
            "X-Pineal-Route-ID": route_plan.route_id,
            "X-Pineal-Route-Mode": route_plan.mode.value,
            "X-Pineal-Routing-Strategy": route_plan.strategy.value,
        })
    return JSONResponse(body, headers=response_headers)


# ---------------------------------------------------------------
# TELEMETRI BUS — oda basina FIFO kuyruk (ADIM 3)
# Oncesi: sync_* -> loop.create_task(...) deseninde eventler 'result'
# mesajiyla yarisiyor, ilk canli testte hic event ulasmiyordu.
# Simdi: her mesaj kuyruga girer, tek gonderici SIRAYLA iletir.
# ---------------------------------------------------------------

async def _room_sender(room: dict):
    queue: asyncio.Queue = room["queue"]
    while True:
        kind, payload = await queue.get()
        try:
            if kind == "log":
                await _send_log(room, payload)
            elif kind == "event":
                await _send_event(room, payload)
            elif kind == "snapshot":
                await _send_snapshot(room, payload)
            elif kind == "result":
                await _send_result(room, payload)
            elif kind == "result_error":
                await _send_result_error(room, payload)
            elif kind == "speech":
                await _send_speech(room, payload)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # gonderici task asla olmemeli
            # [BOSS-11] Eskiden yalnız print ediliyordu: kaybolan çerçeve
            # telemetride görünmüyordu. Artık oda durumu DEGRADED işaretlenir.
            _record_frame_error(room, kind, e)
            print(f"[room_sender] hata: {type(e).__name__}: {e}")

def _lifecycle(room: dict) -> TaskLifecycleRegistry:
    return room.setdefault("lifecycle", TaskLifecycleRegistry())


# [AUDIT R1] Oda-özel, task_id/event anahtarlı yapılar HİÇBİR temizliğe
# sahipken WS'li odalar evict'ten muaf (ölümsüz) -> monoton sızıntı
# (P0-2/P0-5 deseninin üçüncü tekrarı, bu sefer tetikleyicisiz). Ölçülen alt
# sınır: 2000 görev/oda -> 4.6 MB (1 event/görev); gerçek görev ~30-60 event
# taşıyarak 50-100 KB/görev'e çıkar. Çözüm: terminal durum + retention TTL
# (PINEAL_LIFECYCLE_RETENTION_SECONDS, 1800 sn) + sert tavanlar. Etki: oda
# belleği "retention x görev hızı" ile sınırlı, toplam görev sayısı ile değil.
_ROOM_PRUNE_INTERVAL_SECONDS = 30.0
_ROOM_ACTIVE_TASKS_CAP = _bounded_env_int("PINEAL_ROOM_ACTIVE_TASKS_CAP", 256, 1, 100_000)
_ROOM_INTERVENTIONS_CAP = _bounded_env_int("PINEAL_ROOM_INTERVENTIONS_CAP", 512, 1, 100_000)
_TERMINAL_PIPELINE_STATES = frozenset({
    "completed", "partially_completed", "failed",
    # [BOSS-8] Görev bütçesi doldu → terminal. Bu kümede olmazsa terminal
    # işaretleme yolu durumu "failed"a ezer (ölçüldü: timed_out → failed).
    "timed_out",
    "cancelled", "canceled",
    "halted_evidence", "halted_frequency", "halted_critical", "halted_user",
})


def _snapshot_status(snap) -> str:
    """Snapshot.status'un küçük harfli KADAR değerini döndürür.

    [AUDIT N1] PipelineStatus bir str-mixin enum'dur; Python 3.11'de
    `str(enum_uyesi)` -> 'PipelineStatus.COMPLETED' (değeri DEĞİL).
    Eski kod `str(snap.status).lower()` yazdığı için GERÇEK TaskSnapshot
    durumları ASLA terminal kümesine eşleşmiyordu (retention trim'i
    gerçek snapshot'larda hiç çalışmıyordu; üniteler string-tabanlı sahte
    sınıf kullandığı için yeşil görünüyordu). `.value` enum ve string'i
    birden doğru ele alır.
    """
    status = getattr(snap, "status", "")
    value = getattr(status, "value", status)
    return str(value).lower()


def _close_active_task(room: dict, task_id: Optional[str], status: str) -> bool:
    """[BOSS-2] Oda kaydını TERMİNAL duruma çevirir (hayalet görev yasağı).

    Röntgen bulgusu: ``active_tasks`` kaydı yalnız ``_send_snapshot`` ile
    yazılır. Görev zaman aşımına uğrar, iptal edilir veya beklenmeyen bir
    istisnayla düşerse görevin SON snapshot'ı "processing" olarak kalır ve
    hiçbir kod yolu onu güncellemez. ``_prune_room_stale_state`` terminal
    olmayan kaydı bilinçli olarak SİLMEZ (bkz. [AUDIT N1]); sonuç: kayıt
    sonsuza kadar "aktif" sayılır, ``_active_tasks_full`` odayı doygun görür
    ve oda KALICI 503 verir (ölçüldü: tavan 2, 3 askıda görev → kalıcı kilit).

    Bu fonksiyon kaydı öldürmez, ÖLDÜĞÜNÜ İŞARETLER: durum terminal kümesine
    yazılır (snapshot nesnesi paylaşıldığı için UI son durumu görebilir),
    retention sweep de kaydı normal yoldan düşürebilir.

    Dönüş: durum gerçekten değiştirildiyse True.
    """
    if not task_id:
        return False
    active = room.get("active_tasks")
    if not isinstance(active, dict):
        return False
    snapshot = active.get(task_id)
    if snapshot is None:
        return False
    if _snapshot_status(snapshot) in _TERMINAL_PIPELINE_STATES:
        return False
    normalized = str(status or "").lower()
    if normalized not in _TERMINAL_PIPELINE_STATES:
        # Bilinmeyen durum asla terminal sayılmaz; dürüst varsayılan "failed".
        normalized = "failed"
    try:
        from agent_core.domain.pipeline_status import PipelineStatus

        setattr(snapshot, "status", PipelineStatus(normalized))
    except Exception:
        try:
            setattr(snapshot, "status", normalized)
        except Exception:
            return False
    # Not: kayıt zamanı SIFIRLANMAZ — kapalı kayıt retention penceresini
    # hak etmek için bekletilmez; [AUDIT R1] sözleşmesi "oda belleği =
    # retention x görev hızı" ile sınırlı kalır ve hayalet hiç birikmez.
    room.setdefault("_active_tasks_ts", {}).setdefault(task_id, time.monotonic())
    return True


def _finalize_finished_missions(room: dict) -> None:
    """Bitiş sinyali ALINMIŞ görevlerin oda kayıtlarını terminal duruma sabitler.

    Kaynak yalnız ``room["_finished_missions"]`` kümesidir: mission task'inin
    done_callback'i (normal dönüş, istisna, iptal, timeout, kapanış) oraya
    task_id yazar. Böylece odaya snapshot basan ama ``mission_tasks``'a hiç
    girmeyen (kaydı olmayan) bir iş akışı YANLIŞLIKLA "failed" işaretlenmez —
    yalnız gerçekten bitmiş görevler kapatılır.

    Kayıt hâlâ terminal değilse kapatılır; zaten terminal ise (ör.
    "partially_completed") gerçek durum ASLA ezilmez.
    """
    finished = room.get("_finished_missions")
    if not isinstance(finished, set) or not finished:
        return
    active = room.get("active_tasks")
    for task_id in list(finished):
        _close_active_task(room, task_id, "failed")
        snapshot = (active or {}).get(task_id)
        if snapshot is None or _snapshot_status(snapshot) in _TERMINAL_PIPELINE_STATES:
            finished.discard(task_id)


def _run_display_fields(run) -> dict:
    """(Şeffaflık düzeltmesi, F2) AgentRun'dan CANLI model/provider gösterimi türetir.

    Backend ``AgentRun`` şeması ``model``/``via`` ÜRETMEZ; bir ajanın gerçekten
    çağırdığı model/provider, o ajanın ``output_summary._provenance`` kaydında
    yaşar (kaynak: yakalanan çağrı kayıtlarının son başarılısı). UI "ACTIVE
    MODEL/VIA" çubuğu bu alanlardan beslenir; provenance yoksa/fallback/
    deterministik ise değerler açıkça söyler — statik fallback'e sessiz düşme
    yerine (üretici yorumuyla birebir).
    """
    prov = (getattr(run, "output_summary", None) or {}).get("_provenance") or {}
    source = prov.get("source")
    model = prov.get("model")
    provider = prov.get("provider")
    if source in ("llm", "llm_cache"):
        return {"model": model, "via": provider or "openrouter", "run_source": source}
    if source == "llm_error":
        return {
            "model": model,
            "via": (provider or "llm") + " (hata)",
            "run_source": source,
        }
    if source == "deterministic":
        return {"model": None, "via": "deterministik-motor", "run_source": source}
    if source == "fallback":
        reason = prov.get("fallback_reason")
        suffix = f":{reason}" if reason else ""
        return {"model": None, "via": "fallback" + suffix, "run_source": source}
    return {"model": None, "via": None, "run_source": source or None}


# [BOSS-5] Deterministik 7-sütun ve psikodinamik derinlik çıktıları hesaplanıyordu
# ama hiçbir WS payload'ına girmiyordu (ne snapshot ne result): UI'de o veriyi
# gösterecek bileşen (PillarFeed) hiçbir zaman veri alamıyordu. `pillar_bundle`
# yedi raporun TAM kopyası olduğu için yayında TEKRAR EDİLMEZ; kanonik tam kayıt
# mühürde (evidence_chain) tutulur.
_PILLAR_SNAPSHOT_FIELDS = (
    "frequency_map", "seismos_events", "void_map", "strata_map",
    "gravity_map", "pulse_map", "key_matrix",
)


def _pillar_payload_fields(source: Any) -> dict:
    fields = {
        name: _json_field(getattr(source, name, None))
        for name in _PILLAR_SNAPSHOT_FIELDS
    }
    fields["psychodynamic_depth"] = _json_field(
        getattr(source, "psychodynamic_depth", None)
    )
    return fields


def _json_field(val: Any) -> Any:
    """Pydantic modeli → JSON modu; aksi hâlde değeri olduğu gibi döndürür."""
    if val is None:
        return None
    if hasattr(val, "model_dump"):
        return val.model_dump(mode="json")
    return val


def _serialize_run_entry(run, *, with_timestamps: bool) -> dict:
    """AgentRun serileştirmesi — tek SoT (iki broadcast noktası da bunu çağırır)."""
    entry = {
        "status": getattr(run, "status", None),
        "confidence": getattr(run, "confidence", None),
        "error_message": getattr(run, "error_message", None),
        "call_ids": list(getattr(run, "call_ids", []) or []),
        "output_summary": redact_structure(
            getattr(run, "output_summary", None) or {}
        ),
        "provenance": redact_structure(
            (getattr(run, "output_summary", None) or {}).get("_provenance")
        ),
    }
    if with_timestamps:
        entry["started_at"] = (
            run.started_at.isoformat() if getattr(run, "started_at", None) else None
        )
        entry["completed_at"] = (
            run.completed_at.isoformat() if getattr(run, "completed_at", None) else None
        )
    entry.update(_run_display_fields(run))
    return entry


def _prune_room_stale_state(room: dict) -> None:
    """Odanın task_id ile büyüyen yapılarını retention/tavanla geri kazanır.

    Çağrı sıklığı yüksek (her broadcast); maliyet oda başına ~30 sn'de bir
    O(N) taramaya amortize edilir (tek float karşılaştırması).
    """
    now = time.monotonic()
    last = room.get("_stale_prune_ts", 0.0)
    if now - last < _ROOM_PRUNE_INTERVAL_SECONDS:
        return
    room["_stale_prune_ts"] = now

    # 1) Lifecycle registry: terminal (+ canlı olmayan askıda) eski run'lar.
    try:
        live = set((room.get("mission_tasks") or {}).keys())
        _lifecycle(room).sweep(now, live_task_ids=live)
    except Exception:
        pass

    # 2) active_tasks: terminal snapshot'lar retention dolunca düşer; sert
    # tavan aşımında EN ESKİ terminal (hepsi terminal değilse en eski kayıt)
    # düşer. Girdi zamanı paralel ts sözlüğünde izlenir (snapshot'ta
    # güvenilir zaman damgası yok).
    _finalize_finished_missions(room)
    active = room.get("active_tasks")
    if isinstance(active, dict) and active:
        ts = room.setdefault("_active_tasks_ts", {})
        retention = 1800.0
        try:
            retention = _lifecycle(room).retention_seconds
        except Exception:
            pass
        for task_id in [
            t for t, snap in active.items()
            if _snapshot_status(snap) in _TERMINAL_PIPELINE_STATES
            and now - ts.get(t, 0.0) > retention
        ]:
            active.pop(task_id, None)
            ts.pop(task_id, None)
        # [AUDIT N1] Tavan trim'i ARTIK DURUM FARKINDA: yalnız TERMINAL
        # kayıtlar düşer (en eski önce). Aktif (processing) snapshot'lar
        # ASLA sessizce silinmez — eskiden en eski kayıt terminal OLSA BİLE
        # aktifse silinir, görev /api/tasks + UI'da görünmez (hayalet) olur,
        # mission timeout'a kadar arka planda çalışmaya devam ederdi
        # (ölçülen: 300 aktiften 44 hayalet). Aktif tek başına tavanı
        # aşıyorsa odayı "doymuş" sayarız ve yeni görev 503 alır
        # (_active_tasks_full).
        overflow = len(active) - _ROOM_ACTIVE_TASKS_CAP
        if overflow > 0:
            terminals = sorted(
                (
                    t for t, snap in active.items()
                    if _snapshot_status(snap) in _TERMINAL_PIPELINE_STATES
                ),
                key=lambda t: ts.get(t, 0.0),
            )
            for task_id in terminals[:overflow]:
                active.pop(task_id, None)
                ts.pop(task_id, None)
        for stale_ts in [t for t in ts if t not in active]:
            ts.pop(stale_ts, None)

    # 3) interventions: audit listesi sert tavanla (en eski düşer).
    interventions = room.get("interventions")
    if isinstance(interventions, list):
        overflow = len(interventions) - _ROOM_INTERVENTIONS_CAP
        if overflow > 0:
            del interventions[:overflow]


def _active_tasks_full(room: dict) -> bool:
    """[AUDIT N1] Odada AKTİF (terminal olmayan) snapshot sayısı tavanı aşıyor mu?

    Tavan trim'i aktifleri sessizce silmediği (hayalet yasağı) için, aktif
    işyükü tavanı dolduğunda yeni görev kabulü 503 ile reddedilir. O(N)
    tarama yalnız initiate yollarında (rate-limit 5/dk) çalışır.
    """
    active = room.get("active_tasks")
    if not isinstance(active, dict):
        return False
    # [BOSS-2] Biten görevler terminal işaretlenmeden doygunluk kararı verilmez:
    # aksi hâlde hayalet kayıt odayı kalıcı 503'e kilitler.
    _finalize_finished_missions(room)
    full = 0
    for snap in active.values():
        if _snapshot_status(snap) not in _TERMINAL_PIPELINE_STATES:
            full += 1
            if full > _ROOM_ACTIVE_TASKS_CAP:
                return True
    return False


def _delivery_status(room: dict) -> dict:
    delivery = room.setdefault("telemetry_delivery", {
        "state": "NORMAL",
        "dropped_messages_total": 0,
        "dropped_event_count": 0,
        "dropped_by_kind": {},
    })
    return {
        "state": delivery["state"],
        "dropped_messages_total": delivery["dropped_messages_total"],
        "dropped_event_count": delivery["dropped_event_count"],
        "dropped_by_kind": dict(delivery["dropped_by_kind"]),
        # [BOSS-11] Çerçeve hataları artık raporlanır (eskiden sessizdi).
        "frame_errors_total": delivery.get("frame_errors_total", 0),
        "frame_errors_by_kind": dict(delivery.get("frame_errors_by_kind", {})),
    }


def _record_queue_drop(room: dict, kind: str) -> None:
    _delivery_status(room)
    delivery = room["telemetry_delivery"]
    delivery["state"] = "DEGRADED_QUEUE_OVERFLOW"
    delivery["dropped_messages_total"] += 1
    delivery["dropped_by_kind"][kind] = delivery["dropped_by_kind"].get(kind, 0) + 1
    if kind == "event":
        delivery["dropped_event_count"] += 1


def _enqueue(client_id: str, item: tuple):
    if client_id in app.state.rooms:
        room = app.state.rooms[client_id]
        q: asyncio.Queue = room["queue"]
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:
            try:
                dropped_kind, _ = q.get_nowait()  # Explicit drop-oldest policy.
                _record_queue_drop(room, dropped_kind)
            except asyncio.QueueEmpty:
                pass
            try:
                q.put_nowait(item)
            except asyncio.QueueFull:
                # Defensive accounting if another producer fills the slot.
                _record_queue_drop(room, item[0])

# [FIX #6] WebSocket gönderimi oda (ROOM) ile sınırlıdır. Eski kod
# app.state.rooms'daki TÜM odaların soketlerini topluyordu: bir odanın
# log/telemetri payload'u (profil verisi içerebilir) HER istemciye
# sızdırılıyordu. Ayrıca send_text üzerinde bekleme süresi yoktu: yavaş/
# ölü soketler yayını asılı bırakırdı ve asla temizlenmezdi.
_WS_SEND_TIMEOUT_S = 5.0


def _ws_json(data: dict) -> str:
    """[BOSS-11] WS çerçeveleri için TEK serileştirme sözleşmesi.

    Mühür (canonical memory) `json.dumps(..., default=str)` kullanır; WS ise
    çıplak `json.dumps` çağırıyordu. `model_dump()` bugün JSON-uyumlu ama tek
    bir Enum/datetime alanı eklendiğinde çerçeve sessizce kaybolurdu
    (bkz. schemas/telemetry.py:98). İki yol aynı sözleşmeyi paylaşır.
    """
    return json.dumps(data, ensure_ascii=False, default=str)


def _record_frame_error(room: dict, kind: str, exc: BaseException) -> None:
    """Çerçeve üretim/gönderim hatası görünür olsun: sessiz yutma yok."""
    _delivery_status(room)
    delivery = room["telemetry_delivery"]
    delivery["state"] = "DEGRADED_FRAME_ERROR"
    delivery["frame_errors_total"] = delivery.get("frame_errors_total", 0) + 1
    delivery.setdefault("frame_errors_by_kind", {})
    delivery["frame_errors_by_kind"][kind] = delivery["frame_errors_by_kind"].get(kind, 0) + 1
    room.setdefault("frame_error_samples", [])
    room["frame_error_samples"].append(f"{kind}: {type(exc).__name__}: {exc}"[:200])
    del room["frame_error_samples"][:-5]


async def _send_ws(room: dict, payload: str) -> None:
    ws_set = room.get("websockets", set())
    for ws in list(ws_set):
        try:
            await asyncio.wait_for(ws.send_text(payload), timeout=_WS_SEND_TIMEOUT_S)
        except Exception:
            # Ölü/açık soket: odaya ait setten at; yayına diğerleriyle devam.
            ws_set.discard(ws)

async def _send_log(room: dict, payload: tuple):
    level, msg = payload
    ts = datetime.now().strftime("%H:%M:%S")
    if "logs" not in room: room["logs"] = []
    room["logs"].append(f"[{ts}] [{level}] {msg}")
    if len(room["logs"]) > 50: room["logs"].pop(0)
    await _send_ws(room, _ws_json({"type": "log", "ts": ts, "level": level, "msg": msg}))

async def _send_speech(room: dict, payload: dict):
    """[FAZ C · C2/C3] Konuşma durumu UI'a akar: speaking / idle / denied."""
    await _send_ws(room, _ws_json({"type": "speech", **payload}))


def broadcast_speech(client_id: str, payload: dict):
    _enqueue(client_id, ("speech", payload))


def broadcast_log(client_id: str, level: str, msg: str):
    _enqueue(client_id, ("log", (level, redact_text(msg))))

def sync_log(client_id: str, level: str, msg: str):
    broadcast_log(client_id, level, msg)

async def _send_event(room: dict, telemetry: Any):
    delivery = _delivery_status(room)
    telemetry = telemetry.model_copy(update={
        "delivery_state": delivery["state"],
        "dropped_event_count": delivery["dropped_event_count"],
    })
    # [AUDIT R1] Eski `room["events"]` birikimi SİLİNDİ: eklenen telemetri
    # hiçbir yerde okunmuyordu (grep: yalnız append) — saf bellek sızıntısıydı.
    # Canlı akış `websockets` üzerinden gidiyor; oda geçmişine gerek yok.
    await _send_ws(room, telemetry.model_dump_json())


def broadcast_event(client_id: str, event: Any):
    room = app.state.rooms.get(client_id)
    if room is None:
        return
    _prune_room_stale_state(room)  # [AUDIT R1]
    if hasattr(event, "model_dump"):
        clean_event_data = redact_structure(event.model_dump(mode="json"))
        event = type(event).model_validate(clean_event_data)
    decision = _lifecycle(room).record_event(event)
    if decision.accepted:
        _enqueue(client_id, ("event", decision.envelope))

def sync_event(client_id: str, event: Any):
    broadcast_event(client_id, event)

async def _send_snapshot(room: dict, snapshot: Any):
    def _dump_field(val):
        if val is None:
            return None
        if hasattr(val, "model_dump"):
            return val.model_dump(mode="json")
        return val

    snapshot_telemetry = dict(getattr(snapshot, "telemetry", None) or {})
    snapshot_telemetry["delivery"] = _delivery_status(room)
    snapshot_telemetry["lifecycle"] = _lifecycle(room).metrics()

    payload = _ws_json({
        "type": "snapshot_update",
        "task_id": snapshot.task_id,
        "current_agent": snapshot.current_agent,
        "status": snapshot.status,
        "planned_agents": snapshot.planned_agents,
        "completed_agents": snapshot.completed_agents,
        "halted_reason": getattr(snapshot, "halted_reason", None),
        "resonance_score": getattr(snapshot, "resonance_score", None),
        "holistic_profile": _dump_field(getattr(snapshot, "holistic_profile", None)),
        "follower_audit": _dump_field(getattr(snapshot, "follower_audit", None)),
        "timing_forensics": _dump_field(getattr(snapshot, "timing_forensics", None)),
        "depth_report": _dump_field(getattr(snapshot, "depth_report", None)),
        "visual_evidence": _dump_field(getattr(snapshot, "visual_evidence", None)),
        "shadow_profile": _dump_field(getattr(snapshot, "shadow_profile", None)),
        "osint_footprint": _dump_field(getattr(snapshot, "osint_footprint", None)),
        **_pillar_payload_fields(snapshot),
        "telemetry": snapshot_telemetry,
        "runs": {
            name: _serialize_run_entry(r, with_timestamps=True)
            for name, r in snapshot.agent_runs.items()
        }
    })
    if "active_tasks" not in room:
        room["active_tasks"] = {}
    room["active_tasks"][snapshot.task_id] = snapshot
    room.setdefault("_active_tasks_ts", {})[snapshot.task_id] = time.monotonic()
    await _send_ws(room, payload)

def broadcast_snapshot(client_id: str, snapshot: Any):
    room = app.state.rooms.get(client_id)
    if room is None:
        return
    _prune_room_stale_state(room)  # [AUDIT R1]
    decision = _lifecycle(room).accept_snapshot(snapshot)
    if decision.accepted:
        _enqueue(client_id, ("snapshot", snapshot))

def sync_snapshot(client_id: str, snapshot: Any):
    broadcast_snapshot(client_id, snapshot)

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    try:
        posture = security_posture()
    except SecurityConfigurationError:
        await websocket.close(code=1013)
        return

    await websocket.accept()
    if posture["auth_required"]:
        try:
            auth_message = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
        except (asyncio.TimeoutError, ValueError):
            await websocket.close(code=1008)
            return
        if auth_message.get("type") != "auth" or not token_matches(auth_message.get("token")):
            await websocket.close(code=1008)
            return
        await websocket.send_json({"type": "auth_ok"})

    room = get_room(client_id)
    room["websockets"].add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        # [AUDIT P1-18c] Eskiden bare `except:` idi. Ölçülen: bare except
        # BaseException'ı da yakaladığı için asyncio.CancelledError yutuluyor
        # ve görev iptal edilmiş sayılmıyordu (task.cancelled() == False).
        # `except Exception:`'a geçmek tek başına YETMEZ: kontrol ölçümünde
        # iptal durumunda temizlik kayboldu. Bu yüzden temizlik finally'de.
        logger.debug("WebSocket bağlantısı koptu: %s", client_id)
    finally:
        room["websockets"].discard(websocket)

class InitiatePayload(BaseModel):
    # [AUDIT 2026-09-11 P2] Public /api/initiate gövdesi sınırsız string
    # kabul ediyordu (OpenAI ucu 1 MiB + alan limitliyken burası değildi).
    # Bellek/istismar yüzeyini daraltmak için katı alan tavanları:
    client_id: str = Field(max_length=_MAX_CLIENT_ID_LENGTH)
    url: str = Field(max_length=8_192)
    # [main 481edb8'den taşındı] Alanlar opsiyonel: `default=""` olmadan istemci
    # bu üç alanı göndermezse 422 alıyordu. Bellek tavanı (max_length) korunur.
    rituals: str = Field(default="", max_length=32_000)
    playlist: str = Field(default="", max_length=32_000)
    envies: str = Field(default="", max_length=32_000)
    scraper_type: str = Field(default="instagram", max_length=64)
    # ASPASIA TRUE CHIEF LAYER: kullanicinin AMACI (goal id'leri) görev
    # verisiyle birlikte tasinir — ama AJAN SECIMI degil; sozlesme tek
    # kaynagi CognitiveRouter.GOAL_FOCUS. Bos = eski davranis (compat).
    aspasia_goals: List[str] = Field(default_factory=list, max_length=64)
    # [037] fix: aggressiveness/evidence_th kabul ediliyordu ama HİÇBİR davranışa
    # bağlanmamıştı (ölü API sözleşmesi). Kaldırıldı; eşik ayarı gerekiyorsa
    # DecisionConfig üzerinden gerçek davranışla bağlanmalı. Eski istemcilerin
    # bu alanları göndermesi pydantic tarafından sessizce yok sayılır.

# [W4.2] Tek sahiplik: platform kararları agent_core/services/platform_registry'de.
# Rust TaskManager (scripts/run_task.py) aynı registry'yi kullanır; ikinci bir
# karar katmanı YARATILMAZ ([009] duplication dersi). Geriye uyumluluk için
# isimler burada da geçerli.
from agent_core.services.platform_registry import (
    effective_scraper_type as _effective_scraper_type,
    scrape_instagram,
    scrape_x,
    build_user_context,
)
# Geriye uyumluluk re-export'u: Dalga 1 sözleşme testleri bu adı backend.api'den
# içe aktarıyor ([024]/[025]/[026] mapping testleri).
from agent_core.services.platform_registry import (  # noqa: F401
    ig_target_profile_update as _ig_target_profile_update,
)


def _x_sensor_ready() -> bool:
    """X sensörü gerçekten kullanılabilir mi? (tek kaynak: capability spine).

    Eskiden `/api/telemetry` alanı sabit `False` idi — sensör eklense bile
    UI "yok" demeye devam ederdi. Şimdi kasa + env kapısı + kütüphane
    durumunu registry'den okur; sebep makine-okunur olarak loglanır.
    """
    try:
        from agent_core.capabilities import bootstrap
        from agent_core.capabilities.state import policy_state

        registry = bootstrap()
        cap = registry.get("sensor.x.twscrape")
        availability = cap.availability()
        if not availability.available:
            logger.debug("x sensörü kapalı: %s", availability.reason)
            return False
        from agent_core.capabilities.policy import PolicyKernel

        state = policy_state(vault_locked=False, rate_ok=True)
        return PolicyKernel().evaluate(cap.gates, state).allowed
    except Exception as exc:  # telemetri asla API'yı düşürmez
        logger.debug("x sensör durumu okunamadı: %s", type(exc).__name__)
        return False


def _new_task_id() -> str:
    """[029] fix: saniye-çözünürlüklü op_HHMMSS çakışıyordu; aynı saniyede iki
    görev (farklı client'lar dahil) aynı memory dosyasında birleşiyordu.
    Tarihi saniye + uuid4 öneki -> CanonicalMemory task_id regex'i ile uyumlu."""
    import uuid
    return f"op_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"


async def run_mission(req: InitiatePayload, task_id: Optional[str] = None):
    client_id = req.client_id
    executor = get_executor(client_id)
    vault = get_vault(client_id)
    
    try:
        # [009] Kullanıcı göndermediyse ASLA örnek/placeholder ritüel ÜRETME.
        # Boş kullanıcı verisi -> boş listeler; MirrorOfTruth "user_data_missing"
        # fallback'iyle çalışır. Sahte ritüel ile kullanıcı frekansı kirletilmez.
        user_rituals = [r.strip() for r in req.rituals.split(",") if r.strip()] if req.rituals else []
        user_playlist = [req.playlist.strip()] if req.playlist and req.playlist.strip() else []
        user_envies = [e.strip() for e in req.envies.split(",") if e.strip()] if req.envies else []

        # [BOSS-3] Kullanıcı bölümleri TEK kaynaktan kurulur: aynı yardımcı
        # scripts/run_task.py (Rust/Tauri yolu) tarafından da kullanılır. Satır
        # içi kopya, tüketici ajanlarla sözleşme ayrışmasına yol açmıştı
        # (resonance_synthesizer bio/posts bekliyordu → her görevde erken dönüş).
        payload = {
            **build_user_context(user_rituals, user_playlist, user_envies),
            "target_profile": {"bio": "", "posts": [], "post_times": [], "images": []},
            # Amaç kaybi fix: Aspasia goal'leri payload'da yasar; router yoksa
            # eski plani aynen kurar. Gecerlilik/uydurma filtresi router'da.
            "aspasia_goals": list(req.aspasia_goals or []),
        }
        
        # Otonom Cookie Rotasyonu — canlı LCD oturumu önceliklidir.
        cookie = ""
        live_session = (vault.get("ig_sessionid", "") or "").strip()
        if live_session:
            cookie = live_session
            broadcast_log(client_id, "INFO", "DAEMON: Canlı LCD oturum çerezi kullanılıyor.")
        else:
            cookie_pool = vault.get("x_cookie", "").strip()
            if cookie_pool:
                cookie_list = [c.strip() for c in cookie_pool.split('\n') if c.strip()]
                if cookie_list:
                    import random
                    cookie = random.choice(cookie_list)
                    broadcast_log(client_id, "INFO", "DAEMON: Rotasyondan rastgele cookie seçildi.")
                
        enable_cross = os.getenv("ENABLE_CROSS_PLATFORM", "false").lower() == "true"
        effective_type = _effective_scraper_type(req.url, req.scraper_type)
        if req.url and effective_type == "unsupported_web":
            if not enable_cross:
                # [023] fix: tanınmayan platformda URL segmentini Instagram adı gibi
                # kullanıp yanlış hedefi kazımak YASAK. Tahmin üretme, açıkça dur.
                broadcast_log(
                    client_id, "WARNING",
                    f"PLATFORM DESTEKLENMİYOR: {req.url} — yalnızca Instagram kazıması var; "
                    "tanınmayan URL tahmine dayalı kazınmaz, analiz başlatılmadı.",
                )
                broadcast_result_error(
                    client_id, "unsupported_platform",
                    "Bu URL'nin platformu desteklenmiyor (destekli: Instagram). Analiz başlatılmadı.",
                )
                return
            effective_type = "cross"
        task_id = task_id or _new_task_id()

        # [FAZ A · Retina] X DELİĞİ KAPANDI. Eskiden X'in sensörü yoktu: istek
        # "yetki bekliyor" diye geri çevriliyor, yetki verildiğinde ise arama
        # snippet'leri profil diye giydiriliyordu (uydurma takipçi sayısı
        # dâhil). Artık X de Instagram gibi OMURGADAN kazınır:
        #   platform_registry.scrape_x → capability spine → sensor.x.twscrape
        # Sensör kanıt üretemezse sahte profil ÜRETİLMEZ; açık kaynak dosyası
        # olduğu gibi işaretlenerek devam edilir (aşağıdaki web dosyası yolu).
        x_sensor_reason = ""
        x_profile: dict = {}
        if req.url and effective_type == "x":
            from agent_core.services.platform_registry import extract_x_username
            clean_u = extract_x_username(req.url) or ""
            broadcast_log(client_id, "INFO", f"UPLINK: Hedefe sızılıyor -> {req.url} [X · twscrape]")
            try:
                x_profile = await scrape_x(
                    req.url,
                    log=lambda lvl, msg: broadcast_log(client_id, lvl, msg),
                    vault_locked=not _check_vault_interlock(client_id),
                    rate_ok=True,
                )
                broadcast_log(
                    client_id, "INFO",
                    f"TELEMETRİ: X akışı ele geçirildi — {len(x_profile['post_times'])} gerçek zaman damgalı gönderi.",
                )
            except (InsufficientEvidenceError, ScraperInsufficientEvidenceError) as exc:
                x_sensor_reason = str(exc)[:200]
                broadcast_log(
                    client_id, "WARNING",
                    f"X SENSÖRÜ KANIT ÜRETEMEDİ ({x_sensor_reason}); "
                    "profil uydurulmadı, açık kaynak dosyası ile devam ediliyor.",
                )

        if req.url and (effective_type == "cross" or (effective_type == "x" and not x_profile)):
            from agent_core.services.platform_registry import extract_x_username
            clean_u = extract_x_username(req.url) or (req.url.split('/')[-1] if '/' in req.url else req.url).lstrip('@').strip()
            if effective_type == "x":
                broadcast_log(client_id, "INFO", f"UPLINK: Hedefe sızılıyor -> {req.url} [X · açık kaynak dosyası]")
            else:
                broadcast_log(client_id, "INFO", f"UPLINK: Hedefe sızılıyor -> {req.url} [{effective_type.upper()}]")
            broadcast_log(client_id, "INFO", f"AÇIK KAYNAK VE OSINT: {clean_u} için veriler taranıyor...")
            try:
                # Çok kanallı paralel OSINT araması (Instagram, LinkedIn, Web)
                if " " in clean_u:
                    queries = [
                        f'"{clean_u}" instagram',
                        f'"{clean_u}" linkedin',
                        f'"{clean_u}"',
                        f'site:instagram.com "{clean_u}"',
                        f'site:linkedin.com/in "{clean_u}"',
                    ]
                else:
                    queries = [
                        f"{clean_u} instagram",
                        f"{clean_u} linkedin twitter",
                        f"{clean_u}",
                    ]
                search_tasks = [executor.search_engine.search(q, num_results=6) for q in queries]
                search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

                all_raw_results = []
                seen_urls = set()
                for s_res in search_results:
                    if isinstance(s_res, Exception):
                        continue
                    for r in getattr(s_res, "results", []):
                        u = r.source_url or ""
                        if u and u in seen_urls:
                            continue
                        seen_urls.add(u)
                        all_raw_results.append(r)

                # Katmanlı alaka sıralaması: Tam ad eşleşmesi > parça eşleşmesi > genel
                target_parts = [p.lower() for p in clean_u.split() if len(p) > 1]
                name_full = clean_u.lower()
                tier1 = []
                tier2 = []
                tier3 = []
                for r in all_raw_results:
                    text_blob = f"{r.content or ''} {r.source_url or ''}".lower()
                    if name_full in text_blob:
                        tier1.append(r)
                    elif all(p in text_blob for p in target_parts):
                        tier2.append(r)
                    elif any(p in text_blob for p in target_parts):
                        tier3.append(r)

                ordered_results = (tier1 + tier2 + tier3) or all_raw_results

                # Anlamlı içerikleri filtrele
                snippets = []
                for r in ordered_results:
                    c = (r.content or "").strip()
                    if c and len(c) > 20:
                        snippets.append(f"[{r.provider.upper()}] {c}")

                # Tespit edilen doğrudan sosyal medya profilleri
                found_profiles = []
                for r in ordered_results:
                    u = r.source_url or ""
                    if any(dom in u.lower() for dom in ("instagram.com/", "twitter.com/", "x.com/", "linkedin.com/in/", "linkedin.com/pub/", "facebook.com/")):
                        if u not in found_profiles:
                            found_profiles.append(u)

                if found_profiles:
                    broadcast_log(client_id, "INFO", f"HEDEF PROFİLLERİ TESPİT EDİLDİ: {', '.join(found_profiles[:3])}")

                display_user = f"@{clean_u.replace(' ', '_').lower()}" if " " in clean_u else f"@{clean_u}"
                # [FAZ A] Dürüst dosya: arama snippet'i BİYOGRAPHİ diye
                # sunulmaz, takipçi sayısı UYDURULMAZ (eski kod profil
                # bulunduğunda sabit 150 yazıyordu). Ölçülmeyen alan None.
                payload["target_profile"].update({
                    "username": display_user,
                    "name": clean_u,
                    "bio": "",
                    "posts": snippets or [],
                    "post_times": [],
                    "posts_meta": [],
                    "post_types": ["text" for _ in snippets] if snippets else [],
                    "images": [],
                    "followers": None,
                    "following": None,
                    "is_private": None,
                    "detected_urls": found_profiles,
                    "platform": "web_dossier",
                    "sensor_note": (
                        f"X sensörü kanıt üretemedi: {x_sensor_reason}" if x_sensor_reason
                        else "Açık kaynak dosyası: platform sensörüyle kazınmadı."
                    ),
                })
                broadcast_log(client_id, "INFO", f"TELEMETRİ: {len(snippets)} açık kaynak verisi ve {len(found_profiles)} profil hedefe bağlandı.")
            except Exception as se:
                broadcast_log(client_id, "WARNING", f"OSINT ARAMA UYARISI: {se}")
                payload["target_profile"].update({
                    "username": f"@{clean_u}",
                    "name": clean_u,
                    "bio": "",
                    "posts": [],
                    "post_times": [],
                    "posts_meta": [],
                    "post_types": [],
                    "images": [],
                    "followers": None,
                    "following": None,
                    "is_private": None,
                    "platform": "web_dossier",
                    "sensor_note": f"Açık kaynak araması başarısız: {type(se).__name__}",
                })
        if x_profile:
            payload["target_profile"].update(x_profile)
        if req.url and effective_type == "instagram":
            broadcast_log(client_id, "INFO", f"UPLINK: Hedefe sızılıyor -> {req.url} [INSTAGRAM]")
            # [FIX #8] Eski kod: (1) tek deneme + hata yutuluyordu ve
            # operasyon BOŞ profille sessizce devam ediyordu; (2) ISE
            # kontrolü str(type(e).__name__) ile yapılıyordu — iki farklı
            # ISE sınıfı (task_executor + scraper) ad eşleşmesiyle
            # yakalanmaya çalışılıyordu, TargetPrivateError ise hiç
            # tanımlanmayan bir sınıftı.
            scrape_max = _bounded_env_int("PINEAL_SCRAPE_MAX_ATTEMPTS", 3, 1, 5)
            last_err = None
            for scrape_attempt in range(1, scrape_max + 1):
                try:
                    # [W4.2] Kazıma tek sahiplikli platform_registry'de; Rust
                    # TaskManager (run_task.py) da aynı fonksiyonu kullanır.
                    payload["target_profile"].update(await scrape_instagram(
                        req.url, cookie,
                        log=lambda lvl, msg: broadcast_log(client_id, lvl, msg),
                    ))
                    broadcast_log(client_id, "INFO", "TELEMETRİ: Veri ele geçirildi.")
                    last_err = None
                    break
                except (InsufficientEvidenceError, ScraperInsufficientEvidenceError):
                    # Kanıt yok (ör. özel profil) = altyapı hatası değil;
                    # denemek anlamsız. Dış handler "halted_evidence"
                    # terminal durumuna çevirir.
                    raise
                except Exception as e:
                    last_err = e
                    broadcast_log(
                        client_id, "ERROR",
                        f"UPLINK KOPTU (Deneme {scrape_attempt}/{scrape_max}): "
                        f"{type(e).__name__}: {str(e)[:100]}",
                    )
                    if scrape_attempt < scrape_max:
                        await asyncio.sleep(min(2 * scrape_attempt, 5))
            if last_err is not None:
                # [FIX #8] Altyapı tükenmesi → dürüst terminal durum.
                # Boş profille operasyon ÇALIŞTIRILMAZ (eski kod sessizce
                # devam edip kanıtsız "analiz" üretiyordu).
                logger.error("HEDEF VERİSİ ALINAMADI: %s", str(last_err)[:200])
                broadcast_result_error(
                    client_id, "failed",
                    "HEDEF VERİSİ ALINAMADI: kazıma altyapısı denemeleri tüketti; analiz başlatılmadı.",
                    task_id,
                )
                return
        # [FAZ A · Retina] Kasa gerçeği görev payload'ına yazılır: ajanlar
        # capability omurgasını çağırırken durumu TAHMİN ETMEZ, operatörün
        # mandalının tek sahibi olan interlock'tan okur (kasa kapalıysa hiçbir
        # dış yetenek koşamaz). İkinci bir "env'den kasa okuma" katmanı yok.
        payload["policy"] = {"vault_locked": not _check_vault_interlock(client_id)}
        # Arama motoru da aynı gerçeği görür: kasa kapalıyken omurga yetenekleri
        # (SearXNG dâhil) koşamaz. Ücretsiz DuckDuckGo yolu bugünkü davranışını
        # korur; kararı bu katman uydurmaz, interlock'tan okur.
        try:
            executor.search_engine.set_policy(payload["policy"])
        except Exception:  # telemetri/arama asıl görevi düşürmesin
            logger.debug("search engine policy aktarılamadı")
        max_attempts = _bounded_env_int("PINEAL_TASK_MAX_ATTEMPTS", 3, 1, 3)
        task_timeout = _bounded_env_int("PINEAL_TASK_TIMEOUT_SECONDS", 300, 1, 1800)
        for attempt in range(1, max_attempts + 1):
            try:
                broadcast_log(
                    client_id,
                    "INFO",
                    f"OPERASYON BAŞLATILIYOR (Deneme {attempt}/{max_attempts})...",
                )
                res = await asyncio.wait_for(
                    executor.execute_task(payload, task_id),
                    timeout=task_timeout,
                )
                setattr(res, "target_profile", payload.get("target_profile"))
                broadcast_result(client_id, res)
                return
            except (InsufficientEvidenceError, ScraperInsufficientEvidenceError):
                raise
            except (asyncio.TimeoutError, TimeoutError):
                # [BOSS-8] Zaman aşımı ARTIK yeniden başlatılmaz. Eski davranış:
                # görev 300s'de iptal edilir, aynı ajanlar sıfırdan koşar ve
                # LLM faturası 3'e katlanırdı — sonuç yine aynı darboğaz.
                # Bunun yerine son kısmi durum 'timed_out' olarak yayınlanır.
                _finalize_timed_out_mission(client_id, task_id, task_timeout)
                return
            except Exception as e:
                broadcast_log(client_id, "ERROR", f"HATA: {type(e).__name__}: {str(e)[:100]}")
                if attempt == max_attempts:
                    broadcast_log(client_id, "ERROR", "SİSTEM PANİĞİ: MAKSİMUM DENEME AŞILDI.")
                    # [028] fix: terminal durum MUTLAKA WS'ye düşer; exception'ı
                    # yutmak UI'ı sonsuz 'işleniyor' durumunda asılı bırakır.
                    broadcast_result_error(
                        client_id, "failed",
                        f"SİSTEM PANİĞİ: MAKSİMUM DENEME AŞILDI ({max_attempts}/{max_attempts}).",
                        task_id,
                    )
                    return
    except (InsufficientEvidenceError, ScraperInsufficientEvidenceError):
        broadcast_result_error(
            client_id, "halted_evidence", "DURDURULDU: YETERSİZ KANIT", task_id
        )
    except Exception as e:
        broadcast_result_error(
            client_id, "failed", f"SİSTEM PANİĞİ: {str(e)}", task_id
        )

def _finalize_timed_out_mission(client_id: str, task_id: str, budget_seconds: int) -> None:
    """[BOSS-8] Görev bütçesi dolduğunda kısmi kanıtı terminal durumla yayınlar.

    Eski davranışta timeout sessizce "failed" olur ve o ana kadar üretilen tüm
    kanıt (ajan koşuları, kanıt zinciri, 7-sütun raporları) çöpe giderdi.
    Oda kaydındaki son snapshot terminal işaretlenip `timed_out` durumuyla
    yayınlanır; baştan koşma yoktur.
    """
    from agent_core.domain.pipeline_status import PipelineStatus

    room = app.state.rooms.get(client_id)
    partial = None
    if room is not None:
        partial = (room.get("active_tasks") or {}).get(task_id)
    if partial is not None:
        try:
            partial.status = PipelineStatus.TIMED_OUT
            partial.halted_reason = (
                f"Görev bütçesi doldu ({budget_seconds}s). Kısmi kanıt korundu; "
                "aynı darboğaz tekrar tıkanmasın diye görev baştan koşulmadı."
            )
        except Exception:  # pragma: no cover - savunma: şema dışı snapshot
            partial = None
    broadcast_log(
        client_id,
        "ERROR",
        f"ZAMAN AŞIMI: görev {budget_seconds}s bütçesini aştı. Görev baştan "
        "başlatılmadı (tekrarlanan tıkanma + 3x maliyet önlenir).",
    )
    if partial is not None:
        broadcast_result(client_id, partial)
    broadcast_result_error(
        client_id, PipelineStatus.TIMED_OUT.value,
        f"ZAMAN AŞIMI: {budget_seconds}s bütçesi doldu; kısmi kanıt yayınlandı.", task_id,
    )


def broadcast_result_error(client_id, status, msg, task_id: Optional[str] = None):
    broadcast_log(client_id, "ERROR", msg)
    # [BOSS-2] Terminal hata bildirimi oda kaydını da kapatır; aksi hâlde
    # snapshot "processing" kalıp odayı kalıcı 503'e kilitliyordu.
    room = app.state.rooms.get(client_id)
    if room is not None:
        _close_active_task(room, task_id, status)
    payload = {"type": "result", "status": status}
    if task_id:
        payload["task_id"] = task_id
    _enqueue(client_id, ("result_error", payload))

async def _send_result_error(room: dict, data: dict):
    await _send_ws(room, _ws_json(data))

def broadcast_result(client_id, res):
    room = app.state.rooms.get(client_id)
    if room is None:
        return
    _prune_room_stale_state(room)  # [AUDIT R1]
    decision = _lifecycle(room).transition(res.task_id, res.status)
    if not decision.accepted:
        return
    # [BOSS-2] Snapshot nesnesi terminal duruma geçmemişse (ör. iptal/istisna
    # sonrası geç gelen sonuç) oda kaydı burada kapatılır.
    _close_active_task(room, getattr(res, "task_id", None), getattr(res, "status", None))

    def find(chain, name):
        for e in chain:
            if e["agent"] == name:
                return e["result"]
        return None

    def _dump_field(val):
        if val is None:
            return None
        if hasattr(val, "model_dump"):
            return val.model_dump(mode="json")
        return val

    payload = {
        "type": "result",
        "task_id": res.task_id,
        "status": res.status,
        "evidence_chain": redact_structure(getattr(res, "evidence_chain", []) or []),
        "mirror": find(res.evidence_chain, "mirror_truth"),
        "reading": find(res.evidence_chain, "human_behavior"),
        "reso": find(res.evidence_chain, "resonance_calc"),
        "hook": find(res.evidence_chain, "pattern_interrupt"),
        # W4: zincir durumu final result'ta da korunur; UI snapshot bilgisini
        # kaybetmesin diye planned/completed/runs buraya da girer.
        "planned_agents": getattr(res, "planned_agents", []) or [],
        "completed_agents": getattr(res, "completed_agents", []) or [],
        "runs": {
            name: _serialize_run_entry(run, with_timestamps=False)
            for name, run in (getattr(res, "agent_runs", None) or {}).items()
        },
        "follower_audit": _dump_field(getattr(res, "follower_audit", None)),
        "timing_forensics": _dump_field(getattr(res, "timing_forensics", None)),
        "depth_report": _dump_field(getattr(res, "depth_report", None)),
        "visual_evidence": _dump_field(getattr(res, "visual_evidence", None)),
        "shadow_profile": _dump_field(getattr(res, "shadow_profile", None)),
        "osint_footprint": _dump_field(getattr(res, "osint_footprint", None)),
        "target_profile": getattr(res, "target_profile", None),
        **_pillar_payload_fields(res),
        "telemetry": getattr(res, "telemetry", None)
    }
    # [FAZ B · B7] DEĞİŞİM İZLEME: her biten görev, aynı hedefin GEÇMİŞİNE bir
    # parmak izi bırakır. Sonraki görev "ne değişti?" sorusunu cevaplayabilir.
    # Yazma asla yayını bozmaz (try/except) ve önceki kayıt yoksa fark
    # UYDURULMAZ (rapor `available:false` + sebep `no_baseline` kalır).
    try:
        payload["changes"] = _record_change_snapshot(room, res)
    except Exception as exc:  # değişim izleme asıl sonucu asla bozmasın
        logger.debug("change tracking skipped: %s", type(exc).__name__)
    # [FAZ B · B2/B3] HAFIZA KRİSTALİ: görev bitince kanıt, hedefin KALICI
    # hafızasına işlenir. Sonraki görev aynı hedefe bakarken "geçmişte ne
    # bulmuştuk?" sorusunu cevaplayabilir (recall).
    try:
        payload["memory"] = _crystallize_task(room, res)
    except Exception as exc:  # kristal asıl sonucu asla bozmasın
        logger.debug("memory crystal skipped: %s", type(exc).__name__)

    room["latest_result"] = payload
    _enqueue(client_id, ("result", payload))


def _record_change_snapshot(room: dict, res: Any) -> dict:
    """Görevin kanıtını hedef geçmişine yazar + öncekiyle farkını döner."""
    from agent_core.services.change_tracker import (
        build_snapshot,
        diff_snapshots,
        latest_before,
        record_snapshot,
    )

    executor = room.get("executor")
    storage = getattr(getattr(executor, "memory", None), "storage_path", "./memory/")
    chain = list(getattr(res, "evidence_chain", []) or [])
    profile = getattr(res, "target_profile", None) or {}

    snapshot = build_snapshot(chain, profile, task_id=str(getattr(res, "task_id", "") or ""))
    if not snapshot.target:
        return {"available": False, "reason": "no_target", "machine_note": "DEĞİŞİM: hedef anahtarı yok."}

    previous = latest_before(storage, snapshot.target, snapshot.task_id)
    report = diff_snapshots(previous, snapshot)
    record_snapshot(storage, snapshot)
    return report.model_dump()

def _crystallize_task(room: dict, res: Any) -> dict:
    """Görevin kanıtını hedefin kristaline işler + özetini döner."""
    from agent_core.services import memory_crystal
    from agent_core.services.change_tracker import target_key

    executor = room.get("executor")
    storage = getattr(getattr(executor, "memory", None), "storage_path", "./memory/")
    task_id = str(getattr(res, "task_id", "") or "")
    profile = getattr(res, "target_profile", None) or {}

    memory_payload: Any = {}
    try:
        memory_payload = executor.memory.get_task_memory(task_id) or {}
    except Exception:  # bellek okunamazsa kanıt zinciriyle devam edilir
        memory_payload = {}

    evidence = memory_payload.get("evidence")
    if not evidence:
        evidence = list(getattr(res, "evidence_chain", []) or [])
    if not isinstance(profile, dict):
        profile = {}

    target = target_key(profile, evidence if isinstance(evidence, list) else [])
    if not target:
        return {
            "available": False,
            "reason": "no_target",
            "machine_note": "KRİSTAL: hedef anahtarı yok — hatıra işlenmedi.",
        }

    query = " ".join(
        str(profile.get(field) or "")
        for field in ("username", "name", "bio")
    ).strip()
    crystal = memory_crystal.crystallize(target, task_id, evidence, base=storage)
    payload = memory_crystal.summarize(target, base=storage)
    # Bu görev kendi hatıralarını geri çağırmaz (yalnız GEÇMİŞ bağlam).
    payload["recall_preview"] = [
        hit.model_dump()
        for hit in memory_crystal.recall(
            target, query or target, base=storage, exclude_task_id=task_id
        ).hits
    ]
    payload["crystallized_task"] = task_id
    payload["machine_note"] = crystal.machine_note or payload.get("machine_note", "")
    return payload


async def _send_result(room: dict, data: dict):
    result_telemetry = dict(data.get("telemetry") or {})
    result_telemetry["delivery"] = _delivery_status(room)
    result_telemetry["lifecycle"] = _lifecycle(room).metrics()
    data = {**data, "telemetry": result_telemetry}
    await _send_ws(room, _ws_json(data))

@app.post("/api/initiate")
async def api_initiate(req: InitiatePayload, request: Request):
    if not rate_limit(f"initiate:{_rate_identity(request)}", "initiate"):
        return JSONResponse(
            {"error": {"code": "RATE_LIMITED", "message": "Çok fazla görev başlatma isteği; bir dakika içinde tekrar deneyin."}},
            status_code=429,
        )
    # VAULT INTERLOCK: anahtar çevrilmeden dış dünyaya OSINT/Scraper isteği yok
    if req.url and req.url.strip():
        if not _check_vault_interlock(req.client_id):
            return JSONResponse(
                {
                    "error": {
                        "code": "VAULT_LOCKED",
                        "message": "VAULT KİLİTLİ: Operatör anahtarı çevirmeden dış dünyaya hiçbir OSINT/Scraper isteği çıkamaz. Önce /api/vault ile anahtar girin veya Tauri kasasını açın."
                    }
                },
                status_code=423,
            )
    room = get_room(req.client_id)
    if _active_tasks_full(room):
        return JSONResponse(
            {
                "error": {
                    "code": "ACTIVE_TASKS_FULL",
                    "message": (
                        f"Oda aktif görev tavanını doldurdu (>{_ROOM_ACTIVE_TASKS_CAP}); "
                        "aktif görevler tamamlanana kadar yeni görev başlatılamaz."
                    ),
                }
            },
            status_code=503,
        )
    task_id = _new_task_id()
    _lifecycle(room).transition(task_id, "processing")
    # Agent Rack: görev başladı — tüm slotlar BEKLEMEDE (Wait).
    # [RÖNTGEN 2026-09-23] Eskiden burada "tahmini plan" bahanesiyle
    # set_all_ready() çağrılıyordu: daha tek bir ajan çalışmadan rack 12/12
    # READY gösteriyordu. Ready/Active geçişlerinin TEK kaynağı executor'ın
    # gerçek ajan geçişleridir (PinealExecutor._rack_update).
    if HAS_AGENT_RACK and get_tracker:
        try:
            tracker = get_tracker()
            await tracker.set_all_wait()
        except Exception:
            pass
    mission = asyncio.create_task(run_mission(req, task_id))
    room["mission_tasks"][task_id] = mission

    def _on_mission_done(_task, _room=room):
        _room["mission_tasks"].pop(task_id, None)
        _room.setdefault("_finished_missions", set()).add(task_id)
        _finalize_finished_missions(_room)

    mission.add_done_callback(_on_mission_done)
    return {"status": "started", "task_id": task_id}

class VaultPayload(BaseModel):
    client_id: str
    x_cookie: str = ""
    api_key: str = ""
    tavily_key: str = ""
    serpapi_key: str = ""
    exa_key: str = ""
    local_url: str = ""
    local_model: str = ""
    # Optional so omitted != explicit false (UI toggle must be able to turn local OFF).
    use_local: Optional[bool] = None
    # FAZ 3: dogrudan-saglayici anahtarlari {provider_id: key}. Yalniz odaya
    # ozel gateway bellegine yazilir; degerler asla loglanmaz/dondurulmez.
    provider_keys: Optional[Dict[str, str]] = None
    
@app.post("/api/vault")
async def api_vault(req: VaultPayload):
    # [FORENSIC VAULT-INTERLOCK] Placeholder fail-closed: ret HER ŞEYDEN ÖNCE
    # yapılır, böylece reddedilen istek HİÇBİR bayrak kuramaz (kısmi mutasyon yok).
    if req.api_key and not _is_real_key(req.api_key):
        return JSONResponse(
            {"error": {"code": "PLACEHOLDER_KEY", "message": "KASA REDDETTİ: API anahtarı placeholder (ör. sk-or-v1-YOUR...); gerçek anahtar girin."}},
            status_code=400,
        )
    if req.x_cookie and not _cookie_pool_has_key(req.x_cookie):
        return JSONResponse(
            {"error": {"code": "PLACEHOLDER_KEY", "message": "KASA REDDETTİ: cookie havuzunda gerçek anahtar malzemesi yok (boş/placeholder)."}},
            status_code=400,
        )
    vault = get_vault(req.client_id)
    executor = get_executor(req.client_id)
    if req.x_cookie:
        vault["x_cookie"] = req.x_cookie
        broadcast_log(req.client_id, "INFO", "KASA: Cookie belleğe mühürlendi.")
    if req.api_key:
        executor.llm_gateway.set_key(req.api_key, unlock_live=True)
        if shadow_executor is not None:
            shadow_executor.llm_gateway.set_key(req.api_key, unlock_live=True)
        if dialogue_manager is not None:
            dialogue_manager.llm.set_key(req.api_key, unlock_live=True)
        vault["or_key"] = True
        broadcast_log(req.client_id, "INFO", "KASA: API Anahtarı girildi. Ağ geçidi aktif — canlı LLM kilidi açıldı.")
        
    # FAZ 3: dogrudan-saglayici anahtarlari (oda gateway bellegi; degerler
    # loglanmaz, yalniz uygulanan saglayici ID'leri isaretlenir).
    if req.provider_keys:
        applied = []
        gateways = [executor.llm_gateway]
        if shadow_executor is not None:
            gateways.append(shadow_executor.llm_gateway)
        if dialogue_manager is not None:
            gateways.append(dialogue_manager.llm)
        for provider_id, provider_key in req.provider_keys.items():
            # [FORENSIC VAULT-INTERLOCK] Placeholder havuza girmez; atlanan
            # ID dürüstçe raporlanır (değer asla loglanmaz).
            if not _is_real_key(provider_key):
                broadcast_log(req.client_id, "WARNING", f"KASA: placeholder saglayici anahtari reddedildi: {provider_id}")
                continue
            ok = True
            for gateway in gateways:
                try:
                    gateway.set_provider_key(provider_id, provider_key)
                except (ValueError, AttributeError):
                    ok = False
            if ok:
                applied.append(str(provider_id))
            else:
                broadcast_log(req.client_id, "WARNING", f"KASA: saglayici anahtari uygulanamadi: {provider_id}")
        if applied:
            vault["provider_keys_set"] = sorted(set(applied))
            broadcast_log(req.client_id, "INFO", f"KASA: {len(applied)} dogrudan-saglayici anahtari havuza eklendi.")

    if req.local_url or req.local_model or req.use_local is not None:
        active = bool(req.use_local) if req.use_local is not None else bool(vault.get("use_local", False))
        executor.llm_gateway.set_local_config(
            base_url=req.local_url or None,
            model_name=req.local_model or None,
            active=active,
        )
        if req.use_local is not None:
            vault["use_local"] = active
        broadcast_log(req.client_id, "INFO", f"KASA: Yerel Kısıtlamasız LLM Yapılandırıldı ({req.local_model or 'Ollama/LM Studio'}).")

    if req.tavily_key or req.serpapi_key or req.exa_key:
        # [FORENSIC VAULT-INTERLOCK] Yalnızca GERÇEK arama anahtarları
        # uygulanır ve bayrak kurar; placeholder sessizce bayrak kuramaz.
        real_search = {
            name: val for name, val in (
                ("tavily", req.tavily_key),
                ("serpapi", req.serpapi_key),
                ("exa", req.exa_key),
            ) if _is_real_key(val)
        }
        provided = [name for name, val in (
            ("tavily", req.tavily_key),
            ("serpapi", req.serpapi_key),
            ("exa", req.exa_key),
        ) if val]
        rejected = [name for name in provided if name not in real_search]
        if rejected:
            broadcast_log(req.client_id, "WARNING", f"KASA: placeholder arama anahtari reddedildi: {', '.join(rejected)}")
        if real_search:
            executor.search_engine.set_keys(
                tavily=real_search.get("tavily"),
                serpapi=real_search.get("serpapi"),
                exa=real_search.get("exa"),
            )
        # Kasa durumu değişti: omurga politikası da yenilenir (tek kaynak).
        try:
            executor.search_engine.set_policy(
                {"vault_locked": not _check_vault_interlock(req.client_id)}
            )
        except Exception:
            logger.debug("search engine policy aktarılamadı")
            vault["search_keys"] = True
            broadcast_log(req.client_id, "INFO", "KASA: Arama Motoru anahtarları mühürlendi.")
        
    return {"status": "secured"}

class OverridePayload(BaseModel):
    client_id: str
    # [FIX #3] Sınırsız str alanları learnings.json'a sınırsız büyütme
    # + inject promptuna sınırsız enjeksiyon oluyordu; sınırlar hem
    # depolamayı hem prompt maliyetini sınırlar.
    fact: str = Field(min_length=1, max_length=2000)
    tag: str = Field(min_length=1, max_length=64)

_override_lock = asyncio.Lock()


def _read_learnings_safe(lp: str) -> tuple:
    """[AUDIT P2-9] learnings.json'ı her zaman (liste, sorun) olarak döndürür.

    Eskiden `json.load` try/except'i OLMADAN çağrılıyordu: dosya bir kez
    bozulursa (elle düzenleme, yarım yazma) endpoint KALICI 500 üretiyordu.
    Bozuk/şemasız dosya [] sayılır; orijinal baytlar ayrı yedeklenir (aşağı).
    """
    if not os.path.exists(lp):
        return [], None
    try:
        with open(lp, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, RecursionError) as exc:
        # [AUDIT N2] RecursionError: derin nested JSON (geçerli JSON ama
        # ~60.000 seviye) json.load'ı RecursionError'a düşürür; eski catch
        # tuple'ında YOKTU -> endpoint KALICI 500 üretiyordu ve dosya
        # quarantine'edilmiyordu (dosya bozulmadan kaldığı için her istek
        # aynı 500'ü veriyordu).
        logger.warning(
            "LEARNINGS_CORRUPT: %s okunamadı (%s: %s); boş liste + yedek",
            lp, type(exc).__name__, str(exc)[:80],
        )
        return [], "corrupt"
    if not isinstance(data, list):
        logger.error("LEARNINGS_SCHEMA_INVALID: %s bir JSON listesi değil (%s)", lp, type(data).__name__)
        return [], "schema"
    return data, None


def _quarantine_learnings(lp: str, problem: str) -> Optional[str]:
    """Bozuk dosyayı okunabilir kalıcılıkla yedekler; dönen değer yedek yolu.

    [AUDIT N3] Yedekler ARTIK Sınırlı: her bozuk olay 1 dosya üretiyordu
    (ölçülen: 20 olay -> 20 dosya) ve hiçbir temizleyici yoktu — R1 deseninin
    disk versiyonu. Yedek başına `PINEAL_LEARNINGS_BACKUP_KEEP` (5) son
    yedek tutulur; en eski fazlası silinir. Ad içindeki mikrosaniye damgası
    sözlük sıralamasında kronolojiktir.
    """
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    backup = f"{lp}.{problem}.{stamp}"
    try:
        os.replace(lp, backup)
    except OSError as exc:
        logger.warning("LEARNINGS_BACKUP_FAILED: %s (%s)", lp, str(exc)[:80])
        return None
    try:
        keep = max(1, int(os.getenv("PINEAL_LEARNINGS_BACKUP_KEEP", "5")))
    except (TypeError, ValueError):
        keep = 5
    base, _ = os.path.split(lp)
    prefix = os.path.basename(lp) + "."
    try:
        backups = sorted(
            (
                name for name in os.listdir(base)
                if name.startswith(prefix) and name[len(prefix):].split(".")[0] in ("corrupt", "schema")
            )
        )
        for name in backups[:-keep]:
            try:
                os.remove(os.path.join(base, name))
            except OSError:
                pass
    except OSError:
        pass
    return backup


def _write_learnings_atomic(lp: str, data: list) -> None:
    """[AUDIT P2-9] Atomik yazım: yarım/kısmi dosya bir daha asla oluşmaz."""
    tmp = f"{lp}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, lp)


@app.post("/api/override")
async def api_override(req: OverridePayload):
    quarantined = None
    if req.fact.strip():
        executor = get_executor(req.client_id)
        mem_dir = executor.memory.storage_path
        lp = os.path.join(mem_dir, "learnings.json")
        async with _override_lock:
            learn, problem = await asyncio.to_thread(_read_learnings_safe, lp)
            if problem:
                quarantined = await asyncio.to_thread(_quarantine_learnings, lp, problem)
            learn.append({"fact": req.fact.strip(), "tag": req.tag.strip(), "ts": datetime.now().isoformat(), "hash": hashlib.sha256(req.fact.strip().encode()).hexdigest()[:12]})
            await asyncio.to_thread(_write_learnings_atomic, lp, learn)
        if quarantined:
            broadcast_log(req.client_id, "WARNING", f"HAFIZA: bozuk learnings.json yedeklendi ({os.path.basename(quarantined)}); kayıtsız devam")
        broadcast_log(req.client_id, "INFO", f"HAFIZA: Yeni konsept mühürlendi [{req.tag.strip()}]")
    return {"status": "sealed", "quarantined": quarantined}

@app.get("/api/telemetry")
async def api_telemetry(client_id: str = "default"):
    room = get_room(client_id)
    executor = room["executor"]
    vault = room["vault"]
    capability = await _scraper_capability()
    budget_reader = getattr(type(executor.llm_gateway), "budget_status", None)
    budget = budget_reader(executor.llm_gateway) if callable(budget_reader) else {}
    # Agent Rack status
    agent_statuses = {}
    if HAS_AGENT_RACK:
        try:
            tracker = get_tracker() if get_tracker else None
            if tracker:
                agent_statuses = tracker.get_all_statuses()
        except Exception:
            agent_statuses = {}
    # [FORENSIC VAULT-INTERLOCK] Telemetri, kilidin GERÇEK durumunu söyler:
    # placeholder anahtar "hazır" sayılmaz; `vault_locked` interlock ile birebir.
    vault_open = _check_vault_interlock(client_id)
    search_keys = getattr(executor, "search_engine", None)
    return {
        "core": True,
        "gateway": _is_real_key(getattr(executor.llm_gateway, 'api_key', None)),
        "scraper": capability["instagram"],
        "vault": vault_open,
        "search_engine": bool(vault.get("search_keys", False)) or any(
            _is_real_key(getattr(search_keys, attr, None))
            for attr in ("tavily_key", "serpapi_key", "exa_key")
        ),
        # [FAZ A] Artık SABİT False değil: X sensörü gerçekten var mı, kapıları
        # açık mı? Cevap capability spine'ın TEK kaynağından gelir.
        "x_scraper": _x_sensor_ready(),
        "instagram_scraper": capability["instagram"],
        "instagram_session": _is_real_key(vault.get("ig_sessionid")),
        "browser_installed": capability["browser"],
        "llm_spend_usd": round(float(budget.get("spend_usd", 0.0)), 6),
        "llm_reserved_spend_usd": round(float(budget.get("reserved_usd", 0.0)), 6),
        "llm_spend_cap_usd": float(budget.get("cap_usd", 0.0)),
        "llm_active_reservations": int(budget.get("active_reservations", 0)),
        "telemetry_delivery": _delivery_status(room),
        "task_lifecycle": _lifecycle(room).metrics(),
        "rust_core": rust_core_status(),
        "llm_unpriced_calls": int(getattr(executor.llm_gateway, "unpriced_calls", 0)),
        "agent_statuses": agent_statuses,
        "vault_locked": not vault_open,
    }


# ─── v5.0: Agent Rack + Vault + Dialogue Manager canlı köprüleri ─────────

@app.get("/api/agents/status")
async def api_agents_status():
    """12 ajanin anlik durumu - Agent Rack beslenir.

    ``source`` UI'nin KAYNAK satırını besler ve GERÇEK taşıyıcıyı beyan eder:
      - ``redis_bus``  : PING'lenmiş Redis bağlantısı üzerinden okundu
      - ``in_memory``  : Redis yok/bağlanamadı, süreç-içi bellek
      - ``fallback``   : Agent Rack modülü hiç yüklenmedi
      - ``error``      : okuma patladı
    [RÖNTGEN 2026-09-23] Eskiden tracker varsa koşulsuz ``redis_bus``
    yazılıyordu; Redis kapalıyken bile UI "REDIS PUB/SUB" etiketi basıyordu.
    """
    if not HAS_AGENT_RACK or not get_tracker:
        return {"agents": [], "source": "fallback", "count": 0}
    try:
        tracker = get_tracker()
        agents = tracker.get_status_list()
        state_fn = getattr(getattr(tracker, "redis_bus", None), "connection_state", None)
        source = state_fn() if callable(state_fn) else "in_memory"
        return {"agents": agents, "source": source, "count": len(agents)}
    except Exception as e:
        logger.warning(f"Agent status okuma hatasi: {e}")
        return {"agents": [], "source": "error", "error": str(e)[:100], "count": 0}


@app.post("/api/agents/status/{agent_id}")
async def api_update_agent_status(agent_id: str, status: str, metadata: Optional[dict] = None):
    """Ajan durumunu guncelle - Docker Compose servisleri buraya POST eder"""
    if not HAS_AGENT_RACK or not get_tracker:
        return {"status": "fallback", "agent_id": agent_id}
    try:
        tracker = get_tracker()
        result = await tracker.update_status(agent_id, status, metadata)
        # WS uzerinden de yayinla
        # Tum odalara broadcast
        for client_id in list(app.state.rooms.keys()):
            room = app.state.rooms.get(client_id)
            if room:
                payload = _ws_json({
                    "type": "agent_status_update",
                    "agent_id": agent_id,
                    "status": status,
                    "timestamp": result.get("timestamp"),
                    "metadata": metadata or {}
                })
                # Kuyruga ekle - dogrudan WS gonderimi
                try:
                    await _send_ws(room, payload)
                except Exception:
                    pass
        return {"status": "updated", "agent": result}
    except Exception as e:
        return JSONResponse({"error": {"code": "AGENT_UPDATE_FAILED", "message": str(e)[:200]}}, status_code=500)


class VaultStatusPayload(BaseModel):
    client_id: str = "default"
    action: Optional[str] = None


@app.get("/api/vault/status")
async def api_vault_status(client_id: str = "default"):
    """Vault kilit durumu - mandal baglantisi.

    [FORENSIC VAULT-INTERLOCK] `locked`/`can_scrape`, `/api/initiate` ile
    AYNI kapıdan (`_check_vault_interlock`) okunur: dosya varlığı kilidi
    açmaz, yalnızca gerçek anahtar malzemesi açar.
    """
    room = get_room(client_id)
    vault = room["vault"]
    unlocked = _check_vault_interlock(client_id)
    file_vault = _load_vault()
    return {
        "locked": not unlocked,
        "has_api_key": vault.get("or_key") is True,
        "has_session": _is_real_key(vault.get("ig_sessionid")),
        "has_cookie": _cookie_pool_has_key(vault.get("x_cookie")),
        "file_vault_exists": bool(file_vault),
        "file_vault_has_keys": _vault_file_has_key_material(file_vault),
        "can_scrape": unlocked,  # Vault kilidi: anahtar yoksa OSINT/Scraper cikmaz
        "message": "VAULT ACIK - dis dunya erisimi serbest" if unlocked else "VAULT KILITLI - operator anahtari cevirmeden OSINT/Scraper cikmaz"
    }


@app.post("/api/vault/status")
async def api_vault_status_toggle(payload: VaultStatusPayload):
    """Vault kilit durumu gecisi (POST /api/vault/status toggle)"""
    if payload.action == "lock":
        return await api_vault_lock(payload)
    elif payload.action == "unlock":
        return await api_vault_unlock(payload)
    return await api_vault_status(payload.client_id)


@app.post("/api/vault/lock")
async def api_vault_lock(payload: VaultStatusPayload):
    """Vault'u kilitle - dis dunya erisimini durdur"""
    room = get_room(payload.client_id)
    # Vault'u temizle
    room["vault"] = {}
    broadcast_log(payload.client_id, "WARNING", "VAULT KILITLENDI: Dis dunya erisimi durduruldu, OSINT/Scraper bloklandi")
    return {"status": "locked", "message": "Kasa kilitlendi, dis dunya erisimi durduruldu"}


@app.post("/api/vault/unlock")
async def api_vault_unlock(payload: VaultStatusPayload):
    """Vault kilidini ac - backend tarafinda sadece durum raporu, gercek acma /api/vault ile"""
    room = get_room(payload.client_id)
    vault = room["vault"]
    has_key = _room_vault_unlocked(vault)
    if not has_key:
        return JSONResponse(
            {"error": {"code": "VAULT_LOCKED", "message": "Kasada anahtar yok, once /api/vault ile anahtar girin"}},
            status_code=423
        )
    broadcast_log(payload.client_id, "INFO", "VAULT ACILDI: Dis dunya erisimi serbest")
    return {"status": "unlocked", "can_scrape": True}


# Vault interlock helper
_VAULT_KEY_FIELDS = (
    "api_key",       # OpenRouter master (eski düz şema)
    "or_key",        # oda kasasında "gerçek anahtar uygulandı" bayrağı
    "ig_sessionid",  # Instagram oturum kimliği
    "x_cookie",      # Instagram çerez malzemesi
    "tavily_key",
    "serpapi_key",
    "exa_key",
)

# Yer tutucu değerler anahtar DEĞİLDİR: .env.example'dan kopyalanan
# "sk-or-v1-YOUR..." satırı kasayı açmamalı.
_VAULT_PLACEHOLDER_MARKERS = ("your", "changeme", "placeholder", "xxx", "<", "ornek", "örnek")


def _vault_bears_key_material(vault: dict) -> bool:
    """Kasa dict'i GERÇEK anahtar/oturum malzemesi taşıyor mu?

    [RÖNTGEN 2026-09-23] `.pineal_vault.json` dosyasının VARLIĞI yetki
    değildi ama eski `_check_vault_interlock` onu öyle sayıyordu
    (`or ... or _load_vault()`): `{"providers": {}}` gibi bomboş bir dosya
    bile dış-dünya mandalını açıyordu. Bu yardımcı "dosya var" ile "anahtar
    var" ayrımını tek yerde yapar:
      - providers/provider_keys içinde uygulanabilir anahtar, VEYA
      - _VAULT_KEY_FIELDS'te yer tutucu olmayan gerçek değer.
    """
    if not isinstance(vault, dict) or not vault:
        return False
    applied, openrouter_key, _skipped = _extract_vault_provider_keys(vault)
    # `_extract_*` yer tutucu süzmez; çıkarılan her değer gerçeklik kapısından
    # geçirilir (örn. providers.gemini.api_key="PLACEHOLDER" mandalı açamaz).
    if openrouter_key and _is_real_key(openrouter_key):
        return True
    if any(_is_real_key(key) for key in applied.values()):
        return True
    for field in _VAULT_KEY_FIELDS:
        raw = vault.get(field)
        if raw is True:  # oda kasasında "uygulandı" bayrağı
            return True
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        if not value:
            continue
        lowered = value.lower()
        if any(marker in lowered for marker in _VAULT_PLACEHOLDER_MARKERS):
            continue
        return True
    return False


def _check_vault_interlock(client_id: str) -> bool:
    """True = acik, False = kilitli (dis dunya erisimi yok).

    [RÖNTGEN 2026-09-23] Eskiden son koşul `_load_vault()` idi: diskteki
    `.pineal_vault.json` dosyasının VARLIĞI (içinde tek anahtar olmasa bile,
    ör. `{"providers": {}}`) mandalı açıyordu. Dosya varlığı yetki değildir;
    kasa ancak GERÇEK anahtar/oturum malzemesi taşıyorsa açıktır.
    """
    try:
        room = get_room(client_id)
        vault = room["vault"]
        if vault.get("or_key") or vault.get("ig_sessionid") or vault.get("x_cookie"):
            return True
        # Dosya kasası: VARLIK değil, GERÇEK anahtar malzemesi aranır.
        return _vault_bears_key_material(_load_vault())
    except Exception:
        return False


@app.get("/api/dialogue/sessions")
async def api_dialogue_sessions():
    """DialogueManager oturumlari - Aspasia terminal -> ajan zinciri"""
    if dialogue_manager is None:
        return {"sessions": [], "count": 0}
    try:
        sessions = []
        for task_id, ctx in dialogue_manager.sessions.items():
            sessions.append({
                "task_id": task_id,
                "history_count": len(ctx.history),
                "last_seen": ctx.last_seen,
                "target_profile": bool(ctx.target_profile),
            })
        return {"sessions": sessions, "count": len(sessions), "evicted": dialogue_manager.evicted}
    except Exception as e:
        return {"sessions": [], "count": 0, "error": str(e)[:100]}

class SocidExtractPayload(BaseModel):
    url: str


class MaigretScanPayload(BaseModel):
    username: str
    limit: Optional[int] = None
    timeout: Optional[int] = None


@app.post("/api/experimental/maigret/scan")
async def maigret_scan(payload: MaigretScanPayload):
    """Kullanıcı adını maigret DB'sinde tarar (FAZ 2).

    Kapı: ENABLE_MAIGRET=true (varsayılan kapalı). Dürüst sonuç: kayıt
    çıkmazsa `available:false` + makine-okunur sebep; site/hesap uydurulmaz.
    """
    from agent_core.services.maigret_scanner import scan_username
    result = await scan_username(
        payload.username, limit=payload.limit, site_timeout=payload.timeout
    )
    return result.model_dump()


class HoleheScanPayload(BaseModel):
    email: str
    limit: Optional[int] = None
    timeout: Optional[int] = None


@app.post("/api/experimental/holehe/scan")
async def holehe_scan(payload: HoleheScanPayload):
    """E-postanın sitelerdeki kaydını holehe ile tarar (FAZ 3, deneysel).

    Kapı: ENABLE_HOLEHE=true (varsayılan kapalı). Dürüst sonuç: kayıt
    çıkmazsa `available:false` + makine-okunur sebep; site uydurulmaz.
    holehe'nin istisnaları rateLimit olarak maskelemesi hata sayılır —
    kapalı ağda asla "kayıtlı değil" iddia edilmez.
    """
    from agent_core.services.holehe_scanner import scan_email
    result = await scan_email(
        payload.email, limit=payload.limit, site_timeout=payload.timeout
    )
    return result.model_dump()


class CrawlFetchPayload(BaseModel):
    url: str


@app.post("/api/experimental/crawl/fetch")
async def crawl_fetch(payload: CrawlFetchPayload):
    """Public-web sayfasını crawl4ai ile LLM-dostu metne çevirir (FAZ 4).

    Kapı: ENABLE_CRAWL4AI=true (varsayılan kapalı; renderer=http tarayıcı
    binary'si gerektirmez). Dürüst sonuç: içerik çekilemezse `available:false`
    + makine-okunur sebep; ASLA uydurma içerik döner. SSRF guard'lı.
    """
    from agent_core.services.crawl_enricher import fetch_readable
    return (await fetch_readable(payload.url)).model_dump()


@app.get("/api/experimental/stealth")
async def stealth_resolve(provider: Optional[str] = None):
    """STEALTH_PROVIDER seçimini ve dürüst kullanılabilirliği gösterir (FAZ 5).

    Salt-okunur: tarayıcı başlatmaz, binary indirmeyi TETİKLEMEZ. invisible/
    cloak yalnız operatörün env ile gösterdiği binary varsa available döner;
    yoksa makine-okunur sebep (binary_missing / library_missing).
    """
    from agent_core.services.stealth_provider import resolve_stealth
    return resolve_stealth(override=provider).model_dump()


@app.post("/api/experimental/socid/extract")
async def socid_extract(payload: SocidExtractPayload):
    """Profil URL'sinden yapılandırılmış kimlik kaydı çıkarır (socid-extractor).

    Dürüst sonuç sözleşmesi: kayıt çıkmazsa `available:false` + makine-okunur
    sebep döner; alan uydurulmaz. SSRF guard'lı (private/loopback engelli).
    """
    from agent_core.services.socid_enricher import extract_profile
    record = await extract_profile(payload.url)
    return record.model_dump()


@app.post("/api/experimental/shadow/analyze")
async def shadow_analyze(profile: dict):
    """Dark Triad analizi"""
    if shadow_executor is None:
        return {"error": "Shadow Protocol yüklü değil"}
    from agent_core.psychology.dark_triad import DarkTriadAnalyzer
    analyzer = DarkTriadAnalyzer()
    result = analyzer.analyze(profile)
    return result.model_dump()

@app.post("/api/experimental/shadow/generate")
async def shadow_generate(task: dict):
    """Shadow mesaj üretimi"""
    if shadow_executor is None:
        return {"error": "Shadow Protocol yüklü değil"}
    result = await shadow_executor.execute(task)
    return result.model_dump()

class ChatPayload(BaseModel):
    # [AUDIT R3] task_id, DialogueManager.sessions anahtarı olur; sınırsız
    # gövde ile 512 oturum x MB'lık anahtar = yüzlerce MB DoS yüzeyiydi.
    task_id: str = Field(min_length=1, max_length=_MAX_TASK_ID_LENGTH)
    target_profile: dict
    user_profile: dict
    target_message: str = Field(max_length=32_000)

@app.post("/api/experimental/chat/respond")
async def chat_respond(payload: ChatPayload):
    """Hedefin mesajına otonom karşı hamle üretir"""
    if dialogue_manager is None:
        return {"error": "Gölge Sohbet modülü yüklü değil"}
    
    try:
        if payload.task_id not in dialogue_manager.sessions:
            dialogue_manager.start_session(payload.task_id, payload.target_profile, payload.user_profile)
            
        res = await dialogue_manager.generate_response(payload.task_id, payload.target_message)
        return res.model_dump()
    except Exception as e:
        logger.error("Dialogue generation failed: %s", type(e).__name__)
        return {"error": {"code": "DIALOGUE_FAILED", "message": type(e).__name__}}

class AspasiaChatPayload(BaseModel):
    client_id: str
    user_message: str
    model_override: Optional[str] = None
    image_data: Optional[str] = None


def _aspasia_command_dispatch(spec: dict) -> "str | None":
    """ASPASIA PROMOTION — komutların TEK yetkili yazma kanalı.

    /api/initiate ile BİREBİR aynı akış: görev kimliği _new_task_id, yaşam
    döngüsü TaskLifecycleRegistry, yürütme run_mission, takip mission_tasks.
    Kota/harcama/routing politikaları içinde bulunduğumuz gerçek gateway
    yığınındadır; bu fonksiyon hiçbir politika katmanını atlatmaz ve yeni bir
    planlama beyni kurmaz (ajan planı = executor'ın CognitiveRouter'ı).
    """
    client_id = spec["client_id"]
    room = get_room(client_id)
    # [AUDIT N1] /api/initiate ile aynı doyma kuralı (tek yazma kanalı).
    if _active_tasks_full(room):
        return None  # komut kabul edilmez; gateway "reason" ile yanıtlar
    req = InitiatePayload(
        client_id=client_id,
        url=spec["target_url"],
        # [009] doktrini: kullanicidan gelmeyen rituel/sarki/ozlem verisi
        # ASLA uydurulmaz — Aspasia komutu yalnizca kullaniciya ait alanlari tasir.
        rituals="",
        playlist="",
        envies="",
        # AMAÇ TAŞIMA (Phase 1): kullanici mesajindaki odak, görev verisiyle
        # birlikte CognitiveRouter'a kadar gider; burada planlama YAPILMAZ.
        aspasia_goals=list(spec.get("goals") or []),
    )
    task_id = _new_task_id()
    _lifecycle(room).transition(task_id, "processing")
    mission = asyncio.create_task(run_mission(req, task_id))
    room["mission_tasks"][task_id] = mission

    def _on_mission_done(_task, _room=room):
        # [BOSS-2] Görev bitti/iptal edildi: terminal olmayan oda kaydı kalmasın.
        _room["mission_tasks"].pop(task_id, None)
        _room.setdefault("_finished_missions", set()).add(task_id)
        _finalize_finished_missions(_room)

    mission.add_done_callback(_on_mission_done)
    return task_id


class AspasiaCommandPayload(BaseModel):
    client_id: str
    user_message: str


@app.post("/api/aspasia/command")
async def aspasia_command(payload: AspasiaCommandPayload, request: Request):
    """Aspasia: doğal dil niyeti -> yapılandırılmış komut -> gerçek orchestrator.

    Kabul edilen tek yazma eylemi run_profile_analysis'tir ve hedef doğrulama
    (gerçek scraper host sözleşmesi) + gateway politika yığınını aynen geçer.
    """
    if not rate_limit(f"aspasia:{_rate_identity(request)}", "aspasia"):
        return JSONResponse(
            {"error": {"code": "RATE_LIMITED", "message": "Aspasia yoğun; kısa bir mola verin."}},
            status_code=429,
        )
    room = get_room(payload.client_id)
    aspasia = room.get("aspasia") or aspasia_chief
    if not aspasia or getattr(aspasia, "commands", None) is None:
        return JSONResponse(
            {"error": {"code": "COMMANDS_UNAVAILABLE", "message": "Aspasia komut kanalı tanımlı değil"}},
            status_code=503,
        )
    result = await aspasia.commands.submit(payload.user_message, client_id=payload.client_id)
    if result.accepted and result.task_id:
        broadcast_log(payload.client_id, "INFO",
                      f"ASPASIA KOMUT [{result.command_id}] {result.intent} → görev {result.task_id}")
    return result.model_dump()


@app.get("/api/aspasia/state")
async def aspasia_state(client_id: str = "default"):
    """Read-only denetim görünümü: registry + görev durumu + bütçe + kota + anomaliler.

    Yeni bir telemetri sistemi DOĞMAZ; hepsi mevcut SoT okuyucularıdır
    (gateway call_log/budget, QuotaGovernor, executor.agents, lifecycle).
    """
    from agent_core.aspasia.interface import (
        AgentInspector,
        CostReader,
        QuotaReader,
        TelemetryReader,
    )

    room = get_room(client_id)
    executor = room.get("executor")
    gateway = executor.llm_gateway if executor is not None else aspasia_chief.llm
    inspector = AgentInspector(executor)
    return {
        "registry": inspector.registry(),
        "run": inspector.run_status(room),
        "budget": CostReader(gateway).snapshot(),
        "quota": {p: QuotaReader(gateway=gateway).snapshot(p) for p in ("groq", "cerebras")},
        "anomalies": TelemetryReader(gateway).anomalies(),
    }


@app.post("/api/aspasia/chat")
async def aspasia_chat(payload: AspasiaChatPayload, request: Request):
    """Aspasia Kokpit Şefi ile canlı Sokratik diyalog"""
    if not rate_limit(f"aspasia:{_rate_identity(request)}", "aspasia"):
        return JSONResponse(
            {"error": {"code": "RATE_LIMITED", "message": "Aspasia yoğun; kısa bir mola verin."}},
            status_code=429,
        )
    room = get_room(payload.client_id)
    aspasia = room.get("aspasia") or aspasia_chief
    if not aspasia:
        return {"error": {"code": "ASPASIA_UNAVAILABLE", "message": "Aspasia Kokpit Şefi yüklenemedi"}}
    
    resp = await aspasia.chat(payload.user_message, room, payload.model_override, payload.image_data)
    return resp.model_dump()

class AlternativeAuthorizationPayload(BaseModel):
    client_id: str
    alternative: str
    approved: bool


def _extract_handle_from_url(url: str) -> str:
    """X/Instagram URL'sinden kullanıcı adı (subject) çıkarır."""
    import re
    if not url:
        return ""
    needle = re.search(r"(?:instagram\.com|x\.com|twitter\.com)/([^/?#]+)", url)
    if needle:
        return needle.group(1).strip().lstrip("@").lower()
    return url.split("?")[0].rstrip("/").split("/")[-1].replace("@", "").lower()


async def _run_public_web_research(
    url: str, search_engine: Any, client_id: str = "default"
) -> Dict[str, Any]:
    """Yetki verilmiş alternatif: kanıt kaynaklı public-web araması.

    Sözleşme (sahte veri YASAK):
    - Biyografi/gönderi/kişilik ÜRETİLMEZ; yalnızca gerçek arama kayıtları
      döner (source_url + provider + content).
    - Subject matching: hedef kullanıcı adı kaynak URL'sinde veya içeriğinde
      geçmeyen sonuçlar düşürülür (yanlış kişi eşleşmesi engeli).
    - Sağlayıcı yok/çöktü -> available=False; sonuç yok -> no_results.
    """
    handle = _extract_handle_from_url(url)
    if not handle:
        return {
            "status": "invalid_target", "available": False,
            "query": "", "results": [], "matched_username": "",
            "total_results_searched": 0,
            "searched_at": datetime.now().isoformat(),
            "note": "URL'den hedef kullanıcı adı çıkarılamadı.",
        }

    query = f'"{handle}"'
    outcome = await search_engine.search(query, num_results=8)
    if not getattr(outcome, "available", False):
        return {
            "status": "unavailable", "available": False, "query": query,
            "results": [], "matched_username": handle,
            "total_results_searched": 0,
            "searched_at": datetime.now().isoformat(),
            "note": getattr(outcome, "error", None) or "Arama sağlayıcısı kullanılamadı.",
        }

    raw = getattr(outcome, "results", []) or []
    matched = [
        {
            "source_url": r.source_url,
            "provider": r.provider,
            "content": r.content,
            "subject_match": True,
        }
        for r in raw
        if handle in (r.source_url or "").lower()
        or handle in (r.content or "").lower()
    ]
    # socid-extractor zenginleştirmesi: eşleşen kaynak URL'lerden kararlı kimlik
    # kaydı çıkmaya çalışılır. Kütüphane yok/ağ yok/kayıt yoksa alan EKLENMEZ —
    # sonuç sözleşmesi bozulmaz (dürüst boş).
    try:
        socid_records = await socid_enricher.enrich_urls(
            [m["source_url"] for m in matched], limit=3
        )
        by_url = {r.source_url: r for r in socid_records}
        for m in matched:
            rec = by_url.get(m["source_url"])
            if rec is not None:
                m["socid"] = rec.model_dump()
        if socid_records:
            socid_note = f" {len(socid_records)} sonuçtan yapılandırılmış kimlik kaydı çıkarıldı."
        else:
            socid_note = ""
    except Exception as exc:  # zenginleştirme asıl sonucu asla bozmasın
        logger.warning("socid enrichment skipped: %s: %s", type(exc).__name__, str(exc)[:80])
        socid_note = ""
    # [FAZ A · Retina] TEMİZ METİN OMURGASI. Eskiden tek bir crawl4ai çağrısı
    # vardı ve yalnız ENABLE_CRAWL4AI açıkken çalışıyordu. Artık üç kademeli
    # omurga devrede: trafilatura → crawl4ai → scrapling. İlk KANIT ÜRETEN
    # kademe sonucu verir; hiçbiri üretemezse alan uydurma metinle DOLDURULMAZ
    # (sebep + deneme izi yazılır). Tek arayüz: capabilities.extract_web_text.
    crawl_note = ""
    try:
        from agent_core.capabilities import bootstrap as _caps_bootstrap
        from agent_core.capabilities.adapters_web import extract_web_text
        from agent_core.capabilities.state import policy_state

        _caps_bootstrap()
        web_state = policy_state(vault_locked=not _check_vault_interlock(client_id))
        if matched:
            crawled = 0
            for m in matched[:crawl_enricher.research_limit()]:
                result = await extract_web_text(m["source_url"], state=web_state)
                if result.ok:
                    # payload kademeye göre değişir (pydantic kayıt veya dict);
                    # ikisi de desteklenir, erişim güvenli.
                    payload_raw = result.payload
                    title = (
                        payload_raw.get("title", "") if isinstance(payload_raw, dict)
                        else getattr(payload_raw, "title", "") or ""
                    )
                    m["crawl"] = {
                        "available": True,
                        # HANGİ kademenin ürettiği kayıtta yazar (görünürlük).
                        "provider": result.capability_id,
                        "requested_url": m["source_url"],
                        "title": title,
                        "text": result.items[0].content if result.items else "",
                        "evidence_ids": [i.evidence_id for i in result.items],
                        "attempts": result.notes.get("attempts", []),
                    }
                    crawled += 1
                else:
                    # Dürüst boş (sözleşme korunur): çekilemeyen sonuca `crawl`
                    # alanı EKLENMEZ; sebep yalnız logda (uydurma metin yok).
                    logger.info(
                        "web extraction failed for %s: %s (attempts=%s)",
                        m["source_url"], result.unavailable_reason,
                        result.notes.get("attempts", []),
                    )
            if crawled:
                crawl_note = f" {crawled} sonuca temiz metin çekildi (omurga: trafilatura → crawl4ai → scrapling)."
    except Exception as exc:  # zenginleştirme asıl sonucu asla bozmasın
        logger.warning("web extraction skipped: %s: %s", type(exc).__name__, str(exc)[:80])

    if matched:
        status = "ok"
        note = f"{len(matched)}/{len(raw)} sonuç hedef kullanıcı adıyla eşleşti." + socid_note + crawl_note
    elif raw:
        status = "no_subject_match"
        note = f"Arama yapıldı ({len(raw)} sonuç) ama hiçbiri hedef kullanıcı adıyla eşleşmedi; sonuç gösterilmiyor (yanlış kişi eşleşmesi engeli)."
    else:
        status = "no_results"
        note = "Arama yapıldı, hiç sonuç döndü."

    return {
        "status": status,
        "available": True,
        "query": query,
        "results": matched,
        "matched_username": handle,
        "total_results_searched": len(raw),
        "searched_at": datetime.now().isoformat(),
        "note": note,
    }


class BrowserClientPayload(BaseModel):
    client_id: str


class BrowserOpenPayload(BaseModel):
    client_id: str
    url: str = ""


class BrowserClickPayload(BaseModel):
    client_id: str
    x: int = 0
    y: int = 0


class BrowserTypePayload(BaseModel):
    client_id: str
    text: str = Field(max_length=500)


class BrowserPressPayload(BaseModel):
    client_id: str
    key: str = Field(max_length=24)


def _browser_error_response(e: Exception):
    from agent_core.services.browser_session import (
        BrowserNotOpenError,
        BrowserUnavailableError,
    )

    if isinstance(e, BrowserUnavailableError):
        return JSONResponse(
            {"error": {"code": "BROWSER_UNAVAILABLE", "message": str(e)[:200]}},
            status_code=503,
        )
    if isinstance(e, BrowserNotOpenError):
        return JSONResponse(
            {"error": {"code": "BROWSER_NOT_OPEN", "message": str(e)[:200]}},
            status_code=409,
        )
    if isinstance(e, ValueError):
        return JSONResponse(
            {"error": {"code": "BROWSER_BAD_REQUEST", "message": str(e)[:200]}},
            status_code=400,
        )
    return JSONResponse(
        {"error": {"code": "BROWSER_ERROR", "message": str(e)[:200]}}, status_code=500
    )


@app.post("/api/browser/open")
async def api_browser_open(req: BrowserOpenPayload):
    room = get_room(req.client_id)
    try:
        result = await _room_browser(room).open(req.url)
    except Exception as e:
        return _browser_error_response(e)
    broadcast_log(req.client_id, "INFO", f"TARAYICI: Canlı oturum açıldı -> {result.get('url', '')[:80]}")
    return result


@app.get("/api/browser/shot")
async def api_browser_shot(client_id: str):
    room = get_room(client_id)
    try:
        png = await _room_browser(room).shot()
    except Exception as e:
        return _browser_error_response(e)
    return StreamingResponse(io.BytesIO(png), media_type="image/png")


@app.get("/api/browser/state")
async def api_browser_state(client_id: str):
    room = get_room(client_id)
    st = await _room_browser(room).state()
    st["saved_session"] = "ig_sessionid" in room.get("vault", {})
    return st


@app.post("/api/browser/click")
async def api_browser_click(req: BrowserClickPayload):
    room = get_room(req.client_id)
    try:
        return await _room_browser(room).click(req.x, req.y)
    except Exception as e:
        return _browser_error_response(e)


@app.post("/api/browser/type")
async def api_browser_type(req: BrowserTypePayload):
    room = get_room(req.client_id)
    try:
        # NOT: metin yalnızca tarayıcıya yazılır; loga/hafızaya alınmaz.
        return await _room_browser(room).type_text(req.text)
    except Exception as e:
        return _browser_error_response(e)


@app.post("/api/browser/press")
async def api_browser_press(req: BrowserPressPayload):
    room = get_room(req.client_id)
    try:
        return await _room_browser(room).press(req.key)
    except Exception as e:
        return _browser_error_response(e)


@app.post("/api/browser/back")
async def api_browser_back(req: BrowserClientPayload):
    room = get_room(req.client_id)
    try:
        return await _room_browser(room).back()
    except Exception as e:
        return _browser_error_response(e)


@app.post("/api/browser/save")
async def api_browser_save(req: BrowserClientPayload):
    room = get_room(req.client_id)
    try:
        sessionid = await _room_browser(room).session_cookie()
    except Exception as e:
        return _browser_error_response(e)
    if not sessionid:
        return {
            "status": "no_session",
            "saved": False,
            "hint": "Tarayıcıda Instagram girişi tamamlanmamış (sessionid yok).",
        }
    room["vault"]["ig_sessionid"] = sessionid
    broadcast_log(req.client_id, "INFO", "KASA: Canlı IG oturumu mühürlendi (sessionid).")
    return {"status": "saved", "saved": True}


@app.post("/api/browser/close")
async def api_browser_close(req: BrowserClientPayload):
    room = get_room(req.client_id)
    return await _room_browser(room).close()


@app.post("/api/scraper/authorize-alternative")
async def authorize_scraper_alternative(req: AlternativeAuthorizationPayload):
    room = get_room(req.client_id)
    pending = room.get("pending_alternative_authorization")
    if not pending:
        return {"status": "no_pending_authorization"}
    if not req.approved or req.alternative not in pending["alternatives"]:
        room.pop("pending_alternative_authorization", None)
        return {"status": "declined"}
    # Authorization is recorded; provider execution is a separate explicit
    # route and must not fabricate an X profile from unrelated sources.
    room["authorized_alternatives"] = room.get("authorized_alternatives", []) + [{
        "alternative": req.alternative,
        "url": pending["url"],
        "authorized_at": datetime.now().isoformat(),
    }]

    if req.alternative == "public_web_search":
        executor = get_executor(req.client_id)
        research = await _run_public_web_research(
            pending["url"], executor.search_engine, client_id=req.client_id
        )
        room["web_research"] = research
        room.pop("pending_alternative_authorization", None)
        broadcast_log(
            req.client_id, "INFO",
            f"ALTERNATİF ARAŞTIRMA: {research['note']}",
        )
        return {"status": "research_completed", "alternative": req.alternative,
                "research": research}

    room.pop("pending_alternative_authorization", None)
    return {"status": "authorized", "alternative": req.alternative}


class IntervenePayload(BaseModel):
    client_id: str
    action_type: str
    target_agent: Optional[str] = None
    parameters: dict = Field(default_factory=dict)
    reason: str = ""


class InterventionRecord(BaseModel):
    client_id: str
    action_type: str
    target_agent: Optional[str] = None
    parameters: dict = Field(default_factory=dict)
    reason: str = ""
    requested_at: str
    outcome: str


@app.post("/api/executor/intervene")
async def executor_intervene(req: IntervenePayload):
    """Record intervention requests without mutating shared executor safety state."""
    room = get_room(req.client_id)
    record = InterventionRecord(
        client_id=req.client_id,
        action_type=req.action_type,
        target_agent=req.target_agent,
        parameters=req.parameters,
        reason=req.reason,
        requested_at=datetime.now().isoformat(),
        outcome="review_required",
    )
    room.setdefault("interventions", []).append(record.model_dump())

    # These actions previously rewrote uncertainty or deleted agents from the
    # room's shared executor. They are now auditable requests, not bypasses.
    if req.action_type in {"OVERRIDE_CONFIDENCE", "SKIP_AGENT", "HALT"}:
        broadcast_log(req.client_id, "WARNING", f"MÜDAHALE KAYDEDİLDİ: {req.action_type}; otomatik uygulanmadı.")
        return {
            "status": "review_required",
            "message": "Talep kaydedildi. Kanıt/güvenlik kuralları otomatik olarak değiştirilmedi.",
            "intervention": record.model_dump(),
        }

    return {
        "status": "acknowledged",
        "message": "Müdahale talebi kaydedildi; uygulanmadan önce inceleme gerekir.",
        "intervention": record.model_dump(),
    }

class InterpreterPayload(BaseModel):
    client_id: str
    prompt: str
    auto_run: bool = False

@app.post("/api/experimental/interpreter/execute")
async def interpreter_execute(req: InterpreterPayload):
    """Open Interpreter ile otonom kod icra eder"""
    if os.getenv("ENABLE_INTERPRETER", "false").lower() != "true":
        raise HTTPException(status_code=403, detail="Interpreter endpoint is disabled by default for security.")
        
    room = get_room(req.client_id)
    executor = room.get("executor")
    interpreter_agent = executor.agents.get("interpreter")
    
    if not interpreter_agent:
        return {"error": "Interpreter Agent aktif değil"}
        
    broadcast_log(req.client_id, "INFO", f"INTERPRETER: Görev icra ediliyor -> {req.prompt[:60]}...")
    res = await interpreter_agent.execute_task(
        prompt=req.prompt,
        api_key=executor.llm_gateway.api_key,
        auto_run=req.auto_run
    )
    
    if res.status == "success":
        broadcast_log(req.client_id, "INFO", "INTERPRETER: İcra başarıyla tamamlandı.")
    else:
        broadcast_log(req.client_id, "ERROR", f"INTERPRETER HATA: {res.error_message}")
        
    return res.model_dump()

# --- Görev geçmişi ve veri silme (FAZ 3 / etik çerçeve: kişisel veri hedefli sistemde
#     retention hakkı): bellekteki kanıt dosyaları listelenir ve KALICI olarak silinir. ---

def _read_tasks_sync(storage: str):
    tasks = []
    if os.path.isdir(storage):
        for fn in sorted(os.listdir(storage)):
            if not fn.endswith(".json") or fn == "learnings.json":
                continue
            task_id = fn[:-5]
            try:
                path = safe_child_path(storage, fn)
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict) or not isinstance(data.get("evidence", []), list):
                    raise ValueError("invalid canonical memory schema")
                tasks.append({
                    "task_id": data.get("task_id", task_id),
                    "last_updated": data.get("last_updated"),
                    "evidence_count": len(data.get("evidence", [])),
                    "confidence": data.get("confidence"),
                    "memory_state": "READY",
                    "memory_error_code": None,
                })
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                # A malformed task remains visible and is never represented as
                # an absent task in retention/operations APIs.
                tasks.append({
                    "task_id": task_id,
                    "last_updated": None,
                    "evidence_count": None,
                    "confidence": None,
                    "memory_state": "CORRUPTED",
                    "memory_error_code": "MEMORY_CORRUPTED",
                })
    return tasks

@app.get("/api/tasks")
async def api_list_tasks(client_id: str):
    room = get_room(client_id)
    storage = room["executor"].memory.storage_path
    tasks = await asyncio.to_thread(_read_tasks_sync, storage)
    active = list(room.get("active_tasks", {}).keys())
    return {"tasks": tasks, "active_tasks": active}


def _terminate_mission(client_id: str, task_id: str, action: str, reason: str):
    # [AUDIT R3] task_id doğrulaması: DELETE'teki INVALID_TASK_ID sözleşmesi
    # cancel/halt'e de taşınır (regex + uzunluk). Uzun `reason` da sınırlanır
    # (WS'e + oda durumuna akıyordu).
    try:
        if len(task_id) > _MAX_TASK_ID_LENGTH:
            raise ValueError
        validate_identifier(task_id, field="task_id")
    except ValueError:
        return JSONResponse(
            {"error": {"code": "INVALID_TASK_ID", "message": "Invalid task identifier"}},
            status_code=400,
        )
    if len(reason or "") > _MAX_TERMINATE_REASON_LENGTH:
        return JSONResponse(
            {"error": {"code": "INVALID_REASON", "message": "reason exceeds 500 chars"}},
            status_code=400,
        )
    room = get_room(client_id)
    run = _lifecycle(room).get_run(task_id)
    if run is None:
        return JSONResponse(
            {"error": {"code": "TASK_NOT_FOUND", "message": "Task not found"}},
            status_code=404,
        )
    decision = _lifecycle(room).terminate(task_id, action)
    if not decision.accepted:
        return JSONResponse(
            {"error": {"code": "TASK_ALREADY_TERMINAL", "message": "Task already reached a terminal state"}},
            status_code=409,
        )

    mission = room.get("mission_tasks", {}).get(task_id)
    if mission is not None and not mission.done():
        mission.cancel()
    if decision.outcome != "IDEMPOTENT":
        if action == "cancel":
            broadcast_event(client_id, TaskCancelledEvent(
                task_id=task_id,
                agent_name="PinealExecutor",
                reason=reason or "Cancelled by user",
            ))
            broadcast_result_error(client_id, "cancelled", "GÖREV İPTAL EDİLDİ", task_id)
        else:
            broadcast_event(client_id, ErrorHaltEvent(
                task_id=task_id,
                agent_name="PinealExecutor",
                error_code="USER_HALT",
                error_message=reason or "Halted by user",
                severity=Severity.Warning,
            ))
            broadcast_result_error(
                client_id,
                "halted_user",
                "GÖREV KULLANICI TARAFINDAN DURDURULDU",
                task_id,
            )
    return {
        "status": "cancelled" if action == "cancel" else "halted_user",
        "task_id": task_id,
        "outcome": decision.outcome,
    }


@app.get("/api/tasks/{task_id}/changes")
async def api_task_changes(
    task_id: str = Path(min_length=1, max_length=_MAX_TASK_ID_LENGTH),
    client_id: str = "default",
):
    """[FAZ B · B7] Bu görev, aynı hedefin ÖNCEKİ taramasına göre ne değişti?

    Önceki kayıt yoksa `available:false` + `no_baseline` döner; fark
    UYDURULMAZ. Görev bitiminde parmak izi otomatik yazılır (broadcast_result).
    """
    try:
        validate_identifier(task_id, field="task_id")
    except ValueError:
        return JSONResponse(
            {"error": {"code": "INVALID_TASK_ID", "message": "Invalid task identifier"}},
            status_code=400,
        )

    room = get_room(client_id)
    latest = room.get("latest_result") or {}
    if latest.get("task_id") == task_id and isinstance(latest.get("changes"), dict):
        return latest["changes"]

    executor = room.get("executor")
    if executor is None:
        return JSONResponse(
            {"error": {"code": "NO_EXECUTOR", "message": "Oda hazır değil"}},
            status_code=503,
        )
    from agent_core.services.change_tracker import build_snapshot, diff_snapshots, latest_before

    try:
        memory = executor.memory.get_task_memory(task_id)
    except Exception as exc:
        return JSONResponse(
            {
                "error": {
                    "code": "MEMORY_UNAVAILABLE",
                    "message": f"Görev belleği okunamadı: {type(exc).__name__}",
                }
            },
            status_code=409,
        )
    snapshot = build_snapshot(
        (memory or {}).get("evidence") or [],
        (memory or {}).get("target_profile") or {},
        task_id=task_id,
    )
    previous = latest_before(
        getattr(executor.memory, "storage_path", "./memory/"), snapshot.target, task_id
    )
    return diff_snapshots(previous, snapshot).model_dump()


@app.get("/api/tasks/{task_id}/graph")
async def api_task_graph(
    task_id: str = Path(min_length=1, max_length=_MAX_TASK_ID_LENGTH),
    client_id: str = "default",
):
    """[FAZ B · B4] Görevin kanıtından GERÇEK ilişki grafı.

    `HolographicResonanceMesh` artık rastgele düğüm üretmiyor: bu uçtan
    beslenir. Kanıt yoksa graf BOŞ döner (`available:false` + sebep) — arayüz
    boş graf için uydurma düğüm ÇİZMEZ.
    """
    try:
        validate_identifier(task_id, field="task_id")
    except ValueError:
        return JSONResponse(
            {"error": {"code": "INVALID_TASK_ID", "message": "Invalid task identifier"}},
            status_code=400,
        )

    room = get_room(client_id)
    executor = room.get("executor")
    if executor is None:
        return JSONResponse(
            {"error": {"code": "NO_EXECUTOR", "message": "Oda hazır değil"}},
            status_code=503,
        )

    try:
        memory = executor.memory.get_task_memory(task_id)
    except Exception as exc:  # bozuk bellek gizlenmez
        logger.warning("graph: bellek okunamadı: %s", type(exc).__name__)
        return JSONResponse(
            {
                "error": {
                    "code": "MEMORY_UNAVAILABLE",
                    "message": f"Görev belleği okunamadı: {type(exc).__name__}",
                }
            },
            status_code=409,
        )

    from agent_core.services.graph_builder import graph_from_task_memory

    graph = graph_from_task_memory(memory, (memory or {}).get("target_profile"))
    return graph.model_dump()


class CalibrationObservationPayload(BaseModel):
    """[FAZ B · B5] Elle ölçüm girişi: skor + (varsa) operatör etiketi."""

    score: float = Field(ge=0.0, le=1.0)
    scope: str = Field(default="quote", max_length=32)
    truth: Optional[bool] = None
    task_id: str = Field(default="", max_length=128)
    claim_id: str = Field(default="", max_length=128)
    note: str = Field(default="", max_length=200)


class CalibrationAdjudicationPayload(BaseModel):
    """[FAZ B · B5] Bir ölçüme operatörün etiket koyması (karar mercii operatör)."""

    observation_id: str = Field(min_length=1, max_length=64)
    truth: bool


@app.get("/api/memory/{target}")
async def api_memory_crystal(target: str = Path(min_length=1, max_length=128)):
    """[FAZ B · B2/B3] Hedefin KALICI hafıza kristali: kaç hatıra, hangi görevler.

    Görev bitince hafıza sıfırlanmıyor: kristal hedef başına yaşar. Yoksa
    `available:false` döner — geçmiş UYDURULMAZ.
    """
    from agent_core.services import memory_crystal

    return memory_crystal.summarize(target)


@app.get("/api/memory/{target}/recall")
async def api_memory_recall(
    target: str = Path(min_length=1, max_length=128),
    query: str = "",
    k: int = 8,
    exclude_task_id: str = "",
):
    """[FAZ B · B2/B3] Kristalden ilgili hatıraları ÇEKER (deterministik vektör).

    Sorgu verilmezse hedefin kendi adıyla aranır. Sonuçta her hatıranın NEDEN
    seçildiği (benzerlik/tazelik/kanıt) açıkça yazar — gizli skor yok.
    """
    from agent_core.services import memory_crystal

    result = memory_crystal.recall(
        target,
        query or target,
        k=max(1, min(50, k)),
        exclude_task_id=exclude_task_id,
    )
    return result.model_dump()


@app.get("/api/telemetry/taste")
async def api_telemetry_taste(limit: int = 20):
    """[FAZ C · C1] Jenerik yanıt telemetrisi: kaç yanıt DÜŞTÜ, neden düştü.

    Aspasia'nın dili artık bir prompt umudu değil, ölçülen bir katman:
    jenerik bulunan yanıt kullanıcıya çıkmaz ve buraya yazılır. Eşik aynı
    kalibrasyon disiplinine bağlıdır (`taste` kapsamı) — ölçülmeden değişmez.
    """
    from agent_core.services import taste_filter

    return taste_filter.telemetry_summary(limit=max(1, min(100, limit)))


@app.get("/api/calibration")
async def api_calibration(scope: str = ""):
    """[FAZ B · B5] Eşik kalibrasyonunun GERÇEK durumu.

    Sabit 0.70 eşiğinin yerini alan ÖLÇÜLEN eşik burada görünür: kaynağı
    (`varsayılan` / `kalibre` / `elle_sabitleme`), güven aralığı, geri test
    tablosu ve güvenilirlik diyagramı. Veri yetersizse eşik DEĞİŞMEMİŞTİR ve
    bu açıkça yazar — "ölçülmüş gibi" yapılmaz.
    """
    from agent_core.services import threshold_calibration as calib

    scopes = [scope] if scope else [calib.SCOPE_QUOTE, calib.SCOPE_CONFIDENCE]
    return {
        "scopes": {name: calib.summary(scope=name) for name in scopes},
        "ledger": {
            "dir": calib.storage_dir(),
            "rows": len(calib.load()),
            "labeled": sum(1 for row in calib.load() if row.truth is not None),
        },
        "min_samples": calib.min_samples(),
    }


@app.post("/api/calibration/observations")
async def api_calibration_record(req: CalibrationObservationPayload):
    """[FAZ B · B5] Ledger'a ölçüm yaz (ham metin DEĞİL: yalnız skor + kimlik)."""
    from agent_core.services import threshold_calibration as calib

    obs = calib.record(
        req.score,
        scope=req.scope,
        matched=req.score >= calib.resolved_threshold(req.scope).value,
        task_id=req.task_id,
        claim_id=req.claim_id,
        truth=req.truth,
        note=req.note,
    )
    if obs is None:
        return JSONResponse(
            {
                "status": "not_recorded",
                "reason": "gözlem_kapali",
                "hint": "PINEAL_CALIB_OBSERVE=true",
            },
            status_code=409,
        )
    return {"status": "recorded", "observation": obs.model_dump()}


@app.post("/api/calibration/adjudicate")
async def api_calibration_adjudicate(req: CalibrationAdjudicationPayload):
    """[FAZ B · B5] Operatör bir ölçümü ETİKETLER: eşiği değiştiren veri budur."""
    from agent_core.services import threshold_calibration as calib

    if not calib.adjudicate(req.observation_id, req.truth):
        return JSONResponse(
            {"error": {"code": "OBSERVATION_NOT_FOUND", "message": "Kayıt bulunamadı"}},
            status_code=404,
        )
    return {
        "status": "adjudicated",
        "observation_id": req.observation_id,
        "truth": req.truth,
        "threshold": calib.summary(scope=calib.SCOPE_QUOTE),
    }


@app.get("/api/tasks/{task_id}/memory")
async def api_task_memory(
    task_id: str = Path(min_length=1, max_length=_MAX_TASK_ID_LENGTH),
    client_id: str = "default",
):
    """[FAZ B · B2/B3] Görevin hedefinin KALICI hafıza kristali.

    `HolographicResonanceMesh` grafi (B4) ve değişim raporu (B7) ile aynı
    desende: kanıt yoksa hafıza UYDURULMAZ (`available:false` + sebep).
    Hatıralar önceki taramalardan gelir; bu görevin kendi kanıtı hariçtir.
    """
    try:
        validate_identifier(task_id, field="task_id")
    except ValueError:
        return JSONResponse(
            {"error": {"code": "INVALID_TASK_ID", "message": "Invalid task identifier"}},
            status_code=400,
        )

    room = get_room(client_id)
    executor = room.get("executor")
    if executor is None:
        return JSONResponse(
            {"error": {"code": "NO_EXECUTOR", "message": "Oda hazır değil"}},
            status_code=503,
        )

    try:
        memory = executor.memory.get_task_memory(task_id)
    except Exception as exc:  # bozuk bellek gizlenmez
        logger.warning("memory crystal: bellek okunamadı: %s", type(exc).__name__)
        return JSONResponse(
            {
                "error": {
                    "code": "MEMORY_UNAVAILABLE",
                    "message": f"Görev belleği okunamadı: {type(exc).__name__}",
                }
            },
            status_code=409,
        )

    from agent_core.services import memory_crystal
    from agent_core.services.change_tracker import target_key

    storage = getattr(executor.memory, "storage_path", None)
    payload = memory or {}
    evidence = payload.get("evidence") or []
    profile = payload.get("target_profile") or {}
    if not isinstance(profile, dict):
        profile = {}

    target = target_key(profile, evidence if isinstance(evidence, list) else [])
    if not target:
        return {
            "available": False,
            "reason": "no_target",
            "machine_note": "KRİSTAL: hedef anahtarı yok — hatıra uydurulmadı.",
        }

    query = " ".join(str(profile.get(field) or "") for field in ("username", "name", "bio")).strip()
    summary = memory_crystal.summarize(target, base=storage)
    result = memory_crystal.recall(
        target, query or target, k=5, base=storage, exclude_task_id=str(task_id or "")
    )
    summary["recalled"] = [hit.model_dump() for hit in result.hits]
    summary["recall_note"] = result.machine_note
    return summary


#: [FAZ C · C3] Mikrofon kaydı için üst sınır: 8 MiB (yetenekteki sınırla aynı).
MAX_LISTEN_AUDIO_BYTES = 8 * 1024 * 1024


class SpeechListenResponse(BaseModel):
    """[FAZ C · C3] Mikrofonun duyduğu: metin YEREL motordan gelir, uydurulmaz."""

    available: bool = False
    reason: str | None = None
    state: str = "idle"
    transcript: str = ""
    engine: str | None = None
    chars: int = 0
    machine_note: str = ""


class SpeechSayPayload(BaseModel):
    """[FAZ C · C2] Seslendirme isteği."""

    text: str = Field(min_length=1, max_length=2000)
    voice: str = Field(default="", max_length=64)
    client_id: str = Field(default="default", max_length=128)


@app.get("/api/speech/status")
async def api_speech_status():
    """[FAZ C · C2] Sesin GERÇEK durumu: motor var mı, hangi kapı, konuşuyor mu."""
    from agent_core.services import speech

    return speech.status()


class SpeechReportPayload(BaseModel):
    """[FAZ C · C4] Sesli rapor: görev sonucu (veya doğrudan metin) okunur."""

    client_id: str = "default"
    report: dict | None = None
    text: str = ""


@app.post("/api/speech/report")
async def api_speech_report(req: SpeechReportPayload):
    """[FAZ C · C4] Bulunanı SÖYLER: görev sonucu sesli rapora çevrilir.

    Metin payload'daki GERÇEK alanlardan kurulur — olmayan alan için cümle
    UYDURULMAZ. Motor yoksa ses üretilmez; metin yine de döner (gizlenmez).
    """
    from agent_core.services import speech

    if not rate_limit(f"report:{req.client_id}", "speech"):
        return JSONResponse(
            {"error": {"code": "RATE_LIMITED", "message": "Çok fazla rapor okuma isteği"}},
            status_code=429,
        )

    result = await speech.read_report(
        req.report,
        text=req.text,
        vault_locked=not _check_vault_interlock(req.client_id),
    )
    payload = result.model_dump()
    if result.available:
        broadcast_speech(req.client_id, {"state": "speaking", **payload})
        duration = max(0.0, float(result.duration_ms or 0) / 1000.0)
        asyncio.create_task(_speech_finished(req.client_id, duration))
        broadcast_log(req.client_id, "INFO", f"SES: {result.machine_note}")
    else:
        broadcast_speech(req.client_id, {"state": "denied", **payload})
        broadcast_log(req.client_id, "WARNING", f"SES: RAPOR OKUNAMADI: {result.reason}")
    return payload


@app.post("/api/speech/listen", response_model=SpeechListenResponse)
async def api_speech_listen(
    request: Request,
    client_id: str = "default",
    language: str = "",
):
    """[FAZ C · C3] Göz dinler: mikrofon kaydı YEREL motorda metne çevrilir.

    Ses dosyası makineden dışarı çıkmaz (yalnız 127.0.0.1/::1/localhost).
    Motor yoksa uydurma transkript DÖNMEZ: `available:false` + sebep.
    Konuşma sürerken çağrılırsa önce SUSTURUR (araya girme).
    """
    from agent_core.services import speech

    if not rate_limit(f"listen:{client_id}", "speech"):
        return JSONResponse(
            {"error": {"code": "RATE_LIMITED", "message": "Çok fazla dinleme isteği"}},
            status_code=429,
        )

    try:
        form = await request.form()
    except Exception:  # python-multipart kurulu değilse net hata (uydurma yanıt yok)
        return JSONResponse(
            {
                "error": {
                    "code": "MULTIPART_UNAVAILABLE",
                    "message": "Dosya yükleme için python-multipart gerekli",
                }
            },
            status_code=500,
        )
    upload = form.get("file")
    if upload is None:
        return JSONResponse(
            {"error": {"code": "NO_AUDIO", "message": "Ses dosyası yok"}},
            status_code=400,
        )
    audio = await upload.read()
    if not audio:
        return JSONResponse(
            {"error": {"code": "EMPTY_AUDIO", "message": "Ses dosyası boş"}},
            status_code=400,
        )
    if len(audio) > MAX_LISTEN_AUDIO_BYTES:
        return JSONResponse(
            {"error": {"code": "AUDIO_TOO_LARGE", "message": "Ses dosyası çok büyük"}},
            status_code=413,
        )

    suffix = os.path.splitext(getattr(upload, "filename", "") or "")[1][:8] or ".webm"
    # ARAYA GİRME: konuşurken dinlemeye geçiyorsa önce susar.
    if speech.status()["state"] == "speaking":
        speech.interrupt()
    speech.start_listening()
    broadcast_speech(client_id, {"state": "listening"})
    result = await speech.listen(
        audio,
        suffix=suffix,
        language=language or None,
        vault_locked=not _check_vault_interlock(client_id),
    )
    payload = result.model_dump()
    if result.available:
        broadcast_speech(client_id, {"state": "idle", "transcript": result.transcript})
        broadcast_log(client_id, "INFO", f"SES: duyuldu ({result.chars} karakter)")
    else:
        broadcast_speech(client_id, {"state": "denied", "reason": result.reason})
        broadcast_log(client_id, "WARNING", f"SES DUYULAMADI: {result.reason}")
    return payload


@app.post("/api/speech/say")
async def api_speech_say(req: SpeechSayPayload):
    """[FAZ C · C2] Aspasia konuşur — ses YERELDE üretilir, makineden çıkmaz.

    Motor yoksa uydurma ses DÖNMEZ: `available:false` + makine-okunur sebep.
    Konuşma durumu (`speaking` → `idle`) WebSocket'ten UI'a akar.
    """
    from agent_core.services import speech

    if not rate_limit(f"speech:{req.client_id}", "speech"):
        return JSONResponse(
            {"error": {"code": "RATE_LIMITED", "message": "Çok fazla seslendirme isteği"}},
            status_code=429,
        )

    # Kasa interlock'u GERÇEK durumdan okunur (uydurma "açık" yok): kilitliyken
    # yetenek zaten koşamaz (Tüzük Md.4).
    result = await speech.speak(
        req.text,
        voice=req.voice or None,
        vault_locked=not _check_vault_interlock(req.client_id),
    )
    payload = result.model_dump()
    if result.available:
        broadcast_speech(req.client_id, {"state": "speaking", **payload})
        duration = max(0.0, float(result.duration_ms or 0) / 1000.0)
        asyncio.create_task(_speech_finished(req.client_id, duration))
        broadcast_log(req.client_id, "INFO", f"SES: {result.machine_note}")
    else:
        broadcast_speech(req.client_id, {"state": "denied", **payload})
        broadcast_log(req.client_id, "WARNING", f"SES ÜRETİLEMEDİ: {result.reason}")
    return payload


async def _speech_finished(client_id: str, seconds: float) -> None:
    """Ses süresi bitince durum `idle`'a döner (tahmin değil: WAV süresi)."""
    try:
        await asyncio.sleep(min(60.0, seconds + 0.35))
    except asyncio.CancelledError:
        return
    from agent_core.services import speech

    speech.set_state("idle")
    broadcast_speech(client_id, {"state": "idle"})


@app.get("/api/speech/audio/{name}")
async def api_speech_audio(name: str = Path(min_length=1, max_length=128)):
    """[FAZ C · C2] Üretilen ses dosyası (yalnız yerel dosya; yol kaçışı kapalı)."""
    from agent_core.services import speech
    from agent_core.capabilities.adapters_voice import speech_dir

    try:
        path = safe_child_path(speech_dir(), name)
    except ValueError:
        return JSONResponse(
            {"error": {"code": "INVALID_AUDIO_NAME", "message": "Geçersiz ses dosyası"}},
            status_code=400,
        )
    if not os.path.exists(path):
        return JSONResponse(
            {"error": {"code": "NOT_FOUND", "message": "Ses dosyası yok"}},
            status_code=404,
        )
    _ = speech  # servis yolu tek kaynaktır; dosya adı yeteneğin verdiği addır
    return FileResponse(path, media_type="audio/wav", filename=name)


@app.post("/api/speech/stop")
async def api_speech_stop(client_id: str = "default"):
    """[FAZ C · C3] Araya girme: konuşma KESİLİR ve durum UI'a düşer."""
    from agent_core.services import speech

    # [FAZ C · C3] ARAYA GİRME: konuşurken mikrofon açılırsa Aspasia SUSAR.
    was_speaking = speech.status()["state"] == "speaking"
    speech.interrupt() if was_speaking else speech.stop()
    broadcast_speech(
        client_id,
        {"state": "interrupted" if was_speaking else "idle", "interrupted": was_speaking},
    )
    return {
        "status": "interrupted" if was_speaking else "stopped",
        "state": speech.status()["state"],
    }


# ---------------------------------------------------------------------------
# [FAZ D · D4] DİL: tespit deterministik (model/ağ yok), çeviri YEREL.
# Uydurma yok: sinyal yoksa etiket dönmez, motor yoksa çeviri dönmez.
# ---------------------------------------------------------------------------


class JuryVotePayload(BaseModel):
    """[FAZ D · D2] Yerel jüri oylaması: iddia + kanıt metni."""

    claim: str = Field(min_length=1, max_length=20000)
    evidence: str = Field(min_length=1, max_length=40000)
    client_id: str = Field(default="default", max_length=128)


@app.get("/api/jury/status")
async def api_jury_status():
    """[FAZ D · D2] Jürinin GERÇEK durumu: uç yerel mi, kaç BAĞIMSIZ koltuk,
    hangi kapı, yeter sayı. Model tanımlı değilse 'hazır' denmez."""
    from agent_core.services import local_jury

    return local_jury.status()


@app.post("/api/jury/vote")
async def api_jury_vote(req: JuryVotePayload):
    """[FAZ D · D2] Aynı kanıt yerel jüriye sorulur: kural açıkça döner.

    Konsensüs yoksa sonuç 'karar üretilmedi' olur (``consensus: false`` +
    ``rule``); koltuk dökümü gizlenmez. Uzak uç yoktur: veri makineden çıkmaz.
    """
    from agent_core.capabilities.base import CapabilityContext
    from agent_core.capabilities.policy import PolicyState
    from agent_core.capabilities.registry import bootstrap
    from agent_core.capabilities.runner import CapabilityRunner
    from agent_core.services import local_jury

    if not rate_limit(f"jury:{req.client_id}", "jury"):
        return JSONResponse(
            {"error": {"code": "RATE_LIMITED", "message": "Çok fazla jüri isteği"}},
            status_code=429,
        )

    runner = CapabilityRunner(registry=bootstrap())
    state = PolicyState(
        enabled_flags={local_jury.GATE: _flag_env(local_jury.GATE)},
        vault_locked=not _check_vault_interlock(req.client_id),
        rate_ok=True,
    )
    result = await runner.run(
        "verifier.jury.local",
        CapabilityContext(subject=req.claim, params={"evidence": req.evidence}),
        state=state,
    )
    notes = dict(result.notes or {})
    payload = {
        "available": bool(result.available),
        "denied_by": result.denied_by,
        "reason": result.unavailable_reason,
        "verdict": notes.get("verdict", ""),
        "rule": notes.get("rule", ""),
        "consensus": bool(notes.get("consensus", False)),
        "seats_run": notes.get("seats_run", 0),
        "counted": notes.get("counted", 0),
        "quorum_required": notes.get("quorum_required", 1),
        "tally": notes.get("tally", {}),
        "dissent": notes.get("dissent", []),
        "seat_errors": notes.get("seat_errors", {}),
        "seats": notes.get("seats", []),
        "endpoint": notes.get("endpoint", ""),
        "machine_note": notes.get("machine_note", ""),
        "evidence_ids": [item.evidence_id for item in result.items],
    }
    if result.denied_by:
        broadcast_log(req.client_id, "WARNING", f"JÜRİ: oylama engellendi — kapı:{result.denied_by}")
    elif payload["consensus"]:
        broadcast_log(
            req.client_id,
            "INFO",
            f"JÜRİ: {payload['verdict']} ({payload['rule']}, {payload['counted']} koltuk)",
        )
    else:
        broadcast_log(
            req.client_id,
            "INFO",
            f"JÜRİ: konsensüs yok — {payload['rule'] or payload['reason']} (karar iddia edilmedi)",
        )
    return payload


class MediaAnalyzePayload(BaseModel):
    """[FAZ D · D3] Medya adli hattı: kaynak (URL/yol) + modlar."""

    source: str = Field(min_length=1, max_length=2048)
    client_id: str = Field(default="default", max_length=128)
    modes: list[str] = Field(default_factory=lambda: ["fetch", "frames"])
    sample_every: int = Field(default=5, ge=1, le=120)
    top_k: int = Field(default=3, ge=1, le=20)


#: Mod başına yanıtta taşınan kanıt satırı tavanı.
MAX_MEDIA_EVIDENCE = 25

_MEDIA_MODES = {
    "fetch": "sensor.media.fetch",
    "frames": "analyzer.media.frames",
    "transcript": "extractor.media.transcript",
    "similarity": "analyzer.media.similarity",
}


@app.get("/api/media/status")
async def api_media_status():
    """[FAZ D · D3] Medya hattının GERÇEK durumu: hangi araç var, hangi mod hazır.

    ffmpeg/yt-dlp/whisper yoksa "hazır" denmez; sebep makine-okunur.
    """
    from agent_core.capabilities import bootstrap
    from agent_core.services import media_forensics

    registry = bootstrap()
    rows = []
    for mode, cap_id in _MEDIA_MODES.items():
        cap = registry.get(cap_id)
        availability = cap.availability()
        rows.append(
            {
                "mode": mode,
                "capability_id": cap_id,
                "available": availability.available,
                "reason": availability.reason,
                "gates": sorted(cap.gates),
            }
        )
    return {
        "gate": media_forensics.GATE,
        "media_dir": str(media_forensics.media_dir()),
        "tools": {
            "yt-dlp": bool(shutil.which("yt-dlp")),
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "opencv": bool(importlib.util.find_spec("cv2")),
            "transcribe_engine": media_forensics.resolve_engine()[0] or "",
        },
        "transcribe_engine_reason": media_forensics.resolve_engine()[1],
        "modes": rows,
        "any_available": any(row["available"] for row in rows),
    }


@app.post("/api/media/analyze")
async def api_media_analyze(req: MediaAnalyzePayload):
    """[FAZ D · D3] Medyayı omurgadan işler: indir · kare kare ölç · yazıya dök · eşleştir.

    Her mod aynı mandaldan geçer (kasa + kapı). Ölçülmeyen şey iddia edilmez;
    araç yoksa sebep makine-okunurdur.
    """
    from agent_core.capabilities.base import CapabilityContext
    from agent_core.capabilities.policy import PolicyState
    from agent_core.capabilities.registry import bootstrap
    from agent_core.capabilities.runner import CapabilityRunner
    from agent_core.services import media_forensics

    if not rate_limit(f"media:{req.client_id}", "media"):
        return JSONResponse(
            {"error": {"code": "RATE_LIMITED", "message": "Çok fazla medya isteği"}},
            status_code=429,
        )

    wanted = [str(m).strip().lower() for m in (req.modes or [])]
    unknown = [m for m in wanted if m not in _MEDIA_MODES]
    if unknown:
        return JSONResponse(
            {"error": {"code": "UNKNOWN_MODE", "message": f"Bilinmeyen mod: {', '.join(unknown)}"}},
            status_code=400,
        )
    if not wanted:
        wanted = ["fetch", "frames"]

    runner = CapabilityRunner(registry=bootstrap())
    state = PolicyState(
        enabled_flags={media_forensics.GATE: _flag_env(media_forensics.GATE)},
        vault_locked=not _check_vault_interlock(req.client_id),
        rate_ok=True,
    )

    results: dict[str, Any] = {}
    for mode in wanted:
        cap_id = _MEDIA_MODES[mode]
        result = await runner.run(
            cap_id,
            CapabilityContext(
                subject=req.source,
                params={
                    "source": req.source,
                    "sample_every": req.sample_every,
                    "top_k": req.top_k,
                },
            ),
            state=state,
        )
        results[mode] = {
            "capability_id": cap_id,
            "available": bool(result.available),
            "denied_by": result.denied_by,
            "reason": result.unavailable_reason,
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "epistemic_type": item.epistemic_type,
                    "source_engine": item.source_engine,
                    "content": item.content[:400],
                    "provenance_refs": list(item.provenance_refs)[:5],
                }
                for item in result.items[:MAX_MEDIA_EVIDENCE]
            ],
            "notes": dict(result.notes or {}),
        }
        if result.denied_by:
            broadcast_log(req.client_id, "WARNING", f"MEDYA: {mode} engellendi — kapı:{result.denied_by}")
        elif not result.available:
            broadcast_log(req.client_id, "WARNING", f"MEDYA: {mode} hazır değil — {result.unavailable_reason}")
        else:
            broadcast_log(req.client_id, "INFO", f"MEDYA: {mode} tamam — {len(result.items)} kanıt")

    return {
        "source": req.source,
        "gate": media_forensics.GATE,
        "modes": results,
        "evidence_total": sum(len(r["evidence"]) for r in results.values()),
    }


class ReportBuildPayload(BaseModel):
    """[FAZ D · D5] Rapor paketi: kanıt satırları + istenen formatlar."""

    title: str = Field(min_length=1, max_length=200)
    client_id: str = Field(default="default", max_length=128)
    subject: str = Field(default="", max_length=200)
    evidence: list[dict] = Field(default_factory=list, max_length=200)
    formats: list[str] = Field(default_factory=lambda: ["markdown", "pdf", "diagram"])


@app.get("/api/report/status")
async def api_report_status():
    """[FAZ D · D5] Rapor fabrikası: hangi format GERÇEKTEN üretilebilir?

    reportlab/Pillow/ffmpeg yoksa "hazır" denmez; sebep makine-okunurdur.
    """
    from agent_core.services import report_factory

    formats = report_factory.availability()
    return {
        "gate": report_factory.GATE,
        "report_dir": str(report_factory.report_dir()),
        "formats": [
            {"format": name, "available": ok, "reason": reason}
            for name, (ok, reason) in sorted(formats.items())
        ],
        "any_available": any(ok for ok, _r in formats.values()),
        "manifest_schema": report_factory.MANIFEST_SCHEMA,
        "seal": "sha256 (bütünlük mührü; kriptografik imza değil)",
    }


@app.post("/api/report/build")
async def api_report_build(req: ReportBuildPayload):
    """[FAZ D · D5] Kanıt satırlarından rapor paketi üretir (hash'li, bağlantılı).

    Rapor UYDURULMAZ: girdi kanonik kanıt satırlarıdır; reddedilen satırlar
    sayılır ve raporda görünür. Format üretilemezse paket yine teslim edilir
    (markdown + manifest), eksik format dürüst sebeple işaretlenir.
    """
    from agent_core.capabilities.base import CapabilityContext
    from agent_core.capabilities.policy import PolicyState
    from agent_core.capabilities.registry import bootstrap
    from agent_core.capabilities.runner import CapabilityRunner
    from agent_core.services import report_factory

    if not rate_limit(f"report:{req.client_id}", "report"):
        return JSONResponse(
            {"error": {"code": "RATE_LIMITED", "message": "Çok fazla rapor isteği"}},
            status_code=429,
        )

    formats = [str(f).strip().lower() for f in (req.formats or [])]
    unknown = [f for f in formats if f not in ("markdown", "pdf", "diagram", "video")]
    if unknown:
        return JSONResponse(
            {"error": {"code": "UNKNOWN_FORMAT", "message": f"Bilinmeyen format: {', '.join(unknown)}"}},
            status_code=400,
        )

    wanted = [f for f in formats if f != "markdown"]  # markdown zaten her pakette
    cap_by_format = {
        "pdf": "renderer.report.pdf",
        "diagram": "renderer.report.diagram",
        "video": "renderer.report.video",
    }
    runner = CapabilityRunner(registry=bootstrap())
    state = PolicyState(
        enabled_flags={report_factory.GATE: _flag_env(report_factory.GATE)},
        vault_locked=not _check_vault_interlock(req.client_id),
        rate_ok=True,
    )

    results: dict[str, Any] = {}
    for fmt in wanted:
        result = await runner.run(
            cap_by_format[fmt],
            CapabilityContext(
                subject=req.title,
                params={"title": req.title, "subject": req.subject, "evidence": req.evidence},
            ),
            state=state,
        )
        results[fmt] = {
            "capability_id": cap_by_format[fmt],
            "available": bool(result.available),
            "denied_by": result.denied_by,
            "reason": result.unavailable_reason,
            "artifacts": result.notes.get("artifacts", []),
            "manifest_path": result.notes.get("manifest_path", ""),
            "manifest_sha256": result.notes.get("manifest_sha256", ""),
            "evidence_ids": result.notes.get("evidence_ids", []),
            "rejected_item_count": result.notes.get("rejected_item_count", 0),
            "excluded_strategy_count": result.notes.get("excluded_strategy_count", 0),
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "content": item.content[:300],
                    "provenance_refs": list(item.provenance_refs)[:5],
                }
                for item in result.items[:10]
            ],
        }
        if result.denied_by:
            broadcast_log(req.client_id, "WARNING", f"RAPOR: {fmt} engellendi — kapı:{result.denied_by}")
        elif not result.available:
            broadcast_log(req.client_id, "WARNING", f"RAPOR: {fmt} üretilemedi — {result.unavailable_reason}")
        else:
            broadcast_log(req.client_id, "INFO", f"RAPOR: {fmt} üretildi ({req.title[:40]})")

    return {
        "title": req.title,
        "subject": req.subject,
        "gate": report_factory.GATE,
        "formats": results or {"note": "yalnız markdown + manifest istendi"},
    }


class CompanyScanPayload(BaseModel):
    """[FAZ D · D6] Kurum hedefi taraması: alan adı + mod seçimi."""

    domain: str = Field(min_length=1, max_length=253)
    client_id: str = Field(default="default", max_length=128)
    modes: list[str] = Field(default_factory=lambda: ["harvester", "seo", "people"])
    limit: int = Field(default=200, ge=1, le=1000)


_COMPANY_MODES = {
    "harvester": "sensor.company.harvester",
    "seo": "sensor.company.seo",
    "people": "sensor.company.people",
}


@app.get("/api/company/status")
async def api_company_status():
    """[FAZ D · D6] Kurum hedefi yeteneklerinin GERÇEK durumu (defterden).

    Kapı kapalıysa ya da theHarvester yoksa "hazır" denmez; sebep makine-okunur.
    """
    from agent_core.capabilities import bootstrap

    registry = bootstrap()
    rows = []
    for mode, cap_id in _COMPANY_MODES.items():
        cap = registry.get(cap_id)
        availability = cap.availability()
        rows.append(
            {
                "mode": mode,
                "capability_id": cap_id,
                "available": availability.available,
                "reason": availability.reason,
                "gates": sorted(cap.gates),
            }
        )
    return {
        "gate": "ENABLE_COMPANY_TARGETING",
        "domain_hint": "yalnız alan adı (örn. ornek.com); özel/yerel adresler reddedilir",
        "modes": rows,
        "any_available": any(row["available"] for row in rows),
    }


@app.post("/api/company/scan")
async def api_company_scan(req: CompanyScanPayload):
    """[FAZ D · D6] Kurum hedefini omurgadan tarar (theHarvester · SEO · kişi).

    Her mod aynı mandaldan geçer: kasa + `ENABLE_COMPANY_TARGETING` + hız.
    Mod reddedilirse sebep gizlenmez; kanıt üretilmediyse `evidence` boş kalır.
    """
    from agent_core.capabilities.base import CapabilityContext
    from agent_core.capabilities.policy import PolicyState
    from agent_core.capabilities.registry import bootstrap
    from agent_core.capabilities.runner import CapabilityRunner
    from agent_core.services import company_recon

    if not rate_limit(f"company:{req.client_id}", "company"):
        return JSONResponse(
            {"error": {"code": "RATE_LIMITED", "message": "Çok fazla kurum taraması"}},
            status_code=429,
        )

    domain = company_recon.normalize_domain(req.domain)
    if not domain:
        return JSONResponse(
            {
                "error": {
                    "code": "INVALID_DOMAIN",
                    "message": "Geçerli bir alan adı verin (örn. ornek.com).",
                }
            },
            status_code=400,
        )

    wanted = [str(m).strip().lower() for m in (req.modes or [])]
    unknown = [m for m in wanted if m not in _COMPANY_MODES]
    if unknown:
        return JSONResponse(
            {"error": {"code": "UNKNOWN_MODE", "message": f"Bilinmeyen mod: {', '.join(unknown)}"}},
            status_code=400,
        )
    if not wanted:
        wanted = list(_COMPANY_MODES)

    runner = CapabilityRunner(registry=bootstrap())
    state = PolicyState(
        enabled_flags={company_recon.GATE: _flag_env(company_recon.GATE)},
        vault_locked=not _check_vault_interlock(req.client_id),
        rate_ok=True,
    )

    results: dict[str, Any] = {}
    for mode in wanted:
        cap_id = _COMPANY_MODES[mode]
        params: dict[str, Any] = {"domain": domain}
        if mode == "harvester":
            params["limit"] = req.limit
        result = await runner.run(
            cap_id,
            CapabilityContext(subject=domain, params=params),
            state=state,
        )
        results[mode] = {
            "capability_id": cap_id,
            "available": bool(result.available),
            "denied_by": result.denied_by,
            "reason": result.unavailable_reason,
            "counts": {
                "evidence": len(result.items),
            },
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "epistemic_type": item.epistemic_type,
                    "source_engine": item.source_engine,
                    "content": item.content[:400],
                    "provenance_refs": list(item.provenance_refs)[:5],
                }
                for item in result.items[:25]
            ],
            "notes": dict(result.notes or {}),
        }
        if result.denied_by:
            broadcast_log(
                req.client_id, "WARNING",
                f"KURUM: {mode} engellendi — kapı:{result.denied_by}",
            )
        elif not result.available:
            broadcast_log(
                req.client_id, "WARNING",
                f"KURUM: {mode} hazır değil — {result.unavailable_reason}",
            )
        else:
            broadcast_log(
                req.client_id, "INFO",
                f"KURUM: {mode} tamam — {len(result.items)} kanıt ({domain})",
            )

    return {
        "domain": domain,
        "gate": company_recon.GATE,
        "modes": results,
        "evidence_total": sum(r["counts"]["evidence"] for r in results.values()),
    }


@app.get("/api/mcp/status")
async def api_mcp_status(client_id: str = "default"):
    """[FAZ D · D1] MCP ihracının GERÇEK durumu: kaç yetenek araç olarak açık,
    hangi sürümler konuşuluyor, kasa mandalı ne durumda.

    Yetenek sayısı ``CapabilityRegistry``den okunur (ikinci envanter yok);
    kasa durumu ``_check_vault_interlock`` ile ``/api/initiate`` ile AYNI
    kapıdan gelir. Bu uç hiçbir yeteneği KOŞTURMAZ; yalnızca rapor eder.
    """
    from agent_core.mcp import protocol as _mcp_protocol
    from agent_core.mcp.tools import build_tools

    try:
        from agent_core.capabilities import bootstrap as _caps_bootstrap

        registry = _caps_bootstrap()
        capabilities = len(registry.ids())
        tools = len(build_tools(registry)) + 1  # + pineal_status (sunucunun kendi aracı)
    except Exception as exc:  # envanter okunamazsa uydurma sayı dönmez
        logger.warning("MCP durumu okunamadı: %s", type(exc).__name__)
        return JSONResponse(
            {"available": False, "reason": f"registry_error:{type(exc).__name__}"},
            status_code=503,
        )

    unlocked = _check_vault_interlock(client_id)
    try:
        from agent_core.mcp.state_bridge import limiter_from_env

        limiter = limiter_from_env()
        rate_limit = {"limit": limiter.limit, "window_seconds": limiter.window}
    except Exception:  # pragma: no cover - savunma
        rate_limit = {}
    from agent_core.mcp.server import server_version

    return {
        "available": True,
        "transport": "stdio",
        "command": "python -m agent_core.mcp",
        "capabilities": capabilities,
        "tools": tools,
        "server_version": server_version(),
        "protocol_current": _mcp_protocol.PROTOCOL_VERSION,
        "protocol_supported": list(_mcp_protocol.SUPPORTED_PROTOCOL_VERSIONS),
        "vault_locked": not unlocked,
        "rate_limit": rate_limit,
        "skills_dir": "skills",
        "gate": "vault",
        "message": (
            "MCP açık — her yetenek araç olarak yayınlanıyor; çağrılar aynı "
            "kapılardan geçer."
            if unlocked
            else "MCP araçları KİLİTLİ — kasa kapalıyken hiçbir yetenek koşmaz."
        ),
    }


class LanguageDetectPayload(BaseModel):
    """[FAZ D · D4] Dil tespiti isteği."""

    text: str = Field(min_length=1, max_length=20000)
    client_id: str = Field(default="default", max_length=128)


class LanguageTranslatePayload(BaseModel):
    """[FAZ D · D4] Yerel çeviri isteği (metin makineden çıkmaz)."""

    text: str = Field(min_length=1, max_length=2000)
    target: str = Field(default="en", min_length=2, max_length=8)
    client_id: str = Field(default="default", max_length=128)


@app.get("/api/language/status")
async def api_language_status():
    """[FAZ D · D4] Dil hattının GERÇEK durumu: tespit her zaman yereldir;
    çeviri motoru var mı, kapı açık mı, kanıta işlenen SON ölçüm ne?"""
    from agent_core.services import language, translation

    return {
        "detect": {"available": True, "method": "deterministic_local"},
        "translate": translation.status(),
        "last": language.last_finding(),
    }


@app.post("/api/language/detect")
async def api_language_detect(req: LanguageDetectPayload):
    """[FAZ D · D4] Metnin dilini ölçer: omurga üzerinden (kasa kapısı dâhil).

    Sinyal yoksa `language=unknown` + sebep döner; etiket UYDURULMAZ.
    Kasa kilitliyken tespit de koşamaz (Tüzük Md.4, istisna yok).
    """
    from agent_core.capabilities.base import CapabilityContext
    from agent_core.capabilities.policy import PolicyState
    from agent_core.capabilities.registry import bootstrap
    from agent_core.capabilities.runner import CapabilityRunner

    if not rate_limit(f"language:{req.client_id}", "language"):
        return JSONResponse(
            {"error": {"code": "RATE_LIMITED", "message": "Çok fazla dil isteği"}},
            status_code=429,
        )

    runner = CapabilityRunner(registry=bootstrap())
    state = PolicyState(
        enabled_flags={}, vault_locked=not _check_vault_interlock(req.client_id), rate_ok=True
    )
    result = await runner.run(
        "extractor.text.language", CapabilityContext(subject=req.text), state=state
    )
    finding = result.payload
    payload = {
        "available": bool(result.available),
        "denied_by": result.denied_by,
        "reason": result.unavailable_reason,
        "language": getattr(finding, "language", "") if result.available else "",
        "confidence": getattr(finding, "confidence", 0.0) if result.available else 0.0,
        "script": getattr(finding, "script", "") if result.available else "",
        "detect_reason": getattr(finding, "reason", None) if result.available else None,
        "chars": getattr(finding, "chars", 0) if result.available else 0,
    }
    if result.denied_by:
        broadcast_log(req.client_id, "WARNING", f"DİL: tespit engellendi — kasa:{result.denied_by}")
    elif payload["language"] == "unknown":
        broadcast_log(req.client_id, "INFO", f"DİL: ölçülemedi — {payload['detect_reason']}")
    else:
        broadcast_log(
            req.client_id,
            "INFO",
            f"DİL: {payload['language']} · güven {payload['confidence']:.2f}",
        )
    return payload


@app.post("/api/language/translate")
async def api_language_translate(req: LanguageTranslatePayload):
    """[FAZ D · D4] Metni YEREL motorda çevirir: ses/dinleme ile aynı kural.

    Uzak uç REDDEDİLİR (`non_local_endpoint`); motor yoksa çeviri ÜRETİLMEZ
    (`available:false` + sebep). Kaynak metin hedef dilmiş gibi DÖNMEZ.
    """
    from agent_core.capabilities.base import CapabilityContext
    from agent_core.capabilities.policy import PolicyState
    from agent_core.capabilities.registry import bootstrap
    from agent_core.capabilities.runner import CapabilityRunner
    from agent_core.services.translation import GATE, MAX_TEXT_CHARS, status as _translation_status

    if not rate_limit(f"language:{req.client_id}", "language"):
        return JSONResponse(
            {"error": {"code": "RATE_LIMITED", "message": "Çok fazla çeviri isteği"}},
            status_code=429,
        )

    runner = CapabilityRunner(registry=bootstrap())
    state = PolicyState(
        enabled_flags={GATE: _flag_env(GATE)},
        vault_locked=not _check_vault_interlock(req.client_id),
        rate_ok=True,
    )
    result = await runner.run(
        "extractor.text.translate_local",
        CapabilityContext(subject=req.text[:MAX_TEXT_CHARS], params={"target": req.target}),
        state=state,
    )
    translated = ""
    if result.items:
        translated = result.items[0].content
    payload = {
        "available": bool(result.available and result.items),
        "denied_by": result.denied_by,
        "reason": result.unavailable_reason,
        "text": translated,
        "source_language": result.notes.get("source_language", ""),
        "source_confidence": result.notes.get("source_confidence", 0.0),
        "target_language": req.target,
        "engine": result.notes.get("engine", ""),
    }
    if payload["available"]:
        broadcast_log(
            req.client_id,
            "INFO",
            f"DİL: çeviri tamam — {payload['source_language']} → {req.target} ({payload['engine']})",
        )
    else:
        why = result.denied_by or result.unavailable_reason or _translation_status().get("reason")
        broadcast_log(req.client_id, "WARNING", f"DİL: ÇEVİRİ ÜRETİLEMEDİ — {why}")
    return payload


def _flag_env(name: str) -> bool:
    """[FAZ D · D4] Env kapısı okuma (speech'teki `_flag` ile aynı dar taraf)."""
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


@app.post("/api/tasks/{task_id}/cancel")
async def api_cancel_task(task_id: str = Path(min_length=1, max_length=_MAX_TASK_ID_LENGTH), client_id: str = "", reason: str = ""):
    return _terminate_mission(client_id, task_id, "cancel", reason)


@app.post("/api/tasks/{task_id}/halt")
async def api_halt_task(task_id: str = Path(min_length=1, max_length=_MAX_TASK_ID_LENGTH), client_id: str = "", reason: str = ""):
    return _terminate_mission(client_id, task_id, "halt", reason)


@app.delete("/api/tasks/{task_id}")
async def api_delete_task(task_id: str, client_id: str):
    """Bir görevin tüm izlerini kalıcı siler (bellek dosyası + aktif snapshot)."""
    room = get_room(client_id)

    try:
        # [AUDIT R3] regex + uzunluk (client_id ile aynı sözleşme).
        if len(task_id) > _MAX_TASK_ID_LENGTH:
            raise ValueError
        validate_identifier(task_id, field="task_id")
        mem_path = safe_child_path(
            room["executor"].memory.storage_path,
            f"{task_id}.json",
        )
    except ValueError:
        return JSONResponse(
            {"error": {"code": "INVALID_TASK_ID", "message": "Invalid task identifier"}},
            status_code=400,
        )
    removed_snapshot = room.get("active_tasks", {}).pop(task_id, None)
    file_deleted = False
    if os.path.exists(mem_path):
        try:
            os.remove(mem_path)
            file_deleted = True
        except OSError as e:
            return JSONResponse(
                {"error": {"code": "DELETE_FAILED", "message": redact_text(e)[:120]}},
                status_code=500,
            )

    if not removed_snapshot and not file_deleted:
        return JSONResponse(
            {"error": {"code": "NOT_FOUND", "message": f"Görev bulunamadı: {task_id}"}},
            status_code=404,
        )

    broadcast_log(client_id, "INFO", f"VERİ SİLME: '{task_id}' görev izleri kalıcı olarak silindi (retention).")
    return {
        "status": "deleted",
        "task_id": task_id,
        "snapshot_removed": removed_snapshot is not None,
        "memory_file_deleted": file_deleted,
    }


static_dir = "frontend/dist" if os.path.exists("frontend/dist") else "frontend"
os.makedirs(static_dir, exist_ok=True)
# Sona ekliyoruz ki api rotaları statik dosyalardan önce ezilmesin
app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
