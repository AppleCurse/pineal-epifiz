"""
Komutan & Ajan Konseyi Modülü — POST /api/commander/dispatch & POST /api/commander/inject

[2026-10-25] Neden var?
    Kullanıcının kokpit üzerinden:
    1. Bütün ajanlarla (Aspasia, Lilith ve 12 saha ajanı) doğrudan muhatap olabilmesi,
       istediği ajana istediği an görev verebilmesi,
    2. Ajanların düşünme ve muhakeme aşamalarını canlı izleyebilmesi,
    3. Kazı esnasında kendi bulduğu ikiz/benzer hesap veya ek kanıtları
       ('İşte bu da onun') sisteme esnek ve limitsiz yönetici yetkisiyle enjekte edebilmesi.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from contextlib import contextmanager
import os
import tempfile
import threading
from datetime import datetime
from typing import Any, Callable, Dict, Optional
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
_WINDOWS_LOCKS = {}
_WINDOWS_LOCKS_GUARD = threading.Lock()

__all__ = ["CommanderDispatchPayload", "CommanderInjectPayload", "CommanderPhoneProbePayload", "register_commander_routes"]


class CommanderDispatchPayload(BaseModel):
    client_id: str = Field(default="default")
    agent_id: str = Field(..., description="aspasia | lilith | depth_analyst | osint_investigator | vb.")
    instruction: str = Field(..., description="Ajana verilecek özel emir veya soru")
    target_url: Optional[str] = Field(default="")
    twin_url: Optional[str] = Field(default="")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict)


class CommanderInjectPayload(BaseModel):
    client_id: str = Field(default="default")
    evidence_type: str = Field(..., description="twin_url | bio_fact | ground_truth | note | phone")
    evidence_value: str = Field(..., description="Kullanıcının sağladığı gerçek kanıt değeri")
    target_agent: Optional[str] = Field(default="all")
    note: Optional[str] = Field(default="")


class CommanderPhoneProbePayload(BaseModel):
    client_id: str = Field(default="default")
    phone: str = Field(..., description="Telefon numarası (örn: (552) 956-87-63, 0552..., +90...)")
    auto_bridge_social: bool = Field(default=False, description="Eğer kullanıcı adı bulunursa sosyal medya yoklamasını tetikle")


@contextmanager
def locked_learnings(path: str):
    """Advisory cross-process lock; all writers must use the same shared path."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lock_path = os.path.join(os.path.dirname(path), ".learnings.lock")
    if os.name == "nt":
        import msvcrt
        with _WINDOWS_LOCKS_GUARD:
            process_lock = _WINDOWS_LOCKS.setdefault(os.path.abspath(lock_path), threading.RLock())
        with process_lock:
            with open(lock_path, "a+b") as lock:
                lock.seek(0)
                if not lock.read(1):
                    lock.seek(0)
                    lock.write(b"0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl
    with open(lock_path, "a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


class EvidenceIdempotencyConflict(ValueError):
    """An idempotency key is already bound to another request."""


def _store_evidence(entry: dict, key: str) -> None:
    mem_path = os.path.join(".pineal_memory", "learnings.json")
    with locked_learnings(mem_path):
        existing = []
        if os.path.exists(mem_path):
            with open(mem_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if not isinstance(existing, list):
                raise ValueError("invalid evidence store")
        if key:
            key_hash = hashlib.sha256(key.encode()).hexdigest()
            signature = hashlib.sha256(json.dumps(
                [entry["fact"], entry["tag"], entry["target_agent"], entry["note"]],
                ensure_ascii=False, separators=(",", ":"),
            ).encode()).hexdigest()
            for old in existing:
                if isinstance(old, dict) and old.get("idempotency_key_hash") == key_hash:
                    if old.get("idempotency_signature") != signature:
                        raise EvidenceIdempotencyConflict("idempotency key conflict")
                    # A previous attempt may have failed after rename but before
                    # directory sync; re-sync before acknowledging the retry.
                    with open(mem_path, "rb") as current:
                        os.fsync(current.fileno())
                    if os.name != "nt":
                        directory_fd = os.open(os.path.dirname(mem_path), os.O_RDONLY)
                        try: os.fsync(directory_fd)
                        finally: os.close(directory_fd)
                    return
            entry["idempotency_key_hash"] = key_hash
            entry["idempotency_signature"] = signature
        existing.append(entry)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=os.path.dirname(mem_path), delete=False
            ) as f:
                tmp_path = f.name
                json.dump(existing, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, mem_path)
            if os.name != "nt":
                directory_fd = os.open(os.path.dirname(mem_path), os.O_RDONLY)
                try: os.fsync(directory_fd)
                finally: os.close(directory_fd)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)


def register_commander_routes(
    app: Any,
    *,
    rate_limit: Callable[[str, str], bool],
    rate_identity: Callable[[Request], str],
    gateway_provider: Callable[[], Any],
    get_executor: Optional[Callable[[str], Any]] = None,
    require_vault_open: Optional[Callable[[str], Any]] = None,
    require_minor_clearance: Optional[Callable[..., Any]] = None,
) -> None:
    @app.post("/api/commander/dispatch")
    async def dispatch_agent_task(payload: CommanderDispatchPayload, request: Request):
        """Do not claim a direct agent run until it is wired to the executor.

        Use /api/aspasia/command or /api/initiate for the actual lifecycle-backed
        mission. In particular, a supplied twin URL is not identity evidence.
        """
        return JSONResponse(
            {"status": "unavailable", "error": {
                "code": "DIRECT_AGENT_DISPATCH_UNAVAILABLE",
                "message": "Doğrudan ajan yürütmesi bağlı değil; görev için Aspasia komutunu veya görev başlatmayı kullanın.",
            }},
            status_code=503,
        )

    @app.post("/api/commander/inject")
    async def inject_commander_evidence(payload: CommanderInjectPayload, request: Request):
        """Operatörün bulduğu ikiz hesap veya ek kanıtı doğrudan sisteme mühürler."""
        ev_type = payload.evidence_type.strip()
        val = payload.evidence_value.strip()
        target_agent = payload.target_agent or "all"
        note = payload.note or ""

        if not val:
            return JSONResponse({"error": {"message": "Kanıt değeri boş olamaz."}}, status_code=400)

        key = request.headers.get("Idempotency-Key", "")
        if key and not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key):
            return JSONResponse({"error": {"code": "INVALID_IDEMPOTENCY_KEY"}}, status_code=400)
        entry = {
            "fact": f"[KOMUTAN KANITI / {ev_type.upper()}] {val}",
            "tag": f"commander_{ev_type}",
            "target_agent": target_agent,
            "note": note,
            "ts": datetime.now().isoformat(),
            "hash": hashlib.sha256(val.encode()).hexdigest()[:12],
        }
        try:
            await asyncio.to_thread(_store_evidence, entry, key)
        except EvidenceIdempotencyConflict:
            return JSONResponse({"error": {"code": "IDEMPOTENCY_CONFLICT"}}, status_code=409)
        except (OSError, ValueError, TypeError, ImportError) as e:
            logger.warning("Komutan kanıtı kaydedilemedi: %s", type(e).__name__)
            return JSONResponse(
                {"status": "error", "error": {"code": "EVIDENCE_STORE_FAILED",
                 "message": "Kanıt kaydedilemedi; ajana aktarılmadı."}}, status_code=500
            )

        return {
            "status": "stored",
            "applied_to_agent": False,
            "evidence_type": ev_type,
            "evidence_value": val,
            "target_agent": target_agent,
            "message": "Kanıt dosyaya kaydedildi; ajana veya göreve aktarım henüz bağlı değil.",
            "ts": datetime.now().isoformat(),
        }

    @app.post("/api/commander/phone-probe")
    async def probe_phone_endpoint(payload: CommanderPhoneProbePayload, request: Request):
        """Telefon numarası üzerinde format, şebeke, mesajlaşma ve açık web ayak izi yoklaması yapar."""
        if require_minor_clearance is None:
            return JSONResponse({"error": {"message": "Çocuk koruma kontrolü kullanılamıyor."}}, status_code=423)
        if (blocked := require_minor_clearance(payload.client_id, subject=payload.phone)) is not None:
            return blocked
        if require_vault_open is None:
            return JSONResponse({"error": {"message": "Kasa kontrolü kullanılamıyor."}}, status_code=423)
        if (locked := require_vault_open(payload.client_id)) is not None:
            return locked
        raw_phone = payload.phone.strip()
        if not raw_phone:
            return JSONResponse({"error": {"message": "Telefon numarası boş olamaz."}}, status_code=400)

        from agent_core.capabilities import CapabilityContext, bootstrap, run_capability
        from agent_core.capabilities.state import policy_state

        try:
            bootstrap()
            result = await run_capability(
                "sensor.identity.phone_probe",
                CapabilityContext(subject=raw_phone, params={"auto_bridge": payload.auto_bridge_social}),
                # Both request-level safety gates have already succeeded above.
                state=policy_state(vault_locked=False),
            )
            if not result.available or result.error or result.payload is None:
                return JSONResponse({"error": {"message": "Telefon yoklaması kullanılamıyor.",
                                               "reason": result.unavailable_reason or result.error}}, status_code=503)
            return result.payload.model_dump()
        except Exception as e:
            logger.error("Phone probe error: %s", type(e).__name__)
            return JSONResponse({"error": {"message": "Telefon yoklaması başarısız."}}, status_code=500)

