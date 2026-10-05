"""Wiring W4+W5 (backend/api.py): result payload korunmasi + telemetry
capability raporu + X unsupported'in WS'de gorunmesi.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api import app, broadcast_result


def test_broadcast_result_includes_runs_and_planned_agents():
    from agent_core.domain.memory_models import AgentRun, TaskSnapshot

    snapshot = TaskSnapshot(
        task_id="fx_w4",
        status="completed",
        created_at=datetime.now(timezone.utc),
        planned_agents=["mirror_truth", "resonance_calc"],
        completed_agents=["mirror_truth"],
        agent_runs={
            "mirror_truth": AgentRun(
                task_id="fx_w4", agent_name="mirror_truth", status="completed", confidence=0.9
            )
        },
    )
    queue = asyncio.Queue()
    app.state.rooms = {
        "fx_w4_client": {"queue": queue, "websockets": set(), "executor": None, "vault": {}}
    }
    broadcast_result("fx_w4_client", snapshot)
    kind, payload = queue.get_nowait()
    assert kind == "result"
    assert payload["planned_agents"] == ["mirror_truth", "resonance_calc"]
    assert payload["completed_agents"] == ["mirror_truth"]
    assert payload["runs"]["mirror_truth"]["status"] == "completed"
    assert payload["runs"]["mirror_truth"]["confidence"] == 0.9


def test_telemetry_reports_real_capabilities():
    with TestClient(app) as client:
        r = client.get("/api/telemetry", params={"client_id": f"fx_{uuid.uuid4().hex[:6]}"})
    assert r.status_code == 200
    data = r.json()
    assert data["core"] is True
    assert data["x_scraper"] is False  # B4: X yolu devre disi
    assert isinstance(data["instagram_scraper"], bool)
    assert isinstance(data["browser_installed"], bool)
    # geriye uyumlu 'scraper' anahtari artik gercek yetenegi yansitir
    assert data["scraper"] == data["instagram_scraper"]


def test_x_initiate_reports_sensor_state_over_ws():
    """[FAZ A] X artık "desteklenmiyor" diye geri ÇEVRİLMEZ.

    Gerçek sensör (`sensor.x.twscrape`) omurgadan denenir; kanıt üretemezse
    sebep makine-okunur olarak loglanır ve profil UYDURULMAZ (eski
    `awaiting_authorization` ölü yolu kaldırıldı). Test yalnız dürüstlüğü
    kilitler: sebep görünür, uydurma durum gelmez.
    """
    cid = f"fx_{uuid.uuid4().hex[:6]}"
    # Vault interlock bypass — v5.0 vault mandalı test ortamında açık sayılır
    with patch("backend.api._check_vault_interlock", return_value=True):
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/{cid}") as ws:
                r = client.post(
                    "/api/initiate",
                    json={
                        "client_id": cid,
                        "url": "https://x.com/testuser",
                        "rituals": "çay",
                        "playlist": "neşet ertaş",
                        "envies": "bağ",
                        "aggressiveness": 1.0,
                        "evidence_th": 3,
                        "scraper_type": "x",
                    },
                )
                assert r.status_code == 200
                logs = []
                result_status = None
                for _ in range(200):
                    m = ws.receive_json()
                    if m.get("type") == "log":
                        logs.append(m.get("msg") or "")
                    if m.get("type") == "result":
                        result_status = m.get("status")
                        break
                joined = "\n".join(logs)
                # Sensör yolu GERÇEKTEN denendi ve sebebini söyledi.
                assert "X" in joined
                assert ("twscrape" in joined or "SENSÖRÜ" in joined), joined[:400]
                # Eski ölü yol yok; uydurma profille "completed" gelmez.
                assert result_status != "awaiting_authorization"
                assert result_status in (
                    "completed",
                    "failed",
                    "halted_evidence",
                    "halted_frequency",
                    "halted_insufficient_evidence",
                    "partially_completed",
                )
