"""
ADIM 4 — Uçtan uca smoke testleri (gerçek ASGI uygulaması, mock'suz yüzey).

Amaç: sistemin "ayakta" sözleşmesini kilitlemek —
  1. / gerçek Svelte kabuğunu servis eder (id="app" + bundle script)
  2. /api/telemetry durum raporu verir
  3. /api/aspasia/chat 200 döner (500 regresyonu ebediyen kilitli)
  4. WS + initiate zinciri result üretir
"""
import os
import uuid

from fastapi.testclient import TestClient

from backend.api import app


def test_root_serves_svelte_shell():
    with TestClient(app) as client:
        r = client.get("/")
    if not os.path.isdir("frontend/dist"):
        # [2026-11-21] Dist yoksa arayüz monte EDİLMEZ — kaynak ağacı
        # (src/, package.json, .env.example) HTTP'ye açılmaz. Bu, güvenlik
        # düzeltmesinin sözleşmesidir; eski davranış (frontend/ mount) geri
        # gelirse bu test kırmızıya döner.
        assert r.status_code == 404
        return
    assert r.status_code == 200
    assert 'id="app"' in r.text, "index.html Svelte mount noktasını içermeli"
    # Eski sahte React artifact geri gelmemeli:
    assert "React Artifact" not in r.text


def test_telemetry_endpoint_reports_honest_state():
    with TestClient(app) as client:
        r = client.get("/api/telemetry", params={"client_id": f"smoke_{uuid.uuid4().hex[:6]}"})
    assert r.status_code == 200
    data = r.json()
    assert data["core"] is True
    assert "gateway" in data and "vault" in data


def test_aspasia_chat_endpoint_200():
    with TestClient(app) as client:
        r = client.post("/api/aspasia/chat", json={
            "client_id": f"smoke_{uuid.uuid4().hex[:6]}",
            "user_message": "Sistem ayakta mı?",
        })
    assert r.status_code == 200
    assert r.json().get("message")


def test_ws_initiate_produces_result():
    cid = f"smoke_{uuid.uuid4().hex[:6]}"
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/{cid}") as ws:
            r = client.post("/api/initiate", json={
                "client_id": cid, "url": "",
                "rituals": "çay", "playlist": "neşet ertaş", "envies": "bağ",
                "aggressiveness": 1.0, "evidence_th": 3,
            })
            assert r.status_code == 200
            saw_result = False
            for _ in range(100):
                m = ws.receive_json()
                t = m.get("type") or (m.get("event") or {}).get("event_type")
                if t == "result":
                    saw_result = True
                    assert m["status"] in ("completed", "failed", "halted_evidence", "halted_frequency")
                    break
            assert saw_result, "initiate sonrası WS'te result mesajı gelmeli"

# --- HERMETIC TEST GUARD: blocks live LLM calls ---
import pytest as _pytest
from agent_core.services.llm_gateway import LLMGateway as _LLMGateway

@_pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    async def _blocked(self, *a, **k):
        raise RuntimeError("REAL_LLM_CALL_NOT_EXECUTED: test kipi")
    monkeypatch.setattr(_LLMGateway, "query", _blocked)
