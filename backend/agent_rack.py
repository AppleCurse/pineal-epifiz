"""Agent Rack canlılık yüzeyi — ``/api/agents/status`` için işaretçi (beacon) filosu.

[AUDIT 2026-10-08] ``backend/api.py`` monolit tavanından (6000 satır, bkz.
``tests/unit/test_api_monolith_ratchet.py``) taşınan kod: işaretçi filosunun
canlılık hesabı (sinyal kaybı → ``deaf``) ve dinamik staleness eşikleri.
``backend.api`` bu isimleri YENİDEN İHRAÇ eder — mevcut içe aktarımlar
değişmeden çalışır (``body_size_limit`` precedentiyle aynı düzen).

Çok-süreçli (multi-process) mimaride sinyalin kaybolduğu durumlar burada AÇIKça
``deaf`` olarak yüzeye çıkar — sessiz kaybolma yok.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def env_float(name: str, default: float, *, min_value: float = 0.0) -> float:
    """Ortam değişkenini güvenli float'a çevirir (bozuk değer → varsayılan)."""
    try:
        value = float(os.getenv(name, "").strip() or default)
    except (TypeError, ValueError):
        return default
    return value if value >= min_value else default


#: İşaretçi (beacon) filosu için staleness eşiği — SABİT sayı değil, worker'ın
#: KENDİ yayın aralığına dinamik bağ: eşik = çarpan × yayın aralığı.
#: Çok-süreçli mimaride sinyal kaybı (deaf) bu eşikle ölçülür; her iki değer
#: de tek env'den okunur (worker CLI varsayılanı ile AYNI kaynak).
AGENT_HEARTBEAT_INTERVAL_S = env_float("PINEAL_AGENT_HEARTBEAT_INTERVAL", 30.0, min_value=1.0)
AGENT_STALE_MULTIPLIER = env_float("PINEAL_AGENT_STALE_MULTIPLIER", 3.0, min_value=1.0)


async def beacon_liveness(bus: Any) -> dict:
    """İşaretçi filosunun canlılığı — çok-süreçli sinyal kaybı burada görünür.

    12 servis her biri kendi işaretçisini yayınlar; ``{channel}:latest`` anahtarı
    son sinyali taşır. Sinyal eşiği aşarsa (yayın aralığı × çarpan) filo ``deaf``
    sayılır — sinyalin kaybolduğu durum AÇIKça yüzeye çıkar (sessiz yok).
    """
    from agent_core.workers.agent_worker import BEACON_CHANNEL

    stale_after = AGENT_STALE_MULTIPLIER * AGENT_HEARTBEAT_INTERVAL_S
    state, age = "unknown", None
    get_latest = getattr(bus, "get_latest", None)
    if callable(get_latest):
        try:
            latest = await get_latest(BEACON_CHANNEL)
        except Exception as exc:
            logger.warning("beacon son sinyali okunamadı: %s", exc)
            latest = None
        if isinstance(latest, dict) and latest.get("timestamp"):
            try:
                age = (
                    datetime.now(timezone.utc)
                    - datetime.fromisoformat(str(latest["timestamp"]))
                ).total_seconds()
                state = "live" if age <= stale_after else "deaf"
            except (TypeError, ValueError):
                state = "unknown"
    return {
        "state": state,
        "last_seen_age_s": round(age, 1) if age is not None else None,
        "stale_after_s": stale_after,
    }
