"""FAZ D · D1 — CapabilityResult → MCP sonucu çevirisi (dürüstlük testleri).

Kilitlenen iddialar:
    * Kanıt üretilmediyse sonuç ``isError: true`` ve sebep makine-okunur.
    * Sürüme ait olmayan alan gönderilmez (structuredContent ≥2025-06-18,
      resultType = 2026-07-28).
    * Kırpma gizlenmez.
"""

from __future__ import annotations

from agent_core.capabilities import CapabilityResult, make_evidence
from agent_core.mcp import protocol as p
from agent_core.mcp import results as r


def _ok_result():
    item = make_evidence(
        content="profil bulundu: ornek_kullanici",
        source_engine="maigret",
        epistemic_type="observation",
        provenance_refs=["https://example.test/u/ornek"],
        confidence=0.62,
    )
    return CapabilityResult(
        capability_id="sensor.identity.maigret",
        available=True,
        items=(item,),
        notes={"sites_checked": 12},
        duration_ms=42,
    )


class TestSuccessShape:
    def test_ok_result_is_not_error_and_carries_evidence(self):
        rendered = r.render_result(_ok_result(), protocol_version=p.PROTOCOL_VERSION)
        assert rendered["isError"] is False
        text = rendered["content"][0]["text"]
        assert "1 kanıt" in text and "ev_" in text
        assert "sensor.identity.maigret" in text

    def test_structured_content_carries_machine_readable_fields(self):
        rendered = r.render_result(_ok_result(), protocol_version=p.PROTOCOL_VERSION)
        structured = rendered["structuredContent"]
        assert structured["ok"] is True
        assert structured["evidence_count"] == 1
        assert structured["notes"] == {"sites_checked": 12}
        assert structured["evidence_ids"][0].startswith("ev_")
        assert structured["duration_ms"] == 42

    def test_result_type_only_on_current_version(self):
        current = r.render_result(_ok_result(), protocol_version="2026-07-28")
        legacy = r.render_result(_ok_result(), protocol_version="2024-11-05")
        assert current["resultType"] == "complete"
        assert "resultType" not in legacy

    def test_structured_content_withheld_from_old_clients(self):
        for version in ("2026-07-28", "2025-11-25", "2025-06-18"):
            assert "structuredContent" in r.render_result(_ok_result(), protocol_version=version)
        for version in ("2025-03-26", "2024-11-05"):
            assert "structuredContent" not in r.render_result(
                _ok_result(), protocol_version=version
            )


class TestHonestFailures:
    def test_unavailable_result_is_error_with_reason(self):
        result = CapabilityResult(
            capability_id="sensor.identity.maigret",
            available=False,
            unavailable_reason="gate_disabled:ENABLE_MAIGRET",
        )
        rendered = r.render_result(result, protocol_version=p.PROTOCOL_VERSION)
        assert rendered["isError"] is True
        assert "gate_disabled:ENABLE_MAIGRET" in rendered["content"][0]["text"]
        assert rendered["structuredContent"]["unavailable_reason"] == "gate_disabled:ENABLE_MAIGRET"

    def test_policy_denial_names_the_gate(self):
        result = CapabilityResult(
            capability_id="extractor.text.language",
            available=False,
            unavailable_reason="policy:vault_locked",
            denied_by="vault",
        )
        rendered = r.render_result(result, protocol_version=p.PROTOCOL_VERSION)
        text = rendered["content"][0]["text"]
        assert "policy:vault_locked" in text and "reddeden kapı: vault" in text
        assert rendered["structuredContent"]["denied_by"] == "vault"

    def test_zero_evidence_without_error_is_not_success(self):
        # `ok` üç koşul ister: available + hata yok + en az bir kanıt.
        result = CapabilityResult(capability_id="extractor.text.language", available=True, items=())
        rendered = r.render_result(result, protocol_version=p.PROTOCOL_VERSION)
        assert rendered["isError"] is True
        assert rendered["structuredContent"]["ok"] is False


class TestTruncation:
    def test_large_evidence_is_clipped_and_flagged(self):
        item = make_evidence(content="x" * 9000, source_engine="test", epistemic_type="observation")
        result = CapabilityResult(
            capability_id="analyzer.test", available=True, items=(item,)
        )
        rendered = r.render_result(result, protocol_version=p.PROTOCOL_VERSION)
        assert rendered["structuredContent"]["truncated"] is True
        assert len(rendered["content"][0]["text"]) <= r.max_content_chars()

    def test_many_evidence_items_are_summarised_not_silently_dropped(self):
        items = tuple(
            make_evidence(content=f"kanıt {i}", source_engine="test", epistemic_type="observation")
            for i in range(60)
        )
        result = CapabilityResult(capability_id="sensor.test", available=True, items=items)
        rendered = r.render_result(result, protocol_version=p.PROTOCOL_VERSION)
        text = rendered["content"][0]["text"]
        assert "kanıt daha var" in text
        assert rendered["structuredContent"]["evidence_count"] == 60


def test_payload_is_serialised_when_model_like():
    class _Model:
        def model_dump(self):
            return {"language": "tr"}

    result = CapabilityResult(
        capability_id="extractor.text.language", available=True, items=(), payload=_Model()
    )
    rendered = r.render_result(result, protocol_version=p.PROTOCOL_VERSION)
    assert rendered["structuredContent"]["payload"] == {"language": "tr"}
