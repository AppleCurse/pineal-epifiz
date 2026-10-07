"""FAZ D · D3 — medya uçları: kapılar, dürüst araç durumu, ölçüm kanıtı.

Kilitlenen iddialar:
    * `/api/media/status` araçları GERÇEK durumdan okur (yt-dlp/ffmpeg/opencv).
    * `/api/media/analyze` omurgadan geçer: kasa kilitli ya da kapı kapalıysa
      hiçbir mod KOŞMAZ; reddin sebebi yanıtta görünür.
    * Ölçüm kanıtı dosya yoluna bağlanır; uydurma yorum satırı üretilmez.
    * Bilinmeyen mod 400.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from agent_core.capabilities import CapabilityContext, PolicyState, bootstrap
from agent_core.capabilities.runner import CapabilityRunner
from agent_core.services import media_forensics as mf
from backend import api

FETCH = "sensor.media.fetch"
FRAMES = "analyzer.media.frames"
TRANSCRIPT = "extractor.media.transcript"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for name in (
        "PINEAL_MEDIA_DIR",
        "PINEAL_MEDIA_ALLOW_PRIVATE",
        "PINEAL_TRANSCRIBE_URL",
        "PINEAL_TRANSCRIBE_CMD",
        "ENABLE_MEDIA_FORENSICS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PINEAL_MEDIA_DIR", str(tmp_path / "media"))
    yield


@pytest.fixture()
def client():
    with TestClient(api.app) as test_client:
        yield test_client


@pytest.fixture()
def photo(tmp_path):
    path = tmp_path / "foto.png"
    Image.new("RGB", (120, 90), (30, 120, 200)).save(path)
    return path


def _run(cap_id, ctx, state):
    return asyncio.run(CapabilityRunner(registry=bootstrap()).run(cap_id, ctx, state=state))


def _open_state(**flags):
    return PolicyState(vault_locked=False, rate_ok=True, enabled_flags=dict(flags))


class TestGates:
    def test_registered(self):
        registry = bootstrap()
        assert sorted(registry.get(FRAMES).gates) == ["ENABLE_MEDIA_FORENSICS", "vault"]
        assert registry.get(TRANSCRIPT).kind.value == "extractor"

    def test_vault_blocks_frames(self, photo):
        result = _run(
            FRAMES,
            CapabilityContext(subject=str(photo)),
            PolicyState(vault_locked=True, rate_ok=True, enabled_flags={"ENABLE_MEDIA_FORENSICS": True}),
        )
        assert result.denied_by == "vault"

    def test_closed_gate_blocks(self, photo):
        result = _run(FRAMES, CapabilityContext(subject=str(photo)), _open_state(ENABLE_MEDIA_FORENSICS=False))
        assert result.denied_by == "ENABLE_MEDIA_FORENSICS"


class TestCapabilityEvidence:
    def test_frame_measurement_is_linked(self, photo, monkeypatch):
        monkeypatch.setenv("ENABLE_MEDIA_FORENSICS", "1")
        result = _run(
            FRAMES, CapabilityContext(subject=str(photo)), _open_state(ENABLE_MEDIA_FORENSICS=True)
        )
        assert result.available is True and result.ok is True
        item = result.items[0]
        assert item.provenance_refs == [str(photo)]
        assert "120x90" in item.content
        assert item.scope["claim"] == "measured_frames"

    def test_transcript_without_engine_is_honest(self, photo, monkeypatch):
        monkeypatch.setenv("ENABLE_MEDIA_FORENSICS", "1")
        monkeypatch.setattr(mf.shutil, "which", lambda name: None)
        result = _run(
            TRANSCRIPT,
            CapabilityContext(subject=str(photo)),
            _open_state(ENABLE_MEDIA_FORENSICS=True),
        )
        assert result.available is False
        assert result.unavailable_reason == "no_engine"
        assert result.items == ()

    def test_fetch_missing_source_is_honest(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MEDIA_FORENSICS", "1")
        result = _run(
            FETCH,
            CapabilityContext(subject=""),
            _open_state(ENABLE_MEDIA_FORENSICS=True),
        )
        assert result.available is False
        assert result.unavailable_reason == "invalid_source"


class TestEndpoints:
    def test_status_reports_tools(self, client):
        payload = client.get("/api/media/status").json()
        assert payload["gate"] == "ENABLE_MEDIA_FORENSICS"
        assert set(payload["tools"]) >= {"yt-dlp", "ffmpeg", "opencv"}
        modes = {row["mode"]: row for row in payload["modes"]}
        assert modes["frames"]["reason"] == "gate_disabled:ENABLE_MEDIA_FORENSICS"
        assert payload["any_available"] is False

    def test_vault_locked_blocks_analyze(self, client, photo):
        api.get_room("medya")["vault"].pop("or_key", None)
        payload = client.post(
            "/api/media/analyze",
            json={"source": str(photo), "client_id": "medya", "modes": ["frames"]},
        ).json()
        assert payload["modes"]["frames"]["denied_by"] == "vault"
        assert payload["evidence_total"] == 0

    def test_closed_gate_blocks_analyze(self, client, photo):
        client.get("/api/telemetry?client_id=medya")
        api.get_room("medya")["vault"]["or_key"] = True
        payload = client.post(
            "/api/media/analyze",
            json={"source": str(photo), "client_id": "medya", "modes": ["frames"]},
        ).json()
        assert payload["modes"]["frames"]["denied_by"] == "ENABLE_MEDIA_FORENSICS"
        api.get_room("medya")["vault"].pop("or_key", None)

    def test_analyze_measures_photo(self, client, photo, monkeypatch):
        monkeypatch.setenv("ENABLE_MEDIA_FORENSICS", "1")
        client.get("/api/telemetry?client_id=medya")
        api.get_room("medya")["vault"]["or_key"] = True
        payload = client.post(
            "/api/media/analyze",
            json={
                "source": str(photo),
                "client_id": "medya",
                "modes": ["fetch", "frames"],
            },
        ).json()
        frames = payload["modes"]["frames"]
        assert frames["available"] is True and frames["denied_by"] is None
        assert frames["notes"]["width"] == 120 and frames["notes"]["height"] == 90
        assert frames["evidence"][0]["provenance_refs"] == [str(photo)]
        fetch = payload["modes"]["fetch"]
        assert fetch["available"] is True
        assert len(fetch["notes"]["sha256"]) == 64
        api.get_room("medya")["vault"].pop("or_key", None)

    def test_unknown_mode_is_rejected(self, client, monkeypatch):
        monkeypatch.setenv("ENABLE_MEDIA_FORENSICS", "1")
        response = client.post(
            "/api/media/analyze",
            json={"source": "x.png", "client_id": "medya", "modes": ["deepfake"]},
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "UNKNOWN_MODE"

    def test_rate_bucket_exists_for_media(self):
        assert "media" in api.RATE_LIMITS
