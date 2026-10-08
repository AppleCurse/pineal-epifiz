from agent_core.services.claim_decision_gate import (
    DIRECT_REFUTATION_BASIS,
    build_claim_decision_gate,
    filter_message_for_claim_gate,
)


CLAIM_ID = "clm_0123456789abcdefabcd"


def _result(**overrides):
    result = {
        "claim_id": CLAIM_ID,
        "claim_origin": "bio_extracted",
        "claim_text": "Senior Strategist at Acme",
        "claim_source_refs": ["target_profile.bio"],
        "truth_status": "YALAN",
        "evidence_url": "https://example.test/source",
        "evidence_quote": "The person has never worked at Acme.",
        "contradiction_detail": "The quoted source directly refutes the employer claim.",
        "juror_votes": {"seat_a": "YALAN", "seat_b": "YALAN"},
        "vote_audit": {
            "seat_a": "kanit_kapisi_gecildi:1.0",
            "seat_b": "kanit_kapisi_gecildi:1.0",
        },
        "invalid_votes": {},
        "seat_errors": {},
        "direct_refutation_confirmed": True,
        "direct_refutation_basis": DIRECT_REFUTATION_BASIS,
    }
    result.update(overrides)
    return result


def test_gate_blocks_only_the_same_audited_bio_claim_phrase():
    gate = build_claim_decision_gate({"verifications": [_result()]})

    assert len(gate.decisions) == 1
    decision = gate.decisions[0]
    assert decision.decision_state == "BLOCK_SAME_CLAIM"
    assert decision.claim_id == CLAIM_ID

    filtered, blocked_ids = filter_message_for_claim_gate(
        "I saw that you are a Senior Strategist at Acme.", gate
    )
    assert filtered == ""
    assert blocked_ids == [CLAIM_ID]


def test_gate_does_not_block_partial_words_topics_or_related_claims():
    gate = build_claim_decision_gate({"verifications": [_result()]})

    message = "Would you like to talk about strategy and Acme's products?"
    filtered, blocked_ids = filter_message_for_claim_gate(message, gate)

    assert filtered == message
    assert blocked_ids == []


def test_contradiction_unknown_and_unprovenanced_yalan_are_not_vetoes():
    candidates = [
        _result(truth_status="ÇELİŞKİLİ"),
        _result(truth_status="BİLİNMİYOR"),
        _result(claim_source_refs=[]),
        _result(direct_refutation_confirmed=False),
        _result(vote_audit={"seat_a": "kanit_kapisi_iptal"}),
    ]
    gate = build_claim_decision_gate({"verifications": candidates})

    assert len(gate.decisions) == len(candidates)
    assert all(item.decision_state == "NO_BLOCK" for item in gate.decisions)


def test_gate_abstains_on_a_single_word_instead_of_creating_a_word_filter():
    gate = build_claim_decision_gate({
        "verifications": [_result(claim_text="Mimar")]
    })

    assert gate.decisions[0].decision_state == "NO_BLOCK"
    assert gate.decisions[0].reason_code == "claim_not_specific_enough_for_exact_phrase_gate"
    message = "Mimarlarla ilgili bir önerim var."
    assert filter_message_for_claim_gate(message, gate) == (message, [])


def test_canonical_observation_checks_never_enter_external_claim_gate():
    gate = build_claim_decision_gate({
        "verifications": [],
        "canonical_observation_checks": [{
            "claim_id": CLAIM_ID,
            "claim_origin": "canonical_observation",
            "truth_status": "YALAN",
        }],
    })

    assert gate.decisions == []
