"""FAZ B · B2/B3 — HAFIZA KRİSTALİ uçtan uca: API + görev yürütücü + kristal.

Kilitlenen iddia: hafıza ARTIK görev bitince sıfırlanmıyor — kristal hedef
başına yaşıyor, API'den okunabiliyor ve derin analist çalışmadan önce ajanın
önüne GEÇMİŞ bağlam olarak konuyor (kafesli, temizlenmiş).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from agent_core.domain.memory_models import TaskSnapshot
from agent_core.services import memory_crystal
from agent_core.task_executor import PinealExecutor
from backend import api


@pytest.fixture()
def client():
    with TestClient(api.app) as test_client:
        yield test_client


def _item(content: str, engine: str = "maigret") -> dict:
    return {
        "content": content,
        "source_engine": engine,
        "observed_at": "2026-10-01T10:00:00+00:00",
        "provenance_refs": ["https://github.com/hedef"],
        "scope": {"site": "github.com"},
    }


def test_memory_endpoint_reports_empty_until_a_task_crystallizes(client):
    """Kristal yoksa API boş döner — geçmiş UYDURULMAZ."""
    payload = client.get("/api/memory/hedef_yok").json()
    assert payload["available"] is False
    assert payload["fragment_count"] == 0


def test_crystal_is_readable_and_searchable_via_api(client):
    memory_crystal.crystallize("ada", "task_1", [_item("Ada Kıdemli Stratejist olarak çalışıyor")])
    memory_crystal.crystallize("ada", "task_2", [_item("Ada Başkan oldu", engine="trafilatura")])

    summary = client.get("/api/memory/ada").json()
    assert summary["available"] is True
    assert summary["fragment_count"] == 2
    assert summary["task_count"] == 2

    recalled = client.get("/api/memory/ada/recall", params={"query": "Kıdemli Stratejist", "k": 1}).json()
    assert recalled["available"] is True
    assert len(recalled["hits"]) == 1
    assert "Stratejist" in recalled["hits"][0]["text"]
    assert recalled["hits"][0]["reasons"], "skorun gerekçesi yok"


def test_recall_endpoint_can_exclude_the_running_task(client):
    memory_crystal.crystallize("mert", "task_1", [_item("Mert Stratejist")])
    memory_crystal.crystallize("mert", "task_2", [_item("Mert Başkan")])
    payload = client.get(
        "/api/memory/mert/recall", params={"query": "Mert", "exclude_task_id": "task_2"}
    ).json()
    assert all(hit["task_id"] != "task_2" for hit in payload["hits"])


def test_executor_builds_fenced_memory_block_before_depth_analyst(tmp_path):
    """Yürütücü, derin analiste geçmeden kristalden GEÇMİŞİ çeker."""
    storage = str(tmp_path / "mem")
    memory_crystal.crystallize(
        "ada",
        "eski_gorev",
        [_item("Ada geçen taramada Kıdemli Stratejist görünüyordu")],
        base=storage,
    )

    executor = PinealExecutor()
    executor.memory = MagicMock(storage_path=storage)
    executor._log = MagicMock()
    status = TaskSnapshot(task_id="yeni_gorev")

    block = executor._recall_memory_crystal(
        "yeni_gorev",
        {"target_profile": {"username": "ada", "bio": "Stratejist"}, "forensic_evidence": []},
        status,
    )

    assert block.startswith("<UNTRUSTED_MEMORY_CRYSTAL>")
    assert "Stratejist" in block
    record = next(r for r in status.evidence_chain if r["agent"] == "memory_crystal")
    assert record["evidence_type"] == "memory_recall"
    assert record["result"]["available"] is True
    assert record["result"]["recalled"] >= 1


def test_executor_stays_silent_when_no_target(tmp_path):
    """Hedef anahtarı yoksa hafıza bloğu BOŞTUR (uydurma geçmiş yok)."""
    executor = PinealExecutor()
    executor.memory = MagicMock(storage_path=str(tmp_path / "mem"))
    executor._log = MagicMock()
    status = TaskSnapshot(task_id="t1")

    block = executor._recall_memory_crystal("t1", {"target_profile": {}}, status)

    assert block == ""
    assert [r for r in status.evidence_chain if r["agent"] == "memory_crystal"] == []
