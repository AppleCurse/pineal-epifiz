"""Görev geçmişi uç noktaları — ``GET /api/tasks`` ve ``DELETE /api/tasks/{id}``.

Bu modül ``backend/api.py`` tek-modül tavanı yüzünden AYRILDI
(``tests/unit/test_api_monolith_ratchet.py`` → ``MAX_LINES = 6000``; kural:
yeni uç nokta eklemek yerine MODÜL ÇIKAR). Rotalar ``backend/api.py`` içinde
``app.get(...)(...)`` / ``app.delete(...)(...)`` ile KAYDEDİLİR — böylece
``/`` statik mount'undan ÖNCE sıralanırlar.

Neden süzme var (ölçüldü, ``GO_LIVE.md`` §4):
    Kanıt deposu ``task_id`` ile anahtarlanmış DÜZ bir dosya alanıdır
    (``agent_core/services/canonical_memory.py``) ve ``PINEAL_MEMORY_PATH``
    TÜM odalarca paylaşılır. Süzme olmadan her operatör diğerinin görev
    geçmişini görüyordu. Kural oda mührüyle aynıdır: kayıt yoksa çağıran
    SAHİPLENİR, başka operatöre kayıtlıysa satır LİSTEYE HİÇ GİRMEZ — yani
    "bu görev var ama senin değil" bilgisi de sızmaz.

Bağımlılıklar ENJEKTE edilir: bu modül ``backend.api``'yi içe aktarmaz,
dolayısıyla dairesel bağımlılık yoktur ve tek başına test edilebilir.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Callable, Optional

from fastapi.responses import JSONResponse

from agent_core.utils.security import (
    redact_text,
    safe_child_path,
    validate_identifier,
)
from backend.security.task_access import (
    MAX_TASK_ID_LENGTH,
    guard_task,
    owner_for_room,
    visible_tasks,
)
from backend.security.task_ownership import TaskForbiddenError


__all__ = [
    "MAX_TASK_ID_LENGTH",
    "delete_task",
    "list_visible_tasks",
    "read_tasks_sync",
    "visible_tasks_sync",
]


def read_tasks_sync(storage: str):
    """Kanıt deposundaki görev dosyalarını özetler (senkron; disk I/O).

    Bozuk kayıt GİZLENMEZ: ``MEMORY_CORRUPTED`` olarak görünür kalır, çünkü
    retention/operasyon arayüzlerinde "yokmuş gibi" göstermek dürüst değildir.
    """
    tasks = []
    if os.path.isdir(storage):
        for fn in sorted(os.listdir(storage)):
            if not fn.endswith(".json") or fn == "learnings.json":
                continue
            task_id = fn[:-5]
            try:
                path = safe_child_path(storage, fn)
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict) or not isinstance(data.get("evidence", []), list):
                    raise ValueError("invalid canonical memory schema")
                tasks.append({
                    "task_id": data.get("task_id", task_id),
                    "last_updated": data.get("last_updated"),
                    "evidence_count": len(data.get("evidence", [])),
                    "confidence": data.get("confidence"),
                    "memory_state": "READY",
                    "memory_error_code": None,
                })
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                # A malformed task remains visible and is never represented as
                # an absent task in retention/operations APIs.
                tasks.append({
                    "task_id": task_id,
                    "last_updated": None,
                    "evidence_count": None,
                    "confidence": None,
                    "memory_state": "CORRUPTED",
                    "memory_error_code": "MEMORY_CORRUPTED",
                })
    return tasks


def visible_tasks_sync(storage: str, principal: Optional[str]):
    """Oku + sahipliğe göre süz (tek thread'de: SQLite bağlantısı thread'e bağlı)."""
    return visible_tasks(read_tasks_sync(storage), principal)


def list_visible_tasks(
    *,
    get_room: Callable[[str], dict],
    principal_getter: Callable[[], Optional[str]] = lambda: None,
):
    """Uç nokta fabrikası: ``GET /api/tasks`` handler'ını üretir."""

    async def api_list_tasks(client_id: str):
        room = get_room(client_id)
        storage = room["executor"].memory.storage_path
        tasks = await asyncio.to_thread(
            visible_tasks_sync, storage, owner_for_room(room, principal_getter())
        )
        active = list(room.get("active_tasks", {}).keys())
        return {"tasks": tasks, "active_tasks": active}

    return api_list_tasks


def delete_task(
    *,
    get_room: Callable[[str], dict],
    broadcast_log: Callable[[str, str, str], None],
):
    """Uç nokta fabrikası: ``DELETE /api/tasks/{task_id}`` handler'ını üretir.

    Silme KALICIDIR (adli kanıt diskten gider), dolayısıyla oda mührü tek
    başına yetmez: depo paylaşıldığı için başka operatörün ``task_id``'si
    buradan silinebiliyordu (ölçülen PoC: ``200 memory_file_deleted:true``,
    dosya diskten gitti). Ret gövdesi oda reddiyle BİREBİR aynıdır — görevin
    varlığı doğrulanmaz.
    """

    async def api_delete_task(task_id: str, client_id: str):
        """Bir görevin tüm izlerini kalıcı siler (bellek dosyası + snapshot)."""
        room = get_room(client_id)
        try:
            # [AUDIT R3] regex + uzunluk (client_id ile aynı sözleşme).
            if len(task_id) > MAX_TASK_ID_LENGTH:
                raise ValueError
            validate_identifier(task_id, field="task_id")
            mem_path = safe_child_path(
                room["executor"].memory.storage_path,
                f"{task_id}.json",
            )
        except ValueError:
            return JSONResponse(
                {"error": {"code": "INVALID_TASK_ID", "message": "Invalid task identifier"}},
                status_code=400,
            )
        # GÖREV SAHİPLİĞİ: kanıt yok etme çapraz operatör çalışmasın.
        if not guard_task(room, task_id, None):
            raise TaskForbiddenError(task_id)
        removed_snapshot = room.get("active_tasks", {}).pop(task_id, None)
        file_deleted = False
        if os.path.exists(mem_path):
            try:
                os.remove(mem_path)
                file_deleted = True
            except OSError as exc:
                return JSONResponse(
                    {"error": {"code": "DELETE_FAILED", "message": redact_text(exc)[:120]}},
                    status_code=500,
                )

        if not removed_snapshot and not file_deleted:
            return JSONResponse(
                {"error": {"code": "NOT_FOUND", "message": f"Görev bulunamadı: {task_id}"}},
                status_code=404,
            )

        broadcast_log(
            client_id,
            "INFO",
            f"VERİ SİLME: '{task_id}' görev izleri kalıcı olarak silindi (retention).",
        )
        return {
            "status": "deleted",
            "task_id": task_id,
            "snapshot_removed": removed_snapshot is not None,
            "memory_file_deleted": file_deleted,
        }

    return api_delete_task
