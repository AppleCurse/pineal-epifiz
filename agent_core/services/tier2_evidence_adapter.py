"""Narrow canonicalization for semantically explicit agent-output fields.

This is not a generic agent-output-to-evidence converter. Only fields listed
below are classified. Unsupported claims, mixed heuristic signals, free-form
summaries, and unknown agents remain in their original agent records.

Tier-2 items may lack source-native status or item-level source references.
Those values remain absent; the adapter never fabricates them. In particular,
B6's message-context adapter will not admit these unreferenced observations.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agent_core.domain.evidence_models import EvidenceItem, EpistemicType

_SCHEMA_VERSION = "tier2-evidence-adapter-v1"


def _stable_id(
    *,
    agent_name: str,
    field_path: str,
    epistemic_type: EpistemicType,
    content: str,
    scope: dict[str, Any],
) -> str:
    identity = {
        "schema_version": _SCHEMA_VERSION,
        "agent_name": agent_name,
        "field_path": field_path,
        "epistemic_type": epistemic_type,
        "content": content,
        "scope": scope,
    }
    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "ev_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def _payload(result: Any) -> dict[str, Any] | None:
    if hasattr(result, "model_dump"):
        dumped = result.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else None
    return result if isinstance(result, dict) else None


def _make_item(
    *,
    agent_name: str,
    field_path: str,
    epistemic_type: EpistemicType,
    content: str,
    scope: dict[str, Any],
) -> EvidenceItem:
    clean_content = content.strip()
    return EvidenceItem(
        evidence_id=_stable_id(
            agent_name=agent_name,
            field_path=field_path,
            epistemic_type=epistemic_type,
            content=clean_content,
            scope=scope,
        ),
        epistemic_type=epistemic_type,
        source_engine=agent_name,
        source_status=None,
        content=clean_content,
        provenance_refs=[],
        scope=scope,
        observed_at=None,
        window_start=None,
        window_end=None,
        # Agent confidence is not treated as calibrated evidence confidence.
        confidence=None,
        source_metrics=None,
    )


def canonicalize_tier2_output(agent_name: str, result: Any) -> list[EvidenceItem]:
    """Return only explicit, allowlisted Tier-2 fields as typed items.

    The allowlist deliberately stops at the field-level semantic distinction:
    ``human_behavior.observations`` are agent-labeled observations,
    ``possible_interpretations`` and ``alternative_interpretations`` are
    inferences, and ``resonance_calc.recommended_approach`` is strategy.
    No free-form field is promoted based on its wording or content.
    """
    data = _payload(result)
    if data is None or data.get("data_confidence") is not True:
        return []

    items: list[EvidenceItem] = []
    if agent_name == "human_behavior":
        for field_name, epistemic_type in (
            ("observations", "observation"),
            ("possible_interpretations", "inference"),
            ("alternative_interpretations", "inference"),
        ):
            values = data.get(field_name)
            if not isinstance(values, list):
                continue
            for index, value in enumerate(values):
                if not isinstance(value, str) or not value.strip():
                    continue
                scope = {
                    "canonicalization": _SCHEMA_VERSION,
                    "field_path": f"{field_name}[{index}]",
                    "item_provenance": "not_provided_by_agent_output",
                    "status_semantics": "source status unavailable; not synthesized",
                    "epistemic_note": (
                        "Agent-labeled observation; not independently verified or source-linked."
                        if epistemic_type == "observation"
                        else "Agent interpretation; unverified and not an observed event or established cause."
                    ),
                }
                items.append(
                    _make_item(
                        agent_name=agent_name,
                        field_path=f"{field_name}[{index}]",
                        epistemic_type=epistemic_type,
                        content=value,
                        scope=scope,
                    )
                )
        # unsupported_claims and micro_signals are intentionally not mapped:
        # the former is explicitly unsupported, while the latter mixes
        # heuristic labels and measurements without item-level provenance.
        return items

    if agent_name == "resonance_calc":
        recommendation = data.get("recommended_approach")
        if not isinstance(recommendation, str) or not recommendation.strip():
            return []
        state = data.get("state")
        scope = {
            "canonicalization": _SCHEMA_VERSION,
            "field_path": "recommended_approach",
            "item_provenance": "input_field_names_only; no direct source citation",
            "decision_state": state if state in {"confirmed", "contradicted", "inference_gap"} else None,
            "not_factual_evidence": True,
            "epistemic_note": "Agent recommendation/strategy; not a factual claim.",
        }
        return [
            _make_item(
                agent_name=agent_name,
                field_path="recommended_approach",
                epistemic_type="strategy",
                content=recommendation,
                scope=scope,
            )
        ]

    return []
