"""FAZ B · B4 — GERÇEK İLİŞKİ GRAFI (kanıttan).

Bugün `HolographicResonanceMesh.svelte` → `generateNodes()` **rastgele** düğüm
üretiyor: arayüzdeki örgü bir süs, veriyle ilgisi yok. Bu modül o örgüyü
besleyecek GERÇEK grafi kurar.

Kurallar (projenin dürüstlük sözleşmesiyle birebir aynı):
- Düğüm yalnız KANITTAN doğar: hedef, kaynak sunucu (provenance host),
  çıkarıcı motor (source_engine), gözlem günü. Tahmin/örnek düğüm YOKTUR.
- Kenar yalnız birlikte-geçme (co-occurrence) ilişkisidir: aynı kanıt
  kaydında birlikte görünen iki varlık bağlanır. Ağırlık = tekrar sayısı.
- Kanıt yoksa graf BOŞTUR (`available=False` + sebep). Boş graf için arayüz
  uydurma düğüm çizmez.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Iterable, Sequence
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["GraphNode", "GraphEdge", "EvidenceGraph", "build_evidence_graph"]

_MAX_NODES = 60
_MAX_EDGES = 200

_HOST_RE = re.compile(r"^(?:www\.)?(?P<host>[^:/?#]+)")


class GraphNode(BaseModel):
    id: str
    label: str
    kind: str  # target | host | engine | day
    weight: float = 0.0
    evidence_count: int = 0
    model_config = ConfigDict(extra="forbid")


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: float = 1.0
    relation: str = "co_occurrence"
    model_config = ConfigDict(extra="forbid")


class EvidenceGraph(BaseModel):
    available: bool = False
    reason: str | None = None
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    #: En çok kanıt taşıyan düğümler (UI vurgusu için).
    top_nodes: list[str] = Field(default_factory=list)
    machine_note: str = ""
    model_config = ConfigDict(extra="forbid")


def _host_of(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    try:
        host = (urlsplit(raw).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _iter_evidence(evidence: Any) -> Iterable[dict]:
    """Kanıt zinciri iki biçimde gelir: düz liste veya {"evidence": [...]}."""
    if isinstance(evidence, dict):
        evidence = evidence.get("evidence") or []
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        return []
    return [item for item in evidence if isinstance(item, dict)]


def build_evidence_graph(
    evidence: Any,
    target_profile: dict | None = None,
    *,
    max_nodes: int = _MAX_NODES,
    max_edges: int = _MAX_EDGES,
) -> EvidenceGraph:
    """Kanıt zincirinden gerçek ilişki grafı kurar.

    Hiçbir düğüm uydurulmaz: graf yalnız kanıtın KENDİ alanlarından
    (provenance_refs, source_engine, observed_at, scope) doğar.
    """
    items = list(_iter_evidence(evidence))
    if not items:
        return EvidenceGraph(
            available=False,
            reason="no_evidence",
            machine_note="GRAF: kanıt yok — düğüm üretilmedi (uydurma örgü yok).",
        )

    profile = target_profile or {}
    target_label = str(profile.get("username") or profile.get("name") or "").strip()
    if not target_label:
        # Hedef adı yoksa uydurma etiket YAZILMAZ: düğüm kimliği jenerik kalır.
        target_label = "target"
    target_id = f"target:{target_label.lstrip('@').lower()}"

    node_hits: Counter[str] = Counter()
    node_meta: dict[str, dict[str, Any]] = {}
    pair_hits: Counter[tuple[str, str]] = Counter()

    def _add(node_id: str, label: str, kind: str) -> None:
        node_hits[node_id] += 1
        node_meta.setdefault(node_id, {"id": node_id, "label": label, "kind": kind})

    _add(target_id, target_label, "target")

    for item in items:
        engine = str(item.get("source_engine") or item.get("agent") or "").strip()
        engine_id = f"engine:{engine.lower()}" if engine else ""

        hosts: list[str] = []
        for ref in (item.get("provenance_refs") or []):
            host = _host_of(str(ref))
            if host:
                hosts.append(host)

        observed = str(item.get("observed_at") or "").strip()
        day_id = ""
        if len(observed) >= 10 and observed[:4].isdigit():
            day_id = f"day:{observed[:10]}"

        members = [target_id]
        if engine_id:
            _add(engine_id, engine, "engine")
            members.append(engine_id)
        for host in dict.fromkeys(hosts):
            host_id = f"host:{host}"
            _add(host_id, host, "host")
            members.append(host_id)
        if day_id:
            _add(day_id, observed[:10], "day")
            members.append(day_id)

        # Yalnız HEDEFLE ilişkilendirilen varlıklar bağlanır; rastgele tam graf
        # (her şey her şeye) üretilmez — ilişki KANITTAN gelmeli.
        for member in members[1:]:
            pair = (target_id, member) if target_id < member else (member, target_id)
            pair_hits[pair] += 1
        for i in range(1, len(members)):
            for j in range(i + 1, len(members)):
                a, b = sorted((members[i], members[j]))
                pair_hits[(a, b)] += 1

    if not node_hits:
        return EvidenceGraph(
            available=False,
            reason="no_nodes",
            machine_note="GRAF: kanıttan düğüm çıkarılamadı.",
        )

    ranked = sorted(node_hits.items(), key=lambda kv: (-kv[1], kv[0]))[:max_nodes]
    keep = {node_id for node_id, _ in ranked}
    nodes = [
        GraphNode(
            **node_meta[node_id],
            weight=round(float(count), 3),
            evidence_count=int(count),
        )
        for node_id, count in ranked
    ]
    edges = [
        GraphEdge(source=a, target=b, weight=round(float(count), 3))
        for (a, b), count in sorted(pair_hits.items(), key=lambda kv: (-kv[1], kv[0]))
        if a in keep and b in keep
    ][:max_edges]

    top = [n.id for n in sorted(nodes, key=lambda n: -n.weight)[:5]]
    return EvidenceGraph(
        available=True,
        reason=None,
        nodes=nodes,
        edges=edges,
        node_count=len(nodes),
        edge_count=len(edges),
        top_nodes=top,
        machine_note=(
            f"GRAF: {len(nodes)} düğüm / {len(edges)} kenar "
            f"({len(items)} kanıt kaydından)."
        ),
    )


def graph_from_task_memory(memory_payload: Any, target_profile: dict | None = None) -> EvidenceGraph:
    """`CanonicalMemory.get_task_memory` çıktısından graf (API köprüsü)."""
    evidence: Any = memory_payload
    if isinstance(memory_payload, dict):
        evidence = memory_payload.get("evidence") or memory_payload.get("evidence_chain")
    return build_evidence_graph(evidence, target_profile)
