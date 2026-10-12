"""FAZ D · D5 — rapor yetenekleri + uçlar: kapılar, mühür, dürüst eksik format.

Kilitlenen iddialar:
    * Kapı kapalı / kasa kilitli → rapor ÜRETİLMEZ (dosya yazılmaz).
    * Üretilen eser kanıt kimliklerine bağlanır + sha256 taşır; manifest ayrı
      bir kanıt satırı olur (mühür).
    * ffmpeg yoksa video yeteneği dürüstçe kapalıdır; yerine uydurma dosya yok.
    * Uçlar: bilinmeyen format 400; kasa/kapı reddi yanıtta görünür.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_core.capabilities import CapabilityContext, PolicyState, bootstrap
from agent_core.capabilities.runner import CapabilityRunner
from agent_core.services import report_factory as rf
from backend import api

PDF = "renderer.report.pdf"
DIAGRAM = "renderer.report.diagram"
VIDEO = "renderer.report.video"

EVIDENCE = [
    {
        "evidence_id": "ev_" + "a" * 20,
        "epistemic_type": "observation",
        "source_engine": "twscrape",
        "content": "Gönderi: 'Merhaba dünya'",
        "provenance_refs": ["https://x.com/u/1"],
    }
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    monkeypatch.delenv("ENABLE_REPORT_FACTORY", raising=False)
    monkeypatch.setenv("PINEAL_REPORT_DIR", str(tmp_path / "raporlar"))
    yield


@pytest.fixture()
def client():
    with TestClient(api.app) as test_client:
        yield test_client


def _run(cap_id, ctx, state):
    return asyncio.run(CapabilityRunner(registry=bootstrap()).run(cap_id, ctx, state=state))


def _open_state(**flags):
    return PolicyState(vault_locked=False, rate_ok=True, enabled_flags=dict(flags))


def _ctx(title="Örnek Rapor", **params):
    base = {"title": title, "subject": "ornek.com", "evidence": EVIDENCE}
    base.update(params)
    return CapabilityContext(subject=title, params=base)


class TestGates:
    def test_registered_and_gated(self):
        registry = bootstrap()
        assert sorted(registry.get(PDF).gates) == ["ENABLE_REPORT_FACTORY", "vault"]
        assert registry.get(PDF).kind.value == "renderer"

    def test_vault_blocks(self):
        result = _run(PDF, _ctx(), PolicyState(vault_locked=True, rate_ok=True, enabled_flags={"ENABLE_REPORT_FACTORY": True}))
        assert result.denied_by == "vault"
        assert result.items == ()

    def test_gate_closed_blocks(self):
        result = _run(PDF, _ctx(), _open_state(ENABLE_REPORT_FACTORY=False))
        assert result.denied_by == "ENABLE_REPORT_FACTORY"

    def test_video_availability_is_honest(self, monkeypatch):
        monkeypatch.setenv("ENABLE_REPORT_FACTORY", "1")
        monkeypatch.setattr(rf.shutil, "which", lambda name: None)
        availability = bootstrap().get(VIDEO).availability()
        assert availability.available is False
        assert availability.reason == "dependency_missing:ffmpeg"


class TestCapabilityEvidence:
    def test_pdf_artifact_is_linked_and_sealed(self, monkeypatch):
        monkeypatch.setenv("ENABLE_REPORT_FACTORY", "1")
        result = _run(PDF, _ctx(), _open_state(ENABLE_REPORT_FACTORY=True))
        assert result.available is True and result.ok is True
        artifact = next(i for i in result.items if i.scope.get("claim") == "artifact_from_evidence")
        assert artifact.provenance_refs == [EVIDENCE[0]["evidence_id"]]
        pdf_row = next(r for r in result.notes["artifacts"] if r["name"] == "pdf")
        assert Path(pdf_row["path"]).exists()
        seal = next(i for i in result.items if i.scope.get("claim") == "integrity_seal")
        assert seal.scope["manifest_sha256"] == result.notes["manifest_sha256"]
        manifest = json.loads(Path(result.notes["manifest_path"]).read_text(encoding="utf-8"))
        assert manifest["evidence_ids"] == [EVIDENCE[0]["evidence_id"]]

    def test_diagram_artifact(self, monkeypatch):
        monkeypatch.setenv("ENABLE_REPORT_FACTORY", "1")
        result = _run(DIAGRAM, _ctx(), _open_state(ENABLE_REPORT_FACTORY=True))
        assert result.available is True
        row = next(r for r in result.notes["artifacts"] if r["name"] == "diagram")
        assert row["available"] is True
        assert Path(row["path"]).read_bytes().startswith(b"\x89PNG")

    def test_empty_title_is_honest(self, monkeypatch):
        monkeypatch.setenv("ENABLE_REPORT_FACTORY", "1")
        result = _run(PDF, _ctx(title=""), _open_state(ENABLE_REPORT_FACTORY=True))
        assert result.available is False
        assert result.unavailable_reason == "empty_title"


class TestEndpoints:
    def test_status_lists_formats_and_gate(self, client, monkeypatch):
        payload = client.get("/api/report/status").json()
        assert payload["gate"] == "ENABLE_REPORT_FACTORY"
        formats = {row["format"]: row for row in payload["formats"]}
        assert formats["markdown"]["available"] is True
        assert payload["seal"].startswith("sha256")

    def test_vault_locked_blocks_build(self, client):
        api.get_room("rapor")["vault"].pop("or_key", None)
        payload = client.post(
            "/api/report/build",
            json={"title": "Rapor", "client_id": "rapor", "evidence": EVIDENCE, "formats": ["pdf"]},
        ).json()
        assert payload["formats"]["pdf"]["denied_by"] == "vault"

    def test_closed_gate_blocks_build(self, client):
        client.get("/api/telemetry?client_id=rapor")
        api.get_room("rapor")["vault"]["or_key"] = True
        payload = client.post(
            "/api/report/build",
            json={"title": "Rapor", "client_id": "rapor", "evidence": EVIDENCE, "formats": ["pdf"]},
        ).json()
        assert payload["formats"]["pdf"]["denied_by"] == "ENABLE_REPORT_FACTORY"
        api.get_room("rapor")["vault"].pop("or_key", None)

    def test_build_produces_sealed_artifacts(self, client, monkeypatch):
        monkeypatch.setenv("ENABLE_REPORT_FACTORY", "1")
        client.get("/api/telemetry?client_id=rapor")
        api.get_room("rapor")["vault"]["or_key"] = True
        payload = client.post(
            "/api/report/build",
            json={
                "title": "Örnek Rapor",
                "subject": "ornek.com",
                "client_id": "rapor",
                "evidence": EVIDENCE + [{"bozuk": True}],
                "formats": ["pdf", "diagram"],
            },
        ).json()
        pdf = payload["formats"]["pdf"]
        assert pdf["available"] is True and pdf["denied_by"] is None
        assert pdf["rejected_item_count"] == 1
        assert Path(pdf["manifest_path"]).exists()
        assert pdf["evidence_ids"] == [EVIDENCE[0]["evidence_id"]]
        names = {row["name"] for row in pdf["artifacts"]}
        assert "markdown" in names and "pdf" in names
        api.get_room("rapor")["vault"].pop("or_key", None)

    def test_unknown_format_is_rejected(self, client, monkeypatch):
        monkeypatch.setenv("ENABLE_REPORT_FACTORY", "1")
        response = client.post(
            "/api/report/build",
            json={"title": "Rapor", "client_id": "rapor", "formats": ["exe"]},
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "UNKNOWN_FORMAT"

    def test_rate_bucket_exists_for_report(self):
        assert "report" in api.RATE_LIMITS
