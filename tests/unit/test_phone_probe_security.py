"""Phone lookup must use the vault and must not turn failures into absence."""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from agent_core.scraper.vault_gate import VaultLockedError
from agent_core.services import phone_probe
from backend.routes.commander import register_commander_routes


def test_locked_service_does_not_open_client(monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_ENV", "production")
    monkeypatch.setenv("PINEAL_VAULT_FILE", str(tmp_path / "missing"))
    with pytest.raises(VaultLockedError):
        asyncio.run(phone_probe.probe_phone("+12025550123", auto_bridge_social=False))


def test_search_error_is_not_reported_as_absence(monkeypatch):
    def fail(**kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr(phone_probe, "open_client", fail)
    result = asyncio.run(phone_probe.probe_phone("+12025550123", auto_bridge_social=False))
    assert result.metadata.is_valid
    assert result.web_search_status == "unavailable"
    assert "doğrulanamadı" in result.summary_report
    assert "tespit edilmedi" not in result.summary_report


def test_endpoint_rejects_locked_vault_before_service(monkeypatch):
    app = FastAPI()
    register_commander_routes(app, rate_limit=lambda *_: True, rate_identity=lambda *_: "x",
                              gateway_provider=lambda: None,
                              require_minor_clearance=lambda *args, **kwargs: None,
                              require_vault_open=lambda _: JSONResponse({"error": "locked"}, status_code=423))

    async def unexpected(*args, **kwargs):
        pytest.fail("service invoked despite locked vault")

    monkeypatch.setattr(phone_probe, "probe_phone", unexpected)
    response = TestClient(app).post("/api/commander/phone-probe", json={"phone": "+12025550123"})
    assert response.status_code == 423


def test_cross_platform_requires_its_flag(monkeypatch):
    async def found(_queries):
        return [{"url": "https://example.com", "snippet": "@candidate"}], "completed"

    monkeypatch.delenv("ENABLE_CROSS_PLATFORM", raising=False)
    monkeypatch.setattr(phone_probe, "_search_web_footprint", found)
    result = asyncio.run(phone_probe.probe_phone("+12025550123", auto_bridge_social=True))
    assert result.associated_handles == ["candidate"]
    assert result.social_probes == []
    assert result.social_bridge_status == "disabled:ENABLE_CROSS_PLATFORM"
    assert "Doğrulanmamış Aday" in result.summary_report


def test_endpoint_runs_registered_capability(monkeypatch):
    # Real request, registry, policy runner and phone parser; network response stubbed.
    async def unavailable(_queries):
        return [], "unavailable"

    monkeypatch.setattr(phone_probe, "_search_web_footprint", unavailable)
    app = FastAPI()
    register_commander_routes(app, rate_limit=lambda *_: True, rate_identity=lambda *_: "x",
                              gateway_provider=lambda: None,
                              require_minor_clearance=lambda *args, **kwargs: None,
                              require_vault_open=lambda _: None)
    response = TestClient(app).post("/api/commander/phone-probe", json={"phone": "+12025550123"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["metadata"]["is_valid"] is True
    assert result["web_search_status"] == "unavailable"
    assert result["social_bridge_status"] == "not_requested"


def test_candidate_evidence_is_inconclusive(monkeypatch):
    from agent_core.capabilities import CapabilityContext, bootstrap, run_capability
    from agent_core.capabilities.state import policy_state
    from agent_core.domain.pillar_models import EvidenceStatus

    async def found(_queries):
        return [{"url": "https://example.com", "snippet": "@candidate", "engine": "test"}], "completed"

    monkeypatch.setattr(phone_probe, "_search_web_footprint", found)
    bootstrap()
    result = asyncio.run(run_capability("sensor.identity.phone_probe",
                                       CapabilityContext(subject="+12025550123"),
                                       state=policy_state(vault_locked=False)))
    evidence = next(item for item in result.items if item.source_engine == "phone_probe_web")
    assert evidence.epistemic_type == "inference"
    assert evidence.source_status == EvidenceStatus.INCONCLUSIVE
    assert evidence.scope["url"] == "https://example.com"
    assert evidence.observed_at is not None
