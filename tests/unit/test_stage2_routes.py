"""Stage 2 route & 4-fix verification tests."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from agent_core.aspasia.interface import AspasiaCommandGateway
from agent_core.services import report_factory
from agent_core.task_executor import PinealExecutor
from backend.api import app, get_room


def test_task_detail_returns_canonical_evidence_and_rejects_invalid(tmp_path: Path):
    client = TestClient(app)
    room = get_room("stage2_task_room")
    storage = Path(room["executor"].memory.storage_path)
    storage.mkdir(parents=True, exist_ok=True)
    task_id = "task-stage2-detail-01"
    mem_file = storage / f"{task_id}.json"
    mem_file.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "status": "completed",
                "confidence": 0.82,
                "last_updated": "2026-11-16T01:00:00Z",
                "evidence": [
                    {
                        "agent": "authenticity_auditor",
                        "evidence_type": "primary",
                        "epistemic_type": "observation",
                        "uncertainty": {"confidence": 0.82, "data_sufficiency": "sufficient"},
                        "result": {"authenticity_score": 84},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    try:
        res = client.get(f"/api/tasks/{task_id}?client_id=stage2_task_room")
        assert res.status_code == 200
        body = res.json()
        assert body["task_id"] == task_id
        assert body["evidence_count"] == 1
        assert body["evidence_chain"][0]["agent"] == "authenticity_auditor"
        assert re.fullmatch(r"ev_[0-9a-f]{20}", body["evidence_chain"][0]["evidence_id"])

        bad = client.get("/api/tasks/bad..id?client_id=stage2_task_room")
        assert bad.status_code == 400

        missing = client.get("/api/tasks/nonexistent-task-999?client_id=stage2_task_room")
        assert missing.status_code == 404
    finally:
        if mem_file.exists():
            mem_file.unlink()


def test_evidence_record_emits_canonical_evidence_id():
    class _DummyModel:
        def model_dump(self):
            return {"score": 91}

    rec = PinealExecutor._evidence_record("authenticity_auditor", _DummyModel(), evidence_type="primary")
    assert re.fullmatch(r"ev_[0-9a-f]{20}", rec["evidence_id"])


def test_report_all_formats_and_download(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PINEAL_REPORT_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_REPORT_FACTORY", "true")
    ev_id = "ev_" + "a" * 20
    pkg = report_factory.build_report(
        [
            {
                "evidence_id": ev_id,
                "source_engine": "authenticity_auditor",
                "epistemic_type": "observation",
                "content": "Gerçek kanıt satırı",
                "provenance_refs": ["instagram:profile"],
            }
        ],
        title="Stage 2 Rapor Testi",
        subject="https://instagram.com/example",
        formats=("markdown", "pdf", "diagram", "video"),
    )
    assert pkg.available
    assert ev_id in pkg.evidence_ids
    for fmt in ("markdown", "pdf", "diagram", "video"):
        art = pkg.artifact(fmt)
        assert art is not None and art.available, f"{fmt} failed: {art.reason if art else 'missing'}"
        assert art.bytes > 0

    client = TestClient(app)
    res_list = client.get("/api/report/list")
    assert res_list.status_code == 200
    data = res_list.json()
    assert data["gate_enabled"] is True
    assert len(data["reports"]) >= 1
    first = data["reports"][0]
    assert first["title"] == "Stage 2 Rapor Testi"
    md_art = next(a for a in first["artifacts"] if a["kind"] == "markdown")
    assert md_art["download_url"].startswith("/api/report/file/")

    res_file = client.get(md_art["download_url"])
    assert res_file.status_code == 200
    assert "Gerçek kanıt satırı" in res_file.text

    res_bad = client.get("/api/report/file/..%2Fsecret.txt")
    assert res_bad.status_code in (400, 404)


def test_report_ownership_isolation_between_two_principals(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PINEAL_REPORT_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_REPORT_FACTORY", "true")

    pkg = report_factory.build_report(
        [
            {
                "evidence_id": "ev_" + "b" * 20,
                "source_engine": "authenticity_auditor",
                "epistemic_type": "observation",
                "content": "Gizli rapor kanıtı",
                "provenance_refs": ["instagram:secret"],
            }
        ],
        title="Gizli Rapor",
        subject="https://instagram.com/secret",
        formats=("markdown",),
    )
    assert pkg.available
    mname = Path(pkg.manifest_path).name
    md_name = Path(pkg.artifact("markdown").path).name

    from backend.security.task_access import record_new_task

    room_a = get_room("iso_room_a")
    room_b = get_room("iso_room_b")
    room_a["_owner"] = "principal_alpha"
    room_b["_owner"] = "principal_beta"
    try:
        record_new_task(room_a, f"report:{mname}", "principal_alpha")
        record_new_task(room_a, f"report_file:{md_name}", "principal_alpha")

        client = TestClient(app)
        list_a = client.get("/api/report/list?client_id=iso_room_a")
        assert list_a.status_code == 200
        assert any(r["manifest_name"] == mname for r in list_a.json()["reports"])

        list_b = client.get("/api/report/list?client_id=iso_room_b")
        assert list_b.status_code == 200
        assert not any(r["manifest_name"] == mname for r in list_b.json()["reports"])

        dl_a = client.get(f"/api/report/file/{md_name}?client_id=iso_room_a")
        assert dl_a.status_code == 200

        dl_b = client.get(f"/api/report/file/{md_name}?client_id=iso_room_b")
        assert dl_b.status_code == 403
    finally:
        room_a.pop("_owner", None)
        room_b.pop("_owner", None)


def test_aspasia_command_dispatches_runnable_url_when_llm_unavailable():
    dispatched = []

    class _FailGateway:
        async def query_json_chain(self, **kwargs):
            raise RuntimeError("offline_llm")

    def _dispatch(req: dict):
        dispatched.append(req)
        return "tsk-aspasia-real-1"

    cmds = AspasiaCommandGateway(gateway=_FailGateway(), dispatch=_dispatch)
    res = asyncio.run(
        cmds.submit(
            "https://www.instagram.com/example — Bu profilin maskesi arkasındaki gerçek niyeti analiz et.",
            client_id="aspasia_test",
        )
    )
    assert res.accepted is True
    assert res.intent == "run_profile_analysis"
    assert res.task_id == "tsk-aspasia-real-1"
    assert len(dispatched) == 1
    assert dispatched[0]["target_url"] == "https://www.instagram.com/example"
