"""Birleşik Beyin Yönlendirici & 2-Profil Yetenek Merkezi — ``/api/brain/*``.

Neden var?
    Arka uçta yetenekler tek tek çağrılmak yerine tek bir akıllı giriş noktasından
    erişilebilsin diye:
      * ``GET  /api/brain/capabilities`` — 2-profil (Yerel Çekirdek vs Harici)
        durumu + TÜRETİLMİŞ motor envanteri (availability()/kapı/bağımlılık
        problarıyla hesaplanır; sabit "hepsi True" listesi DEĞİLDİR).
      * ``POST /api/brain/route`` — kullanıcı niyetini gerçek motorlara
        yönlendirir: Lilith (strateji/karşı-hamle), Şirket/Domain tarama
        (``company_recon``), Hafıza Kristali (``memory_crystal``), İlişki Grafı
        (``graph_builder``), Telefon OSINT (``phone_probe``), Profil görevi
        (``aspasia.commands``) veya Aspasia çapraz sorgulama (``aspasia.chat``).

Kurallar:
    * Veri taşıyan her kol (graph/memory/company/phone/lilith/profile) aynı
      kapı sırasından geçer: reşitlik → kasa → (explicit görevde) sahiplik.
    * ``graph`` ve ``memory`` kanıt/hatıra okur: kapısız AÇILAMAZ ve başka
      operatörün mühürlü odasından OKUNAMAZ (403).
"""

from __future__ import annotations

import importlib
import logging
import os
import re
from typing import Any, Callable, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agent_core.capabilities.state import capability_profile_summary, flag_enabled, policy_state
from agent_core.services.graph_builder import build_evidence_graph
from agent_core.services.memory_crystal import recall as recall_memory_crystal
from backend.routes.lilith import LilithStrategyPayload, execute_lilith_strategy
from backend.security.principal import current_principal
from backend.security.task_ownership import task_access

logger = logging.getLogger(__name__)

__all__ = ["BrainRoutePayload", "detect_brain_route", "register_brain_hub_routes"]

_PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-()]{8,16}\d)")
_SOCIAL_URL_RE = re.compile(r"https?://(?:www\.)?(?:instagram\.com|x\.com|twitter\.com)/[^\s]+", re.I)
_DOMAIN_RE = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:com|org|net|io|ai|co|tr|de|uk|app|dev)\b", re.I)

_LILITH_HINTS = ("lilith", "karşı hamle", "karsi hamle", "kanca", "hook", "ilk temas", "diyalog ağacı", "gölge strateji", "viral")
_MEMORY_HINTS = ("hafıza", "hafiza", "kristal", "geçmişte ne", "gecmiste ne", "hatırla", "hatirla")
_GRAPH_HINTS = ("ilişki graf", "iliski graf", "grafı çiz", "grafi ciz", "bağlantı haritası", "baglanti haritasi")
_COMPANY_HINTS = ("şirket", "sirket", "kurum", "domain", "alan adı", "alan adi", "firma")


class BrainRoutePayload(BaseModel):
    client_id: str = Field(default="default", max_length=64)
    message: str = Field(default="", max_length=4000)
    mode: str = Field(default="auto", max_length=32)  # auto|lilith|aspasia|company|memory|graph|phone|profile
    # [KVKK · 2026-11-23] Telefon rotası kişisel veri işler; açık rıza beyanı
    # taşınmazsa `consent` kapısı fail-closed ret verir (sebep: consent_not_declared).
    subject_consent: bool = Field(default=False)
    task_id: Optional[str] = Field(default=None, max_length=128)
    target: Optional[str] = Field(default=None, max_length=256)
    intent: str = Field(default="pattern_interrupt", max_length=64)


def detect_brain_route(message: str, mode: str = "auto", target: Optional[str] = None) -> str:
    """Kullanıcı mesajını deterministik kurallarla gerçek motor hattına eşler."""
    explicit = (mode or "auto").strip().lower()
    if explicit in {"lilith", "aspasia", "company", "memory", "graph", "phone", "profile"}:
        return explicit

    text = (message or "").strip()
    low = text.replace("İ", "i").replace("I", "ı").lower().replace("\u0307", "")
    if any(k in low for k in _LILITH_HINTS):
        return "lilith"
    if any(k in low for k in _GRAPH_HINTS):
        return "graph"
    if any(k in low for k in _MEMORY_HINTS):
        return "memory"
    if _SOCIAL_URL_RE.search(text):
        return "profile"
    if any(k in low for k in _COMPANY_HINTS) and (_DOMAIN_RE.search(text) or target):
        return "company"
    if _PHONE_RE.search(text) and not _DOMAIN_RE.search(text):
        return "phone"
    return "aspasia"


def _extract_domain(text: str, fallback: Optional[str]) -> str:
    if fallback and fallback.strip():
        return fallback.strip()
    m = _DOMAIN_RE.search(text or "")
    return m.group(0).lower() if m else ""


def _extract_phone(text: str, fallback: Optional[str]) -> str:
    if fallback and fallback.strip():
        return fallback.strip()
    m = _PHONE_RE.search(text or "")
    return m.group(0).strip() if m else ""




def _forbidden(code: str) -> JSONResponse:
    """Görev/oda sahipliği reddi — gövde oda/task ADI İÇERMEZ (403)."""
    message = (
        "Bu oda başka bir operatöre mühürlü."
        if code == "ROOM_FORBIDDEN"
        else "Bu görev başka bir operatöre kayıtlı."
    )
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=403,
    )


def _room_forbidden(client_id: str, room: Optional[Dict[str, Any]]) -> Optional[JSONResponse]:
    """Oda mührü (salt-okunur): principal yoksa development davranışı korunur."""
    principal = current_principal()
    owner = (room or {}).get("_owner")
    if principal is not None and owner is not None and owner != principal:
        logger.warning(
            "ROOM_FORBIDDEN (brain hub): principal başka mühürlü odaya erişemedi (client_id uzunluğu=%d)",
            len(client_id or ""),
        )
        return _forbidden("ROOM_FORBIDDEN")
    return None


# ── Türetilmiş motor envanteri (sabit "true" listesi YASAK) ──────────────────
# Her prob LOKAL ve belirlenimcidir: ağ çağrısı, yazma YOK. "available" ==
# "import/bağımlılık/kapı problunu geçti" demektir; "koştu" iddiası değildir.
def _pipeline_status(compute) -> Dict[str, Any]:
    try:
        available, reason = compute()
        return {
            "available": bool(available),
            "reason": None if available else (reason or "unavailable"),
        }
    except Exception as exc:  # fail-closed + makine-okunur sebep
        return {"available": False, "reason": f"probe_error:{type(exc).__name__}"}


def _import_check(module: str, attr: str):
    def compute():
        mod = importlib.import_module(module)
        if not hasattr(mod, attr):
            return False, f"dependency_missing:{module}.{attr}"
        return True, None

    return compute


def _aspasia_check(aspasia_provider: Callable[[], Any]):
    def compute():
        aspasia = aspasia_provider() if callable(aspasia_provider) else None
        if aspasia is None:
            return False, "aspasia_unavailable"
        return True, None

    return compute


def _company_recon_check():
    def compute():
        if not flag_enabled("ENABLE_COMPANY_TARGETING"):
            return False, "gate_disabled:ENABLE_COMPANY_TARGETING"
        from agent_core.services import company_recon

        ok, reason = company_recon.harvester_availability()
        return bool(ok), (None if ok else (reason or "unavailable"))

    return compute


def _phone_probe_check():
    def compute():
        try:
            import phonenumbers  # noqa: F401
        except Exception:
            return False, "dependency_missing:phonenumbers"
        return True, None

    return compute


def _build_wired_pipelines(aspasia_provider: Callable[[], Any]) -> Dict[str, Dict[str, Any]]:
    probes = {
        "deterministic_7_pillars": _import_check("agent_core.engines.pillar_orchestrator", "PillarOrchestrator"),
        "cross_profiler": _import_check("agent_core.services.cross_profiler", "correlate_profiles"),
        "aspasia_cross_exam": _aspasia_check(aspasia_provider),
        "lilith_strategy": _import_check("agent_core.agents.lilith_growth", "LilithGrowthAgent"),
        "hook_studio": _import_check("backend.routes.hook_studio", "generate_hook_package"),
        "shadow_executor": _import_check("agent_core.shadow.shadow_executor", "ShadowExecutor"),
        "memory_crystal": _import_check("agent_core.services.memory_crystal", "recall"),
        "evidence_graph": _import_check("agent_core.services.graph_builder", "build_evidence_graph"),
        "company_recon": _company_recon_check(),
        "phone_probe": _phone_probe_check(),
    }
    return {name: _pipeline_status(compute) for name, compute in probes.items()}


def _extract_target_slug(text: str, fallback: Optional[str], executor: Any) -> str:
    if fallback and fallback.strip():
        return fallback.strip().lstrip("@")
    m = re.search(r"@([A-Za-z0-9_.-]+)", text or "")
    if m:
        return m.group(1)
    if executor is not None:
        last = getattr(executor, "last_status", None)
        tp = (last.get("target_profile") if isinstance(last, dict) else getattr(last, "target_profile", None)) or {}
        if isinstance(tp, dict):
            return str(tp.get("username") or tp.get("name") or "")
    return ""


def register_brain_hub_routes(
    app: Any,
    *,
    rate_limit: Callable[[str, str], bool],
    rate_identity: Callable[[Request], str],
    get_room: Callable[[str], Dict[str, Any]],
    get_executor: Callable[[str], Any],
    gateway_provider: Callable[[], Any],
    aspasia_provider: Callable[[], Any],
    check_vault_interlock: Callable[[str], bool],
    require_vault_open: Callable[[str], Any],
    require_minor_clearance: Callable[..., Any],
) -> None:
    @app.get("/api/brain/capabilities")
    async def brain_capabilities(client_id: str = "default"):
        """2-profil yetenek özeti + bağlı motor envanteri."""
        summary = capability_profile_summary()
        return {
            "status": "ok",
            "vault_locked": not bool(check_vault_interlock(client_id)),
            "profiles": summary,
            # TÜRETİLMİŞ envanter: her giriş {"available": bool, "reason": str|None}.
            # "available=True" yalnız "import/bağımlılık/kapı problunu geçti" anlamına gelir.
            "wired_pipelines": _build_wired_pipelines(aspasia_provider),
        }

    @app.post("/api/brain/route")
    async def brain_route_endpoint(payload: BrainRoutePayload, request: Request):
        """Tek merkezi beyin yönlendiricisi — tüm bağlı motorları doğrudan çalıştırır."""
        if not rate_limit(f"brain:{rate_identity(request)}", "brain"):
            return JSONResponse(
                {"error": {"code": "RATE_LIMITED", "message": "Beyin yönlendiricisi yoğun; kısa bir mola verin."}},
                status_code=429,
            )

        route = detect_brain_route(payload.message, payload.mode, payload.target)
        room = get_room(payload.client_id)
        executor = get_executor(payload.client_id)

        if route == "lilith":
            if (blocked := require_minor_clearance(payload.client_id, subject=payload.target or payload.message)) is not None:
                return blocked
            if (locked := require_vault_open(payload.client_id)) is not None:
                return locked
            res = await execute_lilith_strategy(
                LilithStrategyPayload(
                    client_id=payload.client_id,
                    task_id=payload.task_id,
                    instruction=payload.message,
                    intent=payload.intent,
                    target_username=payload.target,
                ),
                gateway=gateway_provider(),
                executor=executor,
            )
            return {"route": "lilith", "result": res}

        if route == "graph":
            if (blocked := require_minor_clearance(payload.client_id, subject=payload.task_id or payload.message)) is not None:
                return blocked
            if (locked := require_vault_open(payload.client_id)) is not None:
                return locked
            if (forbidden := _room_forbidden(payload.client_id, room)) is not None:
                return forbidden
            tasks = getattr(executor, "tasks", None) or {}
            if payload.task_id:
                # Önce VARLIK (404), sonra SAHİPLİK (403) — api.py `_terminate_mission`
                # ile aynı sıra: yok olan görev için sahiplik satırı YAZILMAZ ve
                # başkasının görevi için varlık doğrulaması 403'ün ÜSTÜNE ÇIKMAZ.
                from agent_core.utils.security import safe_child_path

                mem_path = None
                storage = getattr(getattr(executor, "memory", None), "storage_path", None)
                if storage:
                    try:
                        mem_path = safe_child_path(storage, f"{payload.task_id}.json")
                    except ValueError:
                        return JSONResponse(
                            {"error": {"code": "INVALID_TASK_ID", "message": "Invalid task identifier"}},
                            status_code=400,
                        )
                exists = (isinstance(tasks, dict) and payload.task_id in tasks) or (
                    mem_path is not None and os.path.exists(mem_path)
                )
                if not exists:
                    return JSONResponse(
                        {"error": {"code": "TASK_NOT_FOUND", "message": "Task not found"}},
                        status_code=404,
                    )
                decision = task_access(payload.task_id, room.get("_owner") or current_principal())
                if decision == "forbidden":
                    return _forbidden("TASK_FORBIDDEN")
            task = None
            if payload.task_id and isinstance(tasks, dict):
                task = tasks.get(payload.task_id)
            if task is None and not payload.task_id:
                task = getattr(executor, "last_status", None)
            chain = (task.get("evidence_chain") if isinstance(task, dict) else getattr(task, "evidence_chain", None)) or []
            graph = build_evidence_graph(chain)
            return {
                "route": "graph",
                "task_id": payload.task_id or (getattr(task, "task_id", None) if task else None),
                "result": graph.model_dump(),
            }

        if route == "memory":
            slug = _extract_target_slug(payload.message, payload.target, executor)
            # Hafıza kristali GÖREVLER-ARASI kalıcı depodur: reşitlik + kasa kapıları
            # açılmadan ve oda mührü doğrulanmadan HİÇBİR hatıra okunmaz.
            if (blocked := require_minor_clearance(payload.client_id, subject=slug or payload.message)) is not None:
                return blocked
            if (locked := require_vault_open(payload.client_id)) is not None:
                return locked
            if (forbidden := _room_forbidden(payload.client_id, room)) is not None:
                return forbidden
            if not slug:
                return {
                    "route": "memory",
                    "result": {
                        "available": False,
                        "reason": "hedef_belirtilmedi",
                        "machine_note": "Hafıza kristali için @kullanıcı adı veya aktif görev gerekir.",
                        "hits": [],
                    },
                }
            base_dir = getattr(getattr(executor, "memory", None), "storage_path", None)
            recalled = recall_memory_crystal(slug, payload.message or slug, base=base_dir)
            return {"route": "memory", "target": slug, "result": recalled.model_dump()}

        if route == "company":
            domain = _extract_domain(payload.message, payload.target)
            if not domain:
                return JSONResponse(
                    {"error": {"code": "MISSING_DOMAIN", "message": "Kurum taraması için geçerli bir alan adı (ör. example.com) girin."}},
                    status_code=400,
                )
            if (blocked := require_minor_clearance(payload.client_id, subject=domain)) is not None:
                return blocked
            if (locked := require_vault_open(payload.client_id)) is not None:
                return locked
            from agent_core.capabilities import CapabilityContext, bootstrap, run_capability

            bootstrap()
            # Kasa GERÇEK durumu verilir (ön-kontrol yalnız kapak değil) ve hız
            # limiti uçta zaten uygulandı → rate_ok=True (yoksa çekirdek her zaman
            # rate_state_missing ile reddeder — uç yapısal olarak ölü olurdu).
            state = policy_state(
                vault_locked=not bool(check_vault_interlock(payload.client_id)),
                rate_ok=True,
            )
            cap_res = await run_capability(
                "sensor.company.harvester",
                CapabilityContext(subject=domain, params={"domain": domain}),
                state=state,
            )
            return {
                "route": "company",
                "domain": domain,
                "result": {
                    "available": cap_res.available,
                    "reason": cap_res.unavailable_reason or cap_res.error,
                    "payload": cap_res.payload.model_dump() if hasattr(cap_res.payload, "model_dump") else cap_res.payload,
                },
            }

        if route == "phone":
            phone = _extract_phone(payload.message, payload.target)
            if not phone:
                return JSONResponse(
                    {"error": {"code": "MISSING_PHONE", "message": "Telefon numarası okunamadı."}},
                    status_code=400,
                )
            if (blocked := require_minor_clearance(payload.client_id, subject=phone)) is not None:
                return blocked
            if (locked := require_vault_open(payload.client_id)) is not None:
                return locked
            from agent_core.capabilities import CapabilityContext, bootstrap, run_capability

            bootstrap()
            cap_res = await run_capability(
                "sensor.identity.phone_probe",
                CapabilityContext(subject=phone, params={"auto_bridge": False}),
                state=policy_state(
                    vault_locked=not bool(check_vault_interlock(payload.client_id)),
                    rate_ok=True,
                    subject_consent=payload.subject_consent,
                ),
            )
            return {
                "route": "phone",
                "phone": phone,
                "result": {
                    "available": cap_res.available,
                    "reason": cap_res.unavailable_reason or cap_res.error,
                    "payload": cap_res.payload.model_dump() if hasattr(cap_res.payload, "model_dump") else cap_res.payload,
                },
            }

        aspasia = room.get("aspasia") or aspasia_provider()
        if route == "profile":
            if (blocked := require_minor_clearance(payload.client_id, subject=payload.message)) is not None:
                return blocked
            if (locked := require_vault_open(payload.client_id)) is not None:
                return locked
            if aspasia and getattr(aspasia, "commands", None) is not None:
                cmd_res = await aspasia.commands.submit(payload.message, client_id=payload.client_id)
                return {"route": "profile", "result": cmd_res.model_dump()}

        if not aspasia:
            return JSONResponse(
                {"error": {"code": "ASPASIA_UNAVAILABLE", "message": "Aspasia kullanılamıyor."}},
                status_code=503,
            )
        chat_res = await aspasia.chat(payload.message, room)
        return {"route": "aspasia", "result": chat_res.model_dump()}
