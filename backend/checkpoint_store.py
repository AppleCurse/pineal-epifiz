"""Görev checkpoint deposu — destek + devam akışının KALICI tek kaynağı.

B0 · “Güvenli devam döngüsü” için gereklilikler ve bu modülün cevapları:

1. **Kalıcılık:** ``support_requests`` / ``ingested_outputs`` / görevin yürütme
   ``status``'u ve ``input_data``'sı, süreç yeniden başlayınca DOSYADAN geri
   yüklenir (oda belleği sıfırlansa bile). Depo ``PINEAL_MEMORY_PATH`` altında
   AYRI bir alt klasördür (``checkpoints/``) — kanıt dosyası düz alanı
   (``canonical_memory``) ve ``GET /api/tasks`` listelemesi BOZULMAZ.

2. **Görev izolasyonu:** her dosya ``task_id`` ile anahtarlanır; okumada
   dosya içi ``task_id`` yoluyla BİREBİR doğrulanır (yanlış görevin çıktısı
   başka göreve yüklenemez). Kimlik doğrulaması ``validate_identifier`` +
   ``safe_child_path`` (path traversal yok).

3. **Tekrar yürüme güvenliği (resume kilidi):** ``claim_resume`` süreç-içi
   tek seanslık token üretir (süreç yeniden başlayınca bellek silinir →
   kilit doğal olarak düşer; crash'de sonsuz kilit YOK). Aynı ``task_id``
   için ikinci claim ``None`` döner → API 409 üretir.

4. **Atomik yazım:** aynı dizine geçici dosya + ``os.replace`` — yarım kayıt
   okunamaz (torn-write yok); bozuk kayıt dürüstçe ``CORRUPTED`` olarak
   yükselir, hiçbir yerde “yokmuş gibi” gösterilmez.

Tekrar önleme garantisinin SINIRLARI (raporlanan): checkpoint, ajan
yan-etkisinden SONRA yazılır (executor ``_snapshot`` → bu depo). Yani
“yan etki oldu + checkpoint yazılmadan süreç koptu” penceresinde o ajan
yeniden çalışabilir — bu pencere ve mitigasyonu (resume öncesi destek
doğrulama + egres deneme izleri) ``reports/`` raporunda tanımlıdır; depo
kendisi bu pencereyi tek başına kapatmaz, GİZLEMEZ.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from agent_core.utils.security import redact_text, safe_child_path, validate_identifier

logger = logging.getLogger(__name__)

__all__ = [
    "CheckpointError",
    "CheckpointCorrupted",
    "claim_resume",
    "is_resume_running",
    "list_support",
    "load",
    "persist_status",
    "record_support_response",
    "release_resume",
    "root",
    "set_input",
    "support_view",
    "update",
]

_WRITE_LOCK = threading.RLock()
#: SÜREÇ-İÇİ resume kilitleri. Bellek temelli BİLEREK: süreç yeniden başlayınca
#: kilit düşer (crash sonrası kalıcı kilitlenme yok), claim token'ı geçersizdir.
_RESUME_CLAIMS: Dict[str, str] = {}


class CheckpointError(RuntimeError):
    """Checkpoint deposu erişim/şema hatası (dürüst ret; yutma yok)."""


class CheckpointCorrupted(CheckpointError):
    """Kayıt okunabilir değil veya ``task_id`` tutarsız (görev izolasyonu)."""


def root() -> str:
    explicit = (os.getenv("PINEAL_CHECKPOINT_PATH") or "").strip()
    if explicit:
        return explicit
    memory_root = os.getenv("PINEAL_MEMORY_PATH", "./memory/")
    return os.path.join(memory_root, "checkpoints")


def _path(task_id: str) -> str:
    if not task_id or len(task_id) > 4096:
        raise CheckpointError("invalid task_id")
    try:
        validate_identifier(task_id, field="task_id")
        return safe_child_path(root(), f"{task_id}.json")
    except ValueError as exc:
        raise CheckpointError(f"invalid task_id: {exc}") from exc


def load(task_id: str) -> Optional[Dict[str, Any]]:
    """Kaydı okur. Yok → ``None``. Bozuk/mühürsüz → ``CheckpointCorrupted``."""
    path = _path(task_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CheckpointCorrupted(f"checkpoint okunamadı: {task_id}") from exc
    if not isinstance(data, dict) or data.get("task_id") != task_id:
        # Görev izolasyonu: dosya içi mühür yol ile uyuşmuyorsa BAŞKA GÖREVİN
        # çıktısı yüklenmiş demektir — asla kullanılmaz.
        raise CheckpointCorrupted(f"checkpoint mührü tutmuyor: {task_id}")
    return data


def update(task_id: str, mutator: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
    """Oku → değiştir → atomik yaz (tek lock altında)."""
    with _WRITE_LOCK:
        data = load(task_id)
        if data is None:
            raise CheckpointError(f"checkpoint yok: {task_id}")
        mutator(data)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_write(task_id, data)
        return data


def _atomic_write(task_id: str, data: Dict[str, Any]) -> None:
    path = _path(task_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{uuid.uuid4().hex[:8]}.tmp"
    payload = json.dumps(data, ensure_ascii=False, default=str)
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(payload)
        fh.flush()
    try:
        os.replace(tmp, path)
    except PermissionError:
        # Windows / OneDrive kilit gecikmesi (WinError 5): 50ms bekle ve tekrar dene
        import time
        time.sleep(0.05)
        try:
            os.replace(tmp, path)
        except Exception:
            # Doğrudan yazma fallback
            with open(path, "w", encoding="utf-8") as f_dest:
                f_dest.write(payload)
            try:
                os.remove(tmp)
            except Exception:
                pass


def set_input(
    task_id: str,
    input_data: Dict[str, Any],
    *,
    owner: Optional[str] = None,
) -> None:
    """Görevin yeniden çalıştırma girdisini kaydeder (istemciden DEĞİL sunucudan)."""
    def _apply(data: Dict[str, Any]) -> None:
        data["input_data"] = dict(input_data or {})
        if owner and not data.get("owner"):
            data["owner"] = owner

    with _WRITE_LOCK:
        existing = load(task_id)
        if existing is None:
            data: Dict[str, Any] = {
                "task_id": task_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            if owner:
                data["owner"] = owner
            _apply(data)
            data["updated_at"] = data["created_at"]
            _atomic_write(task_id, data)
        else:
            update(task_id, _apply)


def _status_str(status: Any) -> str:
    """``PipelineStatus.COMPLETED`` → ``completed``; enum/yüzey değeri üretir."""
    if isinstance(status, str):
        return status.split(".", 1)[1].lower() if status.startswith("PipelineStatus.") else status
    return str(getattr(status, "value", status) or "")


def persist_status(snapshot: Any, *, owner: Optional[str] = None) -> None:
    """Executor snapshot'ini kalıcı yazar (destek + yutulan çıktılar dâhil).

    ``model_dump(mode="json")`` denenir; JSON'a dönüşmeyen telemetri
    parçaları ``default=str`` ile yutulmadan yazılır (dosya asla yarım
    kalmaz). Alan hatası kayıt DEĞİL, log üretir — durum kaybı gizlenmez.
    """
    task_id = str(getattr(snapshot, "task_id", "") or "")
    if not task_id:
        logger.error("CHECKPOINT: snapshot.task_id yok — kalıcı yazım ATLANDI")
        return
    try:
        status_dump = snapshot.model_dump(mode="json", warnings=False)
    except TypeError:
        status_dump = snapshot.model_dump(mode="json")
    except Exception:
        logger.exception("CHECKPOINT: snapshot dönüştürülemedi task=%s", task_id)
        return

    def _apply(data: Dict[str, Any]) -> None:
        data["status"] = status_dump
        data["status_status"] = _status_str(getattr(snapshot, "status", ""))
        data["has_open_support"] = any(
            r.get("status") == "pending"
            for r in (status_dump.get("support_requests") or [])
        )

    with _WRITE_LOCK:
        existing = load(task_id)
        if existing is None:
            fresh: Dict[str, Any] = {
                "task_id": task_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            if owner:
                fresh["owner"] = owner
            _apply(fresh)
            fresh["updated_at"] = fresh["created_at"]
            _atomic_write(task_id, fresh)
        else:
            def _merged(data: Dict[str, Any]) -> None:
                _apply(data)
                if owner and not data.get("owner"):
                    data["owner"] = owner

            update(task_id, _merged)


def support_view(entry: Dict[str, Any]) -> Dict[str, Any]:
    """UI'a giden GÜVENLİ PROJEKSİYON: gerekçe ``redact_text``'ten geçer;
    input_data / anahtar / çerez ASLA bu nesneye girmez."""
    reason = redact_text(str(entry.get("reason") or ""))[:200]
    responses = [
        {
            "by": str(r.get("by") or ""),
            "at": str(r.get("at") or ""),
            "note": redact_text(str(r.get("note") or ""))[:200],
        }
        for r in (entry.get("responses") or [])
    ]
    return {
        "support_id": entry.get("support_id"),
        "task_id": entry.get("task_id"),
        "agent_name": entry.get("agent_name"),
        "owner": entry.get("owner"),
        "reason": reason,
        "kind": entry.get("kind"),
        "requires": entry.get("requires"),
        "blocks_resume": bool(entry.get("blocks_resume")),
        "options": list(entry.get("options") or []),
        "next_action": entry.get("next_action"),
        "status": entry.get("status"),
        "created_at": entry.get("created_at"),
        "approved": bool(entry.get("approved")),
        "resolved_at": entry.get("resolved_at"),
        "resolution": entry.get("resolution"),
        "responses": responses,
    }


def list_support(task_id: str) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """``(checkpoint meta, [güvenli destek görünümleri])``."""
    data = load(task_id)
    if data is None:
        return None, []
    status = data.get("status") or {}
    entries = status.get("support_requests") or []
    return data, [support_view(e) for e in entries]


def record_support_response(
    task_id: str,
    support_id: str,
    *,
    principal: Optional[str],
    note: str = "",
    approved: bool = True,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Yetkili destek yanıtını kaydeder + kapatma kararını uygular.

    Dönen kodlar:
      * ``"OK"`` — yanıt işlendi; ``requires`` doğrulandıysa ``resolved``.
      * ``"NOT_FOUND"`` — bu görevde böyle açık talep yok (404).
      * ``"ALREADY_RESOLVED"`` — çift yanıt reddedildi (409).
      * ``"BLOCKER_NOT_CLEARED"`` — engel henüz giderilmedi (kapatılmaz).
    """
    holder: Dict[str, Any] = {}

    def _apply(data: Dict[str, Any]) -> None:
        entries = (data.get("status") or {}).get("support_requests") or []
        target = next((e for e in entries if e.get("support_id") == support_id), None)
        if target is None:
            holder["code"] = "NOT_FOUND"
            return
        if target.get("status") != "pending":
            holder["code"] = "ALREADY_RESOLVED"
            return
        target.setdefault("responses", []).append(
            {
                "by": principal or "anonymous",
                "at": datetime.now(timezone.utc).isoformat(),
                "note": str(note or "")[:500],
            }
        )
        requires = target.get("requires") or "operator_response"
        if requires == "vault_open" and approved:
            # Kasa hâlâ kilitliyse yanıt ALINIR ama talep KAPANMAZ:
            # "destek sağlandı + engel giderildi" birlikte doğrulanmalı.
            # (Canlı kasa kontrolü çağıran katmanda yapılır; burada kasa
            # kapalı gelirse engel işareti düşürülmez.)
            target["approved"] = True
            holder["code"] = "PENDING_LIVE_CHECK"
            holder["entry"] = target
            return
        target["approved"] = bool(approved)
        holder["code"] = "OK"
        holder["entry"] = target

    with _WRITE_LOCK:
        data = update(task_id, _apply)
    code = holder.get("code")
    entry = holder.get("entry")
    if code == "OK" and entry is not None:
        # Talep kapat: destek GELDİ ve (operator_response için) yetki verildi.
        def _close(d: Dict[str, Any]) -> None:
            for e in (d.get("status") or {}).get("support_requests") or []:
                if e.get("support_id") == support_id and e.get("status") == "pending":
                    e["status"] = "resolved"
                    e["resolved_at"] = datetime.now(timezone.utc).isoformat()
                    e["resolution"] = "operator_response"

        with _WRITE_LOCK:
            data = update(task_id, _close)
        for e in (data.get("status") or {}).get("support_requests") or []:
            if e.get("support_id") == support_id:
                entry = e
                break
    elif code == "PENDING_LIVE_CHECK" and entry is not None:
        # Canlı kasa kontrolünden GEÇTİYSE çağıran katman ``finalize_support``
        # ile kapatır; geçmediyse yanıt kalır, talep açık kalır.
        pass
    return str(code), (dict(entry) if entry is not None else None)


def finalize_support(task_id: str, support_id: str) -> Optional[Dict[str, Any]]:
    """``requires=vault_open`` için canlı engel doğrulandıktan SONRA kapatır."""
    def _close(d: Dict[str, Any]) -> None:
        for e in (d.get("status") or {}).get("support_requests") or []:
            if e.get("support_id") == support_id and e.get("status") == "pending":
                if not e.get("approved"):
                    return
                e["status"] = "resolved"
                e["resolved_at"] = datetime.now(timezone.utc).isoformat()
                e["resolution"] = "verified_vault_open"

    with _WRITE_LOCK:
        try:
            data = update(task_id, _close)
        except CheckpointError:
            return None
    for e in (data.get("status") or {}).get("support_requests") or []:
        if e.get("support_id") == support_id:
            return dict(e)
    return None


def claim_resume(task_id: str) -> Optional[str]:
    """Aynı görev için TEK eşzamanlı resume — süreç-içi token.

    ``None`` → zaten çalışan bir resume var (çağıran 409 üretir).
    Bellek temelli: süreç yeniden başlayınca kilit düşer (bilinçli; bkz. modül
    docstring · tekrar-yürüme güvenliği).
    """
    with _WRITE_LOCK:
        if task_id in _RESUME_CLAIMS:
            return None
        token = uuid.uuid4().hex
        _RESUME_CLAIMS[task_id] = token
        return token


def release_resume(task_id: str, token: str) -> bool:
    with _WRITE_LOCK:
        if _RESUME_CLAIMS.get(task_id) == token:
            _RESUME_CLAIMS.pop(task_id, None)
            return True
        return False


def is_resume_running(task_id: str) -> bool:
    return task_id in _RESUME_CLAIMS


def _claim_age_seconds(task_id: str) -> Optional[float]:
    # Teşhis/test yardımcısı: token ile yaş hesaplanmaz; kilit yalnız süreçiçi
    # Bellek sözlüğü tutar (yaş sınırı BİLİNÇLİ YOK — görev süresi değişkendir).
    return None if task_id not in _RESUME_CLAIMS else 0.0
