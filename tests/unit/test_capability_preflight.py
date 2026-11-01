"""Effective readiness != package presence != permission != live success."""
from __future__ import annotations

import asyncio
import sys
import types

import pytest

from agent_core.capabilities import (
    Availability, BaseCapability, CapabilityKind,
    CapabilityRegistry, CapabilityResult, PolicyState,
)
from agent_core.capabilities.runner import CapabilityRunner
from agent_core.capabilities.adapters_sensors import XTwscrapeCapability
from agent_core.runtime_env import ROOT


class _Probe(BaseCapability):
    id = "test.preflight"
    kind = CapabilityKind.SENSOR
    license = "MIT"

    def __init__(self, ready=True, delay=0, error=False):
        self.ready = ready
        self.delay = delay
        self.error = error
        self.calls = 0
        self.runs = 0

    def availability(self):
        return Availability.ok()

    async def preflight(self):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if self.error:
            raise RuntimeError("private details must not leak")
        return Availability.ok() if self.ready else Availability.unavailable("no_session_pool")

    async def run(self, ctx):
        self.runs += 1
        return CapabilityResult(capability_id=self.id, available=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("ready,delay,error,reason", [
    (False, 0, False, "no_session_pool"),
    (True, 11, False, "preflight_timeout"),
    (True, 0, True, "preflight_error:RuntimeError"),
])
async def test_failed_preflight_never_executes(ready, delay, error, reason):
    cap = _Probe(ready, delay, error)
    reg = CapabilityRegistry()
    reg.register(cap)
    result = await CapabilityRunner(registry=reg).run(cap.id)
    assert result.available is False
    assert result.unavailable_reason == reason
    assert cap.runs == 0
    assert result.items == ()
    assert "private details" not in str(result.to_dict())


@pytest.mark.asyncio
async def test_policy_precedes_preflight_and_preflight_is_not_live_proof():
    cap = _Probe()
    cap.gates = frozenset({"vault"})
    reg = CapabilityRegistry()
    reg.register(cap)
    runner = CapabilityRunner(registry=reg)
    denied = await runner.preflight(cap.id, state=PolicyState(vault_locked=True))
    assert denied.denied_by == "vault"
    assert cap.calls == 0
    allowed = await runner.preflight(cap.id, state=PolicyState(vault_locked=False))
    assert allowed.available is True
    assert allowed.notes == {"verification": "preflight", "live_execution_verified": False}
    assert cap.runs == 0
    row = (await reg.readiness(PolicyState(vault_locked=False)))[0]
    assert row["available"] is True
    assert row["verification"] == "preflight"
    assert row["live_execution_verified"] is False


@pytest.mark.asyncio
async def test_x_missing_empty_unreadable_and_active_pool(monkeypatch, tmp_path):
    monkeypatch.setattr("agent_core.capabilities.adapters_sensors._module_available", lambda _: True)
    db = tmp_path / "nested" / "accounts.db"
    monkeypatch.setenv("PINEAL_X_ACCOUNTS_DB", str(db))
    cap = XTwscrapeCapability()
    assert (await cap.preflight()).reason == "no_session_pool"
    assert not db.parent.exists()  # status checks do not create storage
    db.parent.mkdir()
    db.touch()
    assert (await cap.preflight()).reason == "no_session_pool"

    accounts = []
    async def get_all():
        return accounts
    pool = types.SimpleNamespace(get_all=get_all)
    monkeypatch.setitem(sys.modules, "twscrape", types.SimpleNamespace(API=lambda **_: types.SimpleNamespace(pool=pool)))
    db.write_bytes(b"fixture")
    assert (await cap.preflight()).reason == "no_session_pool"
    accounts.append(types.SimpleNamespace(active=False))
    assert (await cap.preflight()).reason == "no_session_pool"
    accounts.append(types.SimpleNamespace(active=True))
    assert (await cap.preflight()).available is True

    async def broken():
        raise OSError("corrupt")
    pool.get_all = broken
    assert (await cap.preflight()).reason == "session_pool_unreadable"
    del pool.get_all
    assert (await cap.preflight()).reason == "session_pool_unmeasurable"


def test_registry_keeps_local_diagnostic_separate_from_effective_readiness(monkeypatch):
    from agent_core.capabilities import bootstrap
    monkeypatch.setenv("ENABLE_X_SENSOR", "false")
    rows = {r["id"]: r for r in bootstrap().status(PolicyState(vault_locked=False, rate_ok=True))}
    row = rows["sensor.x.twscrape"]
    assert row["local_available"] is True  # package really is installed in this env
    assert row["available"] is False
    assert row["policy_allowed"] is False
    assert row["reason"].startswith("policy:")


def test_env_loader_is_root_relative_and_never_overrides(tmp_path):
    # Run outside pytest's deliberately disabled dotenv fixture.
    import os
    import subprocess
    env_file = tmp_path / ".env"
    env_file.write_text("PINEAL_TEST_LOADER=from_file\nPINEAL_TEST_OVERRIDE=from_file\n")
    cwd = tmp_path / "other-cwd"
    cwd.mkdir()
    env = dict(os.environ, PINEAL_TEST_OVERRIDE="explicit")
    env.pop("PINEAL_TEST_LOADER", None)
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(ROOT)!r}); "
        "import agent_core.runtime_env as r, os; "
        f"r.ROOT = r.Path({str(tmp_path)!r}); "
        "assert r.load_repo_env() is True; "
        "assert os.environ['PINEAL_TEST_LOADER'] == 'from_file'; "
        "assert os.environ['PINEAL_TEST_OVERRIDE'] == 'explicit'; print('root-relative + override=False: OK')"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=cwd, env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


@pytest.mark.parametrize("value", ["1", "true", "YES", "on", "enabled"])
def test_dependency_health_uses_shared_flag_parser(monkeypatch, value):
    from agent_core.services.dependency_health import DependencyRequirement
    monkeypatch.setenv("ENABLE_EXAMPLE", value)
    assert DependencyRequirement("x", "x", "ENABLE_EXAMPLE").enabled() is True


def test_audit_covers_all_managed_gates_and_declared_tests():
    from scripts.audit_gates import CAPABILITIES, TESTS
    from agent_core.capabilities.policy import MANAGED_GATE_FLAGS
    assert set(CAPABILITIES) == set(TESTS) == set(MANAGED_GATE_FLAGS)
    for names in TESTS.values():
        for name in names:
            assert (ROOT / "tests/unit" / name).is_file()


def test_media_prerequisites_are_not_advertised_when_missing(monkeypatch):
    from agent_core.capabilities.adapters_media import MediaFetchCapability, MediaFramesCapability
    monkeypatch.setenv("ENABLE_MEDIA_FORENSICS", "true")
    monkeypatch.setattr("agent_core.services.media_forensics.ytdlp_command", lambda: [])
    assert MediaFetchCapability().availability().reason == "dependency_missing:yt-dlp"
    monkeypatch.setattr("agent_core.capabilities.adapters_media.module_available", lambda _: False)
    assert MediaFramesCapability().availability().reason == "dependency_missing:opencv"


def test_telemetry_rate_is_measured_not_hardcoded():
    import time
    from backend import api
    key = "initiate:preflight-test"
    api._rate_buckets.pop(key, None)
    assert api.rate_snapshot(key) is True
    limit, window = api.RATE_LIMITS["initiate"]
    bucket = api._RateBucket(window)
    bucket.events.extend([time.monotonic()] * limit)
    api._rate_buckets[key] = bucket
    assert api.rate_snapshot(key) is False
    assert len(bucket.events) == limit  # observation does not spend quota
    api._rate_buckets.pop(key, None)


def test_phone_route_uses_real_capability_and_safety_gates(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import api
    calls = []

    async def fake_run(cap_id, ctx, *, state):
        calls.append((cap_id, ctx.params, state.vault_locked))
        return CapabilityResult(capability_id=cap_id, available=False,
                                unavailable_reason="fixture_no_network")

    monkeypatch.setattr("agent_core.capabilities.run_capability", fake_run)
    monkeypatch.setattr(api, "_check_vault_interlock", lambda _: True)
    with TestClient(api.app) as client:
        response = client.post("/api/commander/phone-probe", json={"client_id": "phone-test", "phone": "+905551112233"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "fixture_no_network"
    assert calls == [("sensor.identity.phone_probe", {"auto_bridge": False}, False)]
    monkeypatch.setattr(api, "_check_vault_interlock", lambda _: False)
    with TestClient(api.app) as client:
        locked = client.post("/api/commander/phone-probe", json={"client_id": "phone-test", "phone": "+905551112233"})
    assert locked.status_code == 423
    assert len(calls) == 1


def test_unknown_rate_bucket_is_not_reported_as_available():
    from backend import api
    assert api.rate_snapshot("unknown-bucket-test", "not-a-real-bucket") is None


@pytest.mark.asyncio
async def test_ytdlp_probe_measures_executable_not_module_presence(monkeypatch):
    from agent_core.services import media_forensics as mf

    monkeypatch.setattr(mf, "ytdlp_command", lambda: [sys.executable, "-c", "print('2026.10.26')"])
    ok = await mf.probe_ytdlp()
    assert ok["available"] is True and ok["version"] == "2026.10.26"

    monkeypatch.setattr(mf, "ytdlp_command", lambda: [sys.executable, "-c", "print('<module object>')"])
    bad = await mf.probe_ytdlp()
    assert bad["available"] is False and bad["reason"] == "ytdlp_version_unreadable"

    monkeypatch.setattr(mf, "ytdlp_command", lambda: [sys.executable, "-c", "raise SystemExit(7)"])
    rc = await mf.probe_ytdlp()
    assert rc["available"] is False and rc["exit_code"] == 7

    monkeypatch.setattr(mf, "ytdlp_command", lambda: [sys.executable, "-c", "import time; time.sleep(2)"])
    slow = await mf.probe_ytdlp(timeout=0.05)
    assert slow["available"] is False and slow["reason"] == "ytdlp_probe_timeout"


@pytest.mark.asyncio
async def test_media_fetch_preflight_blocks_runner_and_survives_policy_denial(monkeypatch):
    from agent_core.capabilities.adapters_media import MediaFetchCapability
    from agent_core.services import media_forensics as mf

    monkeypatch.setenv("ENABLE_MEDIA_FORENSICS", "true")
    monkeypatch.setattr(mf, "ytdlp_command", lambda: [sys.executable, "-c", "print('broken')"])
    cap = MediaFetchCapability()
    reg = CapabilityRegistry()
    reg.register(cap)
    runner = CapabilityRunner(registry=reg)
    state = PolicyState(vault_locked=False, rate_ok=True, enabled_flags={"ENABLE_MEDIA_FORENSICS": True})
    result = await runner.run(cap.id, state=state)
    assert result.available is False
    assert result.unavailable_reason == "ytdlp_version_unreadable"

    locked = (await reg.readiness(PolicyState(vault_locked=True, rate_ok=True)))[0]
    assert locked["available"] is False
    assert locked["reason"] == "policy:vault_locked"
    assert locked["local_preflight_available"] is False
    assert locked["local_preflight_reason"] == "ytdlp_version_unreadable"


@pytest.mark.asyncio
async def test_x_pool_path_oserror_is_unreadable_not_empty(monkeypatch, tmp_path):
    monkeypatch.setattr("agent_core.capabilities.adapters_sensors._module_available", lambda _: True)
    db = tmp_path / "accounts.db"
    db.write_bytes(b"fixture")
    monkeypatch.setenv("PINEAL_X_ACCOUNTS_DB", str(db))

    def denied(self):
        raise PermissionError("fixture")

    monkeypatch.setattr("pathlib.Path.stat", denied)
    assert (await XTwscrapeCapability().preflight()).reason == "session_pool_unreadable"


@pytest.mark.asyncio
async def test_x_preflight_does_not_fallback_to_default_db(monkeypatch, tmp_path):
    monkeypatch.setattr("agent_core.capabilities.adapters_sensors._module_available", lambda _: True)
    db = tmp_path / "accounts.db"
    db.write_bytes(b"fixture")
    monkeypatch.setenv("PINEAL_X_ACCOUNTS_DB", str(db))
    monkeypatch.chdir(tmp_path)

    def unsupported():
        raise TypeError("no pool kwarg")

    monkeypatch.setitem(sys.modules, "twscrape", types.SimpleNamespace(API=unsupported))
    assert (await XTwscrapeCapability().preflight()).reason == "session_pool_unmeasurable"
    assert not (tmp_path / "accounts.db").exists() or db.read_bytes() == b"fixture"
    assert not (tmp_path / "cache").exists()


@pytest.mark.asyncio
async def test_telemetry_exposes_x_session_preflight_reason(monkeypatch, tmp_path):
    from unittest.mock import MagicMock, patch
    import backend.api as api

    monkeypatch.setattr("agent_core.capabilities.adapters_sensors._module_available", lambda _: True)
    monkeypatch.setenv("PINEAL_X_ACCOUNTS_DB", str(tmp_path / "missing-accounts.db"))
    executor = MagicMock()
    executor.llm_gateway = MagicMock()
    executor.search_engine = MagicMock()
    room = {"executor": executor, "vault": {}}
    with patch("backend.api.get_room", return_value=room), \
         patch("backend.api.get_vault", return_value={}), \
         patch("backend.api._scraper_capability", return_value={"instagram": False, "browser": False}), \
         patch("backend.api._check_vault_interlock", return_value=False):
        payload = await api.api_telemetry(client_id="x-preflight-test")
    assert payload["x_session_preflight_reason"] == "no_session_pool"
    assert payload["x_scraper"] is False
