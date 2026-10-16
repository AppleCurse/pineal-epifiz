"""Telemetri ucu — ``GET /api/telemetry``.

[API-BÖLME 3 · 2026-10-16] Bu modül, ``backend/api.py`` tek-modül tavanı
(``tests/unit/test_api_monolith_ratchet.py``; kural: satır eklemek yerine
MODÜL ÇIKAR — ``docs/reports/API_MONOLITH_SPLIT_PLAN.md`` §4, "düşük
bağımlılık" sırasının ``telemetry`` adımı) gereği ayrıldı. Uç
``build_telemetry_endpoint`` ile kurulur ve ``backend.api`` tarafından
``app.get("/api/telemetry")`` ile KAYDEDİLİR; dış sözleşme (ad, yol, gövde)
korunur. Bağımlılıklar ENJEKTE edilir: bu modül ``backend.api``'yi içe
aktarmaz, dairesel bağımlılık yoktur.

Uç sözleşmesi (gövde taşınırken DEĞİŞTİRİLMEDİ):
  * ``core`` / ``gateway`` / ``scraper`` / ``vault`` / ``search_engine`` …
    → mevcut bayraklar aynen korunur.
  * [P0 · DENETİM 2026-10-16 · Bulgu B-3] YENİ: ``capabilities`` — capability
    spine'ın TEK kayıt defterinden (``registry.status``) gelen, her satırda
    ``available`` + MAKİNE-OKUNUR ``reason`` taşıyan tablo. "Kapalı" demek
    yetmez; operatör NEDENini de görmelidir.
  * [P0] ``x_scraper_reason`` — X sensörünün kapalı olma sebebi.
  * ``capabilities_unavailable_reason`` — {id: reason} hızlı sözlük.

Test: ``tests/unit/test_p0_honest_status.py`` (telemetri sözleşmesi),
``tests/unit/test_task_lifecycle.py`` (doğrudan çağrı), ``tests/e2e/test_smoke.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

__all__ = ["TelemetryDeps", "build_telemetry_endpoint", "capability_status_table"]


def capability_status_table(*, vault_locked: bool) -> list[dict]:
    """Yetenek durum tablosu (sebepli) — telemetri/UI için.

    Kaynak: capability spine'ın TEK kayıt defteri (``registry.status``).
    Kasa kilitliyse ``vault_locked=True`` ile değerlendirilir; böylece
    "kapalı" görünümünün sebebi ``gate_disabled:ENABLE_*`` ile
    ``vault_locked`` arasında AYIRT EDİLEBİLİR.
    """
    try:
        from agent_core.capabilities import bootstrap
        from agent_core.capabilities.state import policy_state

        registry = bootstrap()
        state = policy_state(vault_locked=bool(vault_locked), rate_ok=True)
        return registry.status(state)
    except Exception as exc:  # telemetri asla API'yı düşürmez
        logger.debug("yetenek durum tablosu okunamadı: %s", type(exc).__name__)
        return []


@dataclass(frozen=True)
class TelemetryDeps:
    """Uç gövdesinin ihtiyaç duyduğu ``backend/api.py`` bağımlılıkları."""

    get_room: Callable[[str], dict]
    check_vault_interlock: Callable[[str], bool]
    scraper_capability: Callable[[], Any]
    delivery_status: Callable[[dict], dict]
    lifecycle_metrics: Callable[[dict], dict]
    x_sensor_ready: Callable[[], bool]
    is_real_key: Callable[[Any], bool]
    agent_statuses_provider: Callable[[], dict]
    runtime_status_provider: Callable[[], dict]


def build_telemetry_endpoint(deps: TelemetryDeps) -> Callable[..., Any]:
    """``/api/telemetry`` gövdesini kurar (FastAPI'ye kaydedilebilir)."""

    async def api_telemetry(client_id: str = "default"):
        room = deps.get_room(client_id)
        executor = room["executor"]
        vault = room["vault"]
        capability = await deps.scraper_capability()
        budget_reader = getattr(type(executor.llm_gateway), "budget_status", None)
        budget = budget_reader(executor.llm_gateway) if callable(budget_reader) else {}
        # Agent Rack status
        agent_statuses = deps.agent_statuses_provider()
        # [FORENSIC VAULT-INTERLOCK] Telemetri, kilidin GERÇEK durumunu söyler:
        # placeholder anahtar "hazır" sayılmaz; `vault_locked` interlock ile birebir.
        vault_open = deps.check_vault_interlock(client_id)
        search_keys = getattr(executor, "search_engine", None)
        # [P0 · DENETİM 2026-10-16 · Bulgu B-3] Telemetri artık "kapalı" demekle
        # yetinmez: HANGİ yeteneğin NEDEN kapalı olduğunu (makine-okunur sebep)
        # taşır. Kaynak: capability spine'ın TEK kayıt defteri.
        capabilities = capability_status_table(vault_locked=not vault_open)
        return {
            "core": True,
            "gateway": deps.is_real_key(getattr(executor.llm_gateway, "api_key", None)),
            "scraper": capability["instagram"],
            "vault": vault_open,
            "search_engine": bool(vault.get("search_keys", False)) or any(
                deps.is_real_key(getattr(search_keys, attr, None))
                for attr in ("tavily_key", "serpapi_key", "exa_key")
            ),
            # [FAZ A] Artık SABİT False değil: X sensörü gerçekten var mı, kapıları
            # açık mı? Cevap capability spine'ın TEK kaynağından gelir.
            "x_scraper": deps.x_sensor_ready(),
            "instagram_scraper": capability["instagram"],
            "instagram_session": deps.is_real_key(vault.get("ig_sessionid")),
            "browser_installed": capability["browser"],
            "llm_spend_usd": round(float(budget.get("spend_usd", 0.0)), 6),
            "llm_reserved_spend_usd": round(float(budget.get("reserved_usd", 0.0)), 6),
            "llm_spend_cap_usd": float(budget.get("cap_usd", 0.0)),
            "llm_active_reservations": int(budget.get("active_reservations", 0)),
            "telemetry_delivery": deps.delivery_status(room),
            "task_lifecycle": deps.lifecycle_metrics(room),
            "rust_core": deps.runtime_status_provider(),
            "llm_unpriced_calls": int(getattr(executor.llm_gateway, "unpriced_calls", 0)),
            "agent_statuses": agent_statuses,
            "vault_locked": not vault_open,
            # [P0] Yetenek tablosu: id/kind/available/reason/policy_* — her satır
            # operatörün "neden çalışmadı" sorusunu cevaplayabilir.
            "capabilities": capabilities,
            "capabilities_unavailable_reason": {
                row["id"]: row["reason"]
                for row in capabilities
                if not row.get("available")
            },
            "x_scraper_reason": next(
                (
                    row.get("reason") or row.get("policy_reason")
                    for row in capabilities
                    if row.get("id") == "sensor.x.twscrape"
                ),
                "unknown",
            ),
        }

    return api_telemetry
