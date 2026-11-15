"""Durum/telemetri DÜRÜSTLÜĞÜ — ekrandaki her operasyonel iddianın gerçek bir
kaynağı olmalı.

[RÖNTGEN 2026-09-23] Bu dosya kullanıcının üç açık talebini kilitler:
  (1) telemetri yokken SİMÜLASYON çalışmasın (kaldırılsın ya da OFFLINE densin),
  (2) üretim UI'sında gerçek backend telemetrisi gösterilsin,
  (3) UI'daki HER operasyonel durum backend kaynağına kadar izlenebilsin.

Ölçülen eski kusurlar:
  * ``AgentStatusTracker.simulate_processing()`` — üretim modülünde, hiçbir ajan
    çalışmadan Ready→Active→Done geçişlerini zamanlayıcıyla UYDURAN "demo"
    metodu (çağıranı yoktu; aynı veri sözleşmesini ürettiği için bir kablo
    hatası ekranda sahte operasyon demekti).
  * ``set_all_ready()`` + ``init_tracker()`` içindeki açılış çağrısı +
    ``/api/initiate`` içindeki "tahmini plan" çağrısı — tek bir kanıt
    üretilmeden 12/12 READY basıyordu.
  * ``/api/agents/status`` — tracker nesnesi varsa koşulsuz
    ``source: "redis_bus"`` beyan ediyordu; Redis kapalıyken bile UI
    "REDIS PUB/SUB" etiketi basıyordu (etiket sahte, veri gerçek).
  * ``AgentRack.svelte`` — ``readyCount = gerçek || AGENT_DEFINITIONS.length``:
    backend hiç yanıt vermezse 12 READY uyduruyordu; hata sayacı yoktu;
    taşıyıcı etiketi sabit metindi.
  * ``App.svelte`` — telemetri çekilemeyince ESKİ veri ekranda kalıyordu
    (bayat veri canlı veri gibi görünüyordu).
  * ``TacticalWarRoom.svelte`` — operatör profili (ritüeller/çalma listesi/
    imrenmeler) SABİT İNGİLİZCE KURGU ile gönderiliyordu; backend sözleşmesi
    bunu açıkça yasaklıyor (backend/api.py [009]: "Kullanıcı göndermediyse ASLA
    örnek/placeholder ritüel ÜRETME"). Ayrıca özet satırları uydurma varsayılan
    basıyordu ("Analitik", Aşil 15, "3 jürili", plan 12).
  * ``_check_vault_interlock`` — ``.pineal_vault.json`` dosyasının VARLIĞI
    dış-dünya mandalını açıyordu (içi boş olsa bile).
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from agent_core.services.agent_status_tracker import (
    AGENT_DEFINITIONS,
    AgentStatus,
    AgentStatusTracker,
)
from agent_core.services.redis_bus import RedisBus

ROOT = Path(__file__).resolve().parents[2]
TRACKER_SRC = ROOT / "agent_core" / "services" / "agent_status_tracker.py"
API_SRC = ROOT / "backend" / "api.py"
APP_SVELTE = ROOT / "frontend" / "src" / "App.svelte"
STORE_TS = ROOT / "frontend" / "src" / "store.ts"
AGENT_RACK = ROOT / "frontend" / "src" / "components" / "UnifiedPinealCockpit.svelte"
WAR_ROOM = ROOT / "frontend" / "src" / "components" / "UnifiedPinealCockpit.svelte"

ALL_AGENT_IDS = [a["id"] for a in AGENT_DEFINITIONS]


class _RecordingBus:
    """Yayımlanan her durumu kaydeden sahte taşıyıcı."""

    def __init__(self, state: str = "in_memory"):
        self.published: list[tuple[str, str]] = []
        self._state = state

    async def publish_agent_status(self, agent_id, status, metadata=None):
        self.published.append((agent_id, status))
        return {"agent_id": agent_id, "status": status}

    def connection_state(self) -> str:
        return self._state


def _code_only(source: str, comment: str = "#") -> str:
    """Yorum satırları atılmış kaynak (gerekçe metinleri kilidi gevşetmesin)."""
    return "\n".join(ln for ln in source.splitlines() if not ln.strip().startswith(comment))


# --------------------------------------------------------------------------- #
# 1) Tracker: açılış durumu WAIT, READY yalnız gerçek geçişten
# --------------------------------------------------------------------------- #
def test_tracker_slots_start_in_wait_not_ready():
    tracker = AgentStatusTracker(_RecordingBus())
    statuses = tracker.get_all_statuses()
    assert set(statuses) >= set(ALL_AGENT_IDS)
    for agent_id, row in statuses.items():
        assert row["status"] == AgentStatus.WAIT.value, (
            f"{agent_id} açılışta {row['status']} — hiçbir ajan koşmadan "
            "operasyonel durum iddia edilemez"
        )


def test_bulk_ready_and_simulation_api_do_not_exist():
    tracker = AgentStatusTracker(_RecordingBus())
    assert not hasattr(tracker, "set_all_ready")
    assert not hasattr(tracker, "simulate_processing")


def test_ready_is_written_per_agent_by_real_transition():
    bus = _RecordingBus()
    tracker = AgentStatusTracker(bus)
    asyncio.run(tracker.set_active("mirror_truth", task_id="t-1"))
    asyncio.run(tracker.set_done("mirror_truth", result_summary="kanıt üretildi"))

    assert tracker.get_status("mirror_truth")["status"] == AgentStatus.DONE.value
    # Diğer 11 slot hâlâ WAIT: tek ajanın koşusu başkalarını READY yapmaz.
    others = [a for a in ALL_AGENT_IDS if a != "mirror_truth"]
    assert all(tracker.get_status(a)["status"] == AgentStatus.WAIT.value for a in others)
    assert ("mirror_truth", "Active") in bus.published
    assert ("mirror_truth", "Done") in bus.published


def test_init_tracker_seals_wait_and_publishes_no_ready(monkeypatch):
    import agent_core.services.agent_status_tracker as tracker_mod
    import agent_core.services.redis_bus as bus_mod

    bus = _RecordingBus()

    async def fake_init_redis_bus(_url=None):
        return bus

    monkeypatch.setattr(bus_mod, "init_redis_bus", fake_init_redis_bus)
    monkeypatch.setattr(tracker_mod, "_tracker", None)
    try:
        tracker = asyncio.run(tracker_mod.init_tracker("redis://localhost:6379/0"))
    finally:
        tracker_mod._tracker = None

    assert all(row["status"] == AgentStatus.WAIT.value for row in tracker.get_all_statuses().values())
    assert bus.published, "açılış mühürü taşıyıcıya yayımlanmalı"
    ready_published = [(a, s) for a, s in bus.published if s == AgentStatus.READY.value]
    assert not ready_published, f"açılışta READY yayımlandı: {ready_published[:5]}"


def test_tracker_module_source_has_no_simulation_factory():
    code = _code_only(TRACKER_SRC.read_text(encoding="utf-8"))
    assert "def simulate_processing" not in code
    assert "def set_all_ready" not in code
    assert not re.search(r"def\s+\w*(simulate|demo|fake|mock)\w*\s*\(", code), (
        "agent_status_tracker içinde simülasyon/demo metodu tanımlı"
    )


# --------------------------------------------------------------------------- #
# 2) Backend: kaynak beyanı gerçek taşıyıcıyı gösterir
# --------------------------------------------------------------------------- #
def test_redis_bus_connection_state_reports_real_transport():
    bus = RedisBus()
    assert bus.connection_state() == "in_memory"  # hiç bağlanmadı
    bus._use_redis = True
    bus._connected = True
    assert bus.connection_state() == "redis_bus"
    bus._connected = False
    assert bus.connection_state() == "in_memory"  # koptu -> dürüst etiket


def test_agents_status_endpoint_source_follows_transport(monkeypatch):
    from backend import api

    assert api.HAS_AGENT_RACK is True, "Agent Rack modülü test ortamında yüklenmeli"
    tracker = AgentStatusTracker(_RecordingBus(state="in_memory"))
    monkeypatch.setattr(api, "get_tracker", lambda: tracker)

    payload = asyncio.run(api.api_agents_status())
    assert payload["source"] == "in_memory"
    assert payload["count"] == len(ALL_AGENT_IDS)
    assert all(row["status"] == AgentStatus.WAIT.value for row in payload["agents"])

    tracker.redis_bus = _RecordingBus(state="redis_bus")
    payload = asyncio.run(api.api_agents_status())
    assert payload["source"] == "redis_bus"


def test_agents_status_endpoint_reports_fallback_without_rack(monkeypatch):
    from backend import api

    monkeypatch.setattr(api, "HAS_AGENT_RACK", False)
    assert asyncio.run(api.api_agents_status()) == {"agents": [], "source": "fallback", "count": 0}


def test_initiate_rack_block_only_waits():
    """/api/initiate görev başlangıcında READY BOYAMAZ."""
    code = _code_only(API_SRC.read_text(encoding="utf-8"))
    assert "set_all_ready" not in code
    assert "simulate_processing" not in code
    fn = code[code.index("async def api_initiate"):]
    fn = fn[: fn.index("\nasync def ") if "\nasync def " in fn else len(fn)]
    assert "await tracker.set_all_wait()" in fn, (
        "görev başlangıcı Agent Rack slotlarını WAIT'e mühürlemeli"
    )
    assert "set_ready" not in fn, "initiate ajan bazında da READY boyayamaz"


def test_agents_status_endpoint_documents_source_vocabulary():
    source = API_SRC.read_text(encoding="utf-8")
    endpoint = source[source.index('@app.get("/api/agents/status")'):]
    endpoint = endpoint[: endpoint.index("@app.post")]
    for state in ("redis_bus", "in_memory", "fallback", "error"):
        assert state in endpoint, f"/api/agents/status belgelemesi {state} kaynağını içermeli"


# --------------------------------------------------------------------------- #
# 3) Kasa mandalı: dosya varlığı ≠ anahtar varlığı
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "vault,expected",
    [
        ({}, False),
        ({"providers": {}}, False),
        ({"provider_keys": {}}, False),
        ({"api_key": ""}, False),
        ({"api_key": "sk-or-v1-YOUR-KEY-HERE"}, False),
        ({"tavily_key": "   "}, False),
        ({"providers": {"deepseek": {"api_key": "sk-gercek-anahtar"}}}, True),
        ({"provider_keys": {"groq": "gsk_gercek"}}, True),
        ({"api_key": "sk-or-v1-gercek-anahtar"}, True),
        ({"or_key": True}, True),
        ({"tavily_key": "tvly-gercek"}, True),
        ({"ig_sessionid": "sessionid=abc123"}, True),
    ],
)
def test_vault_bears_key_material(vault, expected):
    from backend import api

    assert api._vault_bears_key_material(vault) is expected, vault


def test_interlock_denies_keyless_vault_file(monkeypatch):
    """`.pineal_vault.json` var ama içi boş -> dış dünya KİLİTLİ kalır."""
    from backend import api

    monkeypatch.setattr(api, "get_room", lambda _cid: {"vault": {}})
    monkeypatch.setattr(api, "_load_vault", lambda *a, **k: {"providers": {}})
    assert api._check_vault_interlock("musteri-1") is False

    monkeypatch.setattr(api, "_load_vault", lambda *a, **k: {"api_key": "sk-or-v1-YOUR-KEY"})
    assert api._check_vault_interlock("musteri-1") is False


def test_interlock_opens_with_real_key_material(monkeypatch):
    from backend import api

    monkeypatch.setattr(api, "get_room", lambda _cid: {"vault": {"or_key": True}})
    monkeypatch.setattr(api, "_load_vault", lambda *a, **k: {})
    assert api._check_vault_interlock("musteri-1") is True

    monkeypatch.setattr(api, "get_room", lambda _cid: {"vault": {}})
    monkeypatch.setattr(api, "_load_vault", lambda *a, **k: {"providers": {"groq": {"api_key": "gsk_x"}}})
    assert api._check_vault_interlock("musteri-1") is True


def test_interlock_fails_closed_on_error(monkeypatch):
    from backend import api

    def boom(_cid):
        raise RuntimeError("oda yok")

    monkeypatch.setattr(api, "get_room", boom)
    assert api._check_vault_interlock("musteri-1") is False


# --------------------------------------------------------------------------- #
# 4) Frontend: UI kaynağı izlenebilir, uydurma durum yok
# --------------------------------------------------------------------------- #
def test_store_exposes_status_source_with_honest_vocabulary():
    source = STORE_TS.read_text(encoding="utf-8")
    assert "export const agentStatusSource" in source
    for state in ("redis_bus", "in_memory", "fallback", "error", "unreachable", "none"):
        assert f"'{state}'" in source, f"agentStatusSource sözlüğünde {state} yok"


def test_app_nulls_telemetry_when_backend_unreachable():
    source = APP_SVELTE.read_text(encoding="utf-8")
    fetch_block = source[source.index("async function fetchTelemetry"):]
    fetch_block = fetch_block[: fetch_block.index("\n  }")]
    assert "telemetryData = null" in fetch_block, (
        "fetchTelemetry hata yolunda telemetri null'a çekilmeli (bayat veri "
        "canlı veri gibi gösterilemez)"
    )


def test_app_records_backend_declared_status_source():
    source = APP_SVELTE.read_text(encoding="utf-8")
    assert "agentStatusSource.set(" in source
    assert "data.source" in source, "kaynak backend beyanından okunmalı"
    assert "'unreachable'" in source, "tanımsız/hatalı yanıt unreachable'a düşmeli"


def test_agent_rack_counts_come_from_backend_statuses_only():
    source = AGENT_RACK.read_text(encoding="utf-8")
    code = _code_only(source, comment="//")
    # Eski kusur: `readyCount = ... || AGENT_DEFINITIONS.length` (12 READY uydurma)
    assert re.search(r"readyCount[^;\n]*\|\|", code) is None, (
        "READY sayacı yedeğe düşemez: ölçülmeyen durum uydurma sayıya dönüşür"
    )
    assert re.search(r"\|\|\s*12\b", code) is None
    assert re.search(r"\|\|\s*AGENT_DEFINITIONS\.length", code) is None
    assert "slotLabels.filter" in source, "sayaçlar render edilen slotlardan türemeli"
    assert "errorCount" in source, "ERROR sayacı olmalı (hata gizlenemez)"
    assert "KAYNAK" in source and "$agentStatusSource" in source
    assert "in_memory: 'YEREL BELLEK (REDIS YOK)'" in source
    # Sabit "REDIS PUB/SUB" metni tek yerde tanımlıdır (yalnız kaynak redis_bus
    # iken görünür); koşulsuz basılan ikinci bir kopya olamaz.
    assert source.count("REDIS PUB/SUB") == 1


def test_war_room_does_not_fabricate_operator_profile():
    source = WAR_ROOM.read_text(encoding="utf-8")
    fakes = ("Morning cold exposure", "Max Richter", "Nils Frahm", "intellectual architects")
    for line in source.splitlines():
        if any(fake in line for fake in fakes):
            assert line.strip().startswith("//"), (
                f"uydurma operatör verisi kod satırında yaşıyor: {line.strip()[:120]}"
            )
    assert "let userRituals = ''" in source
    assert "let userPlaylist = ''" in source
    assert "let userEnvies = ''" in source
    assert "OPERATÖR VERİSİ" in source, "operatör girişi UI'da görünür olmalı"


def test_war_room_summaries_have_no_fabricated_defaults():
    source = WAR_ROOM.read_text(encoding="utf-8")
    code = _code_only(source, comment="//")
    assert "?? 15" not in code, "Aşil skoru uydurma varsayılana düşemez"
    assert re.search(r"plannedCount[^;\n]*\|\|\s*12", code) is None
    assert "'Analitik'" not in code
    assert "3 jürili" not in code, "jüri sayısı koşudan okunmalı (koltuk düşebilir)"
    assert "jurors" in code, "gerçek jüri sayısı output_summary.jurors'tan okunur"
    for honest in ("veri yok", "ölçülmedi", "kanıt yok"):
        assert honest in code, f"{honest!r} dürüst varsayılanı kaybolmuş"
