"""[PROD AUDIT 2026-10-12 · P0] GÖREV SAHİPLİĞİ kapatmasını KİLİTLEYEN testler.

Bu dosya neden var: oda mührü (``backend/security/principal.py``) yalnız ODA
ADI sınırını koruyordu, çünkü kanıt deposu oda başına AYRIŞMIYOR:

    ``agent_core/services/canonical_memory.py`` -> ``safe_child_path(storage_path,
    f"{task_id}.json")`` ve ``storage_path = PINEAL_MEMORY_PATH`` (tüm odalar
    aynı klasörü paylaşır; kayıtta oda/operatör damgası yok).

Canlı PoC ile ölçülen sonuç (production, iki ayrı operatör token'ı):

    alice room tasks BEFORE: ['op_...296645f1', 'op_...1f843326']
    bob sees in his OWN room: ['op_...296645f1', 'op_...1f843326']   ← sızıntı
    bob DELETE ... client_id=bob-own-room -> 200 memory_file_deleted:true
    alice room tasks AFTER : ['op_...1f843326']                      ← kanıt yok

Yani Bob, KENDİ ``client_id``'sini kullanarak Alice'in adli kanıtını diskten
kalıcı silebiliyordu. Kapatma: kalıcı ``task_id -> principal`` kaydı
(``backend/security/task_ownership.py``). Biri mührü gevşetirse BURADA KIRMIZI
YANAR.

Testler hermetiktir (dış ağ yok): FastAPI TestClient + gerçek oda/bellek durumu.
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from backend import api
from backend.security.task_ownership import (
    db_path,
    owner_of,
    record_owner,
    task_access,
)

ROOT_TOKEN = "prod-root-token-value"
ALICE_TOKEN = "alice-operator-token-1"
BOB_TOKEN = "bob-operator-token-2"
OPERATOR_TOKENS = f"alice:{ALICE_TOKEN},bob:{BOB_TOKEN}"

ALICE_ROOM = "alice-room"
BOB_ROOM = "bob-room"
VICTIM_TASK = "op_victim_0001"


@pytest.fixture
def prod_posture(monkeypatch, tmp_path):
    """Production duruşu + ÇOK OPERATÖRLÜ kimlik + İZOLE kanıt deposu.

    ``PINEAL_MEMORY_PATH`` tmp_path'e bağlanır: bu testlerin konusu zaten
    PAYLAŞILAN depo olduğundan iki odanın da aynı klasörü görmesi gerekir.
    """
    memory_root = tmp_path / "shared_memory"
    memory_root.mkdir()
    monkeypatch.setenv("PINEAL_ENV", "production")
    monkeypatch.setenv("PINEAL_TOKEN", ROOT_TOKEN)
    monkeypatch.setenv("PINEAL_OPERATOR_TOKENS", OPERATOR_TOKENS)
    monkeypatch.setenv("OPENROUTER_MAX_SPEND_USD", "50")
    monkeypatch.setenv("PINEAL_MAX_SPEND_USD", "50")
    monkeypatch.setenv("PINEAL_MEMORY_PATH", str(memory_root))
    monkeypatch.setenv("PINEAL_MEMORY_DB", str(memory_root / "hindsight.db"))
    monkeypatch.setenv("PINEAL_TASK_OWNERS_DB", str(memory_root / "task_owners.db"))
    # `app.state.minor_cases` SÜREÇ GENELEDİR (oda tahliyesi beyanı
    # düşürmesin diye bilinçli): testler arasında da temizlenmezse bir testin
    # beyanı diğerinin odasında kalır ve sahiplik kararı yanlış ölçülür.
    api.app.state.rooms.clear()
    api.app.state.minor_cases.clear()
    yield memory_root
    api.app.state.rooms.clear()
    api.app.state.minor_cases.clear()


@pytest.fixture
def client(prod_posture):
    return TestClient(api.app)


def _headers(token: str) -> dict:
    return {"X-API-Key": token}


def _write_evidence(memory_root, task_id: str) -> str:
    """Gerçek şemada bir kanıt dosyası yazar (CanonicalMemory okuyabilsin)."""
    path = memory_root / f"{task_id}.json"
    path.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "last_updated": "2026-10-12T00:00:00+00:00",
                "evidence": [{"agent": "mirror_truth", "kind": "observation"}],
                "confidence": 0.5,
            }
        ),
        encoding="utf-8",
    )
    return str(path)


def _seal_room(client: TestClient, room: str, token: str) -> None:
    """Odayı oluşturur ve çağıran principal'a mühürler (get_room üzerinden)."""
    r = client.get("/api/tasks", params={"client_id": room}, headers=_headers(token))
    assert r.status_code == 200, r.text


# --- 1. Ölçülen P0: liste sızıntısı ----------------------------------------


def test_stranger_cannot_see_victim_task_in_his_own_room(client, prod_posture):
    """Ölçülen kusur: Bob KENDİ odasında Alice'in görevini görüyordu."""
    _write_evidence(prod_posture, VICTIM_TASK)
    _seal_room(client, ALICE_ROOM, ALICE_TOKEN)
    _seal_room(client, BOB_ROOM, BOB_TOKEN)

    alice_ids = [
        t["task_id"]
        for t in client.get(
            "/api/tasks", params={"client_id": ALICE_ROOM}, headers=_headers(ALICE_TOKEN)
        ).json()["tasks"]
    ]
    assert VICTIM_TASK in alice_ids, "sahip kendi kanıtını görmeli"

    bob_ids = [
        t["task_id"]
        for t in client.get(
            "/api/tasks", params={"client_id": BOB_ROOM}, headers=_headers(BOB_TOKEN)
        ).json()["tasks"]
    ]
    assert VICTIM_TASK not in bob_ids, "başka operatörün kanıtı listede olamaz"
    assert bob_ids == []


def test_victim_task_stays_on_disk_after_stranger_lists(client, prod_posture):
    """Süzme dosyayı SİLMEMELİ; yalnız görünürlüğü keser."""
    path = _write_evidence(prod_posture, VICTIM_TASK)
    _seal_room(client, ALICE_ROOM, ALICE_TOKEN)
    client.get("/api/tasks", params={"client_id": BOB_ROOM}, headers=_headers(BOB_TOKEN))
    assert os.path.exists(path)


# --- 2. Ölçülen P0: kanıt yok etme -----------------------------------------


def test_stranger_cannot_delete_victim_evidence_from_his_own_room(client, prod_posture):
    """Ölçülen: DELETE -> 200 memory_file_deleted:true (adli kanıt diskten gitti)."""
    path = _write_evidence(prod_posture, VICTIM_TASK)
    _seal_room(client, ALICE_ROOM, ALICE_TOKEN)
    _seal_room(client, BOB_ROOM, BOB_TOKEN)

    destroyed = client.delete(
        f"/api/tasks/{VICTIM_TASK}",
        params={"client_id": BOB_ROOM},
        headers=_headers(BOB_TOKEN),
    )
    assert destroyed.status_code == 403, destroyed.text
    assert destroyed.json()["error"]["code"] == "ROOM_FORBIDDEN"
    assert os.path.exists(path), "kanıt diskte kalmalı"
    assert owner_of(VICTIM_TASK) == "alice"


def test_owner_can_still_delete_his_own_evidence(client, prod_posture):
    """Tüzük Madde 4/5: silme operatörün elindedir — mühür bunu KESMEMELİ."""
    path = _write_evidence(prod_posture, VICTIM_TASK)
    _seal_room(client, ALICE_ROOM, ALICE_TOKEN)

    r = client.delete(
        f"/api/tasks/{VICTIM_TASK}",
        params={"client_id": ALICE_ROOM},
        headers=_headers(ALICE_TOKEN),
    )
    assert r.status_code == 200, r.text
    assert r.json()["memory_file_deleted"] is True
    assert not os.path.exists(path)


def test_root_token_cannot_delete_operator_evidence(client, prod_posture):
    """``root`` AYRI bir kimliktir: operatörün kanıtını silemez."""
    path = _write_evidence(prod_posture, VICTIM_TASK)
    _seal_room(client, ALICE_ROOM, ALICE_TOKEN)
    _seal_room(client, "root-room", ROOT_TOKEN)

    r = client.delete(
        f"/api/tasks/{VICTIM_TASK}",
        params={"client_id": "root-room"},
        headers=_headers(ROOT_TOKEN),
    )
    assert r.status_code == 403
    assert os.path.exists(path)


# --- 3. Gövde sözleşmesi: sızıntı yok --------------------------------------


def test_task_forbidden_body_is_identical_to_room_forbidden(client, prod_posture):
    """Ret gövdesi oda reddiyle AYNI: görevin varlığı doğrulanmaz."""
    _write_evidence(prod_posture, VICTIM_TASK)
    _seal_room(client, ALICE_ROOM, ALICE_TOKEN)
    _seal_room(client, BOB_ROOM, BOB_TOKEN)

    task_denied = client.delete(
        f"/api/tasks/{VICTIM_TASK}",
        params={"client_id": BOB_ROOM},
        headers=_headers(BOB_TOKEN),
    )
    room_denied = client.get(
        "/api/tasks", params={"client_id": ALICE_ROOM}, headers=_headers(BOB_TOKEN)
    )
    assert task_denied.json() == room_denied.json()
    assert VICTIM_TASK not in task_denied.text
    assert ALICE_ROOM not in task_denied.text


def test_nonexistent_task_is_still_404_not_403(client, prod_posture):
    """Sahiplik mühürü 404 sözleşmesini DEĞİŞTİRMEMELİ (varlık kanalı açılmaz)."""
    _seal_room(client, BOB_ROOM, BOB_TOKEN)
    r = client.delete(
        "/api/tasks/no-such-task",
        params={"client_id": BOB_ROOM},
        headers=_headers(BOB_TOKEN),
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


# --- 4. Geçiş semantiği: sahipsiz kanıt ------------------------------------


def test_unowned_legacy_task_is_adopted_by_first_accessor(client, prod_posture):
    """Bu sürümden önce üretilmiş kanıt kilitlenip dışarıda bırakılmaz."""
    _write_evidence(prod_posture, VICTIM_TASK)
    _seal_room(client, BOB_ROOM, BOB_TOKEN)

    ids = [
        t["task_id"]
        for t in client.get(
            "/api/tasks", params={"client_id": BOB_ROOM}, headers=_headers(BOB_TOKEN)
        ).json()["tasks"]
    ]
    assert ids == [VICTIM_TASK]
    assert owner_of(VICTIM_TASK) == "bob"

    # Artık Alice göremez ve silemez: sahiplik kaydedildi.
    _seal_room(client, ALICE_ROOM, ALICE_TOKEN)
    alice_ids = [
        t["task_id"]
        for t in client.get(
            "/api/tasks", params={"client_id": ALICE_ROOM}, headers=_headers(ALICE_TOKEN)
        ).json()["tasks"]
    ]
    assert alice_ids == []
    assert (
        client.delete(
            f"/api/tasks/{VICTIM_TASK}",
            params={"client_id": ALICE_ROOM},
            headers=_headers(ALICE_TOKEN),
        ).status_code
        == 403
    )
    assert os.path.exists(prod_posture / f"{VICTIM_TASK}.json")


# --- 5. Development geriye dönük uyumu -------------------------------------


def test_no_principal_means_no_task_seal(monkeypatch, tmp_path):
    """Kimlik doğrulama kapalıyken mühür YOK (mevcut davranış korunur)."""
    monkeypatch.setenv("PINEAL_TASK_OWNERS_DB", str(tmp_path / "owners.db"))
    assert task_access(VICTIM_TASK, None) is None
    assert owner_of(VICTIM_TASK) is None, "kimlik yokken kayıt yazılmaz"


# --- 6. Kalıcılık: sahiplik süreçle birlikte kaybolmaz ---------------------


def test_ownership_survives_process_restart(monkeypatch, tmp_path):
    """Kayıt SQLite'ta: süreç içi sözlük bu işi görmezdi (silme kalıcıdır)."""
    db = tmp_path / "owners.db"
    monkeypatch.setenv("PINEAL_TASK_OWNERS_DB", str(db))
    record_owner("op_persist_1", "alice")
    assert db_path() == str(db)
    assert owner_of("op_persist_1") == "alice"
    # "Yeniden başlatma": aynı DB dosyası, yeni okuma.
    assert owner_of("op_persist_1") == "alice"
    assert task_access("op_persist_1", "bob") == "forbidden"
    assert task_access("op_persist_1", "alice") is None


def test_first_owner_wins_on_conflicting_record(monkeypatch, tmp_path):
    """INSERT OR IGNORE: sonradan gelen sahipliği DEĞİŞTİREMEZ."""
    monkeypatch.setenv("PINEAL_TASK_OWNERS_DB", str(tmp_path / "owners.db"))
    record_owner("op_race_1", "alice")
    record_owner("op_race_1", "bob")
    assert owner_of("op_race_1") == "alice"


def test_unusable_db_fails_open_without_blocking_tasks(monkeypatch, tmp_path):
    """Kayıt okunamıyorsa görev ERİŞİLEBİLİR kalır (kayıt kanıt değildir)."""
    blocked = tmp_path / "a_file_not_a_dir"
    blocked.write_text("x", encoding="utf-8")
    monkeypatch.setenv(
        "PINEAL_TASK_OWNERS_DB", str(blocked / "nested" / "owners.db")
    )
    assert owner_of("op_x") is None
    assert task_access("op_x", "alice") is None


# --- 7. Görev oluşturma sahipliği kaydediyor mu? ---------------------------


def test_initiate_records_the_owner_before_evidence_exists(client, prod_posture, monkeypatch):
    """/api/initiate kanıt dosyası oluşmadan ÖNCE sahibi yazmalı."""
    monkeypatch.setattr(api, "_check_vault_interlock", lambda _cid: True)

    async def _no_run_mission(req, task_id):  # görev gerçekten koşmasın
        return None

    monkeypatch.setattr(api, "run_mission", _no_run_mission)

    r = client.post(
        "/api/initiate",
        params={},
        headers=_headers(ALICE_TOKEN),
        json={"client_id": ALICE_ROOM, "url": "", "rituals": "", "playlist": "", "envies": ""},
    )
    assert r.status_code == 200, r.text
    task_id = r.json()["task_id"]
    assert owner_of(task_id) == "alice"


# --- 8. Çocuk kilidi çapraz operatör mühürsüzdü (GO_LIVE.md §5.1) ----------


def _declare_minor(client: TestClient, room: str, token: str, **extra):
    payload = {
        "client_id": room,
        "subject_is_minor": True,
        "case_type": "missing",
        "family_notified": True,
        "reason": "kayip vakasi - aile haberdar",
        "verified": True,
        "council_approvals": ["alice", "carol"],
        "case_id": "case-001",
    }
    payload.update(extra)
    return client.post("/api/minor/case", json=payload, headers=_headers(token))


def test_stranger_cannot_read_victim_minor_state(client, prod_posture):
    """Ölçülen: GET /api/minor/state başka operatörün odası için 200 dönüyordu."""
    _seal_room(client, ALICE_ROOM, ALICE_TOKEN)
    _seal_room(client, BOB_ROOM, BOB_TOKEN)

    own = client.get(
        "/api/minor/state", params={"client_id": BOB_ROOM}, headers=_headers(BOB_TOKEN)
    )
    assert own.status_code == 200

    stolen = client.get(
        "/api/minor/state", params={"client_id": ALICE_ROOM}, headers=_headers(BOB_TOKEN)
    )
    assert stolen.status_code == 403, stolen.text
    assert stolen.json()["error"]["code"] == "ROOM_FORBIDDEN"
    assert ALICE_ROOM not in stolen.text


def test_stranger_cannot_unlock_victim_child_lock(client, prod_posture):
    """EN KRİTİK: /api/minor/clear çocuk KİLİDİNİ AÇAR — çapraz operatör olamaz."""
    _seal_room(client, ALICE_ROOM, ALICE_TOKEN)
    assert _declare_minor(client, ALICE_ROOM, ALICE_TOKEN).status_code == 200

    attack = client.post(
        "/api/minor/clear",
        json={"client_id": ALICE_ROOM},
        headers=_headers(BOB_TOKEN),
    )
    assert attack.status_code == 403, attack.text
    assert attack.json()["error"]["code"] == "ROOM_FORBIDDEN"

    still_locked = client.get(
        "/api/minor/state", params={"client_id": ALICE_ROOM}, headers=_headers(ALICE_TOKEN)
    ).json()
    assert still_locked["declared"] is True, "beyan silinmemeli"


def test_stranger_cannot_declare_into_victim_room(client, prod_posture):
    """Başka operatörün odasına beyan KONULAMAZ (DoS / sahte onaylı vaka)."""
    _seal_room(client, ALICE_ROOM, ALICE_TOKEN)
    attack = _declare_minor(client, ALICE_ROOM, BOB_TOKEN)
    assert attack.status_code == 403, attack.text
    assert (
        client.get(
            "/api/minor/state",
            params={"client_id": ALICE_ROOM},
            headers=_headers(ALICE_TOKEN),
        ).json()["declared"]
        is False
    )


def test_minor_endpoints_still_work_for_the_owner(client, prod_posture):
    """Mühür sahibi operatörü KESMEMELİ: beyan koy, oku, kaldır."""
    _seal_room(client, ALICE_ROOM, ALICE_TOKEN)
    assert _declare_minor(client, ALICE_ROOM, ALICE_TOKEN).status_code == 200
    state = client.get(
        "/api/minor/state", params={"client_id": ALICE_ROOM}, headers=_headers(ALICE_TOKEN)
    ).json()
    assert state["declared"] is True and state["case_id"] == "case-001"
    cleared = client.post(
        "/api/minor/clear", json={"client_id": ALICE_ROOM}, headers=_headers(ALICE_TOKEN)
    )
    assert cleared.status_code == 200 and cleared.json()["cleared"] is True


def test_minor_seal_does_not_create_a_room(client, prod_posture):
    """Salt-okunur denetim oda AÇMAMALI (durum sorgusu bellek tüketmez)."""
    before = len(api.app.state.rooms)
    client.get(
        "/api/minor/state", params={"client_id": "hicbir-oda-yok"}, headers=_headers(BOB_TOKEN)
    )
    assert len(api.app.state.rooms) == before
