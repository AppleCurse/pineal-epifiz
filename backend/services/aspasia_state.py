"""Aspasia denetim görünümü (`GET /api/aspasia/state`) — gövde modülü.

[API-BÖLME 6 · 2026-10-18] `backend/api.py` tek-modül tavanı
(`tests/unit/test_api_monolith_ratchet.py`; kural: satır eklemek yerine MODÜL
ÇIKAR — `docs/reports/API_MONOLITH_SPLIT_PLAN.md` §4) gereği uç gövdesi bu
modüle taşındı. Uç sözleşmesi **aynen korunur** (`/api/aspasia/state` yolu,
yöntemi, yanıt anahtarları); `backend/api.py` yalnız `app.get(...)` ile kaydeder
ve bağımlılıkları ENJEKTE eder (dairesel bağımlılık yok).

Yanıtın tamamı **mevcut SoT okuyucularından** türetilir:
  * `registry`  → `AgentInspector.registry()` (executor.agents)
  * `run`       → `AgentInspector.run_status(room)` (yaşam döngüsü snapshot'ı)
  * `budget`    → `CostReader(gateway).snapshot()`
  * `quota`     → `QuotaReader(gateway).snapshot(p)`
  * `anomalies` → `TelemetryReader(gateway).anomalies()`
  * `calls`     → `TelemetryReader.window(offset, limit)` (gateway `call_log`)
  * `call_binding` → `CallBinder.bind(run_view, offset, limit)`

[P8 · CANLI PANEL] `calls` artık **sayfalıdır** (`offset`/`limit`): çağrı
günlüğü 500 kayıtla sınırlıdır; panel önceden yalnız son 40 kaydı
görebiliyordu. Kayıt **UYDURULMAZ** — pencerenin kaymasıdır. Varsayılan
değerler (offset=0, limit=40) eski davranışın AYNI kopyasıdır.
"""

from __future__ import annotations

from typing import Any, Dict

from agent_core.aspasia.interface import (
    AgentInspector,
    CallBinder,
    CostReader,
    QuotaReader,
    TelemetryReader,
)

__all__ = ["build_state_payload"]

#: Kota okuyucusunun okuduğu sağlayıcılar (aynı küme — tek yer).
_QUOTA_PROVIDERS = ("groq", "cerebras")


def build_state_payload(
    *,
    room: Dict[str, Any],
    executor: Any,
    chief_gateway: Any,
    offset: int = 0,
    limit: int = 40,
) -> Dict[str, Any]:
    """Salt-okur denetim görünümünü kurar.

    `room`/`executor`/`chief_gateway` ENJEKTE edilir (modül `backend.api`'yi
    içe aktarmaz → dairesel bağımlılık yok).
    """
    gateway = executor.llm_gateway if executor is not None else chief_gateway
    inspector = AgentInspector(executor)
    telemetry = TelemetryReader(gateway)
    # [P6/P8] Çağrı izi (traceability): call_id → ajan → model → sağlayıcı →
    # süre → maliyet zinciri. Kaynak TEK yerdedir: gateway'in `call_log`u
    # (paralel telemetri deposu YOK). `run.call_ids` ile `call_log` AYNI
    # kimlik uzayını paylaşır (call_id); bağ sunucu tarafında kurulur.
    run_view = inspector.run_status(room)
    calls, binding = CallBinder(telemetry).bind(run_view, offset=offset, limit=limit)
    return {
        "registry": inspector.registry(),
        "run": run_view,
        "budget": CostReader(gateway).snapshot(),
        "quota": {
            provider: QuotaReader(gateway=gateway).snapshot(provider)
            for provider in _QUOTA_PROVIDERS
        },
        "anomalies": telemetry.anomalies(),
        "calls": calls,
        "call_count": len(calls),
        # Çağrı kimliği bağlama özeti (panel "izlenebilirlik" satırı).
        "call_binding": binding,
        # Sayfalama durumu (panel "DAHA ESKİ / DAHA YENİ" düğmeleri).
        "call_window": {
            "offset": max(0, int(offset)),
            "limit": max(0, int(limit)),
            "total": binding.get("log_total", 0),
        },
    }
