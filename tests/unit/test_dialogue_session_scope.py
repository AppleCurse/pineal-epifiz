"""Regression tests for principal-scoped dialogue storage and listing."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend import api

ROOT_TOKEN = "dialogue-root-token-value"
ALICE_TOKEN = "dialogue-alice-token-value"
BOB_TOKEN = "dialogue-bob-token-value"


class _FakeDialogueManager:
    def __init__(self):
        self.sessions = {}
        self.evicted = 0

    def start_session(self, task_id, target_profile, user_profile):
        self.sessions[task_id] = SimpleNamespace(
            history=[], last_seen=1.0, target_profile=target_profile,
            user_profile=user_profile,
        )

    async def generate_response(self, task_id, target_message):
        session = self.sessions[task_id]
        session.history.append({"role": "target", "content": target_message})
        return SimpleNamespace(
            model_dump=lambda: {
                "stance": "Bilinmiyor",
                "internal_analysis": "test result",
                "next_move": "test response",
            }
        )


def test_dialogue_task_ids_are_scoped_to_authenticated_identity(monkeypatch):
    monkeypatch.setenv("PINEAL_ENV", "production")
    monkeypatch.setenv("PINEAL_TOKEN", ROOT_TOKEN)
    monkeypatch.setenv(
        "PINEAL_OPERATOR_TOKENS",
        f"alice:{ALICE_TOKEN},bob:{BOB_TOKEN}",
    )
    monkeypatch.setenv("OPENROUTER_MAX_SPEND_USD", "50")
    monkeypatch.setenv("PINEAL_MAX_SPEND_USD", "50")
    monkeypatch.setenv("PINEAL_MAX_ROOMS", "512")
    monkeypatch.setenv("PINEAL_MINORS_GATE", "true")

    manager = _FakeDialogueManager()
    previous_manager = api.dialogue_manager
    api.dialogue_manager = manager
    api.app.state.rooms.clear()
    api.app.state.minor_cases.clear()
    try:
        with TestClient(api.app) as client:
            for token, profile, message in (
                (ALICE_TOKEN, {"owner": "alice"}, "alice turn"),
                (BOB_TOKEN, {"owner": "bob"}, "bob turn"),
            ):
                response = client.post(
                    "/api/experimental/chat/respond",
                    headers={"X-API-Key": token},
                    json={
                        "task_id": "shared-task-id",
                        "target_profile": profile,
                        "user_profile": {},
                        "target_message": message,
                    },
                )
                assert response.status_code == 200, response.text

            assert len(manager.sessions) == 2
            scoped_keys = list(manager.sessions)
            assert scoped_keys[0] != scoped_keys[1]
            assert all(key.endswith(":shared-task-id") for key in scoped_keys)
            assert {session.target_profile["owner"] for session in manager.sessions.values()} == {
                "alice", "bob"
            }

            alice_sessions = client.get(
                "/api/dialogue/sessions", headers={"X-API-Key": ALICE_TOKEN}
            )
            bob_sessions = client.get(
                "/api/dialogue/sessions", headers={"X-API-Key": BOB_TOKEN}
            )
            assert alice_sessions.status_code == bob_sessions.status_code == 200
            assert alice_sessions.json()["count"] == 1
            assert bob_sessions.json()["count"] == 1
            assert alice_sessions.json()["sessions"][0]["task_id"] == "shared-task-id"
            assert bob_sessions.json()["sessions"][0]["task_id"] == "shared-task-id"
    finally:
        api.dialogue_manager = previous_manager
        api.app.state.rooms.clear()
        api.app.state.minor_cases.clear()
