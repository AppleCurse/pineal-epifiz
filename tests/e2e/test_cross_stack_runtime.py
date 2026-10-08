"""Critical API→executor→LLM→evidence→memory→telemetry→UI protocol E2E."""

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import app


def _schema_payload(prompt: str) -> dict:
    if "MirrorReflection" in prompt:
        return {
            "user_core_frequency": "cay_muzik_baglanti",
            "surface_persona": "sakin ve analitik",
            "alignment_score": 0.91,
            "authentic_anchors": ["çay ritüeli", "müzik", "derin bağlantı"],
            "confidence": 0.95,
            "data_confidence": True,
            "fallback_reason": None,
        }
    if "AuthenticVectorResult" in prompt:
        return {
            "depth": 0.8,
            "energy": 0.6,
            "achilles_heel": "belirsizlik",
            "core_wound": "kanıtlanamaz",
            "dark_detail": "kanıtlanamaz",
        }
    if "DepthReport" in prompt:
        return {
            "reality_index": 0.8,
            "reality_rationale": "Yalnızca verilen kanıt değerlendirildi.",
            "reality_findings": [],
            "contradictions": [],
            "state_drift": None,
            "timing_pattern": None,
            "essence_one_liner": "Kanıt sınırları korunuyor.",
            "follower_audit_summary": None,
        }
    return {}


class _LocalLLMHandler(BaseHTTPRequestHandler):
    request_count = 0
    entered = threading.Event()
    release = threading.Event()
    should_block = False

    def do_POST(self):  # noqa: N802 - stdlib handler API
        type(self).request_count += 1
        type(self).entered.set()
        if type(self).should_block:
            type(self).release.wait(timeout=5)
        length = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(length))
        content = body["messages"][-1]["content"]
        payload = {
            "id": f"local-{type(self).request_count}",
            "object": "chat.completion",
            "created": 1,
            "model": body.get("model", "local-e2e"),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": json.dumps(_schema_payload(content))},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        }
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except BrokenPipeError:
            # Test sunucusu: istemci erken kapattı — beklenen, debug izi bırakılır.
            import logging

            logging.getLogger(__name__).debug("test http sunucusu: istemci erken kapattı (BrokenPipe)")

    def log_message(self, _format, *_args):
        return


@pytest.fixture
def local_llm():
    _LocalLLMHandler.request_count = 0
    _LocalLLMHandler.entered.clear()
    _LocalLLMHandler.release.set()
    _LocalLLMHandler.should_block = False
    server = ThreadingHTTPServer(("127.0.0.1", 0), _LocalLLMHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", _LocalLLMHandler
    finally:
        _LocalLLMHandler.should_block = False
        _LocalLLMHandler.release.set()
        server.shutdown()
        thread.join(timeout=2)


def _configure_local(client: TestClient, client_id: str, url: str):
    response = client.post("/api/vault", json={
        "client_id": client_id,
        "local_url": url,
        "local_model": "local-e2e",
        "use_local": True,
    })
    assert response.status_code == 200


def test_critical_cross_stack_happy_path_without_method_mocks(
    local_llm, monkeypatch, tmp_path
):
    base_url, handler = local_llm
    monkeypatch.setenv("PINEAL_MEMORY_PATH", str(tmp_path / "memory"))
    client_id = f"cross_{uuid.uuid4().hex[:8]}"

    with TestClient(app) as client:
        _configure_local(client, client_id, base_url)
        with client.websocket_connect(f"/ws/{client_id}") as websocket:
            started = client.post("/api/initiate", json={
                "client_id": client_id,
                "url": "",
                "rituals": "çay, kitap",
                "playlist": "Neşet Ertaş",
                "envies": "derin bağlantı",
            })
            assert started.status_code == 200
            task_id = started.json()["task_id"]

            events = []
            final = None
            for _ in range(300):
                message = websocket.receive_json()
                if "event" in message:
                    events.append(message)
                if message.get("type") == "result":
                    final = message
                    break

    assert final is not None
    assert final["task_id"] == task_id
    assert final["status"] in {"completed", "partially_completed"}
    assert handler.request_count >= 2

    mirror = next(item for item in final["evidence_chain"] if item["agent"] == "mirror_truth")
    assert len(mirror["llm_calls"]) == 1
    call = mirror["llm_calls"][0]
    assert call["task_id"] == task_id
    assert call["agent_id"] == "mirror_truth"
    assert call["provider"] == "local"
    assert mirror["call_ids"] == [call["call_id"]]
    assert final["runs"]["mirror_truth"]["call_ids"] == [call["call_id"]]
    assert final["runs"]["mirror_truth"]["provenance"]["call_id"] == call["call_id"]

    memory_file = tmp_path / "memory" / f"{task_id}.json"
    persisted = json.loads(memory_file.read_text(encoding="utf-8"))
    stored_mirror = next(item for item in persisted["evidence"] if item["agent"] == "mirror_truth")
    assert stored_mirror["call_ids"] == [call["call_id"]]

    task_events = [event for event in events if event["task_id"] == task_id]
    sequences = [event["sequence"] for event in task_events]
    assert sequences == sorted(set(sequences))
    assert any(event["event_type"] == "TaskCompleted" for event in task_events)

    # The built UI consumes the same snapshot/event/result protocol exercised above.
    app_source = Path(__file__).resolve().parents[2] / "frontend/src/App.svelte"
    source = app_source.read_text(encoding="utf-8")
    assert 'data.type === "snapshot_update"' in source
    assert 'data.type === "result"' in source
    assert "data.event.event_type" in source
    assert "run.output_summary._provenance" in (
        Path(__file__).resolve().parents[2]
        / "frontend/src/components/UnifiedCompactPanel.svelte"
    ).read_text(encoding="utf-8")


def test_running_task_can_be_cancelled_idempotently(local_llm, monkeypatch, tmp_path):
    base_url, handler = local_llm
    monkeypatch.setenv("PINEAL_MEMORY_PATH", str(tmp_path / "memory"))
    handler.should_block = True
    handler.release.clear()
    client_id = f"cancel_{uuid.uuid4().hex[:8]}"

    with TestClient(app) as client:
        _configure_local(client, client_id, base_url)
        with client.websocket_connect(f"/ws/{client_id}") as websocket:
            started = client.post("/api/initiate", json={
                "client_id": client_id,
                "url": "",
                "rituals": "çay",
                "playlist": "müzik",
                "envies": "bağlantı",
            })
            task_id = started.json()["task_id"]
            cancelled = client.post(
                f"/api/tasks/{task_id}/cancel",
                params={"client_id": client_id, "reason": "e2e cancellation"},
            )
            repeated = client.post(
                f"/api/tasks/{task_id}/cancel",
                params={"client_id": client_id, "reason": "duplicate"},
            )
            handler.should_block = False
            handler.release.set()

            final = None
            for _ in range(100):
                message = websocket.receive_json()
                if message.get("type") == "result" and message.get("task_id") == task_id:
                    final = message
                    break

    assert cancelled.json()["status"] == "cancelled"
    assert repeated.json()["outcome"] == "IDEMPOTENT"
    assert final is not None and final["status"] == "cancelled"
