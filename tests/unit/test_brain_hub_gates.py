"""Brain Hub kapıları — davranış + kaynak bekçisi testleri.

Kapsam (hepsi ağsız, deterministik):
  1. `/api/brain/route` graph/memory dalları: reşitlik (451) → kasa (423) → oda (403)
     sırası BOZULMAZ; kasa kapalıyken hiçbir kanıt/hatıra okunmaz.
  2. graph dalı: görev VARLIK (404) → SAHİPLİK (403) sırası; hata gövdeleri
     oda/görev adını TAŞIMAZ.
  3. `/api/brain/capabilities`: `wired_pipelines` artık TÜRETİLMİŞ envanter —
     her giriş `{"available": bool, "reason": str|None}`; kapalı ise sebep dolu.
  4. Kaynak bekçisi: brain_hub.py içinde `"deterministic_7_pillars": True` gibi
     sabit True envanteri geri gelemez.
  5. /api/hook/generate: kapı enjekte edildiğinde 429 → 451 → 423 sırası korunur.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from backend.routes.brain_hub import register_brain_hub_routes
from backend.routes.hook_studio import register_hook_studio_routes
from backend.security.principal import bind_principal, reset_principal

REPO_ROOT = Path(__file__).resolve().parents[2]


class _FakeMemory:
    storage_path = "/nonexistent-for-brain-hub-tests"


class _FakeExecutor:
    def __init__(self):
        self.tasks = {}
        self.last_status = None
        self.memory = _FakeMemory()


def _gates(minor_blocks: bool, vault_locked: bool):
    def require_minor_clearance(client_id, subject=None):
        if minor_blocks:
            return JSONResponse(
                {"error": {"code": "MINOR_BLOCKED", "message": "reşitlik"}},
                status_code=451,
            )
        return None

    def require_vault_open(client_id):
        if vault_locked:
            return JSONResponse(
                {"error": {"code": "VAULT_LOCKED", "message": "kasa"}},
                status_code=423,
            )
        return None

    return require_minor_clearance, require_vault_open


def _make_app(*, room_owner=None, minor_blocks=False, vault_locked=False):
    app = FastAPI()
    room = {"_owner": room_owner} if room_owner else {}
    executor = _FakeExecutor()
    require_minor, require_vault = _gates(minor_blocks, vault_locked)

    register_brain_hub_routes(
        app,
        rate_limit=lambda key, bucket: True,
        rate_identity=lambda request: "test-ip",
        get_room=lambda client_id: room,
        get_executor=lambda client_id: executor,
        gateway_provider=lambda: None,
        aspasia_provider=lambda: None,
        check_vault_interlock=lambda client_id: not vault_locked,
        require_vault_open=require_vault,
        require_minor_clearance=require_minor,
    )
    return app, room, executor


# ── 1. Kapı SIRASI: reşitlik (451) her şeyden önce, kasa (423) ondan sonra ──

def test_graph_minor_block_precedes_vault():
    app, _, _ = _make_app(minor_blocks=True, vault_locked=True)
    client = TestClient(app)
    resp = client.post("/api/brain/route", json={"client_id": "room-a", "message": "ilişki", "mode": "graph"})
    assert resp.status_code == 451
    assert resp.json()["error"]["code"] == "MINOR_BLOCKED"


def test_graph_vault_locked_after_minor_passes():
    app, _, _ = _make_app(minor_blocks=False, vault_locked=True)
    client = TestClient(app)
    resp = client.post("/api/brain/route", json={"client_id": "room-a", "message": "ilişki", "mode": "graph"})
    assert resp.status_code == 423
    assert resp.json()["error"]["code"] == "VAULT_LOCKED"


def test_memory_gate_order_minor_then_vault():
    app, _, _ = _make_app(minor_blocks=True, vault_locked=True)
    client = TestClient(app)
    resp = client.post("/api/brain/route", json={"client_id": "room-a", "message": "@hedef1 hafıza", "mode": "memory"})
    assert resp.status_code == 451
    app2, _, _ = _make_app(minor_blocks=False, vault_locked=True)
    client2 = TestClient(app2)
    resp2 = client2.post("/api/brain/route", json={"client_id": "room-a", "message": "@hedef1 hafıza", "mode": "memory"})
    assert resp2.status_code == 423


def test_company_vault_locked_blocks_capability():
    app, _, _ = _make_app(minor_blocks=False, vault_locked=True)
    client = TestClient(app)
    resp = client.post("/api/brain/route", json={"client_id": "room-a", "message": "x.com kurum", "mode": "company", "target": "example.com"})
    assert resp.status_code == 423


# ── 2. Oda mührü (403) + görev sahipliği (404 → 403) ──

def test_graph_foreign_room_seal_yields_403_without_room_name():
    app, _, _ = _make_app(room_owner="operator-b", vault_locked=False)
    token = bind_principal("operator-a")
    try:
        client = TestClient(app)
        resp = client.post("/api/brain/route", json={"client_id": "room-a", "message": "graf", "mode": "graph"})
        assert resp.status_code == 403
        body = resp.json()
        assert body["error"]["code"] == "ROOM_FORBIDDEN"
        assert "room-a" not in str(body), "403 gövdesi oda adını sızdırıyor"
    finally:
        reset_principal(token)


def test_graph_memory_room_seal_403():
    app, _, _ = _make_app(room_owner="operator-b", vault_locked=False)
    token = bind_principal("operator-a")
    try:
        client = TestClient(app)
        resp = client.post("/api/brain/route", json={"client_id": "room-a", "message": "@hedef1 hafıza", "mode": "memory"})
        assert resp.status_code == 403
        assert "room-a" not in str(resp.json())
    finally:
        reset_principal(token)


def test_graph_missing_task_returns_404_and_never_reaches_memory():
    app, _, executor = _make_app(vault_locked=False)
    client = TestClient(app)
    resp = client.post("/api/brain/route", json={"client_id": "room-a", "message": "graf", "mode": "graph", "task_id": "no_such_task_xyz"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "TASK_NOT_FOUND"


def test_graph_foreign_task_yields_403(monkeypatch):
    import backend.routes.brain_hub as brain_hub_module

    app, _, executor = _make_app(vault_locked=False)
    executor.tasks = {"task_foreign": {"evidence_chain": [], "task_id": "task_foreign"}}
    monkeypatch.setattr(brain_hub_module, "task_access", lambda task_id, principal: "forbidden")
    client = TestClient(app)
    resp = client.post("/api/brain/route", json={"client_id": "room-a", "message": "graf", "mode": "graph", "task_id": "task_foreign"})
    assert resp.status_code == 403
    body = resp.json()
    assert body["error"]["code"] == "TASK_FORBIDDEN"
    assert "task_foreign" not in str(body), "403 gövdesi görev kimliğini sızdırıyor"


def test_graph_allowed_task_returns_graph():
    app, _, executor = _make_app(vault_locked=False)
    executor.tasks = {"task_own": {"evidence_chain": [], "task_id": "task_own"}}
    client = TestClient(app)
    resp = client.post("/api/brain/route", json={"client_id": "room-a", "message": "graf", "mode": "graph", "task_id": "task_own"})
    assert resp.status_code == 200
    assert resp.json()["route"] == "graph"


# ── 3. Türetilmiş wired_pipelines envanteri ──

def test_capabilities_wired_pipelines_is_derived_and_reasoned(monkeypatch):
    monkeypatch.delenv("ENABLE_COMPANY_TARGETING", raising=False)
    monkeypatch.delenv("PINEAL_CAPABILITY_PROFILE", raising=False)
    app, _, _ = _make_app(vault_locked=False)
    client = TestClient(app)
    resp = client.get("/api/brain/capabilities?client_id=room-a")
    assert resp.status_code == 200
    wired = resp.json()["wired_pipelines"]
    assert set(wired) == {
        "deterministic_7_pillars",
        "cross_profiler",
        "aspasia_cross_exam",
        "lilith_strategy",
        "hook_studio",
        "shadow_executor",
        "memory_crystal",
        "evidence_graph",
        "company_recon",
        "phone_probe",
    }
    for name, entry in wired.items():
        assert set(entry) >= {"available", "reason"}, f"{name}: şema eksik"
        assert isinstance(entry["available"], bool)
        if not entry["available"]:
            assert entry["reason"], f"{name}: kapalıysa sebep boş olamaz"
    # Kapı env'siz (strict) iken kurum avı probları kapıyı gerekçe göstermeli
    assert wired["company_recon"]["available"] is False
    assert "gate_disabled" in (wired["company_recon"]["reason"] or "")


def test_capabilities_profile_summary_has_consent_only_section():
    app, _, _ = _make_app(vault_locked=False)
    client = TestClient(app)
    resp = client.get("/api/brain/capabilities?client_id=room-a")
    profiles = resp.json()["profiles"]
    assert profiles["consent_only"]["flags"]["ENABLE_CROSS_PLATFORM"] is False
    assert profiles["consent_only"]["total_count"] == 1
    assert profiles["local_core"]["total_count"] == 7


# ── 4. Kaynak bekçisi: sabit "true" envanteri geri gelemez ──

def test_brain_hub_has_no_hardcoded_true_pipeline_inventory():
    source = (REPO_ROOT / "backend" / "routes" / "brain_hub.py").read_text(encoding="utf-8")
    assert not re.search(r'"(deterministic_7_pillars|lilith_strategy|hook_studio)":\s*True', source), (
        "wired_pipelines sabit True envanterine geri döndü"
    )


# ── 5. /api/hook/generate kapı sırası: 429 → 451 → 423 ──

def _make_hook_app(*, rate_ok=True, minor_blocks=False, vault_locked=False):
    app = FastAPI()
    require_minor, require_vault = _gates(minor_blocks, vault_locked)

    register_hook_studio_routes(
        app,
        rate_limit=lambda key, bucket: rate_ok,
        rate_identity=lambda request: "test-ip",
        gateway_provider=lambda: None,
        get_executor=lambda client_id: None,
        require_vault_open=require_vault,
        require_minor_clearance=require_minor,
    )
    return app


def test_hook_generate_rate_limit_precedes_everything():
    app = _make_hook_app(rate_ok=False, minor_blocks=True, vault_locked=True)
    client = TestClient(app)
    resp = client.post("/api/hook/generate", json={"client_id": "room-a", "custom_goal": "test"})
    assert resp.status_code == 429


def test_hook_generate_minor_precedes_vault():
    app = _make_hook_app(rate_ok=True, minor_blocks=True, vault_locked=True)
    client = TestClient(app)
    resp = client.post("/api/hook/generate", json={"client_id": "room-a", "custom_goal": "test", "target_username": "@kid"})
    assert resp.status_code == 451


def test_hook_generate_vault_locked_after_minor_passes():
    app = _make_hook_app(rate_ok=True, minor_blocks=False, vault_locked=True)
    client = TestClient(app)
    resp = client.post("/api/hook/generate", json={"client_id": "room-a", "custom_goal": "test"})
    assert resp.status_code == 423


def test_hook_generate_vault_locked_blocked_without_target():
    # Hedef/reşitlik alanı olmadan da kasa kapısı geçerlidir (hedefsiz çağrı bile kasa ister).
    app = _make_hook_app(rate_ok=True, minor_blocks=False, vault_locked=True)
    client = TestClient(app)
    resp = client.post("/api/hook/generate", json={"client_id": "room-a"})
    assert resp.status_code == 423
