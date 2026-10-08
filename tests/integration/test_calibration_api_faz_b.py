"""FAZ B · B5 — EŞİK KALİBRASYONU uçtan uca (API + ledger + karar).

Kilitlenen iddia: eşik ÖLÇÜLMEDEN değişmez ve ölçüldüğünde DEĞİŞİR; karar
mercii operatördür (etiketleme onun elinde) ve ham metin hiçbir yere yazılmaz.
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from backend import api


@pytest.fixture(autouse=True)
def _observe_on(monkeypatch):
    """Kalibrasyon gözlemi bu dosyada AÇIK (tests/conftest.py kapalı bırakır)."""
    monkeypatch.setenv("PINEAL_CALIB_OBSERVE", "true")


@pytest.fixture()
def client():
    with TestClient(api.app) as test_client:
        yield test_client


def _push(client, score: float, truth: bool) -> str:
    """Ledger'a ölçüm yaz + operatör etiketi koy."""
    created = client.post("/api/calibration/observations", json={"score": score})
    assert created.status_code == 200, created.text
    obs_id = created.json()["observation"]["observation_id"]
    adjudicated = client.post(
        "/api/calibration/adjudicate", json={"observation_id": obs_id, "truth": truth}
    )
    assert adjudicated.status_code == 200, adjudicated.text
    return obs_id


def test_calibration_endpoint_reports_unmeasured_threshold(client, monkeypatch):
    """Veri yokken eşik 0.70'te kalır ve bunu AÇIKÇA söyler."""
    monkeypatch.setenv("PINEAL_CALIB_MIN_SAMPLES", "30")
    payload = client.get("/api/calibration").json()
    quote = payload["scopes"]["quote"]
    assert quote["threshold"] == 0.70
    assert quote["source"] == "varsayılan"
    assert "ÖLÇÜLMEDİ" in quote["report"]["machine_note"]
    assert payload["ledger"]["labeled"] == 0


def test_threshold_moves_only_after_operator_labels(client, monkeypatch):
    """Etiket yok -> değişim yok. Etiket var -> ÖLÇÜLEN eşik + güven aralığı."""
    monkeypatch.setenv("PINEAL_CALIB_MIN_SAMPLES", "10")
    for score in (0.95, 0.92, 0.90, 0.88, 0.85, 0.80, 0.78, 0.72, 0.68):
        client.post("/api/calibration/observations", json={"score": score})

    # Etiketsiz ölçüm eşiği değiştirmez.
    assert client.get("/api/calibration").json()["scopes"]["quote"]["source"] == "varsayılan"

    rows = client.get("/api/calibration").json()["ledger"]
    assert rows["rows"] == 9 and rows["labeled"] == 0

    _push(client, 0.62, False)
    for score, truth in ((0.55, False), (0.50, False), (0.45, False), (0.40, False), (0.35, False), (0.30, False)):
        _push(client, score, truth)
    for obs in _reload_observations(client):
        if obs["truth"] is None:
            client.post(
                "/api/calibration/adjudicate",
                json={"observation_id": obs["observation_id"], "truth": True},
            )

    quote = client.get("/api/calibration").json()["scopes"]["quote"]
    assert quote["source"] == "kalibre"
    assert quote["threshold"] != 0.70
    assert 0.5 <= quote["threshold"] <= 0.95
    assert len(quote["report"]["confidence_interval"]) == 2
    assert quote["report"]["grid"], "geri test ızgarası boş"


def _reload_observations(client):
    """Ledger dosyasını doğrudan okur (uç yok: yalnız test yardımcısı)."""
    from agent_core.services import threshold_calibration as calib

    return [json.loads(line) for line in open(os.path.join(calib.storage_dir(), "observations.jsonl"), encoding="utf-8") if line.strip()]


def test_ledger_never_stores_raw_text(client, monkeypatch):
    """Ölçüm yazılır, METİN yazılmaz: alıntının kendisi hiçbir yere gitmez."""
    monkeypatch.setenv("PINEAL_CALIB_MIN_SAMPLES", "10")
    _push(client, 0.77, True)
    path = os.path.join(
        __import__("agent_core.services.threshold_calibration", fromlist=["x"]).storage_dir(),
        "observations.jsonl",
    )
    blob = open(path, "r", encoding="utf-8").read()
    payload = json.loads(blob.strip().splitlines()[0])
    assert set(payload) == {
        "observation_id",
        "recorded_at",
        "scope",
        "task_id",
        "claim_id",
        "score",
        "matched",
        "truth",
        "note",
    }
    assert "gizli" not in blob


def test_adjudication_of_unknown_id_is_rejected(client):
    response = client.post("/api/calibration/adjudicate", json={"observation_id": "yok", "truth": True})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "OBSERVATION_NOT_FOUND"


def test_manual_threshold_override_is_visible(client, monkeypatch):
    monkeypatch.setenv("PINEAL_THRESHOLD_QUOTE", "0.93")
    quote = client.get("/api/calibration").json()["scopes"]["quote"]
    assert quote["threshold"] == pytest.approx(0.93)
    assert quote["source"] == "elle_sabitleme"
