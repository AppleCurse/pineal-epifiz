"""CapabilityRunner — yetenekleri çalıştıran TEK geçit.

Sıra (kısaltma yok, atlama yok):
    1. Registry'den çöz           → yoksa `unknown_capability` (istisna değil, ret)
    2. PolicyKernel kapıları      → reddedilirse `denied_by=<gate>`
    3. availability()             → değilse `unavailable_reason=<sebep>`
    4. run() (+ timeout)          → hata/timeout → `error`, **kanıt üretilmez**

Fail-closed: hiçbir adımda kanıt uydurulmaz. Bir yetenek patlarsa rapora
giden şey "0 kanıt + hata sınıfı"dır; sessizce boş sonuç değil.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from agent_core.capabilities.base import CapabilityContext, CapabilityResult
from agent_core.capabilities.policy import PolicyKernel, PolicyState
from agent_core.capabilities.registry import CapabilityRegistry, default_registry

logger = logging.getLogger(__name__)

__all__ = ["run_capability", "CapabilityRunner"]


class CapabilityRunner:
    """Durumsuz koşucu: politika + kullanılabilirlik + timeout + hata sınıfı."""

    def __init__(
        self,
        registry: CapabilityRegistry | None = None,
        kernel: PolicyKernel | None = None,
        emit: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        # Boş registry `or` ile ezilmesin (bkz. registry.py uyarısı): açık None kontrolü.
        self.registry = registry if registry is not None else default_registry
        self.kernel = kernel if kernel is not None else PolicyKernel()
        self.emit = emit

    async def run(
        self,
        cap_id: str,
        ctx: CapabilityContext | None = None,
        *,
        state: PolicyState | None = None,
    ) -> CapabilityResult:
        ctx = ctx or CapabilityContext()
        started = time.perf_counter()

        def _finish(result: CapabilityResult) -> CapabilityResult:
            result.duration_ms = int((time.perf_counter() - started) * 1000)
            if self.emit is not None:
                try:
                    self.emit(result.to_dict())
                except Exception:  # telemetri asla koşuyu bozmasın
                    logger.debug("capability emit failed", exc_info=True)
            return result

        # 1) çözüm
        try:
            cap = self.registry.get(cap_id)
        except KeyError as exc:
            logger.warning("capability çözülemedi: %s", exc)
            return _finish(
                CapabilityResult(
                    capability_id=cap_id,
                    available=False,
                    unavailable_reason="unknown_capability",
                )
            )

        # 2) politika kapıları
        decision = self.kernel.evaluate(getattr(cap, "gates", frozenset()), state or PolicyState())
        if not decision.allowed:
            logger.info(
                "capability reddedildi: %s gate=%s reason=%s",
                cap_id,
                decision.gate,
                decision.reason,
            )
            return _finish(
                CapabilityResult(
                    capability_id=cap_id,
                    available=False,
                    unavailable_reason=f"policy:{decision.reason}",
                    denied_by=decision.gate,
                )
            )

        # 3) kullanılabilirlik
        try:
            availability = cap.availability()
        except Exception as exc:
            logger.warning("availability patladı: %s: %s", cap_id, type(exc).__name__)
            return _finish(
                CapabilityResult(
                    capability_id=cap_id,
                    available=False,
                    unavailable_reason=f"availability_error:{type(exc).__name__}",
                )
            )
        if not availability.available:
            return _finish(
                CapabilityResult(
                    capability_id=cap_id,
                    available=False,
                    unavailable_reason=availability.reason or "unavailable",
                )
            )

        # 4) koşu (+ timeout)
        timeout = ctx.timeout_seconds if ctx.timeout_seconds is not None else getattr(
            cap, "timeout_seconds", 30.0
        )
        try:
            result = await asyncio.wait_for(cap.run(ctx), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("capability timeout: %s (%ss)", cap_id, timeout)
            return _finish(
                CapabilityResult(
                    capability_id=cap_id,
                    available=False,
                    unavailable_reason="timeout",
                    error=f"timeout_after_{timeout}s",
                )
            )
        except Exception as exc:  # fail-closed: hata = kanıt yok
            logger.warning("capability hatası: %s: %s", cap_id, type(exc).__name__)
            return _finish(
                CapabilityResult(
                    capability_id=cap_id,
                    available=False,
                    unavailable_reason="run_error",
                    error=f"{type(exc).__name__}",
                )
            )

        if not isinstance(result, CapabilityResult):
            return _finish(
                CapabilityResult(
                    capability_id=cap_id,
                    available=False,
                    unavailable_reason="contract_violation",
                    error="run() CapabilityResult döndürmedi",
                )
            )
        return _finish(result)


async def run_capability(
    cap_id: str,
    ctx: CapabilityContext | None = None,
    *,
    state: PolicyState | None = None,
    registry: CapabilityRegistry | None = None,
    emit: Callable[[dict[str, Any]], None] | None = None,
) -> CapabilityResult:
    """Tek çağrılık kısayol (runner oluşturmadan kullanım)."""
    runner = CapabilityRunner(registry=registry, emit=emit)
    return await runner.run(cap_id, ctx, state=state)
