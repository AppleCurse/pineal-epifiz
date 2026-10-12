"""PINEAL-HERETIC — Ajan Yuvası CANLILIK İŞARETÇİSİ (liveness beacon).

.. warning::
   Bu modül **analiz yürütmez**. Yalnızca "bu ajan yuvasının işaretçisi
   ayakta ve boşta" bilgisini yayınlar.

[AUDIT 2026-10-07 · Madde 3] Eski hâl ve kusur
----------------------------------------------
Eski başlık "Docker Compose altında bağımsız çalışan **12 ajan servisinin
ortak worker'ı**" idi ve şu kodu koşuyordu::

    await tracker.set_ready(agent_id)          # açılışta
    ... her 30 saniyede bir, koşulsuz: ...
    await tracker.set_ready(agent_id)

Bu, deponun kendi ilkesini doğrudan ihlal ediyordu. ``agent_status_tracker``
içinde (bkz. [RÖNTGEN 2026-09-23]) ``set_all_ready()`` ve
``simulate_processing()`` **tam olarak bu sebeple** kaldırılmıştı:

    "hiçbir ajan çalışmadan 'hazır/çalışıyor' durumu UYDURMAK."

Fakat 12 compose servisi, her 30 saniyede bir koşulsuz ``Ready`` basarak
bu uydurmayı yeniden üretiyordu: hiçbir kanıt üretilmemişken Agent Rack
12/12 READY gösteriyor, üstelik gerçek bir koşunun yazdığı ``Active`` /
``Done`` / ``Error`` durumlarını da 30 saniyede bir EZİYORDU.

Gerçek mimari (denetimde doğrulandı)
------------------------------------
* Analizleri ``PinealExecutor`` **süreç içinde** (in-process) yürütür;
  gerçek ``active``/``ready``/``wait`` geçişleri ``_rack_update`` ile yazılır.
* Bu servislerin işi, yuvanın CANLI olduğunu bildirmektir — iş YÜRÜTMEK
  DEĞİLDİR.
* Depoda görev kuyruğu / iş teslim mekanizması **yoktur**
  (``agent_core`` içinde queue/consumer modülü bulunmuyor). Dolayısıyla
  "kuyruğu dinleyip gerçek iş çeken worker" davranışı uydurulamaz; burada
  uydurulmaz.

Yeni sözleşme
-------------
İşaretçi yalnızca DOĞRULAYABİLDİĞİ şeyi yazar ve bunu **kendi kanalına**
(``pineal:agent:beacon``) yazar; ajan durum kanalına (``pineal:agent:status``)
ASLA yazmaz. Böylece:

* sahte ``Ready`` üretmez,
* yürütücünün yazdığı gerçek durumları ezmez,
* yine de ölçülebilir bir canlılık sinyali bırakır (Redis'te
  ``pineal:agent:beacon:latest`` + yapılandırılmış log).

Operatör notu: 12 servis tek bir "canlılık işaretçisi" hâline de
indirgenebilir; bu bir dağıtım (deployment) kararıdır ve denetim raporunda
öneri olarak kayıtlıdır — burada davranış değiştirilmedi, yalnızca DÜRÜST
hâle getirildi.
"""

import argparse
import asyncio
import logging
import os
import signal
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("agent_worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

AGENT_ID = os.getenv("AGENT_ID", "unknown")
AGENT_NAME = os.getenv("AGENT_NAME", AGENT_ID.upper())
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
BACKEND_URL = os.getenv("BACKEND_URL", "http://pineal:8000")

#: İşaretçinin KENDİ kanalı. Ajan durum kanalı (``pineal:agent:status``)
#: yürütücüye (PinealExecutor) aittir; işaretçi oraya yazmaz.
BEACON_CHANNEL = "pineal:agent:beacon"

#: Ajan durum kanalı — yalnızca "buraya yazmıyoruz" sözleşmesini belgelemek
#: ve testte doğrulamak için burada durur.
AGENT_STATUS_CHANNEL = "pineal:agent:status"

#: İşaretçinin rolü: makinece okunabilir dürüstlük etiketi.
BEACON_ROLE = "liveness_beacon"

#: Durum sözlüğü ``agent_core.services.agent_status_tracker.AgentStatus`` ile
#: AYNIDIR. Burada kopya durmasının sebebi: bu süreç tracker'ı GEVŞEK (lazy)
#: içe aktarır, Redis/aioredis yoksa da ayağa kalkabilmelidir.
#: ``tests/unit/test_agent_worker.py`` iki listeyi birbirine kilitler.
STATUS_WAIT = "Wait"
STATUS_READY = "Ready"
STATUS_ACTIVE = "Active"
STATUS_DONE = "Done"
STATUS_ERROR = "Error"


def build_liveness_message(
    agent_id: str,
    *,
    alive: bool = True,
    redis_link: Optional[bool] = None,
    backend_link: Optional[bool] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """İşaretçinin yayınlayacağı canlılık mesajını kurar (saf fonksiyon).

    Bilinçli olarak **hiçbir operasyonel iddia içermez**: ``status`` alanı
    YOKTUR, çünkü ajanın durumu bu sürecin bilebileceği bir şey değildir.
    Yalnızca doğrudan ölçtüğü üç şeyi yazar: kendisi ayakta mı, Redis'e
    erişiyor mu, backend'e erişiyor mu.
    """
    return {
        "type": "agent_beacon_liveness",
        "agent_id": agent_id,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "beacon": {
            "role": BEACON_ROLE,
            # AÇIK ETİKET: bu süreç analiz yürütmez. Eskiden buradan "Ready"
            # basılıyordu ve bu alanın karşılığı yoktu.
            "executes_analysis": False,
            "alive": alive,
            "redis_link": redis_link,
            "backend_link": backend_link,
        },
    }


async def probe_backend(backend_url: str, *, timeout: float = 5.0) -> bool:
    """Backend'e SAĞLIK SONDASI atar; durum YAZMAZ, yalnızca erişilebilirliği ölçer.

    Eski kod buradan ``POST /api/agents/status/{id}?status=Ready`` çağırarak
    hem durum uyduruyor hem de gerçek durumu eziyordu. Sonda salt okunur.
    """
    if not backend_url:
        return False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{backend_url.rstrip('/')}/health")
            return response.status_code < 500
    except Exception as exc:  # noqa: BLE001 - sonda: her türlü hata "erişilemiyor" demektir
        logger.debug("[%s] backend sondası başarısız: %s", backend_url, exc)
        return False


async def publish_liveness(
    bus: Any,
    agent_id: str,
    *,
    alive: bool = True,
    redis_link: Optional[bool] = None,
    backend_link: Optional[bool] = None,
) -> Dict[str, Any]:
    """Canlılık mesajını KENDİ kanalına yayınlar.

    Redis erişilemezse ``RedisBus`` kendi içinde bellek-içi yedeğe düşer;
    bu durumda mesaj kaybolmaz ama yalnızca bu süreçte görülür — bu yüzden
    ``redis_link`` bayrağı mesajın içinde açıkça taşınır.
    """
    message = build_liveness_message(
        agent_id, alive=alive, redis_link=redis_link, backend_link=backend_link
    )
    await bus.publish(BEACON_CHANNEL, message)
    return message


async def run_worker(
    agent_id: str,
    *,
    bus: Any = None,
    heartbeat_interval: float = 30.0,
    max_heartbeats: Optional[int] = None,
    backend_url: Optional[str] = BACKEND_URL,
) -> None:
    """İşaretçi döngüsü: sonda → yayınla → bekle.

    Args:
        agent_id: Bu işaretçinin sahip olduğu ajan yuvası.
        bus: Testler için hazır veri yolu (``publish`` metodunu taşır).
            ``None`` ise Redis yolundan kurulmaya çalışılır.
        heartbeat_interval: Yayın aralığı (saniye).
        max_heartbeats: Varsa, bu kadar yayından sonra döngü biter
            (testler için; üretimde ``None`` = sonsuz).

    Not:
        Bu döngü HİÇBİR ZAMAN ``set_ready`` / ``update_status`` çağırmaz.
        Ajan durumu yürütücünün tekelindedir (bkz. modül docstring'i).
    """
    redis_link: Optional[bool] = None

    if bus is None:
        try:
            from agent_core.services.redis_bus import init_redis_bus
        except ImportError as exc:
            logger.warning("Redis bus import edilemedi (yalnızca log modunda): %s", exc)
            init_redis_bus = None  # type: ignore[assignment]

        if init_redis_bus is not None:
            try:
                bus = await init_redis_bus(REDIS_URL)
                redis_link = getattr(bus, "connection_state", lambda: "unknown")() == "connected"
                logger.info("[%s] Redis veri yolu kuruldu: %s", agent_id, REDIS_URL)
            except Exception as exc:  # noqa: BLE001 - işaretçi: Redis yoksa da yaşamalı
                logger.warning("[%s] Redis kurulamadı: %s — yalnızca log modu", agent_id, exc)
                redis_link = False

    if bus is None:
        # Bellek-içi yedek: mesajlar yalnızca loglanır. İşaretçi yine de
        # canlılığını loglardan belli eder; asla durum uydurmaz.
        class _LogOnlyBus:
            async def publish(self, channel: str, message: Dict[str, Any]) -> int:
                logger.info("[%s] beacon(%s): %s", agent_id, channel, message)
                return 0

        bus = _LogOnlyBus()
        if redis_link is None:
            redis_link = False

    logger.info(
        "[%s] canlılık işaretçisi başladı (rol=%s, analiz_yürütmez=True)", agent_id, BEACON_ROLE
    )

    beats = 0
    try:
        while max_heartbeats is None or beats < max_heartbeats:
            backend_link = await probe_backend(backend_url) if backend_url else None
            message = await publish_liveness(
                bus, agent_id, alive=True, redis_link=redis_link, backend_link=backend_link
            )
            logger.debug("[%s] canlılık yayınlandı: %s", agent_id, message)
            beats += 1
            if max_heartbeats is not None and beats >= max_heartbeats:
                break
            await asyncio.sleep(heartbeat_interval)
    except asyncio.CancelledError:
        logger.info("[%s] işaretçi durduruluyor", agent_id)
        try:
            await publish_liveness(
                bus, agent_id, alive=False, redis_link=redis_link, backend_link=None
            )
        except Exception:  # noqa: BLE001 - kapanışta yayın başarısız olabilir
            pass
        raise
    finally:
        logger.info("[%s] işaretçi döngüsü sonlandı (%d yayın)", agent_id, beats)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pineal Agent Liveness Beacon (analiz yürütmez; yalnızca canlılık yayınlar)"
    )
    parser.add_argument("--agent-id", default=AGENT_ID, help="Agent ID (mirror_truth vb.)")
    parser.add_argument("--redis-url", default=REDIS_URL, help="Redis URL")
    parser.add_argument(
        "--heartbeat-interval", type=float, default=30.0, help="Canlılık yayın aralığı (saniye)"
    )
    parser.add_argument("--backend-url", default=BACKEND_URL, help="Sağlık sondası için backend adresi")
    args = parser.parse_args()

    agent_id = args.agent_id or AGENT_ID
    os.environ["AGENT_ID"] = agent_id

    logger.info("Ajan canlılık işaretçisi başlatılıyor: %s (%s)", agent_id, AGENT_NAME)
    logger.info("Redis: %s", args.redis_url)
    logger.info("Backend sondası: %s", args.backend_url)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: loop.stop())
        except NotImplementedError:
            pass  # Windows

    try:
        loop.run_until_complete(
            run_worker(
                agent_id,
                heartbeat_interval=args.heartbeat_interval,
                backend_url=args.backend_url,
            )
        )
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt - kapanıyor")
    except RuntimeError as exc:
        if "Event loop stopped" in str(exc):
            logger.info("Olay döngüsü durduruldu - kapanıyor")
        else:
            raise
    finally:
        loop.close()


if __name__ == "__main__":
    main()
