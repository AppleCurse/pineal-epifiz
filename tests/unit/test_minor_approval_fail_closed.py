"""Operator-supplied labels cannot authorize minor investigations."""
from fastapi.testclient import TestClient

from agent_core.safety import MinorCaseContext, MinorGate, coerce_minor_case
from backend import api


def _declaration():
    return {
        "subject_is_minor": True,
        "case_type": "missing_or_harm",
        "family_notified": True,
        "reason": "Missing child; family reports case to local authorities.",
        "verified": True,
        "council_approvals": ["operator:one", "council:two"],
        "case_id": "case-42",
    }


def test_gate_rejects_names_even_in_direct_context():
    decision = MinorGate().evaluate(MinorCaseContext(**{**_declaration(), "council_approvals": ("one", "two")}))
    assert decision.allowed is False
    assert decision.reason_code == "independent_approval_unavailable"


def test_raw_coercion_cannot_forge_approval():
    raw = {**_declaration(), "independent_approval": True, "approved": True}
    assert not MinorGate().evaluate(coerce_minor_case(raw)).allowed


def test_api_cannot_authorize_with_self_attested_names(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PINEAL_MINOR_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))
    cid = "fail_closed_regression"
    try:
        with TestClient(api.app) as client:
            result = client.post("/api/minor/case", json={"client_id": cid, **_declaration()})
            assert result.status_code == 200
            assert result.json()["allowed"] is False
            assert result.json()["reason_code"] == "independent_approval_unavailable"
            state = client.get("/api/minor/state", params={"client_id": cid})
            assert state.json()["allowed"] is False
            blocked = client.get("/api/browser/state", params={"client_id": cid})
            assert blocked.status_code == 451
    finally:
        api.app.state.minor_cases.pop(cid, None)
        api.app.state.rooms.pop(cid, None)
