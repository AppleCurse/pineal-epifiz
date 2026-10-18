"""Görev sahipliği UYGULAMA yardımcıları.

``backend/security/task_ownership.py`` yalnız KAYDI tutar (``task_id ->
principal``, SQLite). Bu modül o kaydın HANGİ uca nasıl uygulanacağını tek
yerde toplar; ``backend/api.py`` tek-modül tavanı
(``tests/unit/test_api_monolith_ratchet.py`` → ``MAX_LINES = 6000``) gövdeleri
şişirmeyi yasakladığı için kural burada: yeni mantık eklemek yerine MODÜL
ÇIKAR.

Kurallar (``backend/security/principal.py`` ile birebir aynı semantik):
  * ``principal is None`` -> kimlik doğrulama kapalı (development): mühür yok.
  * Kayıt yok -> İLK ERİŞEN SAHİPLENİR (bu sürümden önce üretilmiş kanıt
    kilitlenip dışarıda bırakılmaz).
  * Kayıt başka operatörde -> ret; gövde oda reddiyle AYNI (görevin varlığı
    doğrulanmaz).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Iterable, Optional

from backend.security.task_ownership import adopt, record_owner, task_access

logger = logging.getLogger(__name__)

__all__ = [
    "MAX_TASK_ID_LENGTH",
    "guard_task",
    "owner_for_room",
    "record_new_task",
    "visible_tasks",
]


def _task_id_ceiling() -> int:
    """``PINEAL_MAX_TASK_ID_LENGTH`` -> [8, 4096] aralığına kırpılır.

    Bozuk değer açılışı PATLATMAZ ve aralık dışına çıkamaz: bu sabit pydantic
    ``max_length`` alanında kullanıldığı için yanlış bir env değeri tüm
    API'yi kullanılamaz hale getirirdi.
    """
    raw = os.getenv("PINEAL_MAX_TASK_ID_LENGTH", "")
    try:
        value = int(raw.strip())
    except (TypeError, ValueError, AttributeError):
        value = 128
    return max(8, min(4_096, value))


#: Görev kimliği tavanı — TEK sözleşme. ``backend/api.py`` (pydantic alanları,
#: ``_terminate_mission``) ve ``backend/routes/tasks.py`` (DELETE ucu) aynı
#: değeri buradan okur.
MAX_TASK_ID_LENGTH = _task_id_ceiling()


def owner_for_room(room: Optional[dict], principal: Optional[str]) -> Optional[str]:
    """Oda mühründeki sahibi döndürür; mühür yoksa bağlı principal'ı.

    ``get_room`` odayı ``enforce_room_ownership`` ile mühürler ve ``_owner``
    yazar; o alan TEK gerçek kaynaktır. ``principal`` yedeği, ContextVar
    dışından çağrılan yollar (testler, iç çağrılar) içindir.
    """
    if room is None:
        return principal
    return room.get("_owner") or principal


def record_new_task(room: Optional[dict], task_id: str, principal: Optional[str]) -> None:
    """Yeni görevi, kanıt dosyası oluşmadan ÖNCE çağıran operatöre kaydeder.

    Sıra önemlidir: kayıt ile dosya arasındaki pencerede görev sahipsiz
    görünürse başka bir operatör sahiplenebilir.
    """
    record_owner(task_id, owner_for_room(room, principal))


def guard_task(room: Optional[dict], task_id: str, principal: Optional[str]) -> bool:
    """Görev bu operatörün mü? ``True`` -> serbest, ``False`` -> 403 üret.

    Yan ETKİ: sahipsiz görev çağıran adına sahiplenilir (geçiş semantiği).
    """
    return task_access(task_id, owner_for_room(room, principal)) != "forbidden"


def visible_tasks(
    entries: Iterable[dict],
    principal: Optional[str],
    *,
    task_id_of: Callable[[dict], Any] = lambda entry: entry.get("task_id"),
) -> list:
    """Görev listesini SAHİPLİĞE göre süzer.

    Kanıt deposu ``task_id`` ile anahtarlanmış DÜZ bir alandır ve
    ``PINEAL_MEMORY_PATH`` tüm odalarca paylaşılır: süzme olmasa her operatör
    diğerinin görev geçmişini görürdü (ölçüldü, ``GO_LIVE.md`` §4). Başka
    operatöre kayıtlı satır LİSTEYE HİÇ GİRMEZ — "bu görev var ama senin
    değil" bilgisi de sızmaz.
    """
    if principal is None:
        return list(entries)
    visible = []
    for entry in entries:
        task_id = str(task_id_of(entry) or "")
        if task_access(task_id, principal) == "forbidden":
            continue
        adopt(task_id, principal)  # kayıt yoksa sahiplen (idempotent)
        visible.append(entry)
    return visible
