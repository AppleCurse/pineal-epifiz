"""Destek & güvenli devam (resume) uçları — ``backend/routes`` fabrika düzeni.

Bu modül ``backend/api.py`` monolit tavanı yüzünden AYRILDI
(``tests/unit/test_api_monolith_ratchet.py`` → ``MAX_LINES = 6000``; kural:
yeni uç nokta eklemek yerine MODÜL ÇIKAR). Rotalar ``register_support_routes``
ile ``app``'e KAYDEDİLİR (``backend/api.py``, statik mount'tan ÖNCE çağırır);
bağımlılıklar ENJEKTE edilir — modül ``backend.api``'yi içe aktarmaz.

Uçlar:
  * ``GET  /api/tasks/{task_id}/support``     → açık destek talepleri
    (görev, talep kimliği, engel, ihtiyaç, sonraki adım; hassas alan YOK).
  * ``POST /api/tasks/{task_id}/support/{sid}`` → yetkili destek yanıtı
    (çift yanıt 409; engel canlı doğrulanmadan talep KAPANMAZ).
  * ``POST /api/tasks/{task_id}/resume``      → GÜVENLİ DEVAM:
    istemciden TaskStatus/completed listesi KABUL EDİLMEZ; snapshot +
    input + destek kayıtları sunucunun kalıcı checkpoint'inden yüklenir;
    kimlik/oda sahipliği (guard_task), kasa (423), bütçe (409), açık destek
    önkoşulları ve eşzamanlı-resume kilidi (409) sırayla zorlanır.

Görev sahipliği ``backend.security.task_access.guard_task`` ile BİREBİR
aynı mühürden geçer (403 gövdesi görevin varlığını bile doğrulamaz —
``TaskForbiddenError`` handler'ı api katmanında).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agent_core.task_executor import ResumeBlockedError, TaskStatus
from backend import checkpoint_store as ckpt
from backend.security.task_access import MAX_TASK_ID_LENGTH, guard_task
from backend.security.task_ownership import TaskForbiddenError
from agent_core.utils.security import redact_text, validate_identifier

logger = logging.getLogger(__name__)

__all__ = ["SupportProvide", "register_support_routes"]


class SupportProvide(BaseModel):
    """Destek yanıtı gövdesi — yalnız niyet + not. Görev verisi DEĞİL."""

    action: str = Field(default="provide", max_length=32)
    note: str = Field(default="", max_length=500)


def _invalid_task_id() -> JSONResponse:
    return JSONResponse(
        {"error": {"code": "INVALID_TASK_ID", "message": "Invalid task identifier"}},
        status_code=400,
    )


def _clean_ts(value) -> str:
    """Geri okunan durumu ``completed`` biçimine indirger (eski dosyalar dâhil)."""
    if isinstance(value, str) and value.startswith("PipelineStatus."):
        return value.split(".", 1)[1].lower()
    return value


def _budget_blocked(room: dict) -> bool:
    """Bütçe kapısı canlı: ``budget_status`` atomik anlık görüntü."""
    try:
        gateway = room["executor"].llm_gateway
        reader = getattr(gateway, "budget_status", None)
        if not callable(reader):
            return False
        budget = reader()
        cap = float(budget.get("cap_usd") or 0.0)
        if cap <= 0.0:
            return False
        committed = float(budget.get("spend_usd") or 0.0)
        reserved = float(budget.get("reserved_usd") or 0.0)
        return committed + reserved >= cap
    except Exception:
        # Bütçe durumu OKUNAMADIYSA dar taraf: resume ENGELLENİR (fail-closed),
        # arıza yutulmaz.
        logger.error("BÜTÇE DURUMU OKUNAMADI — resume kapatıldı", exc_info=True)
        return True


def register_support_routes(
    app: Any,
    *,
    get_room: Callable[[str], dict],
    principal_getter: Callable[[], Optional[str]] = lambda: None,
    require_vault_open: Callable[[str], Optional[JSONResponse]],
    require_minor_clearance: Callable[..., Optional[JSONResponse]],
    broadcast_log: Callable[[str, str, str], None],
    broadcast_result: Callable[[str, Any], None],
    broadcast_result_error: Callable[..., None],
    lifecycle_registry: Callable[[dict], Any],
    rate_limit: Callable[[str, str], bool],
    rate_identity: Callable[[Request], str],
) -> None:
    """Rotaları kaydeder + ``app.state`` kalıcılık kancalarını bağlar.

    ``backend/api.py`` içindeki tek çağrı satırı bu fonksiyonu çağırır;
    ``sync_snapshot`` / ``broadcast_result`` / ``run_mission`` aynı-satır
    kancalarla ``ckpt_persist`` / ``ckpt_input``'a yazar (tavan aşılmaz).
    """

    # ── app.state kancaları (api.py aynı-satır çağrılarıyla kullanır) ──
    def ckpt_persist(client_id: str, snapshot: Any) -> None:
        try:
            room = app.state.rooms.get(client_id) or {}
            ckpt.persist_status(snapshot, owner=room.get("_owner"))
        except Exception:
            logger.exception("CHECKPOINT persist başarısız (task=%s)",
                             getattr(snapshot, "task_id", "?"))

    def ckpt_input(task_id: str, input_data: Dict[str, Any], owner: Optional[str] = None) -> None:
        try:
            ckpt.set_input(task_id, input_data, owner=owner)
        except Exception:
            logger.exception("CHECKPOINT input kaydı başarısız (task=%s)", task_id)

    app.state.ckpt_persist = ckpt_persist
    app.state.ckpt_input = ckpt_input

    # ── 1) Açık destek talepleri ─────────────────────────────────────────
    async def api_list_support(task_id: str, client_id: str):
        if len(task_id) > MAX_TASK_ID_LENGTH:
            return _invalid_task_id()
        try:
            validate_identifier(task_id, field="task_id")
        except ValueError:
            return _invalid_task_id()
        # Önce kalıcı kayıt + SAHİP mührü (checkpoint owner): yanlış sahipte
        # `guard_task` SAHİPLENME yan etkisi (adopt) yaşamadan 403.
        _pre = None
        try:
            _pre = ckpt.load(task_id)
        except ckpt.CheckpointCorrupted:
            _pre = "corrupt"
        _principal_pre = principal_getter()
        if isinstance(_pre, dict) and _pre.get("owner") and _principal_pre and _pre["owner"] != _principal_pre:
            raise TaskForbiddenError(task_id)
        room = get_room(client_id)
        if not guard_task(room, task_id, _principal_pre):
            raise TaskForbiddenError(task_id)
        try:
            data, views = ckpt.list_support(task_id)
        except ckpt.CheckpointCorrupted:
            return JSONResponse(
                {"error": {"code": "CHECKPOINT_CORRUPTED",
                           "message": "Checkpoint kaydı okunamadı"}},
                status_code=409,
            )
        if data is None:
            return JSONResponse(
                {"error": {"code": "NOT_FOUND", "message": "Checkpoint bulunamadı"}},
                status_code=404,
            )
        open_views = [v for v in views if v.get("status") == "pending"]
        return {
            "task_id": task_id,
            "task_status": _clean_ts(
                data.get("status_status") or ((data.get("status") or {}).get("status"))
            ),
            "support_requests": views,
            "open_count": len(open_views),
            "resume_running": ckpt.is_resume_running(task_id),
        }

    # ── 2) Yetkili destek yanıtı ─────────────────────────────────────────
    async def api_provide_support(
        task_id: str,
        support_id: str,
        payload: SupportProvide,
        client_id: str,
    ):
        if len(task_id) > MAX_TASK_ID_LENGTH or not support_id or len(support_id) > 256:
            return _invalid_task_id()
        try:
            validate_identifier(task_id, field="task_id")
        except ValueError:
            return _invalid_task_id()
        if (blocked := require_minor_clearance(client_id, subject="")) is not None:
            return blocked
        try:
            data = ckpt.load(task_id)
        except ckpt.CheckpointCorrupted:
            return JSONResponse(
                {"error": {"code": "CHECKPOINT_CORRUPTED",
                           "message": "Checkpoint kaydı okunamadı"}},
                status_code=409,
            )
        if data is None:
            return JSONResponse(
                {"error": {"code": "NOT_FOUND", "message": "Checkpoint bulunamadı"}},
                status_code=404,
            )
        room = get_room(client_id)
        _principal = principal_getter()
        if data.get("owner") and _principal and data.get("owner") != _principal:
            raise TaskForbiddenError(task_id)
        if not guard_task(room, task_id, _principal):
            raise TaskForbiddenError(task_id)
        entry = next(
            (
                e
                for e in (data.get("status") or {}).get("support_requests") or []
                if e.get("support_id") == support_id
            ),
            None,
        )
        if entry is None:
            return JSONResponse(
                {"error": {"code": "SUPPORT_NOT_FOUND", "message": "Destek talebi yok"}},
                status_code=404,
            )
        if entry.get("status") != "pending":
            # ÇİFT YANIT: aynı talep ikinci kez kapatılamaz (409).
            return JSONResponse(
                {"error": {"code": "ALREADY_RESOLVED",
                           "message": "Destek talebi zaten kapatıldı"}},
                status_code=409,
            )
        if payload.action != "provide":
            return JSONResponse(
                {"error": {"code": "INVALID_ACTION", "message": "Yalnızca 'provide'"}},
                status_code=400,
            )

        # ENGEL CANLI DOĞRULANIR — yanıt geldi diye talep kendiliğinden
        # kapanmaz (kasa/bütçe kapalıysa 409/423 + talep AÇIK KALIR).
        requires = entry.get("requires") or "operator_response"
        if requires == "vault_open":
            if (locked := require_vault_open(client_id)) is not None:
                return locked  # 423 — engel kalkmadı, kayıt bile yapılmaz
        elif entry.get("kind") == "spend_cap" and _budget_blocked(room):
            return JSONResponse(
                {"error": {"code": "BUDGET_STILL_CAPPED",
                           "message": "Bütçe üst sınırı aşılmış durumda; destek uygulanamaz"}},
                status_code=409,
            )

        code, raw_entry = ckpt.record_support_response(
            task_id,
            support_id,
            principal=principal_getter(),
            note=payload.note,
        )
        if code == "NOT_FOUND":
            return JSONResponse(
                {"error": {"code": "SUPPORT_NOT_FOUND", "message": "Destek talebi yok"}},
                status_code=404,
            )
        if code == "ALREADY_RESOLVED":
            return JSONResponse(
                {"error": {"code": "ALREADY_RESOLVED",
                           "message": "Destek talebi zaten kapatıldı"}},
                status_code=409,
            )
        if code == "PENDING_LIVE_CHECK":
            raw_entry = ckpt.finalize_support(task_id, support_id) or raw_entry

        broadcast_log(
            client_id,
            "INFO",
            f"DESTEK SAĞLANDI: {task_id} · {support_id} · "
            f"talep={redact_text(str(entry.get('agent_name') or ''))} — kapandı.",
        )
        return {"status": "accepted", "support": ckpt.support_view(raw_entry or {})}

    # ── 3) Güvenli resume ───────────────────────────────────────────────
    async def api_resume_task(task_id: str, client_id: str, request: Request):
        if not rate_limit(f"resume:{rate_identity(request)}", "initiate"):
            return JSONResponse(
                {"error": {"code": "RATE_LIMITED",
                           "message": "Çok fazla resume isteği; bir dakika sonra tekrar deneyin."}},
                status_code=429,
            )
        if len(task_id) > MAX_TASK_ID_LENGTH:
            return _invalid_task_id()
        try:
            validate_identifier(task_id, field="task_id")
        except ValueError:
            return _invalid_task_id()
        # Çocuk kilidi — resume da görev çalıştırır (istisnasız beyan).
        if (blocked := require_minor_clearance(client_id, subject="")) is not None:
            return blocked

        # Önce kalıcı kayıt + SAHİP mührü, SONRA oda/oda-görev mührü:
        # adopt (ilk erişen sahiplenir) yan etkisi saldırgana fırsat vermez.
        try:
            data = ckpt.load(task_id)
        except ckpt.CheckpointCorrupted:
            return JSONResponse(
                {"error": {"code": "CHECKPOINT_CORRUPTED",
                           "message": "Checkpoint kaydı okunamadı"}},
                status_code=409,
            )
        if data is None:
            return JSONResponse(
                {"error": {"code": "NOT_FOUND", "message": "Checkpoint bulunamadı"}},
                status_code=404,
            )
        owner = data.get("owner")
        principal = principal_getter()
        if owner and principal and owner != principal:
            # GÖREV SAHİPLİĞİ: başka operatörün görevi resume EDİLEMEZ (403).
            raise TaskForbiddenError(task_id)
        room = get_room(client_id)
        if not guard_task(room, task_id, principal):
            raise TaskForbiddenError(task_id)

        # EŞZAMANLI RESUME: aynı görev için ikinci istek 409 — token
        # süreç-içi bellekte tutulur (yeniden başlangıçta doğal düşer).
        token = ckpt.claim_resume(task_id)
        if token is None:
            return JSONResponse(
                {"error": {"code": "RESUME_ALREADY_RUNNING",
                           "message": "Bu görev için zaten çalışan bir resume var"}},
                status_code=409,
            )
        claimed = True
        try:
            # KASA yeniden kontrol — kilitliyse resume YOK (423).
            if (locked := require_vault_open(client_id)) is not None:
                claimed = False
                ckpt.release_resume(task_id, token)
                return locked
            # BÜTÇE yeniden kontrol.
            if _budget_blocked(room):
                claimed = False
                ckpt.release_resume(task_id, token)
                return JSONResponse(
                    {"error": {"code": "RESUME_BUDGET_BLOCKED",
                               "message": "Bütçe üst sınırı aşıldı; resume engellendi"}},
                    status_code=409,
                )
            # AÇIK DESTEK ÖNKOŞULLARI: yalnız ``blocks_resume`` talepleri
            # kapatılmadan resume başlamaz; yanıtlanmışsa kapalıdır.
            status_dump = data.get("status")
            if not isinstance(status_dump, dict):
                ckpt.release_resume(task_id, token)
                return JSONResponse(
                    {"error": {"code": "CHECKPOINT_CORRUPTED",
                               "message": "Checkpoint durumu yok"}},
                    status_code=409,
                )
            missing = []
            for r in status_dump.get("support_requests") or []:
                if r.get("status") != "pending" or not r.get("blocks_resume"):
                    continue
                req = r.get("requires")
                if req == "vault_open":
                    # Kasa şu an AÇIK (yukarıdaki 423 kapısı geçildi) →
                    # engel kalkmıştır; resume sırasında executor yeniden
                    # doğrular ve talebi ``verified_vault_open`` ile kapatır.
                    continue
                if r.get("kind") == "spend_cap" and not _budget_blocked(room):
                    continue  # bütçe sınırı aşılmıyor → engel kalktı
                if r.get("approved") and r.get("responses"):
                    continue  # destek geldi; kapatma checkpoint'e işlenmemiş
                missing.append(r.get("support_id"))
            if missing:
                ckpt.release_resume(task_id, token)
                open_views = [
                    ckpt.support_view(r)
                    for r in status_dump.get("support_requests") or []
                    if r.get("status") == "pending" and r.get("blocks_resume")
                ]
                return JSONResponse(
                    {
                        "error": {
                            "code": "RESUME_SUPPORT_MISSING",
                            "message": "Bloklayan destek talepleri hâlâ açık",
                            "missing": missing,
                            "open_support": open_views,
                        }
                    },
                    status_code=409,
                )
            input_data = data.get("input_data")
            if not isinstance(input_data, dict):
                ckpt.release_resume(task_id, token)
                return JSONResponse(
                    {"error": {"code": "RESUME_INPUT_MISSING",
                               "message": "Checkpoint'te resume girdisi yok"}},
                    status_code=409,
                )
            try:
                resume_status = TaskStatus.model_validate(status_dump)
            except Exception:
                ckpt.release_resume(task_id, token)
                return JSONResponse(
                    {"error": {"code": "CHECKPOINT_CORRUPTED",
                               "message": "Checkpoint durum şeması geçersiz"}},
                    status_code=409,
                )
        except Exception:
            if claimed:
                ckpt.release_resume(task_id, token)
            raise

        # Terminal koşu YENİDEN AÇILIR (mevcut durum makinesi — yeni durum yok).
        lifecycle_registry(room).reopen(task_id, "processing")
        broadcast_log(
            client_id,
            "INFO",
            f"RESUME: {task_id} — açık destek {len(missing or [])} yok, "
            "yetkiler yeniden doğrulandı; görev kaldığı yerden sürüyor.",
        )

        async def _resume_mission():
            try:
                executor = room["executor"]
                result = await executor.execute_task(
                    dict(input_data), task_id, resume_from=resume_status
                )
                ckpt_persist(client_id, result)
                broadcast_result(client_id, result)
            except ResumeBlockedError as exc:
                lifecycle_registry(room).transition(task_id, "halted_evidence")
                broadcast_log(client_id, "WARNING", f"RESUME REDDEDİLDİ: {exc}")
                broadcast_result_error(
                    client_id, "failed", f"RESUME_BLOCKED: {exc}", task_id
                )
            except Exception as exc:  # noqa: BLE001 — dürüst hata çerçevesi
                lifecycle_registry(room).transition(task_id, "failed")
                broadcast_log(
                    client_id,
                    "ERROR",
                    f"RESUME HATASI: {type(exc).__name__}: {str(exc)[:180]}",
                )
                broadcast_result_error(
                    client_id, "failed",
                    f"RESUME HATASI: {type(exc).__name__}: {str(exc)[:180]}",
                    task_id,
                )
            finally:
                ckpt.release_resume(task_id, token)
                room.get("mission_tasks", {}).pop(task_id, None)

        mission = asyncio.create_task(_resume_mission())
        room.setdefault("mission_tasks", {})[task_id] = mission
        return {"status": "resuming", "task_id": task_id}

    # Statik mount ÖNCESİ sıralama kritik: api.py bu kaydı sonlara çağırır.
    app.get("/api/tasks/{task_id}/support")(api_list_support)
    app.post("/api/tasks/{task_id}/support/{support_id}")(api_provide_support)
    app.post("/api/tasks/{task_id}/resume")(api_resume_task)
