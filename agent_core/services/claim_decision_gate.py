"""Deterministic claim-linked decision gate for outbound message text.

The gate does not treat every ``YALAN`` vote as a veto. A block is eligible
only for the exact bio-extracted claim with a stable claim ID, a bio source
reference, and unanimous panel refutation backed by audited source quotes.
Canonical observations are intentionally outside this external-claim gate.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


DIRECT_REFUTATION_BASIS = "unanimous_yalan_with_audited_source_quote"


class ClaimGateDecision(BaseModel):
    claim_id: str
    claim_origin: Literal["bio_extracted"] = "bio_extracted"
    claim_text: str
    truth_status: str
    decision_state: Literal["BLOCK_SAME_CLAIM", "NO_BLOCK"]
    reason_code: str
    claim_source_refs: list[str] = Field(default_factory=list)
    evidence_url: str = ""
    evidence_quote: str = ""
    direct_refutation_confirmed: bool = False
    direct_refutation_basis: str = ""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ClaimDecisionGateReport(BaseModel):
    schema_version: Literal["claim-decision-gate-v1"] = "claim-decision-gate-v1"
    policy: Literal["exact_claim_only"] = "exact_claim_only"
    decisions: list[ClaimGateDecision] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json")
        except TypeError:
            return dump()
    return {}


def _exact_claim_tokens(text: str) -> list[str]:
    """Normalize punctuation/case while preserving every word in the claim."""
    normalized = unicodedata.normalize("NFKD", str(text or "").casefold())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.translate(str.maketrans({"ı": "i", "đ": "d"}))
    return re.findall(r"[a-z0-9]+", normalized)


def _valid_claim_id(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"clm_[0-9a-f]{20}", value) is not None


def _decision_for(raw: Any) -> ClaimGateDecision | None:
    result = _mapping(raw)
    if result.get("claim_origin") != "bio_extracted":
        return None
    claim_id = result.get("claim_id")
    if not _valid_claim_id(claim_id):
        return None

    claim_text = str(result.get("claim_text") or "").strip()
    status = str(result.get("truth_status") or "")
    source_refs = result.get("claim_source_refs")
    source_refs = [str(ref) for ref in source_refs] if isinstance(source_refs, list) else []
    evidence_url = str(result.get("evidence_url") or "").strip()
    evidence_quote = str(result.get("evidence_quote") or "").strip()
    direct_confirmed = result.get("direct_refutation_confirmed") is True
    votes = result.get("juror_votes") if isinstance(result.get("juror_votes"), dict) else {}
    audit = result.get("vote_audit") if isinstance(result.get("vote_audit"), dict) else {}
    invalid_votes = result.get("invalid_votes") if isinstance(result.get("invalid_votes"), dict) else {}
    seat_errors = result.get("seat_errors") if isinstance(result.get("seat_errors"), dict) else {}
    contradiction = str(result.get("contradiction_detail") or "").strip()
    basis = str(result.get("direct_refutation_basis") or "")

    reason = "status_not_yalan"
    eligible = status == "YALAN"
    if eligible:
        reason = "claim_text_missing" if not claim_text else "missing_bio_source_ref"
        eligible = bool(claim_text) and "target_profile.bio" in source_refs
    if eligible:
        reason = "direct_refutation_not_confirmed"
        eligible = (
            direct_confirmed
            and basis == DIRECT_REFUTATION_BASIS
            and bool(contradiction)
        )
    if eligible:
        reason = "source_quote_missing_or_unusable"
        eligible = (
            evidence_url.lower().startswith(("http://", "https://"))
            and bool(evidence_quote)
        )
    if eligible:
        reason = "panel_or_provenance_audit_failed"
        eligible = (
            len(votes) >= 2
            and set(audit) == set(votes)
            and all(vote == "YALAN" for vote in votes.values())
            and all(
                str(rule).startswith("kanit_kapisi_gecildi:")
                for rule in audit.values()
            )
            and not invalid_votes
            and not seat_errors
        )
    if eligible:
        # A one-token match is indistinguishable from a word/topic-level filter.
        # Abstain rather than expanding a claim-level veto to a generic term.
        reason = "claim_not_specific_enough_for_exact_phrase_gate"
        eligible = len(_exact_claim_tokens(claim_text)) >= 2
    if eligible:
        reason = "unanimous_claim_linked_refutation_with_valid_source_quote"

    return ClaimGateDecision(
        claim_id=claim_id,
        claim_text=claim_text,
        claim_origin="bio_extracted",
        truth_status=status,
        decision_state="BLOCK_SAME_CLAIM" if eligible else "NO_BLOCK",
        reason_code=reason,
        claim_source_refs=source_refs,
        evidence_url=evidence_url,
        evidence_quote=evidence_quote,
        direct_refutation_confirmed=direct_confirmed,
        direct_refutation_basis=basis,
    )


def build_claim_decision_gate(report: Any) -> ClaimDecisionGateReport:
    """Create structured, same-claim decisions from a verifier report."""
    data = _mapping(report)
    raw_results = data.get("verifications")
    decisions = []
    if isinstance(raw_results, list):
        for raw in raw_results:
            decision = _decision_for(raw)
            if decision is not None:
                decisions.append(decision)
    return ClaimDecisionGateReport(decisions=decisions)


def filter_message_for_claim_gate(
    message: str,
    gate: ClaimDecisionGateReport | dict[str, Any] | None,
) -> tuple[str, list[str]]:
    """Suppress a whole generated message only when it contains a blocked claim.

    Matching requires the full normalized claim as a contiguous token phrase.
    Partial words, related topics, aliases, and canonical observation text do
    not trigger the gate. No model interprets verifier instructions here.
    """
    text = str(message or "")
    data = _mapping(gate)
    raw_decisions = data.get("decisions")
    if not isinstance(raw_decisions, list) or not text:
        return text, []

    message_tokens = _exact_claim_tokens(text)
    blocked_ids: list[str] = []
    for raw in raw_decisions:
        decision = _mapping(raw)
        if decision.get("decision_state") != "BLOCK_SAME_CLAIM":
            continue
        claim_id = decision.get("claim_id")
        source_refs = decision.get("claim_source_refs")
        if (
            not _valid_claim_id(claim_id)
            or decision.get("claim_origin") != "bio_extracted"
            or decision.get("truth_status") != "YALAN"
            or decision.get("direct_refutation_confirmed") is not True
            or decision.get("direct_refutation_basis") != DIRECT_REFUTATION_BASIS
            or not isinstance(source_refs, list)
            or "target_profile.bio" not in source_refs
            or not str(decision.get("evidence_url") or "").lower().startswith(("http://", "https://"))
            or not str(decision.get("evidence_quote") or "").strip()
        ):
            continue
        claim_tokens = _exact_claim_tokens(str(decision.get("claim_text") or ""))
        if len(claim_tokens) < 2:
            continue
        width = len(claim_tokens)
        if any(message_tokens[index:index + width] == claim_tokens
               for index in range(len(message_tokens) - width + 1)):
            blocked_ids.append(claim_id)

    if blocked_ids:
        return "", sorted(set(blocked_ids))
    return text, []
