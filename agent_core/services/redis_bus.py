"""
PINEAL-HERETIC v5.0 - Redis Pub/Sub Event Bus
Agent Rack slotlarının Ready/Active/Wait durumunu anlık yayınlayan köprü.
Fallback: Redis yoksa in-memory.
"""
import json
import logging
import os
from typing import Any, Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis  # type: ignore
    HAS_REDIS = True
except ImportError:
    try:
        import redis  # noqa: F401  # varlık kontrolü için, kullanımı connect() içinde
        HAS_REDIS = True
        aioredis = None  # type: ignore
    except ImportError:
        HAS_REDIS = False
        aioredis = None  # type: ignore


class InMemoryBus:
    """Redis yoksa in-memory fallback"""

    def __init__(self):
        self._store: Dict[str, Any] = {}

    async def publish(self, channel: str, message: Dict[str, Any]) -> int:
        # Abone mekanizmasi yok (subscribe kaldirildi): sadece son durum saklanir.
        # Redis PUBLISH anlamiyle abone sayisi her zaman 0'dir.
        self._store[channel] = message
        return 0

    async def set(self, key: str, value: Any):
        self._store[key] = value


class RedisBus:
    """
    Redis Pub/Sub köprüsü
    Channels:
      pineal:agent:status -> Agent Rack durumları
      pineal:telemetry -> sistem telemetrisi
      pineal:events -> genel event bus
    """

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._client: Optional[Any] = None
        self._fallback = InMemoryBus()
        self._use_redis = False
        self._connected = False

    def connection_state(self) -> str:
        """Gerçek taşıyıcı durumu: ``redis_bus`` | ``in_memory``.

        [RÖNTGEN 2026-09-23] Agent Rack'in KAYNAK satırı eskiden yalnız
        "tracker nesnesi var mı"ya bakıyordu: Redis'e hiç bağlanamamış bir
        süreç bile UI'ya ``redis_bus`` diye beyan ediliyordu (etiket sahte,
        veri gerçek). Bu metod ``connect()`` içinde PING ile doğrulanmış
        bağlantı bayrağını okur — UI kaynağı taşıyıcının kendisine kadar
        izlenebilir.
        """
        return "redis_bus" if (self._use_redis and self._connected) else "in_memory"

    async def connect(self) -> bool:
        if not HAS_REDIS:
            logger.info("Redis kutuphanesi yok, in-memory bus kullaniliyor")
            self._use_redis = False
            return False

        try:
            if aioredis:
                self._client = aioredis.from_url(self.redis_url, decode_responses=True)
                await self._client.ping()
            else:
                # Sync fallback - not ideal but works
                import redis as sync_redis
                self._client = sync_redis.from_url(self.redis_url, decode_responses=True)
                self._client.ping()
            self._use_redis = True
            self._connected = True
            logger.info(f"Redis baglandi: {self.redis_url}")
            return True
        except Exception as e:
            logger.warning(f"Redis baglanamadi ({self.redis_url}): {e}, in-memory fallback")
            self._use_redis = False
            self._connected = False
            return False

    async def publish(self, channel: str, message: Dict[str, Any]) -> int:
        payload = json.dumps(message, ensure_ascii=False, default=str)
        if self._use_redis and self._client:
            try:
                if aioredis:
                    count = await self._client.publish(channel, payload)
                else:
                    count = self._client.publish(channel, payload)
                # Also store latest
                await self._store_latest(channel, message)
                return count
            except Exception as e:
                logger.warning(f"Redis publish hatasi {channel}: {e}, fallback")
                return await self._fallback.publish(channel, message)
        else:
            return await self._fallback.publish(channel, message)

    async def _store_latest(self, channel: str, message: Dict[str, Any]):
        """Son durumu key-value olarak da sakla (GET için)"""
        key = f"{channel}:latest"
        try:
            if self._use_redis and self._client:
                data = json.dumps(message, ensure_ascii=False, default=str)
                if aioredis:
                    await self._client.set(key, data, ex=3600)
                else:
                    self._client.set(key, data, ex=3600)
            else:
                await self._fallback.set(key, message)
        except Exception as e:
            logger.debug(f"Store latest hatasi {key}: {e}")

    async def publish_agent_status(self, agent_id: str, status: str, metadata: Optional[Dict] = None):
        msg = {
            "type": "agent_status_update",
            "agent_id": agent_id,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        await self.publish("pineal:agent:status", msg)
        # Also publish to general events
        await self.publish("pineal:events", msg)
        return msg

    async def disconnect(self):
        try:
            if self._client and aioredis:
                await self._client.close()
        except Exception as exc:
            # Kapanış temizliği: bağlantı zaten kopmuş olabilir — debug iziyle bırakılır.
            logger.debug("[disconnect] redis istemcisi kapatılırken hata: %s", exc)
        self._connected = False


# Global singleton
_redis_bus: Optional[RedisBus] = None


def get_redis_bus() -> RedisBus:
    global _redis_bus
    if _redis_bus is None:
        _redis_bus = RedisBus()
    return _redis_bus


async def init_redis_bus(redis_url: Optional[str] = None) -> RedisBus:
    global _redis_bus
    _redis_bus = RedisBus(redis_url)
    await _redis_bus.connect()
    return _redis_bus
