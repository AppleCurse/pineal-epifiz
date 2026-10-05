"""FAZ C · C1 — Jenerik yanıt filtresi uçtan uca: Aspasia + telemetri + API.

Kilitlenen iddia: Aspasia'nın dili artık bir prompt umudu değil — jenerik
yanıt ÖLÇÜLÜR, kullanıcıya ÇIKMAZ, yerine kanıt cümlesi konur ve olay
telemetriye yazılır (operatör neden düştüğünü görür).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_core.aspasia.aspasia_chief import AspasiaChief
from agent_core.services import taste_filter
from backend import api

GENERIC_REPLY = (
    "Tabii ki! Kesinlikle harika bir soru. Elbette size yardımcı olabilirim. "
    "Bir yapay zeka olarak genel olarak şunu söyleyebilirim: belki böyle, "
    "muhtemelen şöyle, sanırım da öyle olabilir. Daha fazla bilgi verirseniz "
    "size nasıl yardımcı olabilirim? Çok önemli, gerçekten oldukça önemli bir konu."
)

CONCRETE_REPLY = (
    "Mösyö, görev fx_1 tamamlandı: 7 kanıt kaydından 3'ü doğrulandı, "
    "gerçeklik endeksi 0.62. Kalan iki sütun için ölçüm yok."
)


class _StubGateway:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list[str] = []

    async def query_chain(self, **kwargs):
        self.calls.append(kwargs.get("agent_name") or "?")
        return self.reply


@pytest.fixture(autouse=True)
def _telemetry(tmp_path, monkeypatch):
    monkeypatch.setenv("PINEAL_TELEMETRY_DIR", str(tmp_path / "tel"))
    yield


@pytest.mark.asyncio
async def test_generic_reply_never_reaches_the_user():
    room = {"client_id": "t1", "active_tasks": {}, "task_id": "fx_1", "status": "completed"}
    chief = AspasiaChief(llm_gateway=_StubGateway(GENERIC_REPLY))
    response = await chief.chat("Ne buldun?", room)

    assert GENERIC_REPLY not in response.message
    assert response.confidence_assessment == "filtered_generic"
    assert response.message.strip(), "yerine hiçbir şey konmadı"


@pytest.mark.asyncio
async def test_generic_reply_is_replaced_by_the_verdict_line():
    room = {"client_id": "t1", "task_id": "fx_1", "status": "completed"}
    chief = AspasiaChief(llm_gateway=_StubGateway(GENERIC_REPLY))
    response = await chief.chat("Ne buldun?", room)
    # Kanıt/telemetri boş olsa bile dürüst bir cümle döner (uydurma yok).
    assert isinstance(response.message, str) and response.message
    assert "uydurmayacağım" in response.message or "Mösyö" in response.message


@pytest.mark.asyncio
async def test_concrete_reply_passes_untouched():
    room = {"client_id": "t1", "task_id": "fx_1", "status": "completed"}
    chief = AspasiaChief(llm_gateway=_StubGateway(CONCRETE_REPLY))
    response = await chief.chat("Ne buldun?", room)

    assert response.message == CONCRETE_REPLY
    assert response.confidence_assessment == "high"
    assert taste_filter.telemetry_summary()["total"] == 0


@pytest.mark.asyncio
async def test_dropped_reply_is_recorded_with_its_reason():
    room = {"client_id": "t1", "task_id": "fx_1", "status": "completed"}
    chief = AspasiaChief(llm_gateway=_StubGateway(GENERIC_REPLY))
    await chief.chat("Ne buldun?", room)

    summary = taste_filter.telemetry_summary()
    assert summary["dropped"] == 1
    assert any("jenerik" in reason for reason, _ in summary["top_reasons"])


def test_telemetry_endpoint_reports_the_filter():
    with TestClient(api.app) as client:
        payload = client.get("/api/telemetry/taste").json()
    assert payload["schema_version"] == "taste-telemetry-v1"
    assert payload["scope"] == "taste"
    assert "threshold" in payload
    assert payload["machine_note"].startswith("TASTE:")
