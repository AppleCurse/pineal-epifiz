"""Ölü kapılar: operatör onayı → Instagram/X sensörleri gerçekten koşar mı?

[2026-10-23 ölçümü] Varsayılan `.env` ile (`ENABLE_X_SENSOR` /
`ENABLE_IG_SECONDARY` yazılmamış) ve operatör çapraz arama onayı VERMİŞKEN
derin tarama şunu üretiyordu:

    sensor.ig.instagrapi  not_run  policy:gate_disabled
    sensor.x.twscrape     not_run  policy:gate_disabled

Yani "onay" yalnız `sensor.identity.handle_probe` için işliyordu; bulunan
Instagram/X profilleri hiç kazınmıyordu. Buradaki testler kabloyu gerçek
veri akışıyla kilitler:

    payload.policy.cross_platform_authorized
        → with_operator_consent(state)
            → PolicyKernel
                → channel_run.status (gate_disabled DEĞİL)
"""

from __future__ import annotations

import pytest

from agent_core.capabilities.state import (
    CONSENT_GATED_FLAGS,
    policy_state,
    with_operator_consent,
)

_URLS = ["https://www.instagram.com/hedef/", "https://x.com/hedef"]


def _by_channel(resolution):
    out = {}
    for run in resolution.channel_runs:
        data = run.to_dict() if hasattr(run, "to_dict") else dict(run)
        out[data["channel"]] = data
    return out


def test_consent_is_noop_when_not_authorized():
    state = policy_state(vault_locked=False, rate_ok=True, env={})
    same = with_operator_consent(state, False, env={})
    assert same is state


def test_consent_opens_the_two_dead_sensors():
    state = policy_state(vault_locked=False, rate_ok=True, env={})
    opened = with_operator_consent(state, True, env={})
    for flag in CONSENT_GATED_FLAGS:
        assert opened.enabled_flags[flag] is True, flag
    # Diğer ENABLE_* kapıları onaydan ETKİLENMEZ.
    assert opened.enabled_flags["ENABLE_MAIGRET"] is False


def test_explicit_env_false_is_never_overridden_by_consent():
    env = {"ENABLE_X_SENSOR": "false"}
    state = policy_state(vault_locked=False, rate_ok=True, env=env)
    opened = with_operator_consent(state, True, env=env)
    assert opened.enabled_flags["ENABLE_X_SENSOR"] is False
    assert opened.enabled_flags["ENABLE_IG_SECONDARY"] is True


@pytest.mark.asyncio
async def test_deep_scan_runs_sensors_when_operator_authorized():
    """Onay → `gate_disabled` DEĞİL; gerçek bağımlılık/kimlik sebebi."""
    from agent_core.services.deep_profile_resolver import resolve_deep_profiles_detailed

    resolution = await resolve_deep_profiles_detailed(
        _URLS,
        payload={
            "policy": {
                "vault_locked": False,
                "rate_ok": True,
                "cross_platform_authorized": True,
            }
        },
    )
    channels = _by_channel(resolution)
    for capability in ("sensor.ig.instagrapi", "sensor.x.twscrape"):
        assert capability in channels, channels
        assert channels[capability]["reason"] != "policy:gate_disabled", channels[capability]


@pytest.mark.asyncio
async def test_deep_scan_stays_closed_without_consent():
    """Onay yok → kapı kapalı kalır (fail-closed korunur)."""
    from agent_core.services.deep_profile_resolver import resolve_deep_profiles_detailed

    resolution = await resolve_deep_profiles_detailed(
        _URLS,
        payload={"policy": {"vault_locked": False, "rate_ok": True}},
    )
    channels = _by_channel(resolution)
    for capability in ("sensor.ig.instagrapi", "sensor.x.twscrape"):
        assert channels[capability]["reason"] == "policy:gate_disabled", channels[capability]
