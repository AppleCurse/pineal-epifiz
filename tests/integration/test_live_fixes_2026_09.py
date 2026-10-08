"""
CANLI-FİKİR REVİZYONU 2026-09 — 11 maddelik düzeltme listesinin kanıt testleri.

Her test, düzeltmeden önce KIRMIZI olan davranışı kilitler:
  1  WS oda izolasyonu (cross-room sızıntı yok)
  2  WS soketi bekleme-timeout'ta evict edilir
  3  _close_room browser session'ı kapatır (zombie Chromium yok)
  4  Scrape altyapı tükenmesi → dürüst "failed" (HEDEF VERİSİ ALINAMADI),
     boş profille operasyon ÇALIŞTIRILMAZ
  5  Scraper'ın kendi ISE'si → "halted_evidence" (isinstance, string kontrolü yok)
  6  merge_evidence: (agent, evidence_type) anahtarıyla supersede (retry kirliliği yok)
  7  verification_note'lar source_agent'a göre ayrı kalır
  8  query_json: ProviderEmptyResponseError → ücretli repair YOK, hata yükselir
  9  Upstream bulgu bütçesi (≤2000, FIFO) + _finding_core çekirdeği
  10 Upstream bulgular ajan promptuna enjekte edilir ("doğrulanmamış" etiketiyle)
  11 Operatör kuralları 50 tavan + dürüst kesim notu
     + hüküm özeti (deterministik, kanıtsızsa dürüst satır)
     + devre dışı cache guard (get/put/is_cachable no-op)
     + OverridePayload alan sınırları
"""
import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ValidationError

import backend.api as api
from agent_core.agents.passion_mapper import PassionMapperAgent
from agent_core.domain.memory_models import PassionProfile
from agent_core.services.canonical_memory import CanonicalMemory
from agent_core.services import response_cache as rc_mod
from agent_core.services import verdict_synthesizer as vs
from agent_core.services.llm_gateway import (
    LLMGateway,
    ProviderEmptyResponseError,
)
from agent_core.services.memory_injector import MemoryInjector
from agent_core.task_executor import (
    UPSTREAM_FINDINGS_BUDGET_CHARS,
    PinealExecutor,
    _append_upstream_finding,
)


# ---------------------------------------------------------------------------
# 1 — WS oda izolasyonu (item 6)
# ---------------------------------------------------------------------------

def test_send_ws_room_scoped_no_cross_room_leak():
    """Bir odanın payload'u AYRI odadaki sokete gitmemeli."""
    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_text(self, text):
            self.sent.append(text)

    ws_a, ws_b = FakeWS(), FakeWS()
    room_a = {"websockets": {ws_a}}
    room_b = {"websockets": {ws_b}}
    rooms = api.app.state.rooms
    rooms["leak_a"] = room_a
    rooms["leak_b"] = room_b
    try:
        asyncio.run(api._send_ws(room_a, "room-a-gizli-payload"))
    finally:
        rooms.pop("leak_a", None)
        rooms.pop("leak_b", None)

    assert ws_a.sent == ["room-a-gizli-payload"], "kendi odasına gitmeli"
    assert ws_b.sent == [], "CROSS-ROOM SIZINTISI: oda B, oda A payload'unu aldı"


def test_send_ws_evicts_stuck_socket_on_timeout(monkeypatch):
    """Gönderimi asılı kalan soket timeout'ta odaya ait setten atılmalı."""
    monkeypatch.setattr(api, "_WS_SEND_TIMEOUT_S", 0.05)

    class SlowWS:
        def __init__(self):
            self.sent = []

        async def send_text(self, text):
            await asyncio.sleep(0.5)
            self.sent.append(text)

    ws = SlowWS()
    room = {"websockets": {ws}}
    asyncio.run(api._send_ws(room, "x"))
    assert ws not in room["websockets"], "asılı soket setten atılmadı"


# ---------------------------------------------------------------------------
# 2 — _close_room: zombie Chromium kapatılır (item 7)
# ---------------------------------------------------------------------------

def test_close_room_closes_browser_session():
    closed = []

    class FakeSession:
        async def close(self):
            closed.append(True)

    room = {"browser": FakeSession(), "sender_task": None, "mission_tasks": {}}
    rooms = api.app.state.rooms
    rooms["zombie"] = room
    try:

        async def scenario():
            api._close_room("zombie", room)
            await asyncio.sleep(0.05)

        asyncio.run(scenario())
    finally:
        rooms.pop("zombie", None)

    assert closed, "oda kapanırken browser session KAPATILMADI (zombie Chromium)"


def test_close_room_without_browser_still_works():
    room = {"sender_task": None, "mission_tasks": {}}
    rooms = api.app.state.rooms
    rooms["plain"] = room
    api._rooms_last_seen["plain"] = 0.0
    try:
        api._close_room("plain", room)
    finally:
        api._rooms_last_seen.pop("plain", None)
    assert "plain" not in rooms


# ---------------------------------------------------------------------------
# 3 — Scrape: dürüst terminal durumlar (item 8)
# ---------------------------------------------------------------------------

def _make_initiate():
    return api.InitiatePayload(
        client_id="t_scrape",
        url="https://www.instagram.com/ornekprofil/",
        rituals="cay,kitap",
        playlist="",
        envies="",
    )


def _patch_mission(monkeypatch, fake_scrape, fake_executor, calls):
    monkeypatch.setattr(api, "scrape_instagram", fake_scrape)
    monkeypatch.setattr(api, "get_executor", lambda cid: fake_executor)
    monkeypatch.setattr(api, "get_vault", lambda cid: {})
    monkeypatch.setattr(api, "_effective_scraper_type", lambda url, st: "instagram")
    monkeypatch.setattr(api, "broadcast_log", lambda cid, lvl, msg: None)

    def fake_broadcast_error(cid, status, msg, task_id=None):
        calls["result_errors"].append((status, msg))

    monkeypatch.setattr(api, "broadcast_result_error", fake_broadcast_error)


def test_scrape_infra_exhaustion_honest_failed(monkeypatch):
    """Ağ/altyapı hatası 3 denemede bitince: dürüst 'failed', operasyon YOK."""
    calls = {"scrape": 0, "execute": 0, "result_errors": []}

    async def fake_scrape(url, cookie, log=None):
        calls["scrape"] += 1
        raise ConnectionError("network unreachable")

    class FakeExecutor:
        async def execute_task(self, payload, task_id):
            calls["execute"] += 1
            raise AssertionError("boş profille operasyon çalıştırıldı")

    monkeypatch.setenv("PINEAL_SCRAPE_MAX_ATTEMPTS", "3")
    _patch_mission(monkeypatch, fake_scrape, FakeExecutor(), calls)

    asyncio.run(api.run_mission(_make_initiate()))

    assert calls["scrape"] == 3, "retry loop PINEAL_SCRAPE_MAX_ATTEMPTS kez denemeli"
    assert calls["execute"] == 0, "KANITSIZ profille executor çalıştırılamaz"
    assert calls["result_errors"], "dürüst terminal durum yayınlanmalı"
    status, msg = calls["result_errors"][-1]
    assert status == "failed"
    assert "HEDEF VERİSİ ALINAMADI" in msg


def test_scrape_insufficient_evidence_halted(monkeypatch):
    """Scraper'ın KENDİNE ÖZLÜ ISE'si 'halted_evidence'a döner (tek deneme)."""
    calls = {"scrape": 0, "execute": 0, "result_errors": []}

    async def fake_scrape(url, cookie, log=None):
        calls["scrape"] += 1
        raise api.ScraperInsufficientEvidenceError("private target")

    class FakeExecutor:
        async def execute_task(self, payload, task_id):
            calls["execute"] += 1

    _patch_mission(monkeypatch, fake_scrape, FakeExecutor(), calls)

    asyncio.run(api.run_mission(_make_initiate()))

    assert calls["scrape"] == 1, "kanıt yoksa denemek anlamsız"
    assert calls["execute"] == 0
    assert calls["result_errors"][-1][0] == "halted_evidence"


def test_scrape_success_path_still_runs(monkeypatch):
    """Geriye uyum: kazıma başarılıysa operasyon çalışır (eski yol)."""
    calls = {"scrape": 0, "execute": 0, "result_errors": [], "results": []}

    async def fake_scrape(url, cookie, log=None):
        calls["scrape"] += 1
        return {"bio": "gercek biyo", "posts": ["post1"]}

    ex_payloads = []

    class FakeExecutor:
        async def execute_task(self, payload, task_id):
            calls["execute"] += 1
            ex_payloads.append(payload)
            return SimpleNamespace(status="completed")

    monkeypatch.setenv("PINEAL_SCRAPE_MAX_ATTEMPTS", "3")
    _patch_mission(monkeypatch, fake_scrape, FakeExecutor(), calls)
    monkeypatch.setattr(
        api, "broadcast_result", lambda cid, res: calls["results"].append(res)
    )

    asyncio.run(api.run_mission(_make_initiate()))

    assert calls["scrape"] == 1
    assert calls["execute"] == 1, "başarılı kazımadan sonra operasyon koşmalı"
    assert ex_payloads[0]["target_profile"]["bio"] == "gercek biyo", \
        "kazıma çıktısı payload'a akmalı"
    assert calls["results"], "result yayınlanmalı"


# ---------------------------------------------------------------------------
# 4 — merge_evidence supersede (item 9)
# ---------------------------------------------------------------------------

def _merge_then_read(mem, task_id, chains):
    async def scenario():
        for chain in chains:
            await mem.merge_evidence(task_id, chain)

    asyncio.run(scenario())
    return mem.get_task_memory(task_id)


def test_merge_evidence_supersedes_stale_agent_output(tmp_path):
    """Aynı (agent, evidence_type): ESKİ kayıt düşer, EN YENİ kalır."""
    mem = CanonicalMemory(storage_path=str(tmp_path))
    old = [{
        "agent": "passion_mapper", "evidence_type": "agent_output",
        "result": {"core_passions": ["eski tutku"], "confidence": 0.3},
        "timestamp": "2026-09-01T00:00:00Z",
    }]
    new = [{
        "agent": "passion_mapper", "evidence_type": "agent_output",
        "result": {"core_passions": ["yeni tutku"], "confidence": 0.9},
        "timestamp": "2026-09-02T00:00:00Z",
    }]

    data = _merge_then_read(mem, "op_sup1", [old, new])

    pas = [
        e for e in data["evidence"]
        if e.get("agent") == "passion_mapper"
        and e.get("evidence_type") == "agent_output"
    ]
    assert len(pas) == 1, "eski agent_output supersede edilmeli"
    assert pas[0]["result"]["confidence"] == 0.9, "en yeni kayıt kalmalı"


def test_merge_evidence_keeps_distinct_verification_notes(tmp_path):
    """verification_note'lar source_agent'a göre AYRI yaşar; ama aynı
    source_agent'ın eski notu supersede edilir."""
    mem = CanonicalMemory(storage_path=str(tmp_path))
    first = [
        {
            "agent": "deep_research", "source_agent": "passion_mapper",
            "evidence_type": "verification_note",
            "result": {"note": "a-notu-eski"}, "timestamp": "t1",
        },
        {
            "agent": "deep_research", "source_agent": "friction_detector",
            "evidence_type": "verification_note",
            "result": {"note": "b-notu"}, "timestamp": "t1",
        },
    ]
    second = [
        {
            "agent": "deep_research", "source_agent": "passion_mapper",
            "evidence_type": "verification_note",
            "result": {"note": "a-notu-yeni"}, "timestamp": "t2",
        },
    ]

    data = _merge_then_read(mem, "op_sup2", [first, second])

    notes = [e for e in data["evidence"] if e.get("evidence_type") == "verification_note"]
    by_agent = {e["source_agent"]: e["result"]["note"] for e in notes}
    assert by_agent.get("passion_mapper") == "a-notu-yeni", "eski not supersede"
    assert by_agent.get("friction_detector") == "b-notu", "başka ajanın notu dokunulmaz"


# ---------------------------------------------------------------------------
# 5 — query_json: boş seçim = transport hatası, repair YOK (item 10)
# ---------------------------------------------------------------------------

def test_query_json_no_paid_repair_on_empty_response():
    gw = LLMGateway()
    calls = []

    async def fake_query(*args, **kwargs):
        calls.append(1)
        raise ProviderEmptyResponseError("Provider returned empty choices")

    gw.query = fake_query

    with pytest.raises(ProviderEmptyResponseError):
        asyncio.run(gw.query_json("test prompt", PassionProfile, task="depth"))

    assert len(calls) == 1, "ikinci ÜCRETLİ repair çağrısı yasak"


def test_provider_empty_response_is_not_valueerror():
    assert issubclass(ProviderEmptyResponseError, RuntimeError)
    assert not issubclass(ProviderEmptyResponseError, ValueError)


# ---------------------------------------------------------------------------
# 6 — Upstream bulgu bütçesi + çekirdek (item 3)
# ---------------------------------------------------------------------------

def test_upstream_finding_budget_fifo():
    data: dict = {}
    for i in range(20):
        _append_upstream_finding(data, "mirror_truth", f"{i}:" + "x" * 300)

    findings = data["_upstream_findings"]
    total = sum(len(f["core"]) for f in findings)
    assert total <= UPSTREAM_FINDINGS_BUDGET_CHARS, "bütçe aşıldı"
    assert findings[-1]["core"].startswith("19:")
    assert all(not f["core"].startswith("0:") for f in findings), "en eski düşmeli"


def test_upstream_finding_writer_and_prompt_gate_exclude_non_inferences():
    from agent_core.services.upstream_findings import (
        classify_upstream_finding,
        upstream_findings_block,
    )

    data: dict = {}
    _append_upstream_finding(data, "mirror_truth", "unverified analysis claim")
    _append_upstream_finding(data, "pattern_interrupt", "message strategy")
    _append_upstream_finding(data, "resonance_calc", "recommended approach")
    _append_upstream_finding(data, "autonomous_verifier", "REFUTED")
    _append_upstream_finding(data, "interpreter", "generated code")
    _append_upstream_finding(data, "unknown_agent", "unknown source")

    assert data["_upstream_findings"] == [
        {
            "agent": "mirror_truth",
            "core": "unverified analysis claim",
            "epistemic_type": "inference",
            "verification_status": "unverified",
            "origin": "task_executor",
        }
    ]
    assert classify_upstream_finding("pattern_interrupt") == "strategy"
    assert classify_upstream_finding("resonance_calc") == "strategy"
    assert classify_upstream_finding("autonomous_verifier") == "verification"
    assert classify_upstream_finding("interpreter") == "untyped"
    assert classify_upstream_finding("unknown_agent") == "untyped"

    block = upstream_findings_block(data)
    assert "unverified analysis claim" in block
    for excluded in (
        "message strategy",
        "recommended approach",
        "REFUTED",
        "generated code",
        "unknown source",
    ):
        assert excluded not in block

    # Even manually inserted or legacy raw entries cannot bypass the prompt gate.
    hostile = {
        "_upstream_findings": [
            {
                "agent": "pattern_interrupt",
                "core": "injected strategy",
                "epistemic_type": "strategy",
                "verification_status": "unverified",
                "origin": "task_executor",
            },
            {
                "agent": "resonance_calc",
                "core": "strategy relabeled as inference",
                "epistemic_type": "inference",
                "verification_status": "unverified",
                "origin": "task_executor",
            },
            {"agent": "unknown", "core": "legacy untyped finding"},
        ]
    }
    assert upstream_findings_block(hostile) == ""


def test_finding_core_joins_long_strings_and_caps():
    class R(BaseModel):
        short: str
        a: str
        b: str

    r = R(short="id", a="a" * 50, b="b" * 50)
    core = PinealExecutor._finding_core(r)
    assert core == "a" * 50 + " | " + "b" * 50
    assert PinealExecutor._finding_core(None) == ""
    assert PinealExecutor._finding_core(R(short="id", a="kısa", b="da kısa")) == ""
    assert len(PinealExecutor._finding_core(R(short="id", a="z" * 500, b="y" * 500))) <= 280


# ---------------------------------------------------------------------------
# 7 — Ajan promptuna enjeksiyon (item 3)
# ---------------------------------------------------------------------------

def test_upstream_findings_injected_into_agent_prompt():
    captured: dict = {}

    class FakeLLM:
        async def query_json_chain(self, **kwargs):
            captured["prompt"] = kwargs.get("prompt", "")
            return PassionProfile(core_passions=["çay"], confidence=0.6)

    agent = PassionMapperAgent(llm_gateway=FakeLLM())
    payload = {
        "target_profile": {"bio": "çay içen adam", "posts": ["çay her şeydir"]},
        "_upstream_findings": [
            {
                "agent": "osint_investigator",
                "core": "platformlarda aktif olduğu tespit edildi",
                "epistemic_type": "inference",
                "verification_status": "unverified",
                "origin": "task_executor",
            },
            {
                "agent": "pattern_interrupt",
                "core": "DO NOT INJECT THIS MESSAGE STRATEGY",
                "epistemic_type": "strategy",
                "verification_status": "separate",
                "origin": "task_executor",
            },
            {"agent": "unknown", "core": "UNTYPED BYPASS"},
        ],
    }
    asyncio.run(agent.execute(payload))

    prompt = captured["prompt"]
    assert "DİĞER AJANLARIN BULGULARI" in prompt
    assert "[osint_investigator]" in prompt
    assert "doğrulanmamış" in prompt, "epistemik etiket zorunlu"
    assert "DO NOT INJECT THIS MESSAGE STRATEGY" not in prompt
    assert "UNTYPED BYPASS" not in prompt


def test_upstream_findings_empty_back_compat():
    """Bulgu yoksa prompt bloğu boş → eski davranış birebir korunur."""
    from agent_core.services.upstream_findings import upstream_findings_block

    assert upstream_findings_block({}) == ""
    assert upstream_findings_block({"_upstream_findings": []}) == ""
    assert upstream_findings_block(None) == ""


# ---------------------------------------------------------------------------
# 8 — Operatör kuralı 50 tavan (item 3 / audit 25)
# ---------------------------------------------------------------------------

def test_memory_injector_50_rule_cap_honest_note(tmp_path):
    p = tmp_path / "learnings.json"
    rules = [
        {"hash": f"h{i:03d}", "tag": f"tag{i:02d}", "fact": f"kural metni numara {i} uzunlugu yetiyor"}
        for i in range(60)
    ]
    p.write_text(json.dumps(rules), encoding="utf-8")

    out = MemoryInjector(memory_path=str(p)).fetch_active_rules()

    assert out.count("- [tag") == 50, "en yeni 50 kural enjekte edilir"
    assert "- [tag59]" in out and "- [tag10]" in out, "EN YENİ 50 (i=10..59) kalmalı"
    assert "- [tag09]" not in out, "en eski 10 (i=0..9) düşmeli"
    assert "10 eski kural" in out, "kesim dürüstçe raporlanmalı"


# ---------------------------------------------------------------------------
# 9 — Hüküm özeti (item 4)
# ---------------------------------------------------------------------------

def test_verdict_digest_with_evidence():
    snap = SimpleNamespace(
        status="completed",
        evidence_chain=[
            {
                "agent": "passion_mapper", "evidence_type": "agent_output",
                "result": {"core_passions": ["derin bağlantılar"], "confidence": 0.8},
            },
        ],
    )
    d = vs.build_verdict_digest({"active_tasks": {"op_x": snap}})
    assert "GÖREV op_x" in d
    assert "DURUM: completed" in d
    assert "[passion_mapper/agent_output]" in d


def test_verdict_digest_honest_no_evidence():
    d = vs.build_verdict_digest({
        "active_tasks": {"op_y": SimpleNamespace(status="running", evidence_chain=[])},
    })
    assert "kanıt kaydı yok" in d, "kanıt yoksa dürüst satır — uydurma hüküm yok"

    assert vs.build_verdict_digest({"active_tasks": {}}) == ""
    assert vs.build_verdict_digest("not-a-dict") == ""
    assert vs.build_verdict_digest(None) == ""


# ---------------------------------------------------------------------------
# 10 — Devre dışı cache guard (audit P0-6 tamamlayıcısı)
# ---------------------------------------------------------------------------

def test_response_cache_disabled_guard(tmp_path):
    # _connect, yolun dizinini makedirs ile oluşturur; init'in BAŞARISIZ
    # olması için dizin yolunun ortasında normal bir DOSYA dikilir.
    blocker = tmp_path / "afile"
    blocker.write_text("x", encoding="utf-8")
    c = rc_mod.ResponseCache(db_path=str(blocker / "db.sqlite3"))
    assert c.enabled is False, "başarısız init enabled=False raporlar (mevcut sözleşme)"
    before_errors = c.errors
    assert c.get("k") is None
    c.put("k", "v")
    assert c.is_cachable("bir prompt", None) is False
    assert c.errors == before_errors, "disabled cache hata sayaçlarını şişirmemeli"


# ---------------------------------------------------------------------------
# 11 — OverridePayload sınırları (item 3 / audit 25)
# ---------------------------------------------------------------------------

def test_override_payload_field_bounds():
    with pytest.raises(ValidationError):
        api.OverridePayload(client_id="c", fact="x" * 2001, tag="t")
    with pytest.raises(ValidationError):
        api.OverridePayload(client_id="c", fact="ok", tag="t" * 65)
    with pytest.raises(ValidationError):
        api.OverridePayload(client_id="c", fact="", tag="t")
    ok = api.OverridePayload(client_id="c", fact="kısa gerçek", tag="dealbreaker")
    assert ok.fact == "kısa gerçek"


# ---------------------------------------------------------------------------
# 12 — FREKANS etiketi (item 11): status kodu DEĞİŞMEDİ, metin mekanik
# ---------------------------------------------------------------------------

def test_halted_frequency_status_still_locked():
    """5 testin kilitlediği durum kodu aynen korunur (geriye uyum)."""
    import agent_core.task_executor as te

    src = open(te.__file__, encoding="utf-8").read()
    assert '"halted_frequency"' in src, "status kodu dokunulmaz"
    assert "INSUFFICIENT_RESONANCE_EVIDENCE" in src, "yeni mekanik etiket"
    # Eski etiket artık STRING LITERAL olarak yok (açıklama yorumları hariç).
    assert '"FREKANS UYUSMAZLIGI"' not in src, "eski yanlış etiket gitti"
    assert "'FREKANS UYUSMAZLIGI'" not in src
    assert '"Frekans uyusmazligi"' not in src, "eski reason metni gitti"
