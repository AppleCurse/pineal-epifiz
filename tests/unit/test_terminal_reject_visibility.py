"""Terminal görev retlerinin GÖRÜNÜRLÜĞÜ (2026-11-11 smoke bulgusu).

Ölçülen kusur
-------------
`/api/initiate` bazı dallarda (platform desteklenmiyor, çapraz OSINT kapalı,
kazıma altyapısı tükendi) `broadcast_result_error` çağırıp `return` ediyordu.
Bu yardımcı yalnız WebSocket'e yazıyordu; kanıt deposuna HİÇ yazmıyordu. Gerçek
sunucuda ölçüm:

    POST /api/initiate https://example.com → 200 {"status":"started"}
    GET  /api/tasks                       → {"tasks": []}   # görev hiç yok
    GET  .../graph                        → "no_evidence"   # neden yok belli değil

Sonuç: operatör "başladı" sanıp bekliyor; "hiç çalışmadı" ile "çalıştı ama
kanıt üretemedi" ayırt edilemiyordu.

Sözleşme (bu dosya):
    1. Ret, kanıt deposuna `memory_state="REJECTED"` + `status` +
       `halted_reason` ile yazılır → `GET /api/tasks` görevi GÖSTERİR.
    2. Ret kaydı KANIT DEĞİLDİR: graf kurmaz (sahte düğüm/örgü üretmez).
    3. Gerçek kanıt hâlâ graf kurar (süzme fazla geniş değil).
    4. Yazım hatası yutulmaz: `False` döner ve loglanır.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.services.task_rejection import (
    REJECT_EVIDENCE_TYPE,
    build_reject_record,
    record_terminal_reject,
)
from agent_core.services.graph_builder import graph_from_task_memory


class FakeMemory:
    """`CanonicalMemory.merge_evidence` yüzeyini taklit eden sahte depo."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.raise_on_merge = False

    async def merge_evidence(self, task_id, evidence_chain, metadata=None):
        if self.raise_on_merge:
            raise OSError("disk full")
        self.calls.append((task_id, evidence_chain, metadata))


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# --------------------------------------------------------------------------
# 1. Depoya yazım sözleşmesi
# --------------------------------------------------------------------------
def test_reject_record_is_typed_and_carries_reason():
    record = build_reject_record(
        "unsupported_platform",
        "Bu URL doğrudan kazınamaz. ENABLE_CROSS_PLATFORM etkinleştirilmeli.",
        "op_20261111095420_74be7d07",
    )
    assert record["type"] == REJECT_EVIDENCE_TYPE
    assert record["status"] == "unsupported_platform"
    assert record["id"] == "reject:op_20261111095420_74be7d07"
    assert "kazınamaz" in record["value"]
    assert record["timestamp"].endswith("+00:00")


def test_record_terminal_reject_writes_state_and_reason():
    memory = FakeMemory()

    written = record_terminal_reject(memory, "op_test_1", "unsupported_platform", "sebep")

    assert written is True
    assert len(memory.calls) == 1
    task_id, chain, metadata = memory.calls[0]
    assert task_id == "op_test_1"
    assert chain[0]["type"] == REJECT_EVIDENCE_TYPE
    # [1] Görev geçmişi bu iki alanı OKUR: durum + gerçek ret nedeni.
    assert metadata["memory_state"] == "REJECTED"
    assert metadata["status"] == "unsupported_platform"
    assert metadata["halted_reason"] == "sebep"


def test_record_terminal_reject_without_task_id_is_a_noop():
    memory = FakeMemory()
    assert record_terminal_reject(memory, None, "failed", "x") is False
    assert memory.calls == []


# --------------------------------------------------------------------------
# 2. Hata yutulmaz
# --------------------------------------------------------------------------
def test_write_failure_returns_false_and_logs():
    memory = FakeMemory()
    memory.raise_on_merge = True
    logged: list[tuple] = []

    written = record_terminal_reject(
        memory, "op_test_2", "failed", "sebep", logger_=lambda *a, **k: logged.append(a)
    )

    assert written is False
    assert logged, "yazım hatası sessizce yutulmamalı"


# --------------------------------------------------------------------------
# 3. Graf süzgeci: ret kanıt değildir
# --------------------------------------------------------------------------
def test_reject_record_never_becomes_a_graph_node():
    """Ret tek başına graf KURMAZ: 'available:false' ve SIFIR düğüm."""
    memory_payload = {
        "evidence": [build_reject_record("unsupported_platform", "kazınamaz", "op_x")],
        "status": "unsupported_platform",
        "halted_reason": "kazınamaz",
        "memory_state": "REJECTED",
    }

    graph = graph_from_task_memory(memory_payload, {"username": "hedef"})

    assert graph.available is False
    assert graph.reason == "no_evidence"
    assert graph.nodes == []
    assert graph.edges == []


def test_real_evidence_still_builds_a_graph_alongside_reject_record():
    """Süzme fazla geniş olmamalı: gerçek kanıt varken graf kurulur."""
    memory_payload = {
        "evidence": [
            build_reject_record("partial", "kısmi", "op_y"),
            {
                "type": "agent_output",
                "source_engine": "pineal_7pillar",
                "observed_at": "2026-11-11T09:00:00+00:00",
                "provenance_refs": ["https://instagram.com/hedef"],
            },
        ],
        "memory_state": "READY",
    }

    graph = graph_from_task_memory(memory_payload, {"username": "hedef"})

    assert graph.available is True
    kinds = {node.kind for node in graph.nodes}
    assert "target" in kinds
    assert "engine" in kinds
    # Ret kaydından türetilmiş bir düğüm olmamalı.
    assert all(REJECT_EVIDENCE_TYPE not in node.id for node in graph.nodes)
