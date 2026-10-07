"""HTTP giriş kapısının MinorGate'i atlayamadığını doğrular."""

import json

from backend import api


def test_initiate_payload_age_under_18_becomes_minor_case():
    request = api.InitiatePayload(client_id="api-test", url="https://example.test/child", age=17)
    case = api._minor_case_from_request(request)

    assert case is not None
    assert case.subject_is_minor is True
    assert api.MinorGate().evaluate(case).allowed is False


def test_initiate_payload_nested_case_keeps_all_four_conditions():
    request = api.InitiatePayload(
        client_id="api-test",
        url="https://example.test/child",
        minor_case={
            "subject_is_minor": True,
            "case_type": "missing_or_harm",
            "family_notified": True,
            "reason": "Çocuk kayıp; aile karakola başvurdu ve vaka doğrulandı.",
            "verified": True,
            "council_approvals": ["a", "b"],
        },
    )
    case = api._minor_case_from_request(request)

    assert case is not None
    decision = api.MinorGate().evaluate(case)
    assert decision.allowed is True
    assert decision.reason_code == "approved"


def test_minor_ledger_entry_never_contains_raw_subject(tmp_path, monkeypatch):
    monkeypatch.setenv("PINEAL_MINOR_LEDGER_PATH", str(tmp_path / "minor.jsonl"))
    request = api.InitiatePayload(
        client_id="api-test",
        url="Ahmet Yılmaz",
        minor_case={"subject_is_minor": True},
    )
    case = api._minor_case_from_request(request)
    record = api._minor_gate_record(case, capability_id="api.initiate", subject=request.url)

    assert record is not None
    entry = record[2]
    assert "Ahmet" not in json.dumps(entry, ensure_ascii=False)
    assert entry["subject_ref"].startswith("sha256:")
