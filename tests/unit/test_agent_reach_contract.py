"""Agent-Reach web-fallback command, target, timeout, and output contracts."""

import asyncio

import pytest

from agent_core.capabilities import adapters_sensors
from agent_core.capabilities.base import CapabilityContext
from agent_core.capabilities.adapters_sensors import AgentReachCapability
from agent_core.utils import security


class _Reader:
    def __init__(self, data: bytes = b""):
        self.data = data

    async def read(self, size: int) -> bytes:
        chunk, self.data = self.data[:size], self.data[size:]
        return chunk


class _Process:
    def __init__(self, stdout=b"actual public text", stderr=b"", returncode=0):
        self.stdout = _Reader(stdout)
        self.stderr = _Reader(stderr)
        self.returncode = returncode
        self.killed = False

    async def wait(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


@pytest.mark.asyncio
async def test_agent_reach_uses_operator_command_and_validates_public_target(monkeypatch):
    monkeypatch.setenv("PINEAL_AGENT_REACH_CMD", "python -u")
    monkeypatch.setattr(security, "is_safe_url", lambda _url: True)
    seen = {}
    proc = _Process()

    async def fake_exec(*args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return proc

    monkeypatch.setattr(adapters_sensors.asyncio, "create_subprocess_exec", fake_exec)
    result = await AgentReachCapability().run(
        CapabilityContext(subject="https://x.com/example")
    )

    assert result.ok is True
    assert result.items[0].content == "actual public text"
    assert seen["args"] == ("python", "-u", "read", "https://x.com/example")
    assert seen["kwargs"]["stdout"] == asyncio.subprocess.PIPE
    assert seen["kwargs"]["stderr"] == asyncio.subprocess.PIPE


@pytest.mark.asyncio
async def test_agent_reach_rejects_unsupported_and_private_targets_before_spawn(monkeypatch):
    monkeypatch.setenv("PINEAL_AGENT_REACH_CMD", "python")
    calls = 0

    async def unexpected_exec(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("unsupported/private target reached subprocess")

    monkeypatch.setattr(adapters_sensors.asyncio, "create_subprocess_exec", unexpected_exec)
    cap = AgentReachCapability()

    unsupported = await cap.run(CapabilityContext(subject="https://example.com/article"))
    assert unsupported.unavailable_reason == "unsupported_host"

    monkeypatch.setattr(security, "is_safe_url", lambda _url: False)
    private = await cap.run(CapabilityContext(subject="https://x.com/private"))
    assert private.unavailable_reason == "ssrf_blocked"
    assert calls == 0


@pytest.mark.asyncio
async def test_agent_reach_kills_process_after_timeout(monkeypatch):
    monkeypatch.setenv("PINEAL_AGENT_REACH_CMD", "python")
    monkeypatch.setattr(security, "is_safe_url", lambda _url: True)
    cap = AgentReachCapability()
    cap.timeout_seconds = 0.02

    class _BlockingReader:
        async def read(self, size):
            await asyncio.Event().wait()

    proc = _Process(returncode=None)
    proc.stdout = _BlockingReader()

    async def fake_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(adapters_sensors.asyncio, "create_subprocess_exec", fake_exec)
    result = await cap.run(CapabilityContext(subject="https://reddit.com/r/test"))

    assert result.unavailable_reason == "timeout"
    assert proc.killed is True


@pytest.mark.asyncio
async def test_agent_reach_kills_process_when_caller_cancels(monkeypatch):
    monkeypatch.setenv("PINEAL_AGENT_REACH_CMD", "python")
    monkeypatch.setattr(security, "is_safe_url", lambda _url: True)
    cap = AgentReachCapability()
    cap.timeout_seconds = 10
    read_started = asyncio.Event()

    class _BlockingReader:
        async def read(self, size):
            read_started.set()
            await asyncio.Event().wait()

    proc = _Process(returncode=None)
    proc.stdout = _BlockingReader()

    async def fake_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(adapters_sensors.asyncio, "create_subprocess_exec", fake_exec)
    task = asyncio.create_task(
        cap.run(CapabilityContext(subject="https://github.com/example/repo"))
    )
    await asyncio.wait_for(read_started.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert proc.killed is True


@pytest.mark.asyncio
async def test_agent_reach_bounds_stdout_and_stops_oversized_process(monkeypatch):
    monkeypatch.setenv("PINEAL_AGENT_REACH_CMD", "python")
    monkeypatch.setattr(security, "is_safe_url", lambda _url: True)
    monkeypatch.setattr(adapters_sensors, "_AGENT_REACH_MAX_STDOUT_BYTES", 5)
    proc = _Process(stdout=b"this is more than five bytes", returncode=None)

    async def fake_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(adapters_sensors.asyncio, "create_subprocess_exec", fake_exec)
    result = await AgentReachCapability().run(
        CapabilityContext(subject="https://youtube.com/watch?v=sample")
    )

    assert result.unavailable_reason == "output_too_large"
    assert proc.killed is True
