"""CapabilityRunner — policy, prerequisites and execution through one gate.

``preflight()`` checks readiness without scanning a target or creating evidence.
``run()`` uses the same preparation path, then executes the capability. Neither
path bypasses the minor lock, vault, rate limit or operator consent decision.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from agent_core.capabilities.base import Availability, CapabilityContext, CapabilityResult
from agent_core.capabilities.policy import PolicyKernel, PolicyState
from agent_core.capabilities.registry import CapabilityRegistry, default_registry

logger = logging.getLogger(__name__)
__all__ = ["run_capability", "CapabilityRunner"]


class CapabilityRunner:
    def __init__(
        self,
        registry: CapabilityRegistry | None = None,
        kernel: PolicyKernel | None = None,
        emit: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.registry = registry if registry is not None else default_registry
        self.kernel = kernel if kernel is not None else PolicyKernel()
        self.emit = emit

    async def _prepare(self, cap_id: str, state: PolicyState | None):
        """Return (capability, failure). A failure must never reach run()."""
        try:
            cap = self.registry.get(cap_id)
        except KeyError:
            return None, CapabilityResult(
                capability_id=cap_id, available=False,
                unavailable_reason="unknown_capability",
            )

        # Keep the child lock BEFORE every other gate, including preflight.
        minor_case = getattr(state, "minor_case", None) if state else None
        if minor_case is not None and getattr(minor_case, "subject_is_minor", False):
            from agent_core.safety import MinorCaseLedger, MinorGate

            decision = MinorGate().evaluate(minor_case)
            try:
                MinorCaseLedger().record(
                    minor_case, decision, capability_id=cap_id, subject=""
                )
            except Exception:
                logger.debug("minor ledger write failed", exc_info=True)
            if not decision.allowed:
                return cap, CapabilityResult(
                    capability_id=cap_id, available=False,
                    unavailable_reason=f"minor:{decision.reason_code}",
                    denied_by="minor_safe", notes={"minor_detail": decision.detail},
                )

        decision = self.kernel.evaluate(
            getattr(cap, "gates", frozenset()), state or PolicyState()
        )
        if not decision.allowed:
            return cap, CapabilityResult(
                capability_id=cap_id, available=False,
                unavailable_reason=f"policy:{decision.reason}", denied_by=decision.gate,
            )

        try:
            local = cap.availability()
        except Exception as exc:
            logger.warning("availability failed: %s: %s", cap_id, type(exc).__name__)
            return cap, CapabilityResult(
                capability_id=cap_id, available=False,
                unavailable_reason=f"availability_error:{type(exc).__name__}",
            )
        if not local.available:
            return cap, CapabilityResult(
                capability_id=cap_id, available=False,
                unavailable_reason=local.reason or "unavailable",
            )

        # Local-only by default. X checks its local account DB here, AFTER
        # policy has accepted task-specific consent. No target request is made.
        try:
            hook = getattr(cap, "preflight", None)
            ready = await asyncio.wait_for(hook(), timeout=10.0) if hook else cap.availability()
            if not isinstance(ready, Availability):
                raise TypeError("preflight must return Availability")
        except asyncio.TimeoutError:
            return cap, CapabilityResult(
                capability_id=cap_id, available=False,
                unavailable_reason="preflight_timeout",
            )
        except Exception as exc:
            logger.warning("preflight failed: %s: %s", cap_id, type(exc).__name__)
            return cap, CapabilityResult(
                capability_id=cap_id, available=False,
                unavailable_reason=f"preflight_error:{type(exc).__name__}",
            )
        if not ready.available:
            return cap, CapabilityResult(
                capability_id=cap_id, available=False,
                unavailable_reason=ready.reason or "unavailable",
            )
        return cap, None

    async def preflight(
        self, cap_id: str, *, state: PolicyState | None = None,
    ) -> CapabilityResult:
        """Prerequisite verification, not a claim of successful live execution."""
        _cap, failure = await self._prepare(cap_id, state)
        return failure or CapabilityResult(
            capability_id=cap_id, available=True,
            notes={"verification": "preflight", "live_execution_verified": False},
        )

    async def run(
        self, cap_id: str, ctx: CapabilityContext | None = None,
        *, state: PolicyState | None = None,
    ) -> CapabilityResult:
        ctx = ctx or CapabilityContext()
        started = time.perf_counter()

        def finish(result: CapabilityResult) -> CapabilityResult:
            result.duration_ms = int((time.perf_counter() - started) * 1000)
            if self.emit is not None:
                try:
                    self.emit(result.to_dict())
                except Exception:
                    logger.debug("capability emit failed", exc_info=True)
            return result

        cap, failure = await self._prepare(cap_id, state)
        if failure is not None:
            return finish(failure)

        timeout = ctx.timeout_seconds if ctx.timeout_seconds is not None else getattr(
            cap, "timeout_seconds", 30.0
        )
        try:
            result = await asyncio.wait_for(cap.run(ctx), timeout=timeout)
        except asyncio.TimeoutError:
            return finish(CapabilityResult(
                capability_id=cap_id, available=False, unavailable_reason="timeout",
                error=f"timeout_after_{timeout}s",
            ))
        except Exception as exc:
            logger.warning("capability failed: %s: %s", cap_id, type(exc).__name__)
            return finish(CapabilityResult(
                capability_id=cap_id, available=False, unavailable_reason="run_error",
                error=type(exc).__name__,
            ))
        if not isinstance(result, CapabilityResult):
            return finish(CapabilityResult(
                capability_id=cap_id, available=False,
                unavailable_reason="contract_violation",
                error="run() CapabilityResult döndürmedi",
            ))
        return finish(result)


async def run_capability(
    cap_id: str, ctx: CapabilityContext | None = None, *,
    state: PolicyState | None = None,
    registry: CapabilityRegistry | None = None,
    emit: Callable[[dict[str, Any]], None] | None = None,
) -> CapabilityResult:
    return await CapabilityRunner(registry=registry, emit=emit).run(
        cap_id, ctx, state=state
    )
