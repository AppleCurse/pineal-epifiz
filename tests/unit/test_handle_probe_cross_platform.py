"""Çapraz platform kullanıcı-adı yoklaması — `sensor.identity.handle_probe`.

[Neden] 2026-10-23: "X'te bulunan hedef Instagram/Facebook/Threads'te de
aransın" beklentisi yalnız `ENABLE_MAIGRET` kapısına bağlıydı (varsayılan
KAPALI) → çapraz arama pratikte hiç koşmuyordu. Bu testler yeni native
yoklamanın hem ÇALIŞTIĞINI hem de UYDURMADIĞINI kilitler.

Ağ yok: sahte istemci enjekte edilir. Doğrulananlar:
  1. 200 → `claimed`; IG/FB/Threads/X dahil platformlar gerçekten yoklanır.
  2. 404/410 → `absent`; "yok" iddiası yalnız hata/belirsizlik YOKKEN.
  3. Login duvarı / 403 / 429 / 5xx / ağ hatası → "yok" DENMEZ.
  4. Kapı kapalıyken yetenek `gate_disabled` döner ve HİÇ istek atılmaz.
  5. Kapı açıkken yetenek kanıt üretir ve çapraz kimlik grafiğine girer.
  6. OSINT ajanı yoklama sonucunu `associated_platforms`'a ekler, güveni
     mevcut değerin altına indirmez.
"""

from __future__ import annotations

import asyncio

import pytest

from agent_core.services.handle_probe import (
    PROBE_PLATFORMS,
    STATUS_ABSENT,
    STATUS_ERROR,
    STATUS_UNKNOWN,
    probe_handle,
    probe_platforms,
)


@pytest.fixture(autouse=True)
def _fast_probe(monkeypatch):
    """Testlerde platformlar arası bekleme yok (gerçek üretimde 0.25 sn)."""
    monkeypatch.setenv("PINEAL_HANDLE_PROBE_PAUSE", "0")


class _Response:
    def __init__(self, status_code: int, location: str = ""):
        self.status_code = status_code
        self.headers = {"location": location}


class _FakeClient:
    """Platform bazlı durum kodu döndüren sahte egress istemcisi."""

    def __init__(self, mapping):
        self.mapping = mapping
        self.requests: list[str] = []

    async def get(self, url: str):
        self.requests.append(url)
        platform = next((p for p, t in PROBE_PLATFORMS if t.format(handle="hedef") == url), "?")
        value = self.mapping.get(platform, 404)
        if isinstance(value, Exception):
            raise value
        if isinstance(value, tuple):
            return _Response(*value)
        return _Response(value)


def _run(mapping, username="hedef", platforms=None):
    client = _FakeClient(mapping)
    result = asyncio.run(probe_handle(username, platforms=platforms, client=client))
    return result, client


# ------------------------------------------------------- 1) bulunan platformlar
def test_claimed_platforms_are_reported_with_real_urls():
    result, client = _run({
        "instagram": 200, "facebook": 200, "threads": 200, "x": 404,
    })
    claimed = {p.platform for p in result.claimed}
    assert {"instagram", "facebook", "threads"} <= claimed
    assert all(p.url.startswith("https://") for p in result.claimed)
    assert result.available is True
    assert result.scanned_count == len(PROBE_PLATFORMS)
    # Her platform GERÇEKTEN yoklandı (uydurma yok).
    assert len(client.requests) == len(PROBE_PLATFORMS)
    assert any("instagram.com/hedef" in u for u in client.requests)
    assert any("threads.net/@hedef" in u for u in client.requests)


def test_default_platform_set_covers_the_networks_the_user_asked_for():
    names = {p for p, _ in PROBE_PLATFORMS}
    assert {"instagram", "facebook", "threads", "x", "tiktok"} <= names


# ------------------------------------------------------------- 2) kanıtlı yokluk
def test_absent_is_claimed_only_when_nothing_is_unknown_or_failed():
    result, _ = _run({})  # her platform 404
    assert {p.status for p in result.probes} == {STATUS_ABSENT}
    assert result.error_count == 0 and result.unknown_count == 0
    assert result.absence_claimable is True


def test_unknown_blocks_the_absence_claim():
    result, _ = _run({"instagram": 200, "facebook": 403, "threads": (302, "https://www.instagram.com/accounts/login/")})
    assert result.absence_claimable is False, "403/login duvarı varken 'yok' iddiası kurulamaz"
    fb = next(p for p in result.probes if p.platform == "facebook")
    assert fb.status == STATUS_UNKNOWN and fb.reason == "blocked"
    th = next(p for p in result.probes if p.platform == "threads")
    assert th.status == STATUS_UNKNOWN and th.reason == "login_wall"


@pytest.mark.parametrize("value,expected_status,expected_reason", [
    (429, STATUS_UNKNOWN, "rate_limited"),
    (500, STATUS_ERROR, "http_500"),
    (TimeoutError("boom"), STATUS_ERROR, "transport:TimeoutError"),
    ((307, "https://x.com/hedef"), STATUS_UNKNOWN, "redirect"),
])
def test_ambiguous_results_never_become_absent(value, expected_status, expected_reason):
    result, _ = _run({"instagram": value}, platforms=[PROBE_PLATFORMS[0]])
    probe = result.probes[0]
    assert probe.status == expected_status
    assert probe.reason == expected_reason
    assert result.absence_claimable is False


def test_transport_error_is_counted_not_swallowed():
    result, _ = _run({"instagram": ConnectionError("reset")})
    assert result.error_count == 1
    assert result.probes[0].status == STATUS_ERROR


# ----------------------------------------------------------- 3) girdi doğrulama
def test_invalid_username_never_probes():
    result, client = _run({}, username="bu bir kullanıcı adı değil!!")
    assert result.available is False and result.reason == "invalid_username"
    assert client.requests == []


def test_platform_selection_can_be_narrowed_by_env(monkeypatch):
    monkeypatch.setenv("PINEAL_HANDLE_PROBE_PLATFORMS", "instagram,facebook,threads")
    chosen = [p for p, _ in probe_platforms()]
    assert chosen == ["instagram", "facebook", "threads"]


# ------------------------------------------------------------ 4) yetenek kapısı
def _state(**flags):
    from agent_core.capabilities.policy import PolicyState

    return PolicyState(vault_locked=False, enabled_flags=flags)


def test_capability_is_closed_until_cross_platform_gate_opens(monkeypatch):
    from agent_core.capabilities import CapabilityContext, bootstrap, run_capability

    monkeypatch.setenv("ENABLE_CROSS_PLATFORM", "false")
    bootstrap()
    result = asyncio.run(run_capability(
        "sensor.identity.handle_probe",
        CapabilityContext(subject="hedef"),
        state=_state(),  # bayrak YOK → politika kapıyı kapatır
    ))
    assert result.available is False
    # Sebep makine-okunur: hangi kapı kapattı (denied_by) + sınıf.
    assert result.denied_by == "ENABLE_CROSS_PLATFORM"
    assert "gate_disabled" in (result.unavailable_reason or "")


def test_capability_produces_sealed_evidence_when_open(monkeypatch):
    from agent_core.capabilities import CapabilityContext, bootstrap, run_capability
    import agent_core.services.handle_probe as hp

    monkeypatch.setenv("ENABLE_CROSS_PLATFORM", "true")
    bootstrap()
    fake = _FakeClient({"instagram": 200, "facebook": 404})
    original = hp.probe_handle

    async def _patched(username, **kwargs):
        return await original(username, client=fake)

    monkeypatch.setattr(hp, "probe_handle", _patched)
    result = asyncio.run(run_capability(
        "sensor.identity.handle_probe",
        CapabilityContext(subject="hedef"),
        state=_state(ENABLE_CROSS_PLATFORM=True),
    ))
    assert result.available is True
    assert result.items, "bulunan platform için kanıt üretilmedi"
    assert any("instagram" in item.content for item in result.items)
    assert result.notes["scanned_count"] == len(PROBE_PLATFORMS)


# ------------------------------------------- 5) kimlik grafiği + OSINT birleşimi
def test_cross_profiler_links_handle_probe_findings():
    from agent_core.services.cross_profiler import correlate_profiles

    result = correlate_profiles(
        {
            "platform": "x", "username": "hedef", "bio": "aynı kişi",
            "detected_urls": ["https://x.com/hedef"],
        },
        {"handle_probe": {"found_sites": [
            {"site": "instagram", "url": "https://www.instagram.com/hedef/", "status": "claimed"},
            {"site": "threads", "url": "https://www.threads.net/@hedef", "status": "claimed"},
            {"site": "facebook", "url": "https://www.facebook.com/hedef", "status": "claimed"},
        ]}},
    )
    platforms = {m.target_platform for m in result.matches} | {m.source_platform for m in result.matches}
    assert {"instagram", "threads", "facebook"} <= platforms, (
        f"çapraz platform eşleşmesi kurulmadı: {platforms}"
    )


def test_osint_agent_merges_probe_platforms_monotonically(monkeypatch):
    """Güven MEVCUT değerin altına inmez; bulunan platformlar eklenir."""
    from agent_core.agents.osint_investigator import OsintInvestigatorAgent, OsintProfile

    agent = object.__new__(OsintInvestigatorAgent)

    class _Result:
        available = True
        unavailable_reason = None

        class payload:  # noqa: N801 - basit sahte
            @staticmethod
            def to_username_scan():
                return {
                    "requested_username": "hedef",
                    "available": True,
                    "provider": "handle_probe",
                    "scanned_count": 10,
                    "found_sites": [
                        {"site": "instagram", "url": "https://www.instagram.com/hedef/", "status": "claimed"},
                        {"site": "threads", "url": "https://www.threads.net/@hedef", "status": "claimed"},
                    ],
                }

    class _Timeline:
        entries: list = []

        def model_dump(self, **_kw):
            return {"entries": []}

    async def _fake_spine(capability_id, subject, payload=None, params=None):
        assert capability_id == "sensor.identity.handle_probe"
        return _Result(), _Timeline()

    monkeypatch.setattr(agent, "_run_spine", _fake_spine)

    profile = OsintProfile(associated_platforms=["x"], confidence=0.9, data_confidence=True)
    merged = asyncio.run(agent._apply_cross_platform_probe(profile, "hedef", None))
    assert "instagram" in merged.associated_platforms
    assert "threads" in merged.associated_platforms
    assert "x" in merged.associated_platforms
    assert merged.confidence == 0.9, "mevcut güven düşürüldü"
    assert merged.handle_probe["provider"] == "handle_probe"


def test_osint_agent_records_reason_when_capability_closed(monkeypatch):
    from agent_core.agents.osint_investigator import OsintInvestigatorAgent, OsintProfile

    agent = object.__new__(OsintInvestigatorAgent)

    class _Result:
        available = False
        unavailable_reason = "gate_disabled:ENABLE_CROSS_PLATFORM"
        payload = None

    class _Timeline:
        entries: list = []

        def model_dump(self, **_kw):
            return {"entries": []}

    async def _fake_spine(*_a, **_kw):
        return _Result(), _Timeline()

    monkeypatch.setattr(agent, "_run_spine", _fake_spine)
    profile = OsintProfile(associated_platforms=["x"], confidence=0.4)
    out = asyncio.run(agent._apply_cross_platform_probe(profile, "hedef", None))
    assert out.associated_platforms == ["x"], "kapı kapalıyken alanlar değişmemeli"
    assert out.confidence == 0.4
    assert "gate_disabled" in out.handle_probe["reason"]


# ------------------------------------- 6) ONAY (consent) KABLOSU uçtan uca
def test_room_authorization_opens_the_gate_for_that_task_only():
    """Operatör onayı (`authorized_alternatives`) kapıyı AÇAR — başka yol yok."""
    from agent_core.agents.osint_investigator import OsintInvestigatorAgent

    without = OsintInvestigatorAgent._policy_state({"policy": {"vault_locked": False}})
    assert not dict(without.enabled_flags).get("ENABLE_CROSS_PLATFORM", False)

    with_consent = OsintInvestigatorAgent._policy_state({
        "policy": {"vault_locked": False, "cross_platform_authorized": True},
    })
    assert dict(with_consent.enabled_flags).get("ENABLE_CROSS_PLATFORM") is True


def test_mission_payload_carries_the_operator_consent(monkeypatch):
    """`run_mission` onayı payload'a yazar; ajan onu görür."""
    import inspect

    import backend.api as api

    source = inspect.getsource(api.run_mission)
    assert "cross_platform_authorized" in source, (
        "onay kaydı görev payload'ına taşınmıyor — kapı hiç açılmaz"
    )
    assert "authorized_alternatives" in source


def test_capability_runs_when_the_gate_is_opened_by_consent(monkeypatch):
    """Kapı onayla açıldığında yoklama GERÇEKTEN koşar (kanıt üretir)."""
    import agent_core.services.handle_probe as hp
    from agent_core.capabilities import CapabilityContext, bootstrap, run_capability

    bootstrap()
    fake = _FakeClient({"instagram": 200, "facebook": 200})
    original = hp.probe_handle

    async def _patched(username, **kwargs):
        return await original(username, client=fake)

    monkeypatch.setattr(hp, "probe_handle", _patched)
    from agent_core.capabilities.policy import PolicyState

    state = PolicyState(
        vault_locked=False,
        enabled_flags={"ENABLE_CROSS_PLATFORM": True},
        rate_ok=True,
    )
    result = asyncio.run(run_capability(
        "sensor.identity.handle_probe",
        CapabilityContext(subject="hedef"),
        state=state,
    ))
    assert result.available is True
    assert {item.scope.get("platform") for item in result.items if item.scope} >= {"instagram", "facebook"}
