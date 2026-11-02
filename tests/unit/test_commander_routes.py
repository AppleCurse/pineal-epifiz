import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes.commander import register_commander_routes


@pytest.fixture
def test_app():
    app = FastAPI()
    register_commander_routes(
        app,
        rate_limit=lambda ident, ep: True,
        rate_identity=lambda req: "test_client",
        gateway_provider=lambda: None,
    )
    return app


def test_direct_agent_dispatch_returns_503_for_unwired_agents(test_app):
    """Doğrudan ajan çağrısı sahte 91% başarı üretmemeli; fail-closed 503 dönmelidir."""
    client = TestClient(test_app)
    response = client.post(
        "/api/commander/dispatch",
        json={
            "agent_id": "osint_investigator",
            "instruction": "Hedef analizi yap",
            "target_url": "https://x.com/target",
            "twin_url": "https://x.com/twin",
        },
    )
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unavailable"
    assert data["error"]["code"] == "DIRECT_AGENT_DISPATCH_UNAVAILABLE"


def test_inject_evidence_fails_closed_on_storage_error(test_app, monkeypatch, tmp_path):
    """Kanıt diske yazılamıyorsa sistem 200 dönüp sahte başarı iddia etmemeli; 500 fail-closed dönmelidir."""
    client = TestClient(test_app)

    # .pineal_memory dizini yerine düz bir dosya koyarak os.makedirs / open hatası tetikleyelim
    bad_dir = tmp_path / "bad_memory_file"
    bad_dir.write_text("not a dir", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    # .pineal_memory olarak normal dosya oluştur
    (tmp_path / ".pineal_memory").write_text("not a dir", encoding="utf-8")

    response = client.post(
        "/api/commander/inject",
        json={
            "evidence_type": "note",
            "evidence_value": "kritik_kanit",
            "note": "deneme kanıtı",
        },
    )
    assert response.status_code == 500
    data = response.json()
    assert data["error"]["code"] == "EVIDENCE_PERSISTENCE_FAILED"


def test_inject_evidence_succeeds_when_storage_writable(test_app, tmp_path, monkeypatch):
    """Kanıt diske yazılabiliyorsa başarıyla injected döner."""
    client = TestClient(test_app)
    monkeypatch.chdir(tmp_path)

    response = client.post(
        "/api/commander/inject",
        json={
            "evidence_type": "note",
            "evidence_value": "gercek_kanit",
            "note": "başarılı kayıt",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "injected"
    assert (tmp_path / ".pineal_memory" / "learnings.json").exists()


def test_phone_probe_rejects_locked_vault(test_app, monkeypatch):
    """Kasa kilitliyken telefon sorgusu OSINT çıkışı yapmamalı; 423 kilitli dönmelidir."""
    client = TestClient(test_app)
    from fastapi.responses import JSONResponse
    import backend.api as api_mod

    # _require_vault_open fonksiyonunun 423 kilitli döndüğü durumu simüle edelim
    monkeypatch.setattr(
        api_mod,
        "_require_vault_open",
        lambda cid: JSONResponse({"error": {"code": "VAULT_LOCKED"}}, status_code=423),
    )

    response = client.post(
        "/api/commander/phone-probe",
        json={"phone": "05551234567", "client_id": "test_room"},
    )
    assert response.status_code == 423
    assert response.json()["error"]["code"] == "VAULT_LOCKED"
