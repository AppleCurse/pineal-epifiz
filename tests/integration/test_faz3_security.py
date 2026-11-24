"""
FAZ 3 / G3.1+G3.2 — güvenlik sözleşmeleri (auth, rate limit, deneysel yollar).
"""
import os
import uuid

from fastapi.testclient import TestClient

from backend.api import app, RATE_LIMITS


def _cid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def test_open_mode_when_token_unset(monkeypatch):
    """PINEAL_TOKEN tanımsız: yerel araç kipi — korumasız ama ÇALIŞIR (geriye uyumluluk)."""
    monkeypatch.delenv("PINEAL_TOKEN", raising=False)
    with TestClient(app) as client:
        r = client.get("/api/telemetry", params={"client_id": _cid("open")})
    assert r.status_code == 200


def test_token_mode_blocks_without_key(monkeypatch):
    monkeypatch.setenv("PINEAL_TOKEN", "gizli-anahtar-123")
    with TestClient(app) as client:
        r = client.get("/api/telemetry", params={"client_id": _cid("auth")})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_token_mode_allows_with_key(monkeypatch):
    monkeypatch.setenv("PINEAL_TOKEN", "gizli-anahtar-123")
    with TestClient(app) as client:
        r = client.get("/api/telemetry",
                       params={"client_id": _cid("auth")},
                       headers={"X-API-Key": "gizli-anahtar-123"})
    assert r.status_code == 200


def test_static_ui_not_blocked_by_token(monkeypatch):
    """Statik UI token kipinde de servis edilmeli (login ekranı diye bir şey yok)."""
    monkeypatch.setenv("PINEAL_TOKEN", "gizli-anahtar-123")
    with TestClient(app) as client:
        r = client.get("/")
    if not os.path.isdir("frontend/dist"):
        # Dist yoksa arayüz monte edilmez (2026-11-21 güvenlik düzeltmesi);
        # token kontrolü statik yolu etkilemez — 404 kalır.
        assert r.status_code == 404
        return
    assert r.status_code == 200


def test_initiate_rate_limit_429(monkeypatch):
    monkeypatch.delenv("PINEAL_TOKEN", raising=False)
    monkeypatch.setitem(RATE_LIMITS, "initiate", (2, 60))
    cid = _cid("rl")
    with TestClient(app) as client:
        codes = [client.post("/api/initiate", json={
            "client_id": cid, "url": "", "rituals": "a", "playlist": "b",
            "envies": "c", "aggressiveness": 1.0, "evidence_th": 3, "subject_consent": True}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_experimental_paths_renamed():
    """D5: shadow/chat/interpreter yolları /api/experimental/* altında; eski yollar kapalı."""
    with TestClient(app) as client:
        old = client.post("/api/shadow/analyze", json={})
        from backend import api as api_mod
        api_mod.get_room("default")["vault"]["or_key"] = True
        new = client.post("/api/experimental/shadow/analyze", json={"posts": [], "bio": "", "client_id": "default"})
    # Eski yol kapalı: API rotası yok -> statik mount 405/404 döner, işleme ALINMAZ
    assert old.status_code in (404, 405)
    assert new.status_code == 200


def test_error_model_consistent(monkeypatch):
    """429 yanıtı da tutarlı hata modelinde: {"error": {code, message}}."""
    monkeypatch.delenv("PINEAL_TOKEN", raising=False)
    monkeypatch.setitem(RATE_LIMITS, "aspasia", (1, 60))
    cid = _cid("em")
    with TestClient(app) as client:
        from backend import api as api_mod
        api_mod.get_room(cid)["vault"]["or_key"] = True
        for _ in range(2):
            r = client.post("/api/aspasia/chat", json={"client_id": cid, "user_message": "x"})
    assert r.status_code == 429
    body = r.json()
    assert set(body.keys()) == {"error"} and {"code", "message"} <= set(body["error"].keys())

# --- HERMETIC TEST GUARD: blocks live LLM calls ---
import pytest as _pytest
from agent_core.services.llm_gateway import LLMGateway as _LLMGateway

@_pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    async def _blocked(self, *a, **k):
        raise RuntimeError("REAL_LLM_CALL_NOT_EXECUTED: test kipi")
    monkeypatch.setattr(_LLMGateway, "query", _blocked)
