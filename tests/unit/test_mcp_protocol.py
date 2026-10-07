"""FAZ D · D1 — MCP tel katmanı testleri (I/O yok, saf zarf mantığı).

Kilitlenen iddialar:
    * Güncel sürüm 2026-07-28'dir ve desteklenenler listesinde İLK sıradadır.
    * Legacy istemciler (2025-11-25 ve öncesi) dışarıda bırakılmaz.
    * Bozuk zarf sessizce kabul edilmez; makine-okunur hata döner.
    * Sürüm anlaşmazlığı desteklenen listeyi GİZLEMEZ.
"""

from __future__ import annotations

import json

import pytest

from agent_core.mcp import protocol as p


class TestFraming:
    def test_valid_message_parses(self):
        msg = p.parse_message('{"jsonrpc": "2.0", "id": 7, "method": "tools/list"}')
        assert msg["id"] == 7 and msg["method"] == "tools/list"

    def test_notification_has_no_id(self):
        msg = p.parse_message('{"jsonrpc": "2.0", "method": "notifications/initialized"}')
        assert p.is_notification(msg) is True
        msg_with_id = p.parse_message('{"jsonrpc": "2.0", "id": 1, "method": "ping"}')
        assert p.is_notification(msg_with_id) is False

    @pytest.mark.parametrize(
        "line,code",
        [
            ("", p.ErrorCode.INVALID_REQUEST),
            ("   ", p.ErrorCode.INVALID_REQUEST),
            ("{bozuk json", p.ErrorCode.PARSE_ERROR),
            ("[1,2,3]", p.ErrorCode.INVALID_REQUEST),
            ('{"jsonrpc": "1.0", "id": 1, "method": "ping"}', p.ErrorCode.INVALID_REQUEST),
            ('{"jsonrpc": "2.0", "id": 1}', p.ErrorCode.INVALID_REQUEST),
            ('{"jsonrpc": "2.0", "id": 1, "method": "ping", "params": 5}', p.ErrorCode.INVALID_PARAMS),
        ],
    )
    def test_broken_envelopes_are_rejected(self, line, code):
        with pytest.raises(p.RPCError) as info:
            p.parse_message(line)
        assert info.value.code == code

    def test_oversized_line_is_rejected_not_buffered(self):
        huge = '{"jsonrpc": "2.0", "id": 1, "method": "ping"}'
        with pytest.raises(p.RPCError) as info:
            p.parse_message(huge + " " * (p.MAX_LINE_BYTES + 10))
        assert "satır çok büyük" in info.value.message

    def test_error_response_shape(self):
        err = p.error_response(3, p.ErrorCode.METHOD_NOT_FOUND, "yok", data={"a": 1})
        assert err["error"]["code"] == p.ErrorCode.METHOD_NOT_FOUND
        assert err["error"]["data"] == {"a": 1}
        assert err["id"] == 3

    def test_rpc_error_without_data_omits_field(self):
        err = p.error_response(None, p.ErrorCode.PARSE_ERROR, "bozuk")
        assert "data" not in err["error"] and err["id"] is None

    def test_notification_envelope_has_no_id(self):
        note = p.notification("notifications/tools/list_changed", {"x": 1})
        assert "id" not in note and note["params"] == {"x": 1}


class TestVersions:
    def test_current_version_is_first_supported(self):
        assert p.PROTOCOL_VERSION == "2026-07-28"
        assert p.SUPPORTED_PROTOCOL_VERSIONS[0] == p.PROTOCOL_VERSION

    def test_legacy_versions_are_kept(self):
        # Eski istemcileri dışarıda bırakmak "standart protokol" iddiasını bozar.
        for legacy in ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"):
            assert legacy in p.SUPPORTED_PROTOCOL_VERSIONS

    def test_negotiation_echoes_supported_request(self):
        assert p.negotiate_version("2025-06-18") == "2025-06-18"
        assert p.negotiate_version("2026-07-28") == "2026-07-28"

    def test_negotiation_answers_with_newest_when_unknown(self):
        assert p.negotiate_version("1999-01-01") == p.PROTOCOL_VERSION
        assert p.negotiate_version(None) == p.PROTOCOL_VERSION

    def test_stateless_meta_version_is_read(self):
        msg = p.parse_message(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {"_meta": {p.META_VERSION_KEY: "2026-07-28"}},
                }
            )
        )
        assert p.request_protocol_version(msg) == "2026-07-28"

    def test_legacy_params_version_is_read(self):
        msg = p.parse_message(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-11-25"},
                }
            )
        )
        assert p.request_protocol_version(msg) == "2025-11-25"

    def test_absent_version_is_honest_none(self):
        msg = p.parse_message('{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}')
        assert p.request_protocol_version(msg) is None

    def test_unsupported_version_error_lists_alternatives(self):
        exc = p.unsupported_version_error("1999-01-01")
        assert exc.code == p.ErrorCode.UNSUPPORTED_PROTOCOL_VERSION
        assert exc.data["supportedVersions"] == list(p.SUPPORTED_PROTOCOL_VERSIONS)
        assert exc.data["requestedVersion"] == "1999-01-01"


def test_supported_version_helper():
    assert p.is_supported_version("2026-07-28") is True
    assert p.is_supported_version("2025-06-18") is True
    assert p.is_supported_version("1999-01-01") is False
    assert p.is_supported_version(None) is False
    assert p.is_supported_version("") is False
