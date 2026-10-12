"""FAZ D · D6 — kurum hedefi yetenekleri: kapılar, kanıt, dürüst yokluk.

Kilitlenen iddialar:
    * Kapı kapalı / kasa kilitli → yetenek KOŞMAZ (istisna yok).
    * theHarvester bulguları TEK TEK kanıt olur; kova tavanı aşılırsa
      `truncated` işaretlenir (sessiz kırpma yok).
    * Tarama boş bittiyse yokluk iddiası (`absence`); ARAÇ hatası varsa
      yokluk iddia EDİLMEZ.
    * Ağ hatası (status=0) ne varlık ne yokluk üretir — yalnız notta görünür.
    * Kişi satırları yalnız kaynak URL ile birlikte kanıt olur.
"""

from __future__ import annotations

import asyncio
import json
import os
import stat

import pytest

from agent_core.capabilities import CapabilityContext, PolicyState, bootstrap
from agent_core.capabilities.runner import CapabilityRunner
from agent_core.services import company_recon

HARVESTER = "sensor.company.harvester"
SEO = "sensor.company.seo"
PEOPLE = "sensor.company.people"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (
        "PINEAL_HARVESTER_CMD",
        "PINEAL_HARVESTER_SOURCES",
        "PINEAL_COMPANY_ALLOW_PRIVATE",
        "ENABLE_COMPANY_TARGETING",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PINEAL_COMPANY_ALLOW_PRIVATE", "1")
    # Yetenek uygunluğu env'den okunur (ev deseni); politika kapısı ise
    # PolicyState'ten. Testlerde ikisi de açık başlar.
    monkeypatch.setenv("ENABLE_COMPANY_TARGETING", "1")
    yield


def _run(cap_id, ctx, state):
    return asyncio.run(CapabilityRunner(registry=bootstrap()).run(cap_id, ctx, state=state))


def _open_state(**flags):
    return PolicyState(vault_locked=False, rate_ok=True, enabled_flags=dict(flags))


class TestGates:
    def test_registered_on_the_spine(self):
        registry = bootstrap()
        for cap_id in (HARVESTER, SEO, PEOPLE):
            assert registry.get(cap_id) is not None
        assert sorted(registry.get(HARVESTER).gates) == ["ENABLE_COMPANY_TARGETING", "rate", "vault"]

    def test_vault_blocks(self):
        result = _run(
            SEO,
            CapabilityContext(subject="ornek.com"),
            PolicyState(vault_locked=True, rate_ok=True, enabled_flags={"ENABLE_COMPANY_TARGETING": True}),
        )
        assert result.denied_by == "vault"
        assert result.items == ()

    def test_gate_closed_blocks(self):
        result = _run(SEO, CapabilityContext(subject="ornek.com"), _open_state(ENABLE_COMPANY_TARGETING=False))
        assert result.denied_by == "ENABLE_COMPANY_TARGETING"
        assert result.items == ()

    def test_availability_is_honest(self, monkeypatch):
        monkeypatch.delenv("ENABLE_COMPANY_TARGETING", raising=False)
        registry = bootstrap()
        assert registry.get(SEO).availability().reason == "gate_disabled:ENABLE_COMPANY_TARGETING"
        assert registry.get(PEOPLE).availability().reason == "gate_disabled:ENABLE_COMPANY_TARGETING"


class TestHarvesterEvidence:
    def _fake_cli(self, tmp_path, payload):
        script = tmp_path / "harvester"
        quoted = json.dumps(payload)
        script.write_text("#!/bin/sh\nprintf '%s' '%s' > \"$8.json\"\n" % ("%s", quoted))
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return script

    @pytest.mark.skipif(os.name != "posix", reason="sahte CLI POSIX betiği (WinError 193)")
    def test_each_finding_becomes_evidence(self, monkeypatch, tmp_path):
        payload = {
            "emails": ["info@ornek.com"],
            "hosts": ["vpn.ornek.com"],
            "linkedin_people": ["Ayşe Yılmaz - CEO"],
        }
        monkeypatch.setenv("PINEAL_HARVESTER_CMD", str(self._fake_cli(tmp_path, payload)))
        result = _run(
            HARVESTER,
            CapabilityContext(subject="https://www.ornek.com/hakkinda", params={"limit": 50}),
            _open_state(ENABLE_COMPANY_TARGETING=True),
        )
        assert result.available is True and result.ok is True
        contents = " | ".join(item.content for item in result.items)
        assert "info@ornek.com" in contents
        assert "Ayşe Yılmaz - CEO" in contents
        assert all(item.epistemic_type == "observation" for item in result.items)
        assert result.notes["domain"] == "ornek.com"
        assert result.notes["counts"]["emails"] == 1

    @pytest.mark.skipif(os.name != "posix", reason="sahte CLI POSIX betiği (WinError 193)")
    def test_empty_scan_is_absence(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PINEAL_HARVESTER_CMD", str(self._fake_cli(tmp_path, {})))
        result = _run(
            HARVESTER,
            CapabilityContext(subject="ornek.com"),
            _open_state(ENABLE_COMPANY_TARGETING=True),
        )
        assert result.available is True
        assert len(result.items) == 1
        assert result.items[0].epistemic_type == "absence"
        assert "bulunamadı" in result.items[0].content

    @pytest.mark.skipif(os.name != "posix", reason="sahte CLI POSIX betiği (WinError 193)")
    def test_bucket_cap_is_flagged(self, monkeypatch, tmp_path):
        payload = {"emails": [f"k{i}@ornek.com" for i in range(40)]}
        monkeypatch.setenv("PINEAL_HARVESTER_CMD", str(self._fake_cli(tmp_path, payload)))
        result = _run(
            HARVESTER,
            CapabilityContext(subject="ornek.com"),
            _open_state(ENABLE_COMPANY_TARGETING=True),
        )
        assert result.available is True
        assert len(result.items) == 25
        assert result.notes["truncated"] == {"emails": True}

    def test_tool_failure_is_not_absence(self, monkeypatch):
        monkeypatch.setenv("PINEAL_HARVESTER_CMD", "pineal-olmayan-harvester")
        result = _run(
            HARVESTER,
            CapabilityContext(subject="ornek.com"),
            _open_state(ENABLE_COMPANY_TARGETING=True),
        )
        assert result.available is False
        assert result.unavailable_reason == "configured_command_not_found:PINEAL_HARVESTER_CMD"
        assert result.items == ()


class TestSeoEvidence:
    def _snapshot(self):
        return company_recon.SeoSnapshot(
            available=True,
            domain="ornek.com",
            base_url="https://ornek.com",
            scheme="https",
            checks=(
                company_recon.SeoCheck(
                    "homepage",
                    "https://ornek.com/",
                    200,
                    True,
                    {"title": "Örnek AŞ", "description": "Kurumsal", "lang": "tr", "canonical": "https://ornek.com/"},
                ),
                company_recon.SeoCheck("robots", "https://ornek.com/robots.txt", 404, False, {}),
                company_recon.SeoCheck("sitemap", "https://ornek.com/sitemap.xml", 0, False, {}, "ConnectError"),
            ),
        )

    def test_present_absent_and_error_are_distinct(self, monkeypatch):
        monkeypatch.setattr(company_recon, "seo_snapshot", _fake_async(self._snapshot()))
        result = _run(
            SEO,
            CapabilityContext(subject="ornek.com"),
            _open_state(ENABLE_COMPANY_TARGETING=True),
        )
        assert result.available is True
        types = {item.scope["check"]: item.epistemic_type for item in result.items}
        assert types == {"homepage": "observation", "robots": "absence"}  # sitemap: ağ hatası → KANIT YOK
        assert result.notes["errors"] == ["sitemap:ConnectError"]

    def test_unreachable_is_honest(self, monkeypatch):
        monkeypatch.setattr(
            company_recon,
            "seo_snapshot",
            _fake_async(company_recon.SeoSnapshot(available=False, reason="unreachable")),
        )
        result = _run(
            SEO,
            CapabilityContext(subject="ornek.com"),
            _open_state(ENABLE_COMPANY_TARGETING=True),
        )
        assert result.available is False
        assert result.unavailable_reason == "unreachable"
        assert result.items == ()


class TestPeopleEvidence:
    def test_people_rows_carry_source_url(self, monkeypatch):
        scan = company_recon.PeopleScan(
            available=True,
            domain="ornek.com",
            pages_checked=("https://ornek.com/team",),
            people=(company_recon.PersonRow("Ayşe Yılmaz", "Genel Müdür", "https://ornek.com/team"),),
            contacts=("info@ornek.com",),
        )
        monkeypatch.setattr(company_recon, "people_scan", _fake_async(scan))
        result = _run(
            PEOPLE,
            CapabilityContext(subject="ornek.com"),
            _open_state(ENABLE_COMPANY_TARGETING=True),
        )
        assert result.available is True
        assert all(item.provenance_refs for item in result.items)
        person = next(i for i in result.items if i.scope.get("kind") == "person")
        assert person.provenance_refs == ["https://ornek.com/team"]
        assert "AYŞE" not in person.content and "Ayşe Yılmaz" in person.content

    def test_no_signals_no_errors_is_absence(self, monkeypatch):
        scan = company_recon.PeopleScan(
            available=True, domain="ornek.com", pages_checked=("https://ornek.com/",)
        )
        monkeypatch.setattr(company_recon, "people_scan", _fake_async(scan))
        result = _run(
            PEOPLE,
            CapabilityContext(subject="ornek.com"),
            _open_state(ENABLE_COMPANY_TARGETING=True),
        )
        assert result.available is True
        assert len(result.items) == 1
        assert result.items[0].epistemic_type == "absence"

    def test_errors_suppress_absence_claim(self, monkeypatch):
        scan = company_recon.PeopleScan(
            available=True,
            domain="ornek.com",
            pages_checked=("https://ornek.com/",),
            errors=("status:500:https://ornek.com/team",),
        )
        monkeypatch.setattr(company_recon, "people_scan", _fake_async(scan))
        result = _run(
            PEOPLE,
            CapabilityContext(subject="ornek.com"),
            _open_state(ENABLE_COMPANY_TARGETING=True),
        )
        assert result.available is True
        assert result.items == ()  # hata varken yokluk İDDİA EDİLMEZ


def _fake_async(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner
