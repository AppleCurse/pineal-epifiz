"""FAZ B · B4 — GERÇEK İLİŞKİ GRAFI sözleşme testleri.

Kilitlenen iddialar:
1. `HolographicResonanceMesh`'i besleyen graf artık KANITTAN doğar; eskiden
   arayüz `generateNodes()` ile rastgele düğüm üretiyordu (süs).
2. Kanıt yoksa graf BOŞTUR — uydurma düğüm/kenar üretilmez.
3. Yerleşim DETERMİNİSTİKTİR (aynı kanıt → aynı graf): `Math.random()` yok.
4. API ucu gerçek belleği okur; bozuk/eksik görevde dürüst hata döner.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from agent_core.services.graph_builder import (
    EvidenceGraph,
    build_evidence_graph,
    graph_from_task_memory,
)


def _evidence_item(**kw) -> dict:
    base = {
        "evidence_id": "ev_" + "0" * 20,
        "epistemic_type": "observation",
        "source_engine": "maigret",
        "content": "kullanıcı github.com'da bulundu",
        "provenance_refs": ["https://github.com/hedef"],
        "observed_at": "2026-10-01T12:00:00+00:00",
    }
    base.update(kw)
    return base


# ------------------------------------------------------------- 1 · kanıttan doğar
def test_graph_grows_from_evidence_only():
    graph = build_evidence_graph(
        [
            _evidence_item(),
            _evidence_item(provenance_refs=["https://x.com/hedef"]),
            _evidence_item(source_engine="holehe", provenance_refs=["https://amazon.com/u"]),
        ],
        {"username": "@hedef"},
    )
    assert graph.available is True
    kinds = {n.kind for n in graph.nodes}
    assert {"target", "host", "engine"} <= kinds
    assert any(n.label == "github.com" for n in graph.nodes)
    assert graph.node_count == len(graph.nodes) > 1
    assert graph.edge_count > 0
    # Hedef düğümü MERKEZDEDİR.
    target = next(n for n in graph.nodes if n.kind == "target")
    assert target.id == "target:hedef"


def test_edges_are_co_occurrence_not_all_pairs():
    """Kenar = aynı kanıt kaydında birlikte geçme; her şey her şeye BAĞLANMAZ."""
    graph = build_evidence_graph(
        [
            _evidence_item(provenance_refs=["https://a.com/1"], source_engine="m1"),
            _evidence_item(provenance_refs=["https://b.com/2"], source_engine="m2"),
        ],
        {"username": "hedef"},
    )
    pairs = {(e.source, e.target) for e in graph.edges}
    # a.com ile m2 aynı kayıtta geçmedi -> aralarında kenar YOK.
    assert ("host:a.com", "engine:m2") not in pairs
    assert ("host:a.com", "engine:m1") in pairs or ("engine:m1", "host:a.com") in pairs


# -------------------------------------------------- 2 · dürüstlük (uydurma yok)
def test_no_evidence_means_empty_graph():
    graph = build_evidence_graph([], {"username": "hedef"})
    assert graph.available is False
    assert graph.reason == "no_evidence"
    assert graph.nodes == [] and graph.edges == []


def test_none_or_malformed_evidence_is_empty_not_invented():
    assert build_evidence_graph(None).available is False
    assert build_evidence_graph("bozuk").available is False
    assert build_evidence_graph([{"content": "x"}]).nodes[0].kind == "target"


def test_empty_evidence_never_yields_fake_nodes():
    graph = build_evidence_graph({"evidence": []})
    assert graph.node_count == 0
    assert "uydurma" in graph.machine_note  # dürüst boşluk notu


def test_node_budget_is_bounded():
    items = [
        _evidence_item(provenance_refs=[f"https://site{i}.com/x"]) for i in range(200)
    ]
    graph = build_evidence_graph(items, {"username": "hedef"}, max_nodes=10)
    assert graph.node_count <= 10


# ------------------------------------------------------- 3 · deterministik yerleşim
def test_same_evidence_yields_identical_graph():
    items = [_evidence_item(), _evidence_item(provenance_refs=["https://b.com/1"])]
    first = build_evidence_graph(items, {"username": "hedef"})
    second = build_evidence_graph(items, {"username": "hedef"})
    assert first.model_dump() == second.model_dump()


def test_top_nodes_are_the_heaviest():
    """`top_nodes` ağırlığa göre AZALAN sırada; en çok kanıt taşıyan önce."""
    graph = build_evidence_graph(
        [_evidence_item(provenance_refs=["https://a.com/1"])] * 3
        + [_evidence_item(provenance_refs=["https://b.com/1"])],
        {"username": "hedef"},
    )
    weights = {n.id: n.weight for n in graph.nodes}
    ordered = [weights[node_id] for node_id in graph.top_nodes]
    assert ordered == sorted(ordered, reverse=True)
    # 4 kayıt da aynı gün -> gün düğümü en ağır; a.com (3) onu izler.
    assert graph.top_nodes[0] == "day:2026-10-01"
    assert "host:a.com" in graph.top_nodes


def test_graph_model_rejects_unknown_fields():
    with pytest.raises(Exception):
        EvidenceGraph(available=True, uydurma=1)  # type: ignore[call-arg]


def test_graph_from_task_memory_accepts_memory_shape():
    payload = {"evidence": [_evidence_item()], "target_profile": {"username": "hedef"}}
    graph = graph_from_task_memory(payload, payload.get("target_profile"))
    assert graph.available is True


# ------------------------------------------------------------------ 4 · API ucu
def test_endpoint_returns_graph_from_task_memory():
    class _Memory:
        def get_task_memory(self, task_id: str) -> dict:
            return {
                "evidence": [_evidence_item()],
                "target_profile": {"username": "hedef"},
            }

    class _Executor:
        memory = _Memory()

    from backend.api import app

    app.state.rooms = {
        "graph-client": {
            "queue": asyncio.Queue(),
            "websockets": set(),
            "executor": _Executor(),
            "vault": {},
        }
    }
    with TestClient(app) as client:
        r = client.get("/api/tasks/fx_graph_01/graph", params={"client_id": "graph-client"})
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["node_count"] >= 2


def test_endpoint_rejects_invalid_task_id():
    from backend.api import app

    app.state.rooms = {
        "graph-client": {
            "queue": asyncio.Queue(),
            "websockets": set(),
            "executor": None,
            "vault": {},
        }
    }
    with TestClient(app) as client:
        r = client.get("/api/tasks/bozuk..id/graph", params={"client_id": "graph-client"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_TASK_ID"
