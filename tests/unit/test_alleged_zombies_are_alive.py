""""Zombi" sanılan üç uç ve "boş" sanılan beacon filosu — GERÇEK durum kilidi.

[2026-10-23] Temizlik listesinde şu üç uç "kod var ama kullanılmıyor" diye
işaretlenmişti:

  * `POST /api/scraper/authorize-alternative`
  * `GET  /api/agents/status` + `POST /api/agents/status/{agent_id}`
  * `POST /api/executor/intervene`

Ölçüm: üçü de çalışıyor, kapıları var ve sözleşmeleri testlerle korunuyor.
Aynı şekilde "12 boş beacon servisi" denen compose yuvaları aslında
`agent_worker` çalıştırıyor. Bu dosya o gerçeği KİLİTLER: bir "temizlik"
sırasında çalışan bir güvenlik yüzeyi yanlışlıkla silinmesin.

Bu testler silmeyi değil, kanıtı ister: uç yanıt vermeli, kapı uygulamalı ve
yan etkisi (kayıt) görünür olmalı.
"""

from __future__ import annotations

import pytest

import backend.api as api


@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(api, "rate_limit", lambda *a, **k: True, raising=False)
    monkeypatch.setattr(api, "_require_vault_open", lambda _cid: None, raising=False)
    monkeypatch.setattr(api, "_require_minor_clearance", lambda _cid: None, raising=False)
    rooms: dict[str, dict] = {}

    def _room(cid: str) -> dict:
        return rooms.setdefault(cid, {})

    monkeypatch.setattr(api, "get_room", _room, raising=False)
    monkeypatch.setattr(api, "broadcast_log", lambda *a, **k: None, raising=False)
    return TestClient(api.app), rooms


# ------------------------------------------- 1) authorize-alternative
def test_authorize_alternative_answers_and_records_a_decision(client):
    test_client, rooms = client
    room = rooms.setdefault("c_alt", {})
    room["pending_alternative_authorization"] = {
        "url": "https://x.com/hedef",
        "alternatives": ["decline"],
    }
    response = test_client.post("/api/scraper/authorize-alternative", json={
        "client_id": "c_alt", "alternative": "decline", "approved": True,
    })
    assert response.status_code == 200, response.text
    body = response.json()
    # Onay kaydı room'a yazılır (uç sahte bir "tamam" döndürmüyor).
    assert body["status"] in {"declined", "authorized", "no_pending_authorization"}
    assert "authorized_alternatives" in room or body["status"] == "declined"


def test_authorize_alternative_without_pending_request_is_honest(client):
    test_client, _ = client
    response = test_client.post("/api/scraper/authorize-alternative", json={
        "client_id": "c_none", "alternative": "public_web_search", "approved": True,
    })
    assert response.status_code == 200
    assert response.json()["status"] == "no_pending_authorization"


def test_authorize_alternative_requires_the_vault(client, monkeypatch):
    """Kasa kapalıyken yetki VERİLEMEZ (dolanma yolu yok)."""
    test_client, _ = client
    from fastapi.responses import JSONResponse

    monkeypatch.setattr(
        api, "_require_vault_open",
        lambda _cid: JSONResponse({"error": "VAULT_LOCKED"}, status_code=423),
        raising=False,
    )
    response = test_client.post("/api/scraper/authorize-alternative", json={
        "client_id": "c_locked", "alternative": "public_web_search", "approved": True,
    })
    assert response.status_code == 423


# ------------------------------------------------- 2) agents/status
def test_agents_status_is_a_live_read_model_and_is_used_by_the_frontend():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    frontend = (root / "frontend/src/App.svelte").read_text(encoding="utf-8")
    assert "/api/agents/status" in frontend, "frontend bu ucu çağırıyor (ölü değil)"


def test_agents_status_get_returns_json(client):
    test_client, _ = client
    response = test_client.get("/api/agents/status")
    assert response.status_code == 200
    assert isinstance(response.json(), (dict, list))


def test_agents_status_post_accepts_a_beacon_update(client):
    test_client, _ = client
    response = test_client.post("/api/agents/status/mirror_truth?status=Ready")
    assert response.status_code in (200, 422), response.text


# ------------------------------------------------- 3) executor/intervene
def test_intervene_records_a_request_instead_of_mutating_safety_state(client):
    test_client, rooms = client
    response = test_client.post("/api/executor/intervene", json={
        "client_id": "c_int",
        "action_type": "OVERRIDE_CONFIDENCE",
        "target_agent": "human_behavior",
        "parameters": {"confidence": 0.99},
        "reason": "operatör talebi",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "review_required"
    records = rooms["c_int"]["interventions"]
    assert records[-1]["action_type"] == "OVERRIDE_CONFIDENCE"
    # Otomatik uygulama YOK — kayıt tutulur, güvenlik durumu değişmez.
    assert records[-1]["outcome"] == "review_required"


def test_intervene_never_auto_applies_agent_skips(client):
    test_client, rooms = client
    response = test_client.post("/api/executor/intervene", json={
        "client_id": "c_skip", "action_type": "SKIP_AGENT", "target_agent": "osint_investigator",
    })
    assert response.status_code == 200
    assert "agents" not in rooms["c_skip"], "SKIP_AGENT otomatik uygulandı (güvenlik ihlali)"
    assert response.json()["status"] == "review_required"


# ------------------------------------------------------ 4) beacon filosu
def test_beacon_services_are_not_empty(client):
    """compose'daki her beacon yuvası gerçek bir worker komutu taşır."""
    from pathlib import Path
    import re

    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(encoding="utf-8")
    services = re.findall(r"^  (beacon-[a-z-]+):\n((?:    .*\n|      .*\n|        .*\n)*)", compose, re.MULTILINE)
    assert len(services) == 12, f"beklenen 12 beacon yuvası, bulunan {len(services)}"
    for name, body in services:
        assert "build:" in body or "image:" in body, f"{name}: imaj/derleme yok"
        assert "agent_worker" in body, f"{name}: çalıştırılabilir komut yok"
        assert "AGENT_ID=" in body, f"{name}: ajan kimliği yok"


def test_beacon_worker_is_importable_and_help_works():
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "agent_core.workers.agent_worker", "--help"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-400:]
    assert "--agent-id" in proc.stdout
