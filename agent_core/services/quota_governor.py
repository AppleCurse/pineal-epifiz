"""Provider quota governor: runtime rate/token accounting and health state.

The FINAL routing pipeline feeds this module after every provider attempt.
It maintains per-provider (and per-model) local accounting for RPM/RPD/TPM/TPD
and prefers provider response headers when they are present. Unknown quota is
reported as ``unknown`` and is never treated as unlimited capacity.
"""

from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping, Optional

from agent_core.services.provider_manager import QuotaSnapshot, QuotaStatus


# Common rate-limit header names across OpenAI-compatible providers. Values are
# read case-insensitively. ``retry-after`` is handled by the router separately.
_RPM_HEADERS = (
    "x-ratelimit-remaining-requests",
    "x-ratelimit-remaining",
)
_TPM_HEADERS = (
    "x-ratelimit-remaining-tokens",
)
_RESET_HEADERS = (
    "x-ratelimit-reset-requests",
    "x-ratelimit-reset-tokens",
    "ratelimit-reset",
)

_APPROACHING_FRACTION = 0.10
_MINUTE_SECONDS = 60.0
_DAY_SECONDS = 24 * 3600.0


@dataclass(frozen=True)
class QuotaLimits:
    """Account-verified (or otherwise configured) per-provider limits."""

    rpm: Optional[int] = None
    rpd: Optional[int] = None
    tpm: Optional[int] = None
    tpd: Optional[int] = None

    def __post_init__(self) -> None:
        for name in ("rpm", "rpd", "tpm", "tpd"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or value <= 0):
                raise ValueError(f"{name} must be a positive integer or None")

    @property
    def known(self) -> bool:
        return any(getattr(self, name) is not None for name in ("rpm", "rpd", "tpm", "tpd"))


@dataclass
class _Window:
    """Sliding-window counters for a single provider/model scope."""

    request_times: list[float] = field(default_factory=list)
    token_times: list[tuple[float, int]] = field(default_factory=list)
    header_remaining_requests: Optional[int] = None
    header_remaining_tokens: Optional[int] = None
    header_reset_seconds: Optional[float] = None


class QuotaGovernor:
    """Thread-safe, header-aware rate/token accounting for LLM providers.

    This object performs no network I/O. It consumes observations from the
    routed executor and emits :class:`QuotaSnapshot` values that
    :class:`~agent_core.services.provider_manager.ProviderManager` can store,
    so the UnifiedRouter's existing EXHAUSTED/APPROACHING_LIMIT handling works
    end-to-end without any new network path.
    """

    def __init__(
        self,
        limits: Optional[Mapping[str, QuotaLimits]] = None,
        *,
        clock: Optional[Callable[[], float]] = None,
    ):
        self._limits: dict[str, QuotaLimits] = {
            provider: QuotaLimits(**values) if isinstance(values, dict) else values
            for provider, values in (limits or {}).items()
        }
        self._clock = clock if clock is not None else time.monotonic
        self._windows: dict[tuple[str, str], _Window] = {}
        self._lock = threading.RLock()

    @classmethod
    def from_policy(cls) -> "QuotaGovernor":
        """Seed local limits from the FINAL-KARAR-MATRIX account quotas."""
        from agent_core.services.final_routing_policy import QUOTAS

        return cls({provider: QuotaLimits(**values) for provider, values in QUOTAS.items()})

    def limits_for(self, provider: str) -> QuotaLimits:
        return self._limits.get(provider, QuotaLimits())

    def _window(self, provider: str, model: str) -> _Window:
        key = (provider, model)
        with self._lock:
            window = self._windows.get(key)
            if window is None:
                window = _Window()
                self._windows[key] = window
            return window

    # ------------------------------------------------------------------ #
    # Observation
    # ------------------------------------------------------------------ #
    def record_success(
        self,
        provider: str,
        model: str,
        *,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        now = self._clock()
        window = self._window(provider, model)
        with self._lock:
            self._prune_locked(window, now)
            window.request_times.append(now)
            tokens = 0
            if isinstance(prompt_tokens, int) and prompt_tokens > 0:
                tokens += prompt_tokens
            if isinstance(completion_tokens, int) and completion_tokens > 0:
                tokens += completion_tokens
            if tokens > 0:
                window.token_times.append((now, tokens))
            self._absorb_headers_locked(window, headers)

    def record_failure(
        self,
        provider: str,
        model: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        status_code: Optional[int] = None,
    ) -> None:
        now = self._clock()
        window = self._window(provider, model)
        with self._lock:
            self._prune_locked(window, now)
            # A failed attempt still consumes request headroom for local
            # accounting. A 429 is skipped: the provider already tells us the
            # limit is hit and its headers become authoritative.
            if status_code != 429:
                window.request_times.append(now)
            self._absorb_headers_locked(window, headers)

    def _prune_locked(self, window: _Window, now: float) -> None:
        day_cut = now - _DAY_SECONDS
        window.request_times = [t for t in window.request_times if t >= day_cut]
        window.token_times = [(t, n) for t, n in window.token_times if t >= day_cut]

    @staticmethod
    def _header_int(headers: Optional[Mapping[str, str]], names: tuple[str, ...]) -> Optional[int]:
        if not headers:
            return None
        lowered = {str(key).lower(): str(value).strip() for key, value in headers.items()}
        for name in names:
            raw = lowered.get(name)
            if raw is None:
                continue
            try:
                return int(float(raw))
            except (TypeError, ValueError):
                logger.warning('Suppressed exception observed at agent_core/services/quota_governor.py:178 (continue)')
                continue
        return None

    @staticmethod
    def _header_float(headers: Optional[Mapping[str, str]], names: tuple[str, ...]) -> Optional[float]:
        if not headers:
            return None
        lowered = {str(key).lower(): str(value).strip() for key, value in headers.items()}
        for name in names:
            raw = lowered.get(name)
            if raw is None:
                continue
            try:
                return float(raw)
            except (TypeError, ValueError):
                logger.warning('Suppressed exception observed at agent_core/services/quota_governor.py:193 (continue)')
                continue
        return None

    def _absorb_headers_locked(
        self,
        window: _Window,
        headers: Optional[Mapping[str, str]],
    ) -> None:
        if not headers:
            return
        remaining_requests = self._header_int(headers, _RPM_HEADERS)
        remaining_tokens = self._header_int(headers, _TPM_HEADERS)
        reset_seconds = self._header_float(headers, _RESET_HEADERS)
        if remaining_requests is not None:
            window.header_remaining_requests = remaining_requests
        if remaining_tokens is not None:
            window.header_remaining_tokens = remaining_tokens
        if reset_seconds is not None:
            window.header_reset_seconds = reset_seconds

    # ------------------------------------------------------------------ #
    # Status
    # ------------------------------------------------------------------ #
    def status(self, provider: str, model: Optional[str] = None) -> QuotaStatus:
        return self.snapshot(provider, model).status

    def snapshot(self, provider: str, model: Optional[str] = None) -> QuotaSnapshot:
        """Compute the current health snapshot for a provider/model scope."""
        limits = self.limits_for(provider)
        key_model = model or "*"
        window = self._window(provider, key_model)
        now = self._clock()

        with self._lock:
            self._prune_locked(window, now)
            rpm_count = len([t for t in window.request_times if t >= now - _MINUTE_SECONDS])
            rpd_count = len(window.request_times)
            tpm_tokens = sum(n for t, n in window.token_times if t >= now - _MINUTE_SECONDS)
            tpd_tokens = sum(n for _, n in window.token_times)
            header_remaining_requests = window.header_remaining_requests
            header_remaining_tokens = window.header_remaining_tokens
            header_reset_seconds = window.header_reset_seconds

        if header_remaining_requests is not None or header_remaining_tokens is not None:
            remaining_fraction = self._header_remaining_fraction(
                limits,
                header_remaining_requests,
                header_remaining_tokens,
            )
            reset_at = self._iso_reset(header_reset_seconds) if header_reset_seconds else None
            if remaining_fraction is not None and remaining_fraction <= 0:
                return QuotaSnapshot(
                    status=QuotaStatus.EXHAUSTED,
                    remaining_fraction=0.0,
                    reset_at=reset_at,
                    source="response_header",
                )
            if remaining_fraction is not None and remaining_fraction <= _APPROACHING_FRACTION:
                return QuotaSnapshot(
                    status=QuotaStatus.APPROACHING_LIMIT,
                    remaining_fraction=remaining_fraction,
                    reset_at=reset_at,
                    source="response_header",
                )
            return QuotaSnapshot(
                status=QuotaStatus.HEALTHY,
                remaining_fraction=remaining_fraction,
                reset_at=reset_at,
                source="response_header",
            )

        if not limits.known:
            return QuotaSnapshot(status=QuotaStatus.UNKNOWN, source="unknown")

        fraction = self._local_remaining_fraction(
            limits,
            rpm_count=rpm_count,
            rpd_count=rpd_count,
            tpm_tokens=tpm_tokens,
            tpd_tokens=tpd_tokens,
        )
        if fraction is not None and fraction <= 0:
            return QuotaSnapshot(
                status=QuotaStatus.EXHAUSTED,
                remaining_fraction=0.0,
                source="local_accounting",
            )
        if fraction is not None and fraction <= _APPROACHING_FRACTION:
            return QuotaSnapshot(
                status=QuotaStatus.APPROACHING_LIMIT,
                remaining_fraction=fraction,
                source="local_accounting",
            )
        return QuotaSnapshot(
            status=QuotaStatus.HEALTHY,
            remaining_fraction=fraction,
            source="local_accounting",
        )

    @staticmethod
    def _header_remaining_fraction(
        limits: QuotaLimits,
        remaining_requests: Optional[int],
        remaining_tokens: Optional[int],
    ) -> Optional[float]:
        fractions: list[float] = []
        if remaining_requests is not None and limits.rpm:
            fractions.append(max(0.0, remaining_requests / limits.rpm))
        if remaining_tokens is not None and limits.tpm:
            fractions.append(max(0.0, remaining_tokens / limits.tpm))
        if not fractions:
            return None
        return min(fractions)

    @staticmethod
    def _local_remaining_fraction(
        limits: QuotaLimits,
        *,
        rpm_count: int,
        rpd_count: int,
        tpm_tokens: int,
        tpd_tokens: int,
    ) -> Optional[float]:
        fractions: list[float] = []
        if limits.rpm:
            fractions.append(max(0.0, 1.0 - rpm_count / limits.rpm))
        if limits.rpd:
            fractions.append(max(0.0, 1.0 - rpd_count / limits.rpd))
        if limits.tpm:
            fractions.append(max(0.0, 1.0 - tpm_tokens / limits.tpm))
        if limits.tpd:
            fractions.append(max(0.0, 1.0 - tpd_tokens / limits.tpd))
        if not fractions:
            return None
        return min(fractions)

    @staticmethod
    def _iso_reset(seconds_remaining: float) -> str:
        delta = timedelta(seconds=max(0.0, seconds_remaining))
        return (datetime.now(timezone.utc) + delta).isoformat()
