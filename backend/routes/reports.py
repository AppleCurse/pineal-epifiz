"""Rapor fabrikası uç noktaları: durum, üretim, geçmiş ve dosya indirme.

``GET /api/report/status``, ``POST /api/report/build``,
``GET /api/report/list`` ve ``GET /api/report/file/{filename}`` rotalarını
``backend/routes/reports.py`` içinde sunar (monolit bölme).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from agent_core.services import report_factory
from agent_core.utils.security import safe_child_path
from backend.security.task_access import (
    guard_task,
    owner_for_room,
    record_new_task,
    visible_tasks,
)
from backend.security.task_ownership import TaskForbiddenError

__all__ = ["ReportBuildPayload", "register_report_routes"]

_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,180}$")

_MEDIA_TYPES = {
    ".md": "text/markdown; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".mp4": "video/mp4",
}


class ReportBuildPayload(BaseModel):
    """[FAZ D · D5] Rapor paketi: kanıt satırları + istenen formatlar."""

    title: str = Field(min_length=1, max_length=200)
    client_id: str = Field(default="default", max_length=128)
    subject: str = Field(default="", max_length=200)
    evidence: list[dict] = Field(default_factory=list, max_length=200)
    formats: list[str] = Field(default_factory=lambda: ["markdown", "pdf", "diagram"])


def _read_manifests_sync(base_dir: Path, limit: int = 50) -> list[dict[str, Any]]:
    if not base_dir.is_dir():
        return []
    manifests = sorted(
        (p for p in base_dir.iterdir() if p.is_file() and p.name.endswith(".manifest.json")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    items: list[dict[str, Any]] = []
    for path in manifests[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            artifacts = []
            for art in data.get("artifacts") or []:
                if not isinstance(art, dict):
                    continue
                kind = str(art.get("kind") or art.get("name") or "")
                filename = str(art.get("file") or art.get("name") or "")
                avail = bool(art.get("available", True))
                artifacts.append(
                    {
                        "name": filename,
                        "kind": kind,
                        "available": avail,
                        "reason": art.get("reason") or "",
                        "sha256": art.get("sha256") or "",
                        "bytes": int(art.get("bytes") or 0),
                        "download_url": (
                            f"/api/report/file/{filename}"
                            if avail and _SAFE_FILENAME_RE.fullmatch(filename)
                            else ""
                        ),
                    }
                )
            items.append(
                {
                    "manifest_name": path.name,
                    "manifest_url": f"/api/report/file/{path.name}",
                    "manifest_sha256": data.get("manifest_sha256") or "",
                    "title": data.get("title") or path.stem,
                    "subject": data.get("subject") or "",
                    "created_at": data.get("created_at") or "",
                    "evidence_count": len(data.get("evidence_ids") or []),
                    "epistemic_counts": data.get("epistemic_counts") or {},
                    "rejected_item_count": int(data.get("rejected_item_count") or 0),
                    "artifacts": artifacts,
                }
            )
        except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
            continue
    return items


def register_report_routes(
    app: Any,
    *,
    get_room: Callable[[str], dict],
    rate_limit: Callable[[str, str], bool],
    check_vault_interlock: Callable[[str], bool],
    broadcast_log: Callable[[str, str, str], None],
    flag_env: Callable[[str], bool],
    require_vault_open: Callable[[str], Any] | None = None,
) -> None:
    def _record_package_owner(room: dict, manifest_path: str, artifacts: list[dict[str, Any]]) -> None:
        if manifest_path:
            mname = Path(manifest_path).name
            record_new_task(room, f"report:{mname}", None)
            record_new_task(room, f"report_file:{mname}", None)
        for art in artifacts:
            apath = str(art.get("path") or "")
            if apath and art.get("available", True):
                record_new_task(room, f"report_file:{Path(apath).name}", None)
    """``/api/report/*`` rotalarını kaydeder."""

    @app.get("/api/report/status")
    async def api_report_status():
        formats = report_factory.availability()
        return {
            "gate": report_factory.GATE,
            "report_dir": str(report_factory.report_dir()),
            "formats": [
                {"format": name, "available": ok, "reason": reason}
                for name, (ok, reason) in sorted(formats.items())
            ],
            "any_available": any(ok for ok, _r in formats.values()),
            "manifest_schema": report_factory.MANIFEST_SCHEMA,
            "seal": "sha256 (bütünlük mührü; kriptografik imza değil)",
        }

    @app.post("/api/report/build")
    async def api_report_build(req: ReportBuildPayload):
        from agent_core.capabilities.base import CapabilityContext
        from agent_core.capabilities.policy import PolicyState
        from agent_core.capabilities.registry import bootstrap
        from agent_core.capabilities.runner import CapabilityRunner

        if require_vault_open is not None:
            locked = require_vault_open(req.client_id)
            if locked is not None:
                return locked
        if not rate_limit(f"report:{req.client_id}", "report"):
            return JSONResponse(
                {"error": {"code": "RATE_LIMITED", "message": "Çok fazla rapor isteği"}},
                status_code=429,
            )

        formats = [str(f).strip().lower() for f in (req.formats or [])]
        unknown = [f for f in formats if f not in ("markdown", "pdf", "diagram", "video")]
        if unknown:
            return JSONResponse(
                {"error": {"code": "UNKNOWN_FORMAT", "message": f"Bilinmeyen format: {', '.join(unknown)}"}},
                status_code=400,
            )

        wanted = [f for f in formats if f != "markdown"]
        cap_by_format = {
            "pdf": "renderer.report.pdf",
            "diagram": "renderer.report.diagram",
            "video": "renderer.report.video",
        }
        runner = CapabilityRunner(registry=bootstrap())
        state = PolicyState(
            enabled_flags={report_factory.GATE: flag_env(report_factory.GATE)},
            vault_locked=not check_vault_interlock(req.client_id),
            rate_ok=True,
        )

        results: dict[str, Any] = {}
        for fmt in wanted:
            result = await runner.run(
                cap_by_format[fmt],
                CapabilityContext(
                    subject=req.title,
                    params={"title": req.title, "subject": req.subject, "evidence": req.evidence},
                ),
                state=state,
            )
            results[fmt] = {
                "capability_id": cap_by_format[fmt],
                "available": bool(result.available),
                "denied_by": result.denied_by,
                "reason": result.unavailable_reason,
                "artifacts": result.notes.get("artifacts", []),
                "manifest_path": result.notes.get("manifest_path", ""),
                "manifest_sha256": result.notes.get("manifest_sha256", ""),
                "evidence_ids": result.notes.get("evidence_ids", []),
                "rejected_item_count": result.notes.get("rejected_item_count", 0),
                "excluded_strategy_count": result.notes.get("excluded_strategy_count", 0),
                "evidence": [
                    {
                        "evidence_id": item.evidence_id,
                        "content": item.content[:300],
                        "provenance_refs": list(item.provenance_refs)[:5],
                    }
                    for item in result.items[:10]
                ],
            }
            if result.denied_by:
                broadcast_log(req.client_id, "WARNING", f"RAPOR: {fmt} engellendi — kapı:{result.denied_by}")
            elif not result.available:
                broadcast_log(req.client_id, "WARNING", f"RAPOR: {fmt} üretilemedi — {result.unavailable_reason}")
            else:
                _record_package_owner(
                    get_room(req.client_id),
                    str(result.notes.get("manifest_path") or ""),
                    list(result.notes.get("artifacts") or []),
                )
                broadcast_log(req.client_id, "INFO", f"RAPOR: {fmt} üretildi ({req.title[:40]})")

        if not wanted and "markdown" in formats:
            if not state.enabled_flags.get(report_factory.GATE):
                results["markdown"] = {
                    "capability_id": "renderer.report.markdown",
                    "available": False,
                    "denied_by": f"gate_disabled:{report_factory.GATE}",
                    "reason": f"gate_disabled:{report_factory.GATE}",
                    "artifacts": [],
                    "manifest_path": "",
                    "manifest_sha256": "",
                    "evidence_ids": [],
                    "rejected_item_count": 0,
                    "excluded_strategy_count": 0,
                    "evidence": [],
                }
                broadcast_log(req.client_id, "WARNING", f"RAPOR: markdown engellendi — kapı:gate_disabled:{report_factory.GATE}")
            else:
                pkg = report_factory.build_report(
                    req.evidence,
                    title=req.title,
                    subject=req.subject,
                    formats=("markdown",),
                )
                results["markdown"] = {
                    "capability_id": "renderer.report.markdown",
                    "available": bool(pkg.available),
                    "denied_by": None,
                    "reason": pkg.reason or None,
                    "artifacts": [
                        {
                            "name": a.name,
                            "path": a.path,
                            "available": a.available,
                            "reason": a.reason,
                            "sha256": a.sha256,
                            "bytes": a.bytes,
                        }
                        for a in pkg.artifacts
                    ],
                    "manifest_path": pkg.manifest_path,
                    "manifest_sha256": pkg.manifest_sha256,
                    "evidence_ids": list(pkg.evidence_ids),
                    "rejected_item_count": int(pkg.notes.get("rejected_item_count", 0)),
                    "excluded_strategy_count": int(pkg.notes.get("excluded_strategy_count", 0)),
                    "evidence": [],
                }
                _record_package_owner(
                    get_room(req.client_id),
                    str(pkg.manifest_path or ""),
                    results["markdown"]["artifacts"],
                )
                broadcast_log(req.client_id, "INFO", f"RAPOR: markdown üretildi ({req.title[:40]})")

        return {
            "title": req.title,
            "subject": req.subject,
            "gate": report_factory.GATE,
            "formats": results,
        }

    @app.get("/api/report/list")
    async def api_report_list(client_id: str = "default"):
        room = get_room(client_id)
        principal = owner_for_room(room, None)
        base_dir = report_factory.report_dir()
        reports = visible_tasks(
            _read_manifests_sync(base_dir),
            principal,
            task_id_of=lambda r: f"report:{r['manifest_name']}",
        )
        return {
            "gate": report_factory.GATE,
            "gate_enabled": bool(flag_env(report_factory.GATE)),
            "report_dir": str(base_dir),
            "reports": reports,
        }

    @app.get("/api/report/file/{filename}")
    async def api_report_file(filename: str, client_id: str = "default"):
        if not _SAFE_FILENAME_RE.fullmatch(filename or ""):
            return JSONResponse(
                {"error": {"code": "INVALID_FILENAME", "message": "Geçersiz rapor dosya adı"}},
                status_code=400,
            )
        room = get_room(client_id)
        if not guard_task(room, f"report_file:{filename}", None):
            raise TaskForbiddenError(filename)
        base_dir = report_factory.report_dir()
        try:
            target = Path(safe_child_path(str(base_dir), filename))
        except ValueError:
            return JSONResponse(
                {"error": {"code": "INVALID_FILENAME", "message": "Geçersiz rapor yolu"}},
                status_code=400,
            )
        if not target.is_file():
            return JSONResponse(
                {"error": {"code": "NOT_FOUND", "message": f"Rapor dosyası bulunamadı: {filename}"}},
                status_code=404,
            )
        media_type = _MEDIA_TYPES.get(target.suffix.lower(), "application/octet-stream")
        return FileResponse(path=str(target), filename=target.name, media_type=media_type)
