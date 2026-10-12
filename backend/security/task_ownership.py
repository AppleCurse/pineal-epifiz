"""GÖREV SAHİPLİĞİ — kanıt deposu oda başına ayrışmıyordu; bu modül kapatır.

Problem (ölçüldü, ``GO_LIVE.md`` §4):
    Görev kayıtları ``CanonicalMemory(storage_path)`` altında YALNIZ ``task_id``
    ile anahtarlanmış düz bir dosya alanıdır
    (``agent_core/services/canonical_memory.py``: ``safe_child_path(storage_path,
    f"{task_id}.json")``) ve ``storage_path`` ``PINEAL_MEMORY_PATH``'ten gelir.
    Yani tüm odalar AYNI klasörü paylaşır ve kayıtta oda/operatör damgası yoktur.
    Oda mührü (``principal.enforce_room_ownership``) bu yüzden yalnız ODA ADI
    sınırını koruyordu: operatör B, KENDİ ``client_id``'siyle A'nın görevini
    listeleyebiliyor ve ``DELETE /api/tasks/{id}`` ile kanıt dosyasını diskten
    kalıcı silebiliyordu.

Çözüm: kalıcı ``task_id -> principal`` sahiplik kaydı.
    * Kayıt SQLite'ta tutulur (``PINEAL_TASK_OWNERS_DB``, varsayılan
      ``PINEAL_MEMORY_PATH/task_owners.db``): süreç yeniden başlayınca sahiplik
      KAYBOLMAZ — süreç içi sözlük bu işi görmezdi, çünkü silme kalıcıdır.
    * Semantik ``enforce_room_ownership`` ile BİREBİR aynıdır:
        - ``principal is None`` (kimlik doğrulama kapalı / development) -> mühür
          uygulanmaz, hiçbir şey yazılmaz, bugünkü davranış korunur.
        - Kayıt YOK (bu sürümden önce üretilmiş kanıt) -> İLK ERİŞEN SAHİP OLUR
          (adopt). Bilinçli: mevcut dağıtımlar kilitlenip dışarıda bırakılmaz.
        - Kayıt VAR ve sahibi FARKLI -> ``"forbidden"`` (çağıran 403 üretir).

Tek ``PINEAL_TOKEN`` paylaşan dağıtımda herkes aynı principal'dır; sahiplik
ayrıştırmaz. Operatörleri ayırt etmek için ``PINEAL_OPERATOR_TOKENS`` gerekir
(bkz. ``.env.example``).
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = [
    "TaskForbiddenError",
    "adopt",
    "db_path",
    "owner_of",
    "record_owner",
    "task_access",
]

#: Farklı bir operatöre kayıtlı göreve erişim denemesi.
#: ``RoomForbiddenError`` ile aynı gövde sözleşmesini paylaşır: yanıt görev
#: kimliğini DOĞRULAMAZ, çünkü başkasının görev adının VARLIĞI bile bilgidir.
FORBIDDEN = "forbidden"


class TaskForbiddenError(RuntimeError):
    """Başka bir operatöre kayıtlı göreve erişim denemesi."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__("ROOM_FORBIDDEN")


def db_path() -> str:
    """Sahiplik veritabanının yolu (env ile taşınabilir; testler izole eder)."""
    explicit = os.getenv("PINEAL_TASK_OWNERS_DB", "").strip()
    if explicit:
        return explicit
    memory_root = os.getenv("PINEAL_MEMORY_PATH", "./memory/")
    return os.path.join(memory_root, "task_owners.db")


_lock = threading.Lock()


def _connect() -> Optional[sqlite3.Connection]:
    """Bağlantı açar; açılamıyorsa ``None`` (çağıran fail-OPEN davranır).

    Fail-open bilinçli ve DARdır: sahiplik kaydı OKUNAMADIĞINDA görev
    erişilebilir kalır (bugünkü davranış), çünkü kaydın kendisi kanıt DEĞİLDİR.
    Yazılamadığında ise sahiplik kaydedilemez ve görev sahipsiz kalır — bu
    durumda bir sonraki erişen sahiplenir; yanlışlıkla başka operatöre
    KİLİTLENMEZ.
    """
    path = db_path()
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        connection = sqlite3.connect(path, timeout=5.0)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS task_owners ("
            " task_id TEXT PRIMARY KEY,"
            " principal TEXT NOT NULL,"
            " created_at REAL NOT NULL DEFAULT (strftime('%s','now')))"
        )
        connection.commit()
        return connection
    except (OSError, sqlite3.Error) as exc:  # pragma: no cover - FS hatası
        logger.warning("TASK_OWNERS_DB_UNAVAILABLE: %s", str(exc)[:160])
        return None


def owner_of(task_id: str) -> Optional[str]:
    """Görevin kayıtlı sahibi; kayıt yoksa/okunamadıysa ``None``."""
    if not task_id:
        return None
    connection = _connect()
    if connection is None:
        return None
    try:
        row = connection.execute(
            "SELECT principal FROM task_owners WHERE task_id = ?", (task_id,)
        ).fetchone()
        return row[0] if row else None
    except sqlite3.Error as exc:  # pragma: no cover - bozuk DB
        logger.warning("TASK_OWNER_READ_FAILED: %s", str(exc)[:160])
        return None
    finally:
        connection.close()


def record_owner(task_id: str, principal: Optional[str]) -> None:
    """Görevi bir operatöre kaydeder (INSERT OR IGNORE: ilk sahip kazanır).

    ``principal is None`` -> hiçbir şey yazılmaz (development; kimlik yoksa
    sahiplik de yoktur). Sessizdir: görev oluşturmayı ASLA engellemez.
    """
    if not task_id or not principal:
        return
    connection = _connect()
    if connection is None:
        return
    try:
        with _lock:
            connection.execute(
                "INSERT OR IGNORE INTO task_owners (task_id, principal) VALUES (?, ?)",
                (task_id, principal),
            )
            connection.commit()
    except sqlite3.Error as exc:  # pragma: no cover - bozuk DB
        logger.warning("TASK_OWNER_WRITE_FAILED: %s", str(exc)[:160])
    finally:
        connection.close()


def adopt(task_id: str, principal: Optional[str]) -> None:
    """Sahipsiz görevi çağıran adına sahiplenir (eski kanıt için geçiş yolu)."""
    record_owner(task_id, principal)


def task_access(task_id: str, principal: Optional[str]) -> Optional[str]:
    """Görev erişim kararı — oda mührünün görev düzeyindeki karşılığı.

    Dönüş:
      * ``None``        -> erişim SERBEST (kayıt yazıldı/taşındı ya da kimlik
                           doğrulama kapalı).
      * ``"forbidden"`` -> görev BAŞKA bir operatöre kayıtlı; çağıran 403
                           (``TaskForbiddenError``) üretmelidir.
    """
    if principal is None:
        return None
    existing = owner_of(task_id)
    if existing is None:
        record_owner(task_id, principal)
        return None
    if existing != principal:
        logger.warning(
            "TASK_FORBIDDEN: principal=%s başka bir operatöre kayıtlı göreve "
            "erişmeye çalıştı (task_id uzunluğu=%d)",
            principal,
            len(task_id or ""),
        )
        return FORBIDDEN
    return None
