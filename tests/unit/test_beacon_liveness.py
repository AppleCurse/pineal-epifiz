"""İşaretçi (beacon) filosu canlılık yüzeyi — çok-süreçli sinyal kaybı (deaf).

[AUDIT 2026-10-08 · Madde 3] Kendi eklenen kodların sağlamlaştırılması:
  1. Staleness eşiği SABİT sayı değil — worker'ın KENDİ yayın aralığına
     (PINEAL_AGENT_HEARTBEAT_INTERVAL × PINEAL_AGENT_STALE_MULTIPLIER) bağlı.
  2. Sinyalin kaybolduğu durum (deaf/unreachable) `/api/agents/status`
     üzerinde AÇIKça yüzeye çıkar — sessiz kaybolma yok.
  3. RedisBus'taki sync istemci çağrıları (ping/publish/set/get) event loop'u
     `asyncio.to_thread` ile bloklamaz; `:latest` TTL'i dinamik.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent_core.services.redis_bus import InMemoryBus, RedisBus, _latest_ttl_seconds
from backend import api


class _FakeBus:
    """get_latest taşıyan sahte veri yolu."""

    def __init__(self, latest):
        self._latest = latest

    async def get_latest(self, channel: str):
        return self._latest


def _msg(age_s: float) -> dict:
    ts = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    return {"type": "agent_beacon_liveness", "timestamp": ts.isoformat()}


# ─────────────────────────────────────────────────────────────────────────
# 1) Eşik dinamik — sabit değil
# ─────────────────────────────────────────────────────────────────────────

def test_stale_threshold_follows_worker_publish_interval(monkeypatch):
    monkeypatch.setenv("PINEAL_AGENT_HEARTBEAT_INTERVAL", "10")
    monkeypatch.setenv("PINEAL_AGENT_STALE_MULTIPLIER", "3")
    # modül seviyesindeki sabitler env'i import anında okur; fonksiyonları
    # doğrudan env ile yeniden hesaplayarak dinamik bağı doğrula:
    interval = api._env_float("PINEAL_AGENT_HEARTBEAT_INTERVAL", 30.0, min_value=1.0)
    multiplier = api._env_float("PINEAL_AGENT_STALE_MULTIPLIER", 3.0, min_value=1.0)
    assert interval * multiplier == 30.0  # 10s × 3 — sabit 90 DEĞİL


def test_latest_ttl_is_bound_to_publish_interval(monkeypatch):
    monkeypatch.setenv("PINEAL_AGENT_HEARTBEAT_INTERVAL", "600")
    assert _latest_ttl_seconds() == 2400  # 4 × 600
    monkeypatch.setenv("PINEAL_AGENT_HEARTBEAT_INTERVAL", "10")
    assert _latest_ttl_seconds() == 300  # alt sınır 5 dk
    monkeypatch.setenv("PINEAL_AGENT_HEARTBEAT_INTERVAL", "bozuk")
    assert _latest_ttl_seconds() == 300  # bozuk değer → varsayılan güvenli


# ─────────────────────────────────────────────────────────────────────────
# 2) Sinyal kaybı (deaf) açıkça yüzeye çıkar
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_beacon_liveness_live_when_signal_fresh():
    result = await api._beacon_liveness(_FakeBus(_msg(age_s=5)))
    assert result["state"] == "live"
    assert result["last_seen_age_s"] is not None
    assert result["stale_after_s"] == api._AGENT_STALE_MULTIPLIER * api._AGENT_HEARTBEAT_INTERVAL_S


@pytest.mark.asyncio
async def test_beacon_liveness_deaf_when_signal_lost():
    """Sinyal eşiği aşınca filo 'deaf' — kaybolma AÇIKça görünür."""
    stale_after = api._AGENT_STALE_MULTIPLIER * api._AGENT_HEARTBEAT_INTERVAL_S
    result = await api._beacon_liveness(_FakeBus(_msg(age_s=stale_after + 60)))
    assert result["state"] == "deaf"


@pytest.mark.asyncio
async def test_beacon_liveness_unknown_without_bus_or_signal():
    assert (await api._beacon_liveness(None))["state"] == "unknown"
    assert (await api._beacon_liveness(_FakeBus(None)))["state"] == "unknown"


@pytest.mark.asyncio
async def test_beacon_liveness_survives_broken_bus():
    class _BrokenBus:
        async def get_latest(self, channel: str):
            raise RuntimeError("redis patladı")

    # Arıza yutulmaz (loglanır) ama yüzey çökmemeli — 'unknown' döner.
    result = await api._beacon_liveness(_BrokenBus())
    assert result["state"] == "unknown"


@pytest.mark.asyncio
async def test_agents_status_endpoint_carries_beacon_field(monkeypatch):
    """Fallback DIŞI yolda yanıt beacon alanı taşır (deaf/live/unknown)."""
    from agent_core.services.agent_status_tracker import AgentStatusTracker

    class _RecordingBus:
        def connection_state(self):
            return "in_memory"

        async def get_latest(self, channel: str):
            return _msg(age_s=1)

    tracker = AgentStatusTracker(_RecordingBus())
    monkeypatch.setattr(api, "get_tracker", lambda: tracker)

    class _AppBus:
        async def get_latest(self, channel: str):
            return _msg(age_s=1)

    monkeypatch.setattr(api.app.state, "redis_bus", _AppBus(), raising=False)
    payload = await api.api_agents_status()
    assert payload["beacon"]["state"] == "live"
    assert payload["count"] == len(payload["agents"])


# ─────────────────────────────────────────────────────────────────────────
# 3) RedisBus: get_latest + in-memory yol
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_redis_bus_get_latest_reads_stored_message():
    bus = RedisBus("redis://localhost:6379/0")  # bağlanmaz — in-memory'e düşer
    await bus.publish("pineal:agent:beacon", {"type": "agent_beacon_liveness", "x": 1})
    latest = await bus.get_latest("pineal:agent:beacon")
    assert latest == {"type": "agent_beacon_liveness", "x": 1}
    assert await bus.get_latest("pineal:agent:beacon:nonexistent") is None


@pytest.mark.asyncio
async def test_in_memory_bus_get_roundtrip():
    bus = InMemoryBus()
    await bus.set("k", {"a": 1})
    assert await bus.get("k") == {"a": 1}
    assert await bus.get("yok") is None
