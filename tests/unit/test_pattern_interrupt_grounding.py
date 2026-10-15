import pytest

from agent_core.agents.pattern_interrupt import GeneratedMessage, PatternInterrupt


@pytest.mark.asyncio
async def test_pattern_interrupt_does_not_mark_empty_or_zero_confidence_output_valid():
    class Gateway:
        def __init__(self, result):
            self.result = result

        async def query_json_chain(self, *args, **kwargs):
            return self.result

    evidence = {"target_analysis": {"micro_signals": [{"evidence": "gözlenen paylaşım"}]}}
    result = GeneratedMessage(
        message="",
        strategy="reflective",
        confidence=0.8,
        compliance_score=100.0,
        dialogue_tree=[],
    )
    empty = await PatternInterrupt().execute(evidence, None, Gateway(result))
    assert empty.data_confidence is False
    assert empty.confidence == 0.0
    assert empty.fallback_reason == "empty_generated_message"

    zero = await PatternInterrupt().execute(
        evidence,
        None,
        Gateway(result.model_copy(update={"message": "Gözlemlenen paylaşım hakkında soru?", "confidence": 0.0})),
    )
    assert zero.data_confidence is False
    assert zero.confidence == 0.0
    assert zero.fallback_reason == "model_confidence_zero"


@pytest.mark.asyncio
async def test_pattern_interrupt_returns_unavailable_without_grounded_evidence():
    result = await PatternInterrupt().execute({"target_analysis": {}}, None, None)
    assert result.strategy == "UNAVAILABLE"
    assert result.confidence == 0.0
    assert result.data_confidence is False
    assert result.fallback_reason == "insufficient_grounded_evidence"
