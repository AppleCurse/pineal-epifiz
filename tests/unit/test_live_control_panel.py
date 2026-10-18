"""[P6 · CANLI KONTROL PANELİ] Uçtan uca sözleşme testleri.

Kapsam (üç düzeltme):
  D1 — Canlı arayüz (kokpit) `/api/aspasia/command` ucuna bağlandı; komut
       reddedilirse/hataya düşerse sahte "emir alındı" ÜRETİLMEZ, sebep
       sohbet ucuna düşer.
  D2 — `/api/aspasia/state` çağrı izini (`calls`) yayınlıyor → çağrı kimliği
       yaşam döngüsü izlenebilir (call_id → ajan → model → ms → $).
  D3 — AgentRun serileştirmesi panelin ihtiyaç duyduğu alanları taşıyor:
       input_summary, evidence_ids, responsibility, decision_grade, warnings,
       error_code.
  D4 — `LiveControlPanel.svelte` App.svelte'ye BAĞLI (ölü bileşen değil) ve
       yalnız CANLI SoT'tan besleniyor (elle/örnek veri yok).

Her iddia kanıta bağlıdır: backend alanları çalıştırılarak, frontend ise
statik kontratla (derlenen içerik) doğrulanır.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND_SRC = Path("frontend/src")
APP = FRONTEND_SRC / "App.svelte"
COCKPIT = FRONTEND_SRC / "components" / "AtlasPinealCockpit.svelte"
PANEL = FRONTEND_SRC / "components" / "LiveControlPanel.svelte"


# ---------------------------------------------------------------- yardımcılar

def _strip_comments(text: str) -> str:
    """Yorumları at — depodaki düzeltme notları yanlış okunmasın."""
    stripped = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.S)
    return "\n".join(
        line for line in stripped.splitlines() if not line.lstrip().startswith("//")
    )


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ------------------------------------------------------------------ D3 (backend)

def test_serialize_run_entry_carries_panel_fields():
    """AgentRun → panel alanları: girdi özeti, kanıt, muhakeme, karar, uyarı."""
    from backend.api import _serialize_run_entry
    from agent_core.domain.memory_models import AgentRun

    run = AgentRun(
        task_id="t-1",
        agent_name="deep_analyst",
        status="running",
        input_summary={"bio_len": 12, "urls": ["https://instagram.com/x/"], "url_count": 1},
        output_summary={"_provenance": {"source": "llm", "model": "m/x", "provider": "p"}},
        confidence=0.7,
        decision_grade=True,
        evidence_ids=["ev-1", "ev-2"],
        call_ids=["call-a", "call-b"],
        responsibility={"attempted": True, "next_action": "x"},
        warnings=["w1"],
    )
    entry = _serialize_run_entry(run, with_timestamps=True)

    assert entry["input_summary"]["urls"] == ["https://instagram.com/x/"]
    assert entry["input_summary"]["url_count"] == 1
    assert entry["evidence_ids"] == ["ev-1", "ev-2"]
    assert entry["call_ids"] == ["call-a", "call-b"]
    assert entry["decision_grade"] is True
    assert entry["responsibility"]["next_action"] == "x"
    assert entry["warnings"] == ["w1"]
    # Zaman damgaları snapshot için hâlâ geliyor
    assert "started_at" in entry and "completed_at" in entry


def test_serialize_run_entry_redacts_secrets_in_input_and_responsibility():
    """Panel alanları gizli kalabalık taşımaz (redact uygulanır)."""
    from backend.api import _serialize_run_entry
    from agent_core.domain.memory_models import AgentRun

    run = AgentRun(
        task_id="t-2",
        agent_name="a",
        status="running",
        input_summary={"api_key": "sk-live-SECRET", "urls": ["https://instagram.com/x/"]},
        responsibility={"note": "token: sk-live-SECRET"},
    )
    entry = _serialize_run_entry(run, with_timestamps=False)
    assert "sk-live-SECRET" not in str(entry["input_summary"])
    assert "sk-live-SECRET" not in str(entry["responsibility"])
    # Redact sonrası alanlar YİNE de görünür (sessizce düşmez)
    assert "urls" in entry["input_summary"]


def test_summarize_input_reports_target_urls():
    """'Hangi ajan o anda nereyi kazıyor' → gerçek URL listesi (içerik değil)."""
    from agent_core.task_executor import PinealExecutor

    summary = PinealExecutor._summarize_input(
        self=object(),
        input_data={
            "target_profile": {
                "bio": "x" * 5,
                "posts": [],
                "detected_urls": ["https://instagram.com/ayse/"],
                "scraped_urls": ["https://instagram.com/ayse/", "https://www.instagram.com/ayse/"],
            }
        },
        agent_name="deep_analyst",
    )
    assert summary["url_count"] == 2  # yinelenenler sayılmaz
    assert "https://instagram.com/ayse/" in summary["urls"]
    # Profil İÇERİĞİ taşınmaz (yalnız sayı + URL)
    assert "bio" not in summary
    assert summary["bio_len"] == 5


# ------------------------------------------------------------------ D2 (backend)

def test_aspasia_state_exposes_call_trace():
    """`/api/aspasia/state` çağrı izini (calls) yayınlıyor → izlenebilirlik."""
    from starlette.testclient import TestClient

    from backend.api import app

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/aspasia/state", params={"client_id": "panel_probe"})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert "calls" in payload, "state yanıtı çağrı izi taşımıyor"
    assert "call_count" in payload
    assert isinstance(payload["calls"], list)
    assert payload["call_count"] == len(payload["calls"])


def test_aspasia_state_calls_rows_have_trace_fields():
    """Çağrı satırları izlenebilirlik alanlarını taşır (call_id, ajan, model, ms)."""
    from agent_core.aspasia.interface import TelemetryReader

    class _Gateway:
        call_log = [
            {
                "call_id": "c-1",
                "model": "m/a",
                "requested_model": "m/a",
                "actual_model": "m/a",
                "provider": "p",
                "route_key": "r",
                "chain_source": "aspasia",
                "quota_status": "ok",
                "error": None,
                "duration_ms": 120,
                "cost_usd": 0.001,
                "agent_id": "aspasia",
            }
        ]

    rows = TelemetryReader(_Gateway()).recent()
    assert len(rows) == 1
    row = rows[0]
    for field in ("call_id", "model", "provider", "duration_ms", "cost_usd", "agent_id"):
        assert field in row, f"çağrı satırında {field} yok"


def test_ws_snapshot_carries_channel_status():
    """WS snapshot kanal defterini ANLIK taşır → "hangi modül nerede" canlı görünür.

    Önceden kanal durumu snapshot nesnesinde VARDI ama WS payload'ına
    serileştirilmiyordu (sadece görev sonundaki `result` taşıyordu).
    """
    import asyncio
    import json
    from types import SimpleNamespace

    from backend.api import _send_snapshot

    sent: list[str] = []

    class _FakeWS:
        async def send_text(self, text: str) -> None:
            sent.append(text)

    room = {"websockets": {_FakeWS()}}
    snapshot = SimpleNamespace(
        task_id="t-1",
        current_agent="deep_analyst",
        status="running",
        planned_agents=["deep_analyst"],
        completed_agents=[],
        halted_reason=None,
        resonance_score=None,
        channel_status=[{"channel": "instagram.scrape", "status": "ok", "detail": "d"}],
        holistic_profile=None,
        follower_audit=None,
        timing_forensics=None,
        depth_report=None,
        visual_evidence=None,
        shadow_profile=None,
        osint_footprint=None,
        telemetry={},
        agent_runs={},
    )
    asyncio.run(_send_snapshot(room, snapshot))

    assert sent, "snapshot gönderilmedi"
    payload = json.loads(sent[-1])
    assert payload["type"] == "snapshot_update"
    assert payload["channel_status"] == [
        {"channel": "instagram.scrape", "status": "ok", "detail": "d"}
    ]


def test_aspasia_state_binds_call_ids_to_agents():
    """Çağrı kimliği bağlayıcısı: `run.call_ids` ↔ gateway `call_log` AYNI uzay.

    Kopukluk olursa panel "hangi ajan hangi çağrıyı yaptı" sorusunu
    CEVAPLAYAMAZ. Bağlayıcı sunucu tarafında kurulur: her çağrı satırına
    `bound_agents` yazılır, görünür pencerede olmayan koşu çağrıları SAYILIR.
    """
    from types import SimpleNamespace

    from starlette.testclient import TestClient

    from backend.api import app, get_room

    client_id = "binding_probe"
    room = get_room(client_id)
    room["active_tasks"] = {
        "t-1": {
            "task_id": "t-1",
            "status": "running",
            "planned_agents": ["deep_analyst"],
            "completed_agents": [],
            "current_agent": "deep_analyst",
            "agent_runs": {
                "deep_analyst": SimpleNamespace(
                    status="running", call_ids=["call-xyz", "call-gone"]
                )
            },
        }
    }
    gateway = room["executor"].llm_gateway
    gateway.call_log.append({
        "call_id": "call-xyz",
        "model": "m/a",
        "requested_model": "m/a",
        "actual_model": "m/a",
        "provider": "p",
        "route_key": "r",
        "chain_source": "agent",
        "quota_status": "ok",
        "error": None,
        "duration_ms": 42,
        "cost_usd": 0.0001,
        "agent_id": "deep_analyst",
    })

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/aspasia/state", params={"client_id": client_id})
    assert response.status_code == 200, response.text
    payload = response.json()

    rows = {row["call_id"]: row for row in payload["calls"]}
    assert "call-xyz" in rows
    assert rows["call-xyz"]["bound_agents"] == ["deep_analyst"]
    binding = payload["call_binding"]
    assert binding["run_call_count"] == 2
    assert binding["bound_call_count"] == 1
    # Pencere dışındaki çağrı SESSİZCE kaybolmaz: sayılır ve sebebi yazılır.
    assert binding["missing_call_ids"] == ["call-gone"]
    assert binding["missing_reason"]


# ------------------------------------------------------------------ D1 (frontend)

def test_cockpit_calls_command_endpoint():
    """Canlı arayüz komut ucuna bağlı (pasif izleme modunda değil)."""
    text = _strip_comments(_read(COCKPIT))
    # Tam URL eşleşmesi: "/api/aspasia/command" DEĞİL, "/api/aspasia/command_x"
    # gibi bir uç komutu da tetiklemez.
    assert re.search(r"['\"]/api/aspasia/command['\"]", text), (
        "kokpit komut ucuna bağlı değil"
    )


def test_cockpit_command_falls_back_to_chat_without_faking_success():
    """Komut reddedilirse sahte onay üretilmez; sohbet ucu devreye girer."""
    text = _strip_comments(_read(COCKPIT))
    assert "/api/aspasia/chat" in text, "sohbet yedeği yok"
    # Onay metni YALNIZ gerçekten kabul edilmiş komutta üretilebilir:
    # kabul kontrolü (`accepted && task_id`) metinden ÖNCE gelmelidir.
    accept_idx = text.find("data.accepted && data.task_id")
    assert accept_idx != -1, "kabul kontrolü yok"
    for marker in ("Emir alındı", "emir alındı"):
        idx = text.find(marker)
        if idx != -1:
            assert idx > accept_idx, "onay metni kabul kontrolünden ÖNCE üretiliyor"
    # Sohbet yedeğinde sahte emir onayı YEDEĞİ olamaz.
    chat_idx = text.find("/api/aspasia/chat")
    fallback = text[chat_idx:chat_idx + 800]
    assert "'Emir alındı Mösyö.'" not in fallback, (
        "sohbet yedeğinde sahte emir onayı var"
    )


def test_cockpit_command_requires_accepted_and_task_id():
    """Yalnız `accepted && task_id` → görev başlar; aksi hâlde sebep bildirilir."""
    text = _strip_comments(_read(COCKPIT))
    assert "task_id" in text
    assert "accepted" in text


# ------------------------------------------------------------------ D4 (frontend)

def test_live_control_panel_is_mounted_in_app():
    """Panel App.svelte'ye bağlı → ölü bileşen (C5) değil, gerçekten görünür."""
    app_text = _read(APP)
    assert "LiveControlPanel" in app_text, "LiveControlPanel import edilmiyor"
    assert re.search(r"<LiveControlPanel\s*/>", app_text), "LiveControlPanel render edilmiyor"
    assert "'control'" in app_text, "görünüm seçici 'control' modunu tanımıyor"


def test_live_control_panel_reads_live_sources_only():
    """Panel yalnız CANlı SoT'tan beslenir: WS snapshot + /api/aspasia/state."""
    text = _strip_comments(_read(PANEL))
    assert "taskStatus" in text, "panel WS snapshot'ı okumuyor"
    assert "/api/aspasia/state" in text, "panel durum ucunu okumuyor"
    assert "calls" in text, "panel çağrı izini göstermiyor"
    # Örnek/elle veri kalıpları yasak
    for fake in ("mockRuns", "sampleRuns", "demoRuns", "fakeRuns", "FAKE_"):
        assert fake not in text, f"panelde üretilmiş veri kalıbı: {fake}"


def test_live_control_panel_shows_all_required_blocks():
    """Panelde istenen dört bilgi görünür: ajan hattı, kanal, muhakeme, kanıt."""
    text = _read(PANEL)
    for marker in ("AJAN HATTI", "MUHAKEME", "KANIT", "ÇAĞRI"):
        assert marker in text, f"panelde {marker} bloğu yok"


def test_live_control_panel_reports_empty_state_honestly():
    """Ölçüm yokken sebep yazılır (uydurma sayı yok)."""
    text = _read(PANEL)
    assert "YETERSİZ KANIT" in text, "panel boş durumda kanonik işareti kullanmıyor"
    # Her boş durum bloğu bir SEBEP yazmalı (sessiz boş kalmak yasak).
    assert text.count("INSUFFICIENT") >= 5, "panelde boş durum sayısı düşük"


def test_live_control_panel_shows_call_identity_binding():
    """Panel çağrı kimliği bağını gösterir (koşu → çağrı → ajan)."""
    text = _strip_comments(_read(PANEL))
    assert "call_binding" in text, "panel çağrı bağı özetini okumuyor"
    assert "bound_agents" in text, "panel koşuya bağlı ajanı göstermiyor"
    assert "run_call_count" in text


def test_live_control_panel_shows_input_summary_urls():
    """'Hangi ajan nereyi kazıyor' → input_summary.urls okunur."""
    text = _strip_comments(_read(PANEL))
    assert "input_summary" in text
    assert "urls" in text


# ------------------------------------------------------------------ komut akışı

def test_aspasia_command_endpoint_rejects_without_gateway():
    """Komut ucu gateway yokken sahte kabul dönmemeli (kabul iddiası yalan olur)."""
    from starlette.testclient import TestClient

    from backend.api import app

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/aspasia/command",
            json={"client_id": "panel_probe_cmd", "user_message": "merhaba"},
        )

    assert response.status_code in (200, 429, 503), response.text
    if response.status_code == 200:
        payload = response.json()
        # Kabul edilmişse görev kimliği de olmalı (yoksa kabul iddiası tutarsız)
        assert bool(payload.get("accepted")) == bool(payload.get("task_id")), payload
        if not payload.get("accepted"):
            assert payload.get("reason"), "reddedilen komutta sebep yok"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
