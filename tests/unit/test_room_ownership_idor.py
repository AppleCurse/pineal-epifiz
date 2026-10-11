"""[PROD AUDIT 2026-10-11 · P0] IDOR kapatmasını KİLİTLEYEN regresyon testleri.

Bu dosya neden var: ``client_id`` istemcinin serbestçe seçtiği bir dizedir ve
tek başına bir güvenlik sınırı DEĞİLDİR. Dağıtımın tek bir kimliği
(``PINEAL_TOKEN``) olduğu sürece, o kimliği bilen HERKES ``client_id`` yazarak
BAŞKA bir operatörün odasına erişebiliyordu. Canlı PoC ile ölçülen sonuçlar:

    GET  /api/tasks?client_id=<kurban>        -> 200 (görev listesi okundu)
    GET  /api/telemetry?client_id=<kurban>    -> 200 (telemetri okundu)
    POST /api/vault  client_id=<kurban>       -> 200 (kurbanın LLM anahtarı ve
                                                    X oturum çerezi DEĞİŞTİRİLDİ)
    DELETE /api/tasks/<gerçek>?client_id=...  -> 200 {"memory_file_deleted":true}
                                                 (ADLİ KANIT DİSKTEN SİLİNDİ)
    /ws/<kurban>                              -> auth_ok + CANLI telemetri karesi

Kapatma: token -> OPERATÖR KİMLİĞİ (principal) -> oda o kimliğe MÜHÜRLÜ.
Bu testler o mührü kilitler: biri mührü gevşetirse BURADA KIRMIZI YANAR.

Testler hermetiktir (dış ağ yok): FastAPI TestClient + gerçek oda durumu.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_core.utils import security as sec
from backend import api
from backend.security.principal import (
    RoomForbiddenError,
    bind_principal,
    enforce_room_ownership,
    reset_principal,
)

ROOT_TOKEN = "prod-root-token-value"
ALICE_TOKEN = "alice-operator-token-1"
BOB_TOKEN = "bob-operator-token-2"
OPERATOR_TOKENS = f"alice:{ALICE_TOKEN},bob:{BOB_TOKEN}"


@pytest.fixture
def prod_posture(monkeypatch):
    """Production duruşu + ÇOK OPERATÖRLÜ kimlik (gerçek dağıtım biçimi)."""
    monkeypatch.setenv("PINEAL_ENV", "production")
    monkeypatch.setenv("PINEAL_TOKEN", ROOT_TOKEN)
    monkeypatch.setenv("PINEAL_OPERATOR_TOKENS", OPERATOR_TOKENS)
    monkeypatch.setenv("OPENROUTER_MAX_SPEND_USD", "50")
    monkeypatch.setenv("PINEAL_MAX_SPEND_USD", "50")
    api.app.state.rooms.clear()
    yield
    api.app.state.rooms.clear()


@pytest.fixture
def client(prod_posture):
    return TestClient(api.app)


# --- 1. Kimlik çözümü ------------------------------------------------------


def test_each_operator_token_resolves_to_a_distinct_principal(prod_posture):
    """Tek token = tek kimlik kusurunun panzehiri: token'lar AYRIŞMALI."""
    assert sec.resolve_principal(ROOT_TOKEN) == "root"
    assert sec.resolve_principal(ALICE_TOKEN) == "alice"
    assert sec.resolve_principal(BOB_TOKEN) == "bob"
    assert len({"root", "alice", "bob"}) == 3


def test_operator_tokens_are_accepted_by_the_auth_gate(prod_posture):
    """Ölçülen kusur: resolve_principal doğru çalışıyordu ama token_matches
    yalnız PINEAL_TOKEN'ı kabul ettiği için operatörler 401 alıyordu ve mühür
    hiç devreye giremiyordu. Auth kapısı TÜM tanımlı token'ları kabul etmeli.
    """
    assert sec.token_matches(ROOT_TOKEN) is True
    assert sec.token_matches(ALICE_TOKEN) is True
    assert sec.token_matches(BOB_TOKEN) is True


def test_unknown_or_empty_token_never_authenticates(prod_posture):
    assert sec.token_matches("not-a-configured-token") is False
    assert sec.token_matches("") is False
    assert sec.token_matches(None) is False
    assert sec.resolve_principal("not-a-configured-token") is None
    assert sec.resolve_principal("") is None


def test_malformed_operator_entries_do_not_break_the_others(monkeypatch):
    """Bozuk bir satır tüm operatör listesini kullanılamaz hale getirmemeli."""
    monkeypatch.setenv("PINEAL_TOKEN", ROOT_TOKEN)
    monkeypatch.setenv(
        "PINEAL_OPERATOR_TOKENS",
        "geçersiz etiket!:tok12345678,short:abc,good:valid-token-99",
    )
    # 'geçersiz etiket!' -> geçersiz karakter; 'short:abc' -> token < 8 karakter
    assert sec.resolve_principal("valid-token-99") == "good"
    assert sec.resolve_principal("tok12345678") is None
    assert sec.resolve_principal("abc") is None


def test_bare_operator_token_gets_a_stable_positional_principal(monkeypatch):
    """`etiket:token` yerine çıplak token yazılırsa kimlik yine kararlı olur."""
    monkeypatch.setenv("PINEAL_TOKEN", ROOT_TOKEN)
    monkeypatch.setenv("PINEAL_OPERATOR_TOKENS", "bare-token-value-123")
    assert sec.resolve_principal("bare-token-value-123") == "op0"


# --- 2. Oda sahipliği mühürü (birim) ---------------------------------------


def test_unowned_room_is_sealed_by_the_first_principal():
    room: dict = {"client_id": "c1"}
    assert enforce_room_ownership("c1", room, "alice") is None
    assert room["_owner"] == "alice"


def test_owner_keeps_access_and_stranger_is_refused():
    room: dict = {"client_id": "c1", "_owner": "alice"}
    assert enforce_room_ownership("c1", room, "alice") is None
    assert enforce_room_ownership("c1", room, "bob") == "forbidden"
    # Ret, odayı SAHİPSİZ BIRAKMAZ / devretmez: mühür alice'te kalır.
    assert room["_owner"] == "alice"


def test_no_principal_means_no_seal_development_back_compat():
    """Development (auth kapalı) davranışı BİREBİR korunur: mühür uygulanmaz."""
    room: dict = {"client_id": "c1", "_owner": "alice"}
    assert enforce_room_ownership("c1", room, None) is None
    assert room["_owner"] == "alice"  # değer DEĞİŞMEDİ


def test_principal_contextvar_is_scoped_and_reversible():
    assert api._get_principal() is None
    token = bind_principal("alice")
    try:
        assert api._get_principal() == "alice"
    finally:
        reset_principal(token)
    assert api._get_principal() is None


# --- 3. Uçtan uca HTTP: çapraz-operatör erişimi REDDEDİLMELİ ---------------


def test_stranger_cannot_read_victim_task_list(client):
    alice = {"X-API-Key": ALICE_TOKEN}
    bob = {"X-API-Key": BOB_TOKEN}
    victim_room = "alice-private-room"

    r = client.post("/api/vault", headers=alice,
                    json={"client_id": victim_room,
                          "api_key": "sk-or-v1-alice-real-key"})
    assert r.status_code == 200, r.text

    stolen = client.get("/api/tasks", headers=bob,
                        params={"client_id": victim_room})
    assert stolen.status_code == 403, stolen.text
    assert stolen.json()["error"]["code"] == "ROOM_FORBIDDEN"
    # Oda adı YANITTA SIZDIRILMAZ (varlığı bile bilgi).
    assert victim_room not in stolen.text


def test_stranger_cannot_read_victim_telemetry_or_vault_status(client):
    alice = {"X-API-Key": ALICE_TOKEN}
    bob = {"X-API-Key": BOB_TOKEN}
    room = "alice-telemetry-room"
    client.post("/api/vault", headers=alice,
                json={"client_id": room, "api_key": "sk-or-v1-alice-real-key"})

    for path in ("/api/telemetry", "/api/vault/status"):
        r = client.get(path, headers=bob, params={"client_id": room})
        assert r.status_code == 403, f"{path} -> {r.status_code} {r.text}"
        assert r.json()["error"]["code"] == "ROOM_FORBIDDEN"


def test_stranger_cannot_overwrite_victim_vault(client):
    """Ölçülen en ağır yazma saldırısı: kurbanın LLM anahtarı/çerezi swap."""
    alice = {"X-API-Key": ALICE_TOKEN}
    bob = {"X-API-Key": BOB_TOKEN}
    room = "alice-vault-room"
    client.post("/api/vault", headers=alice,
                json={"client_id": room, "api_key": "sk-or-v1-alice-real-key"})

    hijack = client.post("/api/vault", headers=bob, json={
        "client_id": room,
        "api_key": "sk-or-v1-bob-swapped-in",
        "x_cookie": "auth_token=BOB_SESSION; ct0=fakefakefake1234",
    })
    assert hijack.status_code == 403, hijack.text
    assert hijack.json()["error"]["code"] == "ROOM_FORBIDDEN"

    # Kurbanın kasası BOZULMADI: bob'un anahtarı/çerezi uygulanmadı.
    status = client.get("/api/vault/status", headers=alice,
                        params={"client_id": room})
    assert status.status_code == 200
    body = status.json()
    assert body["has_cookie"] is False, "saldırganın çerezi kurbanın odasına işlendi"


def test_stranger_cannot_delete_victim_evidence(client):
    """Ölçülen: DELETE ... memory_file_deleted=true (kanıt diskten silindi)."""
    alice = {"X-API-Key": ALICE_TOKEN}
    bob = {"X-API-Key": BOB_TOKEN}
    room = "alice-evidence-room"
    client.post("/api/vault", headers=alice,
                json={"client_id": room, "api_key": "sk-or-v1-alice-real-key"})

    destroyed = client.delete("/api/tasks/any-task-id", headers=bob,
                              params={"client_id": room})
    assert destroyed.status_code == 403, destroyed.text
    assert destroyed.json()["error"]["code"] == "ROOM_FORBIDDEN"


def test_owner_retains_full_access_to_own_room(client):
    """Kapatma, MEŞRU operatörü kilitlememeli (yoksa ürün kullanılamaz)."""
    alice = {"X-API-Key": ALICE_TOKEN}
    room = "alice-own-room"
    assert client.post("/api/vault", headers=alice, json={
        "client_id": room, "api_key": "sk-or-v1-alice-real-key"}).status_code == 200
    for path in ("/api/tasks", "/api/telemetry", "/api/vault/status"):
        r = client.get(path, headers=alice, params={"client_id": room})
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text}"


def test_anonymous_request_is_still_unauthorized(client):
    r = client.get("/api/tasks", params={"client_id": "anything"})
    assert r.status_code == 401


def test_room_forbidden_error_does_not_leak_the_room_name():
    exc = RoomForbiddenError("alice-secret-room-name")
    assert "alice-secret-room-name" not in str(exc)
    body = api.forbidden_body(openai_style=False, error_factory=api._openai_error)
    assert "alice-secret-room-name" not in str(body)
    assert body["error"]["code"] == "ROOM_FORBIDDEN"
