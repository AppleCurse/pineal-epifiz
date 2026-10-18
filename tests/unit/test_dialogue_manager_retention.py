import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_core.chat.dialogue_manager import (
    DialogueInputError,
    DialogueManager,
    DialogueSessionCapacityError,
)


@pytest.mark.asyncio
async def test_response_does_not_evict_live_session_at_full_capacity(monkeypatch):
    monkeypatch.setenv("PINEAL_MAX_DIALOGUE_SESSIONS", "1")
    monkeypatch.setenv("PINEAL_DIALOGUE_SESSION_TTL_SECONDS", "3600")
    gateway = MagicMock()
    dm = DialogueManager(llm_gateway=gateway)
    dm.start_session("only-session", {}, {})

    async def fake_query_json(prompt, schema, **kwargs):
        return schema(
            stance="Ilgili",
            internal_analysis="test",
            next_move="test response",
        )

    gateway.query_json = AsyncMock(side_effect=fake_query_json)
    response = await dm.generate_response("only-session", "hello")

    assert response.next_move == "test response"
    assert "only-session" in dm.sessions
    assert len(dm.sessions) == 1


def test_starting_new_session_evicts_oldest_only_to_reserve_capacity(monkeypatch):
    monkeypatch.setenv("PINEAL_MAX_DIALOGUE_SESSIONS", "1")
    monkeypatch.setenv("PINEAL_DIALOGUE_SESSION_TTL_SECONDS", "3600")
    dm = DialogueManager(llm_gateway=MagicMock())

    dm.start_session("first", {}, {})
    first_last_seen = dm.sessions["first"].last_seen
    dm.start_session("second", {}, {})

    assert "first" not in dm.sessions
    assert "second" in dm.sessions
    assert dm.evicted == 1
    assert dm.sessions["second"].last_seen >= first_last_seen


def test_invalid_or_nonfinite_history_cap_uses_safe_default(monkeypatch):
    monkeypatch.setenv("PINEAL_MAX_DIALOGUE_MESSAGES", "1e400")
    dm = DialogueManager(llm_gateway=MagicMock())
    assert dm.max_history_messages == 40


def test_dialogue_history_is_bounded_per_session(monkeypatch):
    monkeypatch.setenv("PINEAL_MAX_DIALOGUE_MESSAGES", "3")
    dm = DialogueManager(llm_gateway=MagicMock())
    dm.start_session("bounded", {}, {})

    for index in range(5):
        dm.add_message("bounded", "target", f"message-{index}")

    history = dm.sessions["bounded"].history
    assert len(history) == 3
    assert [message["content"] for message in history] == [
        "message-2", "message-3", "message-4"
    ]


@pytest.mark.asyncio
async def test_inflight_session_is_protected_from_ttl_and_capacity_eviction(monkeypatch):
    monkeypatch.setenv("PINEAL_MAX_DIALOGUE_SESSIONS", "1")
    monkeypatch.setenv("PINEAL_DIALOGUE_SESSION_TTL_SECONDS", "1")
    gateway = MagicMock()
    dm = DialogueManager(llm_gateway=gateway)
    dm.start_session("active", {}, {})
    request_started = asyncio.Event()
    release_response = asyncio.Event()

    async def delayed_response(prompt, schema, **kwargs):
        request_started.set()
        await release_response.wait()
        return schema(stance="Ilgili", internal_analysis="test", next_move="response")

    gateway.query_json = AsyncMock(side_effect=delayed_response)
    request = asyncio.create_task(dm.generate_response("active", "hello"))
    await request_started.wait()

    # Simulate both expiry and a new session request while the model call waits.
    assert dm._evict_sessions(time.monotonic() + 1000) == 0
    with pytest.raises(DialogueSessionCapacityError):
        dm.start_session("new", {}, {})
    assert "active" in dm.sessions
    assert "new" not in dm.sessions

    release_response.set()
    response = await request
    assert response.next_move == "response"
    assert "active" in dm.sessions
    assert len(dm.sessions) == 1
    assert dm._active_sessions == {}


def test_dialogue_message_and_profile_size_limits_are_enforced(monkeypatch):
    monkeypatch.setenv("PINEAL_MAX_DIALOGUE_MESSAGE_CHARS", "8")
    monkeypatch.setenv("PINEAL_MAX_DIALOGUE_PROFILE_BYTES", "32")
    dm = DialogueManager(llm_gateway=MagicMock())

    with pytest.raises(DialogueInputError, match="boyutu aşıyor"):
        dm.start_session("oversized-profile", {"bio": "x" * 80}, {})
    assert "oversized-profile" not in dm.sessions

    dm.start_session("bounded", {}, {})
    dm.add_message("bounded", "target", "12345678")
    with pytest.raises(DialogueInputError, match="uzunluğu aşıyor"):
        dm.add_message("bounded", "target", "123456789")
    assert [entry["content"] for entry in dm.sessions["bounded"].history] == ["12345678"]
