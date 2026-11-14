"""Terminal görev retlerinin KALICI kaydı.

Neden ayrı modül (``tests/unit/test_api_monolith_ratchet.py``):
    ``backend/api.py`` tek-modül tavanına (5760 satır) dayandı; repo kuralı
    "yeni kod eklemek yerine MODÜL ÇIKAR". Bu yardımcı, ``backend/api.py``
    içine eklenmek yerine buraya taşındı ve ``api.py`` küçüldü.

Neden var (ölçülen kusur, 2026-11-11):
    ``/api/initiate`` bazı dallarda (platform desteklenmiyor, çapraz OSINT
    kapalı, kazıma altyapısı tükendi) ``broadcast_result_error`` çağırıp
    ``return`` ediyordu. O yardımcı yalnız WebSocket'e ve
    ``room["latest_result"]``'a yazıyordu; kanıt deposuna (görev geçmişi) HİÇ
    yazmıyordu. Sonuç, gerçek smoke'ta ölçüldü:

        POST /api/initiate  → 200 {"status":"started","task_id":...}
        GET  /api/tasks     → {"tasks": []}          # görev HİÇ yok
        GET  .../graph      → {"reason":"no_evidence"}  # "hiç çalışmadı" ile
                                                        # "çalıştı, kanıt yok"
                                                        # ayırt edilemiyor

    Operatör "başladı" sanıp bekliyordu. Ret artık depoya yazılır:
    ``memory_state="REJECTED"`` + terminal ``status`` + gerçek ``halted_reason``.

Sözleşme:
    - Bu kayıt KANIT DEĞİLDİR; ``agent_core.services.graph_builder`` onu
      graf düğümüne çevirmez (``type="terminal_reject"`` süzülür).
    - Yazım başarısız olursa sessizce yutulmaz: loglanır, görev yine de
      terminal duruma getirilir.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

__all__ = ["REJECT_EVIDENCE_TYPE", "build_reject_record", "record_terminal_reject"]

logger = logging.getLogger(__name__)

#: Depodaki operasyonel ret kaydının tipi (kanıt grafiğine GİRMEZ).
REJECT_EVIDENCE_TYPE = "terminal_reject"


def build_reject_record(status: str, message: str, task_id: str) -> dict:
    """Depoya yazılacak tek ret kaydı (saf fonksiyon, test edilebilir)."""
    return {
        "id": f"reject:{task_id}",
        "type": REJECT_EVIDENCE_TYPE,
        "value": str(message)[:500],
        "source": "api_initiate",
        "status": str(status),
        "verified": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _schedule(coro) -> None:
    """Coroutine'i çalıştır: koşan döngü varsa görev olarak, yoksa bloklayarak."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        loop.create_task(coro)
    else:  # pragma: no cover - yalnız senkron bağlamda (test/CLI)
        asyncio.run(coro)


def record_terminal_reject(
    memory: Any,
    task_id: Optional[str],
    status: str,
    message: str,
    *,
    logger_: Optional[Callable[..., None]] = None,
) -> bool:
    """Görev retini kanıt deposuna yaz. Yazıldıysa ``True``.

    ``memory`` çağıran tarafından enjekte edilir (``executor.memory``), böylece
    bu modül ``backend.api``'yi içe aktarmaz — dairesel bağımlılık yok ve
    yardımcı tek başına test edilebilir.
    """
    log = logger_ or logger.error
    if not task_id or memory is None:
        return False
    try:
        coro = memory.merge_evidence(
            task_id,
            [build_reject_record(status, message, task_id)],
            metadata={
                "status": str(status),
                "halted_reason": str(message)[:500],
                "memory_state": "REJECTED",
            },
        )
        _schedule(coro)
        return True
    except Exception:
        log(
            "TERMİNAL RET KAYDI YAZILAMADI (task_id=%s, status=%s)",
            task_id,
            status,
            exc_info=True,
        )
        return False
