"""
PINEAL-HERETIC v5.0 - Agent Worker
Docker Compose altında bağımsız çalışan 12 ajan servisinin ortak worker'ı.
Her ajan Redis Pub/Sub üzerinden Ready/Active/Wait durumunu yayınlar.
"""

import argparse
import asyncio
import logging
import os
import signal
from datetime import datetime, timezone

logger = logging.getLogger("agent_worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

AGENT_ID = os.getenv("AGENT_ID", "unknown")
AGENT_NAME = os.getenv("AGENT_NAME", AGENT_ID.upper())
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
BACKEND_URL = os.getenv("BACKEND_URL", "http://pineal:8000")


async def run_worker(agent_id: str):
    """Ana worker loop — Redis'e bağlı, heartbeat atar, görev bekler"""
    try:
        from agent_core.services.redis_bus import init_redis_bus
        from agent_core.services.agent_status_tracker import init_tracker
    except ImportError as e:
        logger.warning(f"Tracker import hatasi (fallback in-memory): {e}")
        init_redis_bus = None
        init_tracker = None

    tracker = None

    if init_redis_bus:
        try:
            await init_redis_bus(REDIS_URL)
            logger.info(f"[{agent_id}] Redis baglandi: {REDIS_URL}")
        except Exception as e:
            logger.warning(f"[{agent_id}] Redis baglanamadi: {e} — in-memory fallback")

    if init_tracker:
        try:
            tracker = await init_tracker(REDIS_URL)
            await tracker.set_ready(agent_id)
            logger.info(f"[{agent_id}] Ready durumuna gecildi")
        except Exception as e:
            logger.warning(f"[{agent_id}] Tracker init hatasi: {e}")

    # Heartbeat + görev bekleme döngüsü
    # Gerçek implementasyonda burada ajan kendi kuyruğunu dinler
    # Şimdilik sadece Ready durumunda bekler ve periyodik heartbeat atar
    try:
        while True:
            # Her 30sn'de bir Ready heartbeat
            await asyncio.sleep(30)
            if tracker:
                try:
                    # Sadece Wait değilse Ready tut
                    current = tracker.get_status(agent_id)
                    if current and current.get("status") in ("Wait", "Ready"):
                        await tracker.set_ready(agent_id)
                        logger.debug(f"[{agent_id}] Heartbeat Ready")
                except Exception as e:
                    logger.debug(f"[{agent_id}] Heartbeat hatasi: {e}")

            # Backend'e de bildir (REST fallback)
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.post(
                        f"{BACKEND_URL}/api/agents/status/{agent_id}",
                        params={"status": "Ready"},
                        json={"worker": agent_id, "timestamp": datetime.now(timezone.utc).isoformat()},
                    )
                    response.raise_for_status()
            except Exception as exc:
                logger.warning(
                    "[%s] Backend durum bildirimi başarısız; worker devam ediyor: %s: %s",
                    agent_id, type(exc).__name__, exc,
                )

    except asyncio.CancelledError:
        logger.info(f"[{agent_id}] Worker durduruluyor")
        if tracker:
            try:
                await tracker.set_wait(agent_id)
            except Exception:
                logger.warning('Suppressed exception observed at agent_core/workers/agent_worker.py:85 (pass)')
        raise


def main():
    parser = argparse.ArgumentParser(description="Pineal Agent Worker")
    parser.add_argument("--agent-id", default=AGENT_ID, help="Agent ID (mirror_truth vb.)")
    parser.add_argument("--redis-url", default=REDIS_URL, help="Redis URL")
    args = parser.parse_args()

    agent_id = args.agent_id or AGENT_ID
    os.environ["AGENT_ID"] = agent_id

    logger.info(f"Agent Worker baslatiliyor: {agent_id} ({AGENT_NAME})")
    logger.info(f"Redis: {args.redis_url}")
    logger.info(f"Backend: {BACKEND_URL}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Graceful shutdown
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: loop.stop())
        except NotImplementedError:
            logger.warning('Suppressed exception observed at agent_core/workers/agent_worker.py:110 (pass)')

    try:
        loop.run_until_complete(run_worker(agent_id))
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt - kapaniyor")
    except RuntimeError as e:
        if "Event loop stopped" in str(e):
            logger.info("Event loop durduruldu - kapaniyor")
        else:
            raise
    finally:
        loop.close()


if __name__ == "__main__":
    main()
