"""[B0] Kokpit.destek & güvenli devam döngüsü — uçtan uca ve negatif testler.

Kapsanan kabul boşlukları (B0 talimatı §1-§6):
  * E2E: engel → görünür destek talebi (WS + REST) → yetkili destek yanıtı →
    doğru talebin çözülmesi → kaldığı yerden devam → doğrulanmış sonuç.
  * Negatifler: başka operatörün görevi (403), çift yanıt (409), eşzamanlı
    resume (409), eksik destekle resume (409), kasa yeniden kilitlendi (423),
    süreç yeniden başlayınca destek sağlama (dosya deposundan).
  * Kalıcılık: checkpoint dosyadan geri yüklenir; başka görevin çıktısı
    mühürsüz YÜKLENEMEZ.
  * Hassas veri: destek görünümü input/anahtar/çerez İÇERMEZ.
  * UI kablolama (statik): AwaitingHuman dalı, geri yükleme, panel.

“Gerçek UI/API/executor bağlantısı”: gerçek FastAPI uygulaması + gerçek WS
+ gerçek PinealExecutor (yalnız LLM/rotlama uçları mock — canlı LLM bu
ortamda kapalı). Tarayıcı DOM'u bu ortamda ÇALIŞTIRILMAZ; UI sözleşmesi
statik kablolama testleriyle kilitlenir (aşağıda) — bu sınır raporda
“çalıştırılmayan” olarak işaretlenir.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from agent_core.scraper.vault_gate import VaultLockedError
from agent_core.services.uncertainty_engine import UncertaintyReport
from backend import api
from backend import checkpoint_store as ckpt

REPO_ROOT = api.os.path.dirname(  # tests/integration/… → repo kökü
    api.os.path.dirname(api.os.path.dirname(api.os.path.abspath(__file__)))
)

ROOT_TOKEN = "cockpit-root-token"
ALICE_TOKEN = "alice-ck-token-1"
BOB_TOKEN = "bob-ck-token-2"
OPERATOR_TOKENS = f"alice:{ALICE_TOKEN},bob:{BOB_TOKEN}"


class _Style(BaseModel):
    communication_tone: str = "analitik"
    complexity_level: str = "teknik"
    humor_style: str = "kuru mizah"
    social_orientation: str = "gözlemci"
    confidence: float = 0.9
    data_confidence: bool = True


def _report(confidence: float = 0.95) -> UncertaintyReport:
    return UncertaintyReport(
        is_suspicious=False,
        confidence=confidence,
        reason="yeterli kanıt" if confidence >= 0.65 else "güven düşük",
        data_score=0.9 if confidence >= 0.65 else 0.3,
        breakdown={},
        no_decision=False,
    )


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """İzole depo + dev kimliği (auth kapalı)."""
    memory_root = tmp_path / "memory"
    monkeypatch.setenv("PINEAL_MEMORY_PATH", str(memory_root))
    monkeypatch.setenv("PINEAL_CHECKPOINT_PATH", str(memory_root / "checkpoints"))
    monkeypatch.setenv("PINEAL_TASK_OWNERS_DB", str(tmp_path / "owners.db"))
    monkeypatch.setenv("PINEAL_MEMORY_DB", str(tmp_path / "hindsight.db"))
    # Fail-closed başlangıç kapısı PINEAL_ENV'siz açılmaz (üretim varsayılır):
    monkeypatch.setenv("PINEAL_ENV", "development")
    # [B0] dev ortamında kasa AÇIK varsayılır; kilit senaryoları test içinde
    # kendisi ``_check_vault_interlock``'u değiştirir (423 testi).
    monkeypatch.setattr(api, "_check_vault_interlock", lambda _cid: True)
    api.app.state.rooms.clear()
    api.app.state.minor_cases.clear()
    ckpt._RESUME_CLAIMS.clear()
    yield tmp_path
    api.app.state.rooms.clear()
    api.app.state.minor_cases.clear()
    ckpt._RESUME_CLAIMS.clear()


@pytest.fixture()
def client(env):
    with TestClient(api.app) as c:
        yield c


@pytest.fixture()
def prod_client(env, monkeypatch):
    """Production duruşu + çok operatörlü kimlik (sahiplik testleri)."""
    monkeypatch.setenv("PINEAL_ENV", "production")
    monkeypatch.setenv("PINEAL_TOKEN", ROOT_TOKEN)
    monkeypatch.setenv("PINEAL_OPERATOR_TOKENS", OPERATOR_TOKENS)
    monkeypatch.setenv("OPENROUTER_MAX_SPEND_USD", "50")
    monkeypatch.setenv("PINEAL_MAX_SPEND_USD", "50")
    with TestClient(api.app) as c:
        yield c


def _headers(token: str) -> dict:
    return {"X-API-Key": token}


def _seed_room(client, cid: str, headers: dict | None = None) -> dict:
    r = client.get("/api/tasks", params={"client_id": cid}, headers=headers or {})
    assert r.status_code == 200, r.text
    return api.app.state.rooms[cid]


def _mock_halt_route(client, cid: str, *, agent_error=None, depth_delay: float = 0.0,
                     monkeypatch=None):
    """Kesin deterministik durdurucu rota: cognitive tamamlanır, depth_analyst
    (graceful kapalı) düşük güvenle görevi ``halted_evidence``'e düşürür —
    ``blocks_resume`` destek talebi üretilir. İkinci turda plan çevrilir."""
    room = api.app.state.rooms[cid]
    executor = room["executor"]
    executor.router.analyze = AsyncMock(
        return_value=SimpleNamespace(agents=["cognitive_profiler", "depth_analyst"])
    )
    executor.injector.fetch_active_rules = MagicMock(return_value={})
    plan = {"cognitive_profiler": 0.9, "depth_analyst": 0.1}
    executor.uncertainty.evaluate = MagicMock(
        side_effect=lambda result, agent_name: _report(plan.get(agent_name, 0.95))
    )
    if monkeypatch is not None:
        cfg = executor.config.get_agent_config("depth_analyst")
        monkeypatch.setattr(cfg, "graceful_degradation", False)
    else:
        executor.config.get_agent_config("depth_analyst").graceful_degradation = False

    counts = {"cognitive_profiler": 0, "depth_analyst": 0}

    async def _cog(*_a, **_k):
        counts["cognitive_profiler"] += 1
        return _Style()

    async def _depth(*_a, **_k):
        counts["depth_analyst"] += 1
        if depth_delay:
            await asyncio.sleep(depth_delay)
        if agent_error is not None:
            raise agent_error
        return _Style()

    executor.agents["cognitive_profiler"].execute = _cog
    executor.agents["depth_analyst"].execute = _depth
    return room, executor, plan, counts


def _payload(bio_marker: str = "HEDEN_METNI") -> dict:
    return {
        "target_profile": {"bio": bio_marker, "posts": [], "post_times": [], "images": []},
        "policy": {"vault_locked": False, "minor_case": ""},
    }


def _run_halted(client, cid: str, task_id: str, payload: dict, **mock_kw):
    """İlk koşu: portal üzerinde GERÇEK executor → halted + destek + checkpoint."""
    room, executor, plan, counts = _mock_halt_route(client, cid, **mock_kw)
    # run_mission'ın ckpt_input çağrısıyla paralel (sunucu tarafı girdi kaydı):
    api.app.state.ckpt_input(task_id, payload, room.get("_owner"))
    status = client.portal.call(executor.execute_task, dict(payload), task_id)
    # Durdurucu rota: yutulan-güvensiz (halted_evidence) veya kritik-durdurucu
    # (halted_critical) — her ikisi de terminal + destek talebi üretilir.
    assert status.status in ("halted_evidence", "halted_critical"), status.status
    assert any(r["status"] == "pending" for r in status.support_requests), status.support_requests
    return room, executor, plan, counts, status


def _get_support(client, cid: str, task_id: str, headers: dict | None = None):
    return client.get(
        f"/api/tasks/{task_id}/support",
        params={"client_id": cid},
        headers=headers or {},
    )


def _wait_terminal(client, cid: str, task_id: str, headers: dict | None = None,
                   timeout: float = 15.0) -> str:
    """Resume kilit düşene kadar bekle (claim → finally), sonra durumu döndür.

    Not: resume başlar başlamaz ``task_status`` hâlâ ``halted_evidence``
    olabilir; ``resume_running=False`` anahtarı güvenilir bitiş işaretidir
    (persist_result yayın → finally release sırası sayesinde durum yazılmıştır).
    """
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = _get_support(client, cid, task_id, headers)
        if r.status_code == 200:
            data = r.json()
            last = data.get("task_status")
            if data.get("resume_running") is False:
                # Görev henüz hiç resume edilmediyse bu test çağrılmaz.
                return str(last)
        time.sleep(0.15)
    raise AssertionError(f"resume tamamlanmadı (son durum: {last})")


# ─────────────────────────────────────────────────────────────────────────────
# 6 · E2E: engel → görünür talep → yetkili yanıt → çözüm → devam → doğrulanmış
# ─────────────────────────────────────────────────────────────────────────────

def _sink_ws(ws, out: list, stop: threading.Event):
    try:
        while not stop.is_set():
            msg = ws.receive_text()
            out.append(msg)
            if '"AwaitingHuman"' in msg:
                stop.set()
    except Exception:
        stop.set()


def test_e2e_block_visible_support_authorized_response_resume_verified(client, monkeypatch, env):
    cid = f"ck-e2e-{uuid.uuid4().hex[:8]}"
    task_id = f"ck_e2e_task_{uuid.uuid4().hex[:8]}"
    _seed_room(client, cid)
    payload = _payload("HEDEN_ACIK_METNI")

    # (a) Engelin ürettiği destek talebi WS üzerinden CANLI GÖRÜNÜR:
    stop = threading.Event()
    frames: list = []
    with client.websocket_connect(f"/ws/{cid}") as ws:
        threading.Thread(target=_sink_ws, args=(ws, frames, stop), daemon=True).start()
        room, executor, plan, counts, first = _run_halted(
            client, cid, task_id, payload, monkeypatch=monkeypatch
        )
        stop.wait(timeout=6.0)
    assert any('"AwaitingHuman"' in fr for fr in frames), (
        f"AwaitingHuman çerçevesi yok; alınan: {len(frames)} çerçeve"
    )

    # (b) REST: açık talep görünür — görev, talep kimliği, ENGEL, ihtiyaç, sonraki adım.
    r = _get_support(client, cid, task_id)
    assert r.status_code == 200, r.text
    body = r.json()
    pending = [s for s in body["support_requests"] if s["status"] == "pending"]
    assert pending, body
    entry = pending[0]
    assert entry["task_id"] == task_id
    assert entry["support_id"] and entry["agent_name"] and entry["reason"]
    assert entry["options"] and entry["next_action"]
    assert entry["blocks_resume"] is True
    # Hassas alan ASLA sızmaz:
    assert "input_data" not in r.text
    assert "HEDEN_ACIK_METNI" not in r.text
    assert "policy" not in r.text

    # (c) Yetkili destek yanıtı → DOĞRU talep çözülür:
    sid = entry["support_id"]
    r = client.post(
        f"/api/tasks/{task_id}/support/{sid}",
        params={"client_id": cid},
        json={"action": "provide", "note": "operatör onayı"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["support"]["status"] == "resolved"
    r = _get_support(client, cid, task_id)
    states = {s["support_id"]: s["status"] for s in r.json()["support_requests"]}
    assert states[sid] == "resolved"

    # (d) Güvenli resume: istemciden TaskStatus GÖNDERİLMEDİ (yalnız POST {}),
    # snapshot sunucunun kalıcı checkpoint'inden yüklenir:
    plan["depth_analyst"] = 0.93  # destek sağlandı → engel kalktı
    r = client.post(f"/api/tasks/{task_id}/resume", params={"client_id": cid}, json={})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "resuming"

    # (e) Doğrulanmış sonuç: tamamlanan ajan tekrarlanmaz (I), durum biter:
    final = _wait_terminal(client, cid, task_id)
    assert final in ("completed", "partially_completed"), final
    r = _get_support(client, cid, task_id)
    data = r.json()
    assert data["resume_running"] is False
    # Kaldığı yerden devam: cognitive 1. koşuda tamamlandı, tekrar çalışmadı:
    assert counts["cognitive_profiler"] == 1, counts
    assert counts["depth_analyst"] >= 2, counts  # engelli tur + devam turu
    # Tüm destek kayıtları kapanmış (kalanı doğrulama ile kapandı):
    assert all(s["status"] == "resolved" for s in data["support_requests"]), data


# ─────────────────────────────────────────────────────────────────────────────
# NEGATİF SENARYOLAR
# ─────────────────────────────────────────────────────────────────────────────

def test_negative_resume_of_other_operators_task_is_forbidden(prod_client, env):
    """Başka kullanıcının görevi resume EDİLEMEZ (403; varlık gövdesi sızar mı: hayır)."""
    alice_room = "alice-ck-room"
    bob_room = "bob-ck-room"
    task_id = "ck_foreign_task_001"
    headers_a = _headers(ALICE_TOKEN)
    headers_b = _headers(BOB_TOKEN)
    _seed_room(prod_client, alice_room, headers_a)
    _seed_room(prod_client, bob_room, headers_b)

    # Görev Alice tarafından üretilir ve sahiplenilir:
    room = api.app.state.rooms[alice_room]
    ckpt.set_input(task_id, {"target_profile": {"bio": "a"}}, owner=room.get("_owner"))
    fake_status = {
        "task_id": task_id,
        "status": "halted_evidence",
        "support_requests": [],
        "completed_agents": [],
        "agent_runs": {},
        "evidence_chain": [],
        "planned_agents": [],
    }
    ckpt.persist_status(
        SimpleNamespace(
            task_id=task_id,
            status="halted_evidence",
            model_dump=lambda **_k: fake_status,
        ),
        owner=room.get("_owner"),
    )
    assert room.get("_owner"), "Alice odası mühürlü olmalı"

    r = prod_client.post(
        f"/api/tasks/{task_id}/resume",
        params={"client_id": bob_room},
        json={},
        headers=headers_b,
    )
    assert r.status_code == 403, r.text
    # Bob görevin varlığını/verisini GÖREMEZ (yanıt gövdesi sızdırmaz):
    assert task_id not in r.text or "forbidden" in r.text.lower()
    # Bob GET support da alamaz:
    r2 = prod_client.get(
        f"/api/tasks/{task_id}/support",
        params={"client_id": bob_room},
        headers=headers_b,
    )
    assert r2.status_code == 403, r2.text


def test_negative_double_response_to_same_support_is_rejected(client, monkeypatch, env):
    cid = f"ck-dbl-{uuid.uuid4().hex[:8]}"
    task_id = f"ck_dbl_{uuid.uuid4().hex[:8]}"
    _seed_room(client, cid)
    _run_halted(client, cid, task_id, _payload(), monkeypatch=monkeypatch)

    entry = next(
        s for s in _get_support(client, cid, task_id).json()["support_requests"]
        if s["status"] == "pending"
    )
    sid = entry["support_id"]
    r1 = client.post(
        f"/api/tasks/{task_id}/support/{sid}",
        params={"client_id": cid},
        json={"action": "provide", "note": "ilk"},
    )
    assert r1.status_code == 200, r1.text
    r2 = client.post(
        f"/api/tasks/{task_id}/support/{sid}",
        params={"client_id": cid},
        json={"action": "provide", "note": "ikinci"},
    )
    assert r2.status_code == 409, r2.text
    assert r2.json()["error"]["code"] == "ALREADY_RESOLVED"


def test_negative_concurrent_resume_second_is_rejected(client, monkeypatch, env):
    cid = f"ck-race-{uuid.uuid4().hex[:8]}"
    task_id = f"ck_race_{uuid.uuid4().hex[:8]}"
    _seed_room(client, cid)
    _run_halted(client, cid, task_id, _payload(), monkeypatch=monkeypatch, depth_delay=0.0)

    sid = next(
        s["support_id"]
        for s in _get_support(client, cid, task_id).json()["support_requests"]
        if s["status"] == "pending"
    )
    assert client.post(
        f"/api/tasks/{task_id}/support/{sid}",
        params={"client_id": cid},
        json={"action": "provide"},
    ).status_code == 200

    # İlk resume yavaşlatılmış (depth uyuması) — ikinci istek KİTLE arası girer:
    room = api.app.state.rooms[cid]
    executor = room["executor"]

    async def _slow_depth(*_a, **_k):
        await asyncio.sleep(0.8)
        return _Style()

    executor.agents["depth_analyst"].execute = _slow_depth
    plan_ref = {"depth_analyst": 0.93}
    executor.uncertainty.evaluate = MagicMock(
        side_effect=lambda result, agent_name: _report(plan_ref.get(agent_name, 0.9))
    )
    r1 = client.post(f"/api/tasks/{task_id}/resume", params={"client_id": cid}, json={})
    assert r1.status_code == 200, r1.text
    r2 = client.post(f"/api/tasks/{task_id}/resume", params={"client_id": cid}, json={})
    assert r2.status_code == 409, r2.text
    assert r2.json()["error"]["code"] == "RESUME_ALREADY_RUNNING"
    # İlk resume tamamlanır (kilit düşer):
    final = _wait_terminal(client, cid, task_id)
    assert final in ("completed", "partially_completed", "failed"), final


def test_negative_resume_with_missing_support_is_rejected(client, monkeypatch, env):
    cid = f"ck-miss-{uuid.uuid4().hex[:8]}"
    task_id = f"ck_miss_{uuid.uuid4().hex[:8]}"
    _seed_room(client, cid)
    _run_halted(client, cid, task_id, _payload(), monkeypatch=monkeypatch)

    # DESTEK SAĞLANMADAN resume:
    r = client.post(f"/api/tasks/{task_id}/resume", params={"client_id": cid}, json={})
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["code"] == "RESUME_SUPPORT_MISSING"
    open_ids = [s["support_id"] for s in _get_support(client, cid, task_id).json()["support_requests"] if s["status"] == "pending"]
    assert err["missing"] == open_ids and err["missing"], err
    # Açık talep hâlâ AÇIK (istemci 'resume' dedi diye kapanmadı):
    assert all(
        s["status"] == "pending"
        for s in _get_support(client, cid, task_id).json()["support_requests"]
    )


def test_negative_vault_relocked_blocks_resume_and_provide(client, monkeypatch, env):
    cid = f"ck-vault-{uuid.uuid4().hex[:8]}"
    task_id = f"ck_vault_{uuid.uuid4().hex[:8]}"
    _seed_room(client, cid)
    # vault_kind destek: depth_analyst VaultLockedError fırlatır (özel kod).
    _run_halted(
        client, cid, task_id, _payload(),
        monkeypatch=monkeypatch, agent_error=VaultLockedError("VAULT_LOCKED purpose=test"),
    )
    entry = next(
        s for s in _get_support(client, cid, task_id).json()["support_requests"]
        if s["status"] == "pending"
    )
    assert entry["kind"] == "vault_open", entry
    assert entry["requires"] == "vault_open"

    # KASA KİLİTLİ: destek yanıtı engeli doğrulayamaz → 423 + talep AÇIK KALIR.
    monkeypatch.setattr(api, "_check_vault_interlock", lambda _cid: False)
    sid = entry["support_id"]
    r = client.post(
        f"/api/tasks/{task_id}/support/{sid}",
        params={"client_id": cid},
        json={"action": "provide"},
    )
    assert r.status_code == 423, r.text
    still = next(
        s for s in _get_support(client, cid, task_id).json()["support_requests"]
        if s["support_id"] == sid
    )
    assert still["status"] == "pending"
    # Kilitliyken resume da YOK (423) — “kasa yeniden kilitlendikten sonra”:
    r = client.post(f"/api/tasks/{task_id}/resume", params={"client_id": cid}, json={})
    assert r.status_code == 423, r.text

    # KASA AÇILDI → destek doğrulanır, talep kapanır:
    monkeypatch.setattr(api, "_check_vault_interlock", lambda _cid: True)
    r = client.post(
        f"/api/tasks/{task_id}/support/{sid}",
        params={"client_id": cid},
        json={"action": "provide"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["support"]["status"] == "resolved"


def test_restart_support_survives_and_provision_still_works(client, monkeypatch, env):
    """Süreç yeniden başladığında (oda belleği sıfırlanır, dosya kalır):
    açık talep GERİ YÜKLENİR, destek SAĞLANIR, resume tamamlanır."""
    cid = f"ck-rest-{uuid.uuid4().hex[:8]}"
    task_id = f"ck_rest_{uuid.uuid4().hex[:8]}"
    _seed_room(client, cid)
    _run_halted(client, cid, task_id, _payload(), monkeypatch=monkeypatch)

    # “Süreç yeniden başladı”: oda belleği silinir (+ gönderici task düşer).
    old_room = api.app.state.rooms.pop(cid)
    sender = old_room.get("sender_task")
    if sender is not None:
        sender.cancel()
    ckpt._RESUME_CLAIMS.clear()

    # Yeni süreç: dosyadan açık talep görünür (kalıcı kayıt):
    _seed_room(client, cid)
    r = _get_support(client, cid, task_id)
    assert r.status_code == 200, r.text
    pending = [s for s in r.json()["support_requests"] if s["status"] == "pending"]
    assert pending, "açık talep süreç yeniden başlayınca kaybolmamalı"
    sid = pending[0]["support_id"]

    # Yeni odadaki FRESH executor ile destek sağlama + devam:
    room2 = api.app.state.rooms[cid]
    executor2 = room2["executor"]
    executor2.router.analyze = AsyncMock(
        return_value=SimpleNamespace(agents=["cognitive_profiler", "depth_analyst"])
    )
    executor2.injector.fetch_active_rules = MagicMock(return_value={})
    executor2.uncertainty.evaluate = MagicMock(side_effect=lambda r_, a: _report(0.9))
    executor2.agents["cognitive_profiler"].execute = AsyncMock(return_value=_Style())
    executor2.agents["depth_analyst"].execute = AsyncMock(return_value=_Style())

    r = client.post(
        f"/api/tasks/{task_id}/support/{sid}",
        params={"client_id": cid},
        json={"action": "provide", "note": "yeniden başlatma sonrası"},
    )
    assert r.status_code == 200, r.text
    r = client.post(f"/api/tasks/{task_id}/resume", params={"client_id": cid}, json={})
    assert r.status_code == 200, r.text
    final = _wait_terminal(client, cid, task_id)
    assert final in ("completed", "partially_completed"), final


def test_checkpoint_is_task_scoped_and_rejects_foreign_output(client, env):
    """Başka görevin çıktıları YÜKLENEMEZ: dosya içi mühür zorunlu."""
    a_id, b_id = "ck_iso_task_a", "ck_iso_task_b"
    ckpt.set_input(a_id, {"marker": "A_INPUT"})
    ckpt.set_input(b_id, {"marker": "B_INPUT"})
    # Bozuk/mühürsüz kayıt (başka görevin verisi A dosyasına girerse):
    path = ckpt._path(a_id)
    data = json.loads(open(path, encoding="utf-8").read())
    data["task_id"] = b_id  # sahte: B'nin verisi A yolunda
    open(path, "w", encoding="utf-8").write(json.dumps(data))

    with pytest.raises(ckpt.CheckpointCorrupted):
        ckpt.load(a_id)
    # API dürüstçe reddeder (409), başka görevin verisini ASLA döndürmez:
    cid = "ck-iso-room"
    _seed_room(client, cid)
    r = _get_support(client, cid, a_id)
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "CHECKPOINT_CORRUPTED"
    assert "B_INPUT" not in r.text and "A_INPUT" not in r.text
    # Var olmayan görev 404:
    r = _get_support(client, cid, "ck_iso_never_written")
    assert r.status_code == 404, r.text


def test_support_response_never_exposes_sensitive_checkpoint_fields(client, monkeypatch, env):
    cid = f"ck-priv-{uuid.uuid4().hex[:8]}"
    task_id = f"ck_priv_{uuid.uuid4().hex[:8]}"
    _seed_room(client, cid)
    _run_halted(client, cid, task_id, _payload(bio_marker="GIZLI_BIO_12345"), monkeypatch=monkeypatch)
    r = _get_support(client, cid, task_id)
    assert r.status_code == 200
    for forbidden in ("input_data", "GIZLI_BIO_12345", "ingested_outputs", "policy"):
        assert forbidden not in r.text, forbidden
    # İzinli alanlar görünür:
    data = r.json()
    s = data["support_requests"][0]
    for allowed in ("support_id", "task_id", "agent_name", "reason", "options",
                    "next_action", "blocks_resume", "status"):
        assert allowed in s, allowed


# ─────────────────────────────────────────────────────────────────────────────
# 2 · UI KABLOLAMA (statik — tarayıcı DOM'u bu ortamda çalıştırılmaz)
# ─────────────────────────────────────────────────────────────────────────────

def test_ui_wiring_support_panel_and_awaiting_human():
    app_ts = (api.os.path.join(REPO_ROOT, "frontend", "src", "App.svelte"))
    store_ts = api.os.path.join(REPO_ROOT, "frontend", "src", "store.ts")
    panel = api.os.path.join(REPO_ROOT, "frontend", "src", "components", "SupportPanel.svelte")
    app_src = open(app_ts, encoding="utf-8").read()
    store_src = open(store_ts, encoding="utf-8").read()
    panel_src = open(panel, encoding="utf-8").read()

    # AwaitingHumanEvent arayüzde görünür:
    assert "AwaitingHuman" in app_src
    assert "refreshSupport" in app_src
    # WS yeniden bağlanınca açık talepler kalıcı kayıttan geri yüklenir:
    assert "ws.onopen" in app_src and "refreshSupport(get(supportTaskId))" in app_src
    # Panel gösterir: görev, talep kimliği, ENGEL, ihtiyaç, sonraki adım:
    assert "data-testid=\"support-panel\"" in panel_src
    for label in ("görev:", "talep:", "engel:", "ihtiyaç:", "sonraki adım:"):
        assert label in panel_src, label
    # Yanıt + güvenli resume düğmeleri (istemciden TaskStatus YOK):
    assert "data-testid=\"support-provide\"" in panel_src
    assert "data-testid=\"support-resume\"" in panel_src
    assert "/resume" in panel_src
    # Hassas girdi/anahtar alanı YOK + resume gövdesi BOŞ (TaskStatus göndermez):
    for secret_field in ("password", "api_key", "apiKey", "secret", "cookie"):
        assert secret_field not in panel_src.lower().replace("api-key", ""), secret_field
    assert "JSON.stringify({})" in panel_src  # POST /resume: boş gövde
    assert "import { TaskStatus" not in panel_src
    # Store: kalıcı geri yükleme yardımcısı:
    assert "export async function refreshSupport" in store_src
    assert "supportRequests" in store_src
