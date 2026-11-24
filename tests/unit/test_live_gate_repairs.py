"""Canlı kapı tamirleri — 2026-11-24 ölçülen hataların regresyon kilidi."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agent_core.services.dependency_health import (
    DependencyRequirement,
    check_startup_dependencies,
)
from backend import api
from backend.api import app


def _cid() -> str:
    return f"repair_{uuid.uuid4().hex[:10]}"


def test_missing_interpreter_package_does_not_crash_startup(monkeypatch):
    monkeypatch.setenv("ENABLE_INTERPRETER", "true")
    optional = DependencyRequirement("open-interpreter", "interpreter", "ENABLE_INTERPRETER")

    def missing(_module):
        raise ModuleNotFoundError("not installed", name="interpreter")

    result = check_startup_dependencies(
        importer=missing, required=(), configured=(optional,)
    )
    assert result["status"] == "ready"
    row = result["dependencies"][0]
    assert row["status"] == "missing"
    assert row["error_code"] == "OPTIONAL_DEPENDENCY_MISSING"


def test_vault_lock_keeps_keys_and_unlock_reopens(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PINEAL_ROUTER_LIVE", raising=False)
    cid = _cid()
    with TestClient(app) as client:
        room = api.get_room(cid)
        room["vault"]["or_key"] = True
        assert api._check_vault_interlock(cid) is True
        locked = client.post("/api/vault/lock", json={"client_id": cid})
        assert locked.status_code == 200
        assert room["vault"].get("or_key") is True
        assert api._check_vault_interlock(cid) is False
        opened = client.post("/api/vault/unlock", json={"client_id": cid})
        assert opened.status_code == 200
        assert api._check_vault_interlock(cid) is True


def test_vault_bypass_doors_return_423_when_locked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PINEAL_ROUTER_LIVE", raising=False)
    cid = _cid()
    with TestClient(app) as client:
        bodies = [
            ("POST", "/api/brain/route", {"client_id": cid, "message": "özetle", "subject_consent": True}),
            ("POST", "/api/aspasia/chat", {"client_id": cid, "user_message": "merhaba"}),
            ("POST", "/api/company/scan", {"client_id": cid, "domain": "example.com"}),
            ("POST", "/api/report/build", {"client_id": cid, "title": "t"}),
            ("POST", "/api/experimental/shadow/analyze", {"client_id": cid, "text": "x"}),
        ]
        for method, path, body in bodies:
            r = client.request(method, path, json=body)
            assert r.status_code == 423, f"{path} {r.status_code} {r.text[:160]}"
            assert r.json()["error"]["code"] == "VAULT_LOCKED"


def test_initiate_and_brain_require_consent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cid = _cid()
    with TestClient(app) as client:
        room = api.get_room(cid)
        room["vault"]["or_key"] = True
        r = client.post("/api/initiate", json={"client_id": cid, "url": "https://www.instagram.com/x/"})
        assert r.status_code == 423
        assert r.json()["error"]["code"] == "CONSENT_REQUIRED"
        r = client.post("/api/brain/route", json={"client_id": cid, "message": "özetle"})
        assert r.status_code == 423
        assert r.json()["error"]["code"] == "CONSENT_REQUIRED"


def test_invalid_minor_case_does_not_lock_the_room(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cid = _cid()
    with TestClient(app) as client:
        room = api.get_room(cid)
        room["vault"]["or_key"] = True
        declared = client.post("/api/minor/case", json={"client_id": cid})
        assert declared.status_code == 200
        assert declared.json()["declared"] is False
        assert declared.json()["reason_code"] == "case_type_not_allowed"
        started = client.post(
            "/api/initiate",
            json={
                "client_id": cid,
                "url": "https://www.instagram.com/x/",
                "subject_consent": True,
            },
        )
        assert started.status_code != 451, started.text[:200]


def test_calibration_returns_observation_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PINEAL_CALIB_OBSERVE", "true")
    with TestClient(app) as client:
        r = client.post("/api/calibration/observations", json={"score": 0.8, "scope": "quote"})
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        oid = body.get("observation_id") or body.get("id")
        assert oid
        judged = client.post(
            "/api/calibration/adjudicate",
            json={"observation_id": oid, "truth": True},
        )
        assert judged.status_code == 200, judged.text[:200]


def test_websocket_header_auth_and_reject_wrong_key(monkeypatch):
    token = "ws-repair-token-long-enough"
    monkeypatch.setenv("PINEAL_ENV", "development")
    monkeypatch.setenv("PINEAL_TOKEN", token)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/ws_hdr", headers={"X-API-Key": token}) as websocket:
            msg = websocket.receive_json()
            assert msg["type"] == "auth_ok"
        with pytest.raises(WebSocketDisconnect) as raised:
            with client.websocket_connect("/ws/ws_bad", headers={"X-API-Key": "wrong"}) as websocket:
                websocket.receive_json()
        assert raised.value.code == 1008
