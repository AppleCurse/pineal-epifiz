"""FAZ D · D6 — kurum hedefi uçları: kapılar, dürüst ret, kanıt zinciri.

Kilitlenen iddialar:
    * `/api/company/status` gerçeği defterden okur: kapı kapalıysa "hazır"
      denmez; theHarvester yoksa sebep `dependency_missing`.
    * `/api/company/scan` omurgadan geçer: kasa kilitli ya da kapı kapalıysa
      tarama KOŞMAZ; mod reddi `denied_by` ile görünür.
    * Geçersiz alan adı 400 (`INVALID_DOMAIN`), bilinmeyen mod 400.
    * Mod başarılıysa kanıt satırları kaynak URL'siyle döner.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_core.services import company_recon
from backend import api


@pytest.fixture()
def client():
    with TestClient(api.app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (
        "PINEAL_HARVESTER_CMD",
        "PINEAL_HARVESTER_SOURCES",
        "PINEAL_COMPANY_ALLOW_PRIVATE",
        "ENABLE_COMPANY_TARGETING",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture()
def vault(client):
    client.get("/api/telemetry?client_id=kurum")
    room = api.get_room("kurum")
    room["vault"]["or_key"] = True
    yield room["vault"]
    room["vault"].pop("or_key", None)


def _fake_async(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner


class TestStatusEndpoint:
    def test_gate_closed_is_honest(self, client):
        payload = client.get("/api/company/status").json()
        assert payload["gate"] == "ENABLE_COMPANY_TARGETING"
        assert payload["any_available"] is False
        reasons = {row["mode"]: row["reason"] for row in payload["modes"]}
        assert reasons["seo"] == "gate_disabled:ENABLE_COMPANY_TARGETING"
        assert reasons["harvester"] == "gate_disabled:ENABLE_COMPANY_TARGETING"

    def test_harvester_missing_binary_is_reported(self, client, monkeypatch):
        monkeypatch.setenv("ENABLE_COMPANY_TARGETING", "1")
        monkeypatch.setenv("PINEAL_HARVESTER_CMD", "pineal-olmayan-harvester")
        payload = client.get("/api/company/status").json()
        rows = {row["mode"]: row for row in payload["modes"]}
        assert rows["harvester"]["available"] is False
        assert rows["harvester"]["reason"] == "configured_command_not_found:PINEAL_HARVESTER_CMD"
        assert rows["seo"]["available"] is True
        assert payload["any_available"] is True


class TestScanGates:
    def test_vault_locked_blocks_every_mode(self, client, monkeypatch):
        monkeypatch.setenv("ENABLE_COMPANY_TARGETING", "1")
        api.get_room("kurum")["vault"].pop("or_key", None)
        payload = client.post(
            "/api/company/scan", json={"domain": "ornek.com", "client_id": "kurum"}
        ).json()
        assert payload["domain"] == "ornek.com"
        for mode_result in payload["modes"].values():
            assert mode_result["denied_by"] == "vault"
            assert mode_result["evidence"] == []
        assert payload["evidence_total"] == 0

    def test_closed_gate_blocks_every_mode(self, client, vault):
        payload = client.post(
            "/api/company/scan", json={"domain": "ornek.com", "client_id": "kurum"}
        ).json()
        for mode_result in payload["modes"].values():
            assert mode_result["denied_by"] == "ENABLE_COMPANY_TARGETING"
            assert mode_result["evidence"] == []

    def test_invalid_domain_is_rejected(self, client, vault, monkeypatch):
        monkeypatch.setenv("ENABLE_COMPANY_TARGETING", "1")
        response = client.post(
            "/api/company/scan", json={"domain": "iki kelime", "client_id": "kurum"}
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_DOMAIN"

    def test_unknown_mode_is_rejected(self, client, vault, monkeypatch):
        monkeypatch.setenv("ENABLE_COMPANY_TARGETING", "1")
        response = client.post(
            "/api/company/scan",
            json={"domain": "ornek.com", "client_id": "kurum", "modes": ["harvester", "magic"]},
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "UNKNOWN_MODE"


class TestScanEvidence:
    def test_evidence_rows_carry_provenance(self, client, vault, monkeypatch):
        monkeypatch.setenv("ENABLE_COMPANY_TARGETING", "1")
        monkeypatch.setattr(
            company_recon,
            "seo_snapshot",
            _fake_async(
                company_recon.SeoSnapshot(
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
                            {"title": "Örnek AŞ", "description": "Kurumsal", "lang": "tr"},
                        ),
                        company_recon.SeoCheck("robots", "https://ornek.com/robots.txt", 404, False, {}),
                    ),
                )
            ),
        )
        payload = client.post(
            "/api/company/scan",
            json={"domain": "https://www.ornek.com/yol", "client_id": "kurum", "modes": ["seo"]},
        ).json()
        assert payload["domain"] == "ornek.com"
        seo = payload["modes"]["seo"]
        assert seo["available"] is True and seo["denied_by"] is None
        assert seo["counts"]["evidence"] == 2
        types = {row["epistemic_type"] for row in seo["evidence"]}
        assert types == {"observation", "absence"}
        assert all(row["provenance_refs"] for row in seo["evidence"])

    def test_harvester_unavailable_is_reported_not_hidden(self, client, vault, monkeypatch):
        monkeypatch.setenv("ENABLE_COMPANY_TARGETING", "1")
        monkeypatch.setenv("PINEAL_HARVESTER_CMD", "pineal-olmayan-harvester")
        payload = client.post(
            "/api/company/scan",
            json={"domain": "ornek.com", "client_id": "kurum", "modes": ["harvester"]},
        ).json()
        harvester = payload["modes"]["harvester"]
        assert harvester["available"] is False
        assert harvester["reason"] == "configured_command_not_found:PINEAL_HARVESTER_CMD"
        assert harvester["evidence"] == []

    def test_rate_bucket_exists_for_company(self):
        assert "company" in api.RATE_LIMITS
