"""Birleşik LILITH Strateji & Karşı-Hamle Hattı — ``POST /api/lilith/strategy``.

Neden var?
    Daha önce ``LilithGrowthAgent`` yalnız CLI (``run_lilith.py``) yolunda
    kalmış, ``/api/commander/dispatch`` ise 503 ile kapatılmıştı; öte yandan
    3 dallı karşı-hamle üreten ``hook_studio`` ve ``shadow_executor`` arayüzde
    bağlı değildi. Bu modül üç gerçek motoru (``LilithGrowthAgent`` +
    ``hook_studio`` 3 dallı karşı-hamle + ``ShadowExecutor``) TEK canlı API
    hattında kalıcı olarak birleştirir.

Kurallar:
    * Kanıt uydurmaz: LLM yoksa deterministik motorlardan (``psychodynamic_depth``,
      ``timing_forensics``, ``follower_audit``) gerçek ``NeuroMetrics`` tabanı ve
      dürüst ``fallback_reason`` döner.
    * 18+ çocuk koruma ve kasa kilit kapıları uygulanır.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agent_core.agents.lilith_growth import LilithGrowthAgent
from agent_core.services.llm_gateway import LLMGateway
from agent_core.shadow.shadow_executor import ShadowExecutor
from backend.routes.hook_studio import HookStudioPayload, generate_hook_package

logger = logging.getLogger(__name__)

__all__ = ["LilithStrategyPayload", "execute_lilith_strategy", "register_lilith_routes"]


class LilithStrategyPayload(BaseModel):
    client_id: str = Field(default="default", max_length=64)
    task_id: Optional[str] = Field(default=None, max_length=128)
    instruction: str = Field(default="", max_length=2000)
    intent: str = Field(default="pattern_interrupt", max_length=64)
    platform: str = Field(default="instagram", max_length=32)
    target_username: Optional[str] = Field(default=None, max_length=128)
    target_profile: Optional[Dict[str, Any]] = None


def _dump(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return {}


def _resolve_task_context(
    executor: Any,
    task_id: Optional[str],
    payload_profile: Optional[Dict[str, Any]],
) -> tuple[Optional[str], Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Görevdeki gerçek analiz çıktılarını çeker (uydurma yok)."""
    task = None
    resolved_id = task_id
    if executor is not None:
        tasks = getattr(executor, "tasks", None) or {}
        if task_id and isinstance(tasks, dict):
            task = tasks.get(task_id)
        if task is None:
            task = getattr(executor, "last_status", None)
        if task is not None and not resolved_id:
            resolved_id = getattr(task, "task_id", None) if not isinstance(task, dict) else task.get("task_id")

    def _get(attr: str) -> Any:
        if task is None:
            return None
        return task.get(attr) if isinstance(task, dict) else getattr(task, attr, None)

    target_profile = dict(payload_profile) if isinstance(payload_profile, dict) else {}
    task_tp = _dump(_get("target_profile"))
    if task_tp:
        merged = dict(task_tp)
        merged.update(target_profile)
        target_profile = merged

    holistic = _get("holistic_profile")
    passions: Dict[str, Any] = {}
    frictions: Dict[str, Any] = {}
    cognitive: Dict[str, Any] = {}
    if holistic is not None:
        passions = _dump(holistic.get("passions") if isinstance(holistic, dict) else getattr(holistic, "passions", None))
        frictions = _dump(holistic.get("frictions") if isinstance(holistic, dict) else getattr(holistic, "frictions", None))
        cognitive = _dump(holistic.get("cognitive") if isinstance(holistic, dict) else getattr(holistic, "cognitive", None))

    engines = {
        "psychodynamic_depth": _dump(_get("psychodynamic_depth")),
        "timing_forensics": _dump(_get("timing_forensics")),
        "follower_audit": _dump(_get("follower_audit")),
        "existing_shadow": _dump(_get("shadow_profile")),
        "existing_lilith": _dump(_get("lilith_report")),
    }
    return resolved_id, target_profile, passions, frictions, cognitive, engines


async def execute_lilith_strategy(
    payload: LilithStrategyPayload,
    *,
    gateway: Optional[LLMGateway],
    executor: Any = None,
) -> Dict[str, Any]:
    """LilithGrowthAgent + ShadowExecutor + gerçek HookStudio 3 dallı karşı-hamle birleşik yürütmesi."""
    gw = gateway if isinstance(gateway, LLMGateway) else LLMGateway()
    task_id, target_profile, passions, frictions, cognitive, engines = _resolve_task_context(
        executor, payload.task_id, payload.target_profile
    )

    target_name = (
        payload.target_username
        or target_profile.get("username")
        or target_profile.get("name")
        or "hedef"
    )
    topic = payload.instruction.strip() or f"@{target_name} karşı-hamle ve strateji"

    # 1. LilithGrowthAgent (nörobilişsel kanca + formül)
    lilith_agent = LilithGrowthAgent(gw)
    lilith_input = {
        "topic": topic,
        "platform": payload.platform,
        "target_profile": target_profile,
        "passion_profile": passions,
        "friction_profile": frictions,
        "cognitive_style": cognitive,
    }
    lilith_pkg = await lilith_agent.execute(lilith_input)
    lilith_data = lilith_pkg.model_dump()

    # LLM çevrimdışıysa deterministik motor sinyallerinden gerçek NeuroMetrics hesapla.
    # Motor ölçümü eksikse metrics ÜRETİLMEZ — sabit yedek DEĞER YAZILMAZ (kaynak hukuku).
    metrics_source = "model_and_formula"
    if not lilith_data.get("neuro_metrics"):
        from agent_core.services.neuro_signals import neuro_inputs_from_engines

        det_inputs = neuro_inputs_from_engines(
            engines["psychodynamic_depth"],
            engines["timing_forensics"],
            engines["follower_audit"],
        )
        if det_inputs is not None:
            det_metrics = LilithGrowthAgent.compute_neuro_formula(**det_inputs)
            lilith_data["neuro_metrics"] = det_metrics.model_dump()
            metrics_source = "deterministic_engines"
        else:
            metrics_source = "engine_signals_missing"
            lilith_data["fallback_reason"] = (
                lilith_data.get("fallback_reason") or "engine_signals_missing"
            )

    # 2. ShadowExecutor (gölge & NLP strateji katmanı)
    shadow_data: Dict[str, Any]
    if engines["existing_shadow"]:
        shadow_data = engines["existing_shadow"]
    else:
        shadow_exec = ShadowExecutor(llm_gateway=gw)
        shadow_res = await shadow_exec.execute(
            {
                "target_profile": target_profile,
                "psychodynamic_depth": engines["psychodynamic_depth"],
                "desired_action": topic,
            }
        )
        shadow_data = shadow_res.model_dump()

    # 3. Gerçek Hook Studio motoru (epistemik durum + 3 dallı karşı-hamle diyalog ağacı)
    hook_payload = HookStudioPayload(
        client_id=payload.client_id,
        task_id=task_id,
        intent=payload.intent,
        custom_goal=payload.instruction or None,
        target_username=str(target_name),
        target_profile=target_profile or None,
        passions=passions or None,
        frictions=frictions or None,
        cognitive=cognitive or None,
    )
    hook_result = await generate_hook_package(
        hook_payload,
        gateway_provider=lambda: gw,
        get_executor=(lambda _cid: executor) if executor is not None else None,
    )
    counter_moves = list(hook_result.get("dialogue_tree") or [])

    has_evidence = bool(
        target_profile.get("bio")
        or target_profile.get("posts")
        or passions
        or frictions
        or engines["psychodynamic_depth"]
    )
    return {
        "status": "ok",
        "agent": "lilith",
        "task_id": task_id,
        "target": str(target_name),
        "intent": payload.intent,
        "evidence_grounded": has_evidence,
        "metrics_source": metrics_source,
        "lilith": lilith_data,
        "neuro_metrics": lilith_data.get("neuro_metrics"),
        "shadow": {
            "strategy": shadow_data.get("strategy", ""),
            "message": shadow_data.get("message", ""),
            "nlp_sequence": shadow_data.get("nlp_sequence", []),
            "data_confidence": bool(shadow_data.get("data_confidence", False)),
            "fallback_reason": shadow_data.get("fallback_reason"),
        },
        "hook_studio": {
            "opening_message": hook_result.get("opening_message", ""),
            "opening_topic": hook_result.get("opening_topic", ""),
            "rationale": hook_result.get("rationale", ""),
            "evidence_verification_status": hook_result.get("evidence_verification_status"),
            "data_confidence": bool(hook_result.get("data_confidence", False)),
            "fallback_reason": hook_result.get("fallback_reason"),
        },
        "counter_moves": counter_moves,
        "fallback_reason": lilith_data.get("fallback_reason"),
    }


def register_lilith_routes(
    app: Any,
    *,
    rate_limit: Callable[[str, str], bool],
    rate_identity: Callable[[Request], str],
    gateway_provider: Callable[[], Any],
    get_executor: Optional[Callable[[str], Any]] = None,
    require_vault_open: Optional[Callable[[str], Any]] = None,
    require_minor_clearance: Optional[Callable[..., Any]] = None,
) -> None:
    @app.post("/api/lilith/strategy")
    async def lilith_strategy_endpoint(payload: LilithStrategyPayload, request: Request):
        """Birleşik Lilith strateji, nöro-kanca ve 3 dallı karşı-hamle ucu."""
        if not rate_limit(f"lilith:{rate_identity(request)}", "lilith"):
            return JSONResponse(
                {"error": {"code": "RATE_LIMITED", "message": "Lilith yoğun; kısa bir mola verin."}},
                status_code=429,
            )
        subject = payload.target_username or (payload.target_profile or {}).get("username") or payload.instruction
        if require_minor_clearance is not None:
            blocked = require_minor_clearance(payload.client_id, subject=subject)
            if blocked is not None:
                return blocked
        if require_vault_open is not None:
            locked = require_vault_open(payload.client_id)
            if locked is not None:
                return locked

        executor = get_executor(payload.client_id) if callable(get_executor) else None
        gw = gateway_provider() if callable(gateway_provider) else None
        try:
            return await execute_lilith_strategy(payload, gateway=gw, executor=executor)
        except Exception as exc:
            logger.error("Lilith strateji hattı hatası: %s", type(exc).__name__)
            return JSONResponse(
                {"error": {"code": "LILITH_PIPELINE_ERROR", "message": "Lilith strateji hattı başarısız."}},
                status_code=500,
            )
