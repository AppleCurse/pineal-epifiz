"""Hedef ön-kontrol (preflight) uç noktası: ``POST /api/target/preflight``.

Görev başlatılmadan önce URL/platform uygunluğunu, kasa kilidini ve veri
toplama kanallarının hazır olup olmadığını ``platform_registry`` ve
``_check_vault_interlock`` tek kaynaklarından ölçer.
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, Field

from agent_core.services.platform_registry import (
    classify_profile_url,
    effective_scraper_type,
)

__all__ = ["PreflightPayload", "register_preflight_routes"]


class PreflightPayload(BaseModel):
    client_id: str = Field(default="default", max_length=128)
    url: str = Field(default="", max_length=2048)
    scraper_type: str = Field(default="cross", max_length=32)


def _single_source_flag_env(name: str) -> bool:
    """Tek kaynak env kapısı okuma (``agent_core.capabilities.state.flag_enabled``)."""
    from agent_core.capabilities.state import flag_enabled

    try:
        return bool(flag_enabled(name))
    except Exception:  # fail-closed + görünür
        return False


def register_preflight_routes(
    app: Any,
    *,
    get_room: Callable[[str], dict],
    check_vault_interlock: Callable[[str], bool],
    flag_env: Callable[[str], bool] | None = None,
) -> None:
    """``POST /api/target/preflight`` rotasını kaydeder.

    ``flag_env`` verilmezse tek kaynak (``flag_enabled``) kullanılır — üçüncü
    bir bağımsız okuma üretilmez (K1 · 2026-11-21).
    """
    flag_reader = flag_env if callable(flag_env) else _single_source_flag_env

    @app.post("/api/target/preflight")
    async def api_target_preflight(req: PreflightPayload):
        raw_url = (req.url or "").strip()
        cross_enabled = bool(flag_reader("ENABLE_CROSS_PLATFORM"))
        vault_unlocked = bool(check_vault_interlock(req.client_id))
        room = get_room(req.client_id)
        vault = room.get("vault") or {}

        reasons: list[str] = []
        if not raw_url:
            reasons.append("MISSING_TARGET: Hedef URL veya kullanıcı adı boş.")
            scraper = "unsupported_web"
            classified = {"platform": "unknown", "sensor_id": None}
        else:
            scraper = effective_scraper_type(raw_url, req.scraper_type)
            classified = classify_profile_url(raw_url)
            if scraper == "unsupported_web":
                if not cross_enabled:
                    reasons.append(
                        "UNSUPPORTED_PLATFORM: Bu kurulumda yalnızca Instagram ve X doğrudan desteklenir (ENABLE_CROSS_PLATFORM=false)."
                    )
                else:
                    reasons.append(
                        "UNSUPPORTED_URL: Hedef URL desteklenen bir sosyal profil formatında değil."
                    )

        if not vault_unlocked:
            reasons.append("VAULT_LOCKED: Kasa kilitli; dış ağ/OSINT/kazıyıcı çıkışı kapalı.")

        has_llm = bool(
            vault.get("or_key")
            or vault.get("provider_keys_set")
            or vault.get("use_local")
        )
        channels = [
            {
                "channel": f"scraper.{scraper}",
                "ready": scraper != "unsupported_web" and vault_unlocked,
                "reason": (
                    ""
                    if (scraper != "unsupported_web" and vault_unlocked)
                    else ("vault_locked" if not vault_unlocked else "unsupported_platform")
                ),
            },
            {
                "channel": "osint.search",
                "ready": bool(vault.get("tavily") or vault.get("serpapi") or vault.get("exa")) and vault_unlocked,
                "reason": (
                    ""
                    if (bool(vault.get("tavily") or vault.get("serpapi") or vault.get("exa")) and vault_unlocked)
                    else ("vault_locked" if not vault_unlocked else "search_key_missing")
                ),
            },
            {
                "channel": "llm.gateway",
                "ready": has_llm,
                "reason": "" if has_llm else "no_vault_llm_key_or_local",
            },
        ]

        eligible = bool(raw_url) and scraper != "unsupported_web" and vault_unlocked
        return {
            "eligible": eligible,
            "url": raw_url,
            "platform": classified.get("platform", "unknown"),
            "scraper_type": scraper,
            "sensor_id": classified.get("sensor_id"),
            "cross_platform_enabled": cross_enabled,
            "vault_unlocked": vault_unlocked,
            "reasons": reasons,
            "channels": channels,
        }
