"""4. Göz — Round 3 (N1-N6 artık maddelerinin) REGRESYON KORUMASI.

N1  active_tasks tavan trim'i durum kör -> hayalet görev
    + GERÇEK TaskSnapshot enum durumları str() ile asla eşleşmiyordu
      (retention trim'i gerçek snapshot'larda hiç çalışmıyordu)
N2  RecursionError (derin nested JSON) -> kalıcı 500
N3  .corrupt.<ts> yedekleri sınırsız birikiyordu
N4  extract_username host substring kontrolü -> bakış-benzeri hostlar

Her test mutasyon dostudur: ilgili koruma geri alınınca KIZAR.
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest
from fastapi.testclient import TestClient


# --------------------------------------------------------------------------
# N1 — durum sınıflandırması: GERÇEK TaskSnapshot (PipelineStatus enum)
# --------------------------------------------------------------------------
def test_snapshot_status_enum_classified_correctly():
    """Python 3.11'de str(PipelineStatus.COMPLETED) == 'PipelineStatus.COMPLETED';
    prune mantığı .value üzerinden gitmelidir (aksi halde terminal hiç eşleşmez)."""
    from agent_core.domain.memory_models import TaskSnapshot
    from backend import api

    completed = TaskSnapshot(task_id="t1", status="completed")
    processing = TaskSnapshot(task_id="t2", status="processing")
    assert api._snapshot_status(completed) == "completed"
    assert api._snapshot_status(processing) == "processing"
    # string durumlar (eski format / sahte snapshot) de çalışır
    assert api._snapshot_status(type("S", (), {"status": "halted_user"})()) == "halted_user"


def test_prune_trims_real_terminal_snapshots_by_cap():
    """Kapanan gizli hata: str(enum) bug'ı ile gerçek TaskSnapshot'ların
    terminal durumu hiç eşleşmiyordu -> tavan trim'i canlıda çalışmıyordu.
    Ünite sahte string sınıfıyla YEŞİL görünüyordu; bu test GERÇEK modeli kullanır."""
    from agent_core.domain.memory_models import TaskSnapshot
    from backend import api

    api.app.state.rooms.clear()
    try:
        room = api.get_room("n1-enum")
        room["active_tasks"] = {}
        room["_active_tasks_ts"] = {}
        for i in range(300):
            snap = TaskSnapshot(task_id=f"op_t_{i:04d}", status="completed")
            room["active_tasks"][snap.task_id] = snap
            room["_active_tasks_ts"][snap.task_id] = time.monotonic()
        room["_stale_prune_ts"] = 0.0
        api._prune_room_stale_state(room)
        assert len(room["active_tasks"]) <= api._ROOM_ACTIVE_TASKS_CAP, (
            f"GERÇEK enum snapshot'larla tavan trim'i çalışmadı: {len(room['active_tasks'])}"
        )
    finally:
        api.app.state.rooms.clear()
        api._rooms_last_seen.clear()


def test_prune_never_drops_active_real_snapshots():
    """N1 hayalet kapanışı: 300 AKTİF gerçek snapshot -> hiçbiri silinmez."""
    from agent_core.domain.memory_models import TaskSnapshot
    from backend import api

    api.app.state.rooms.clear()
    try:
        room = api.get_room("n1-ghost")
        room["active_tasks"] = {}
        room["_active_tasks_ts"] = {}
        for i in range(300):
            snap = TaskSnapshot(task_id=f"op_p_{i:04d}", status="processing")
            room["active_tasks"][snap.task_id] = snap
            room["_active_tasks_ts"][snap.task_id] = time.monotonic()
        room["_stale_prune_ts"] = 0.0
        api._prune_room_stale_state(room)
        gone = [t for t in (f"op_p_{i:04d}" for i in range(300)) if t not in room["active_tasks"]]
        assert not gone, f"{len(gone)} AKTİF snapshot sessizce silindi (hayalet): {gone[:3]}"
    finally:
        api.app.state.rooms.clear()
        api._rooms_last_seen.clear()


def test_prune_mixed_terminal_trimmed_active_kept():
    """300 terminal + 10 aktif -> terminal en eskiden düşer; 10 aktifin TAMAMI korunur."""
    from agent_core.domain.memory_models import TaskSnapshot
    from backend import api

    api.app.state.rooms.clear()
    try:
        room = api.get_room("n1-mix")
        room["active_tasks"] = {}
        room["_active_tasks_ts"] = {}
        for i in range(300):
            snap = TaskSnapshot(task_id=f"op_t_{i:04d}", status="completed")
            room["active_tasks"][snap.task_id] = snap
            room["_active_tasks_ts"][snap.task_id] = time.monotonic()
        for i in range(10):
            snap = TaskSnapshot(task_id=f"op_p_{i:02d}", status="processing")
            room["active_tasks"][snap.task_id] = snap
            room["_active_tasks_ts"][snap.task_id] = time.monotonic()
        room["_stale_prune_ts"] = 0.0
        api._prune_room_stale_state(room)
        active = room["active_tasks"]
        kept_active = [t for t in (f"op_p_{i:02d}" for i in range(10)) if t in active]
        assert len(kept_active) == 10, f"aktif kaybı: {10 - len(kept_active)} hayalet"
        assert len(active) <= api._ROOM_ACTIVE_TASKS_CAP
    finally:
        api.app.state.rooms.clear()
        api._rooms_last_seen.clear()


def test_initiate_rejected_when_room_saturated_of_active():
    """Doymuş oda (aktif > tavan) -> /api/initiate 503 ACTIVE_TASKS_FULL;
    terminal yoğunluğu doyma YARATMAZ."""
    from unittest.mock import patch
    from agent_core.domain.memory_models import TaskSnapshot
    from backend import api

    api.app.state.rooms.clear()
    try:
        with patch("backend.api._check_vault_interlock", return_value=True):
            with TestClient(api.app, raise_server_exceptions=False) as client:
                room = api.get_room("n1-503")
                room.setdefault("active_tasks", {})
                room.setdefault("_active_tasks_ts", {})
                for i in range(260):
                    snap = TaskSnapshot(task_id=f"op_p_{i:04d}", status="processing")
                    room["active_tasks"][snap.task_id] = snap
                    room["_active_tasks_ts"][snap.task_id] = time.monotonic()
                r = client.post("/api/initiate", json={
                    "client_id": "n1-503", "url": "https://www.instagram.com/x",
                    "rituals": "", "playlist": "", "envies": "", "subject_consent": True})
                assert r.status_code == 503, f"doymuş oda 503 vermedi: {r.status_code} {r.text[:80]}"
                assert r.json()["error"]["code"] == "ACTIVE_TASKS_FULL"

                room2 = api.get_room("n1-term")
                room2.setdefault("active_tasks", {})
                room2.setdefault("_active_tasks_ts", {})
                for i in range(300):
                    snap = TaskSnapshot(task_id=f"op_t_{i:04d}", status="completed")
                    room2["active_tasks"][snap.task_id] = snap
                    room2["_active_tasks_ts"][snap.task_id] = time.monotonic()
                assert api._active_tasks_full(room2) is False, (
                    "terminal yoğunluğu doyma yarattı (503 sızması)"
                )
    finally:
        api.app.state.rooms.clear()
        api._rooms_last_seen.clear()


def test_aspasia_dispatch_none_means_rejected_not_accepted():
    """Gateway: dispatch -> None (kapasite reddi) artık accepted=False /
    reason='dispatch_rejected' döner (eski kod accepted=True + task_id=None
    ile 'dispatched' kaydediyordu — yalan kabul)."""
    from agent_core.aspasia.interface import AspasiaCommandGateway, AspasiaIntent

    class FakeGateway:
        def capture_calls(self, *a, **k):
            import contextlib
            return contextlib.nullcontext()

        async def query_json_chain(self, **kwargs):
            return AspasiaIntent(
                intent="run_profile_analysis",
                target_url="https://www.instagram.com/hedef",
            )

    gw = AspasiaCommandGateway(dispatch=lambda spec: None, gateway=FakeGateway())
    result = asyncio.run(gw.submit("hedefi analiz et", client_id="c1"))
    assert result.accepted is False, "dispatch=None kabul edilmiş gibi raporlandı"
    assert result.task_id is None
    assert result.reason == "dispatch_rejected"
    # audit da doğru kaydetmeli
    assert gw.audit()[-1]["status"] == "rejected"


def test_dispatch_returns_none_when_room_saturated():
    """_aspasia_command_dispatch (gerçek yol): doymuş odada görev BAŞLATMAZ,
    None döner (gateway bunu 'dispatch_rejected' olarak raporlar)."""
    from agent_core.domain.memory_models import TaskSnapshot
    from backend import api

    api.app.state.rooms.clear()
    try:
        room = api.get_room("n1-disp")
        room.setdefault("active_tasks", {})
        room.setdefault("_active_tasks_ts", {})
        for i in range(260):
            snap = TaskSnapshot(task_id=f"op_p_{i:04d}", status="processing")
            room["active_tasks"][snap.task_id] = snap
            room["_active_tasks_ts"][snap.task_id] = time.monotonic()
        t = api._aspasia_command_dispatch(
            {"client_id": "n1-disp", "target_url": "https://www.instagram.com/x", "goals": []}
        )
        assert t is None, "doymuş odaya dispatch yeni görev başlattı (sessiz kabul)"
    finally:
        api.app.state.rooms.clear()
        api._rooms_last_seen.clear()


# --------------------------------------------------------------------------
# N2 — RecursionError: derin nested JSON quarantine edilir, 500 YASAK
# --------------------------------------------------------------------------
def test_deeply_nested_learnings_quarantined_and_recovers(tmp_path, monkeypatch):
    from backend import api

    monkeypatch.setenv("PINEAL_MEMORY_PATH", str(tmp_path))
    api.app.state.rooms.clear()
    room = api.get_room("n2-deep")
    storage = room["executor"].memory.storage_path
    os.makedirs(storage, exist_ok=True)
    lp = os.path.join(storage, "learnings.json")
    with open(lp, "w", encoding="utf-8") as fh:
        fh.write("[" * 60000 + "]" * 60000)  # geçerli JSON, 60000 seviye

    try:
        with TestClient(api.app, raise_server_exceptions=False) as client:
            r1 = client.post("/api/override", json={"client_id": "n2-deep", "fact": "derin", "tag": "t"})
            r2 = client.post("/api/override", json={"client_id": "n2-deep", "fact": "derin2", "tag": "t"})
        assert r1.status_code == 200, (
            f"derin nested JSON hâlâ 500 üretiyor: {r1.status_code} {r1.text[:100]}"
        )
        assert r1.json().get("quarantined"), "derin dosya quarantine'edilmedi"
        assert r2.status_code == 200, "quarantine sonrası ikinci istek 500"
        backups = [f for f in os.listdir(storage) if f.startswith("learnings.json.corrupt.")]
        assert backups, "quarantine yedeği yok"
    finally:
        api.app.state.rooms.clear()
        api._rooms_last_seen.clear()


# --------------------------------------------------------------------------
# N3 — yedek dosyaları sınırlı (son N tanesi)
# --------------------------------------------------------------------------
def test_learnings_backups_are_capped(tmp_path, monkeypatch):
    from backend import api

    monkeypatch.setenv("PINEAL_MEMORY_PATH", str(tmp_path))
    monkeypatch.setenv("PINEAL_LEARNINGS_BACKUP_KEEP", "5")
    api.app.state.rooms.clear()
    room = api.get_room("n3-cap")
    storage = room["executor"].memory.storage_path
    os.makedirs(storage, exist_ok=True)
    lp = os.path.join(storage, "learnings.json")

    try:
        with TestClient(api.app, raise_server_exceptions=False) as client:
            for i in range(8):
                with open(lp, "w", encoding="utf-8") as fh:
                    fh.write(f"{{ bozuk {i}")
                time.sleep(0.002)
                r = client.post("/api/override", json={"client_id": "n3-cap", "fact": f"f{i}", "tag": "t"})
                assert r.status_code == 200
        backups = sorted(f for f in os.listdir(storage) if f.startswith("learnings.json."))
        assert len(backups) <= 5, f"yedekler tavanı aşıyor: {len(backups)} dosya"
        assert backups, "hiç yedek yok"
    finally:
        api.app.state.rooms.clear()
        api._rooms_last_seen.clear()


# --------------------------------------------------------------------------
# N4 — bakış-benzeri hostlar REDDEDİLİR; meşru hostlar kabul görür
# --------------------------------------------------------------------------
@pytest.mark.parametrize("url,expected", [
    ("https://notinstagram.com/ornek", ""),
    ("https://www.instagram.com.evil.com/ornek", ""),
    ("https://evilinstagram.com/ornek", ""),
    ("https://instagram.comx/ornek", ""),
    ("https://www.instagram.com/ornek/", "ornek"),
    ("https://instagram.com/ornek", "ornek"),
    ("https://sub.www.instagram.com/ornek", "ornek"),  # .instagram.com soneki
])
def test_extract_username_host_matching(url, expected):
    from agent_core.services.platform_registry import extract_username

    assert extract_username(url) == expected, f"{url!r} -> {extract_username(url)!r}"
