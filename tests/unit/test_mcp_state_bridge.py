"""FAZ D · D1 — kasa köprüsü: tek kaynak + fail-closed + yerellik.

Kilitlenen iddialar:
    * Kasa durumu API'den okunur; API yoksa/uzaksa/cevap bozuksa KİLİTLİ.
    * Uzak ``PINEAL_API_URL`` reddedilir (hedef verisi makineden çıkmaz).
    * Yönlendirme takip EDİLMEZ (yerel uç, veriyi uzak adrese yönlendiremez).
    * Hız sınırı kayan penceredir; bozuk env değeri güvenli varsayılana düşer.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agent_core.mcp import state_bridge as sb


@pytest.fixture(autouse=True)
def _clean_cache():
    sb.clear_vault_cache()
    yield
    sb.clear_vault_cache()


class _StubAPI:
    """Yerel API taklidi: verilen gövdeyi döner, istek sayısını tutar."""

    def __init__(self, body: str = '{"locked": false}', status: int = 200, location: str = ""):
        self.hits = 0
        self.body = body
        self.status = status
        self.location = location

        handler = self._make_handler()
        self.server = HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def _make_handler(inner):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - http.server sözleşmesi
                inner.hits += 1
                payload = inner.body.encode("utf-8")
                self.send_response(inner.status)
                if inner.location:
                    self.send_header("Location", inner.location)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                return

        return Handler

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture()
def stub_api():
    stubs = []
    yield stubs
    for stub in stubs:
        stub.close()


class TestUrlPolicy:
    def test_default_is_local_api(self):
        url, reason = sb.api_base_url({})
        assert url == sb.DEFAULT_API_URL and reason == ""

    def test_remote_url_is_rejected(self):
        url, reason = sb.api_base_url({"PINEAL_API_URL": "https://pineal.example.com"})
        assert url == "" and reason == "non_local_api_url"

    def test_bad_scheme_is_rejected(self):
        url, reason = sb.api_base_url({"PINEAL_API_URL": "ftp://127.0.0.1:8000"})
        assert url == "" and reason == "bad_api_scheme"

    def test_localhost_names_are_accepted(self):
        for url in ("http://localhost:8000", "http://127.0.0.1:9", "http://[::1]:8000"):
            base, reason = sb.api_base_url({"PINEAL_API_URL": url})
            assert base == url.rstrip("/") and reason == ""


class TestVaultState:
    def test_open_vault_is_read_from_api(self, stub_api):
        api = _StubAPI('{"locked": false}')
        stub_api.append(api)
        locked, reason = sb.vault_state(env={"PINEAL_API_URL": api.url})
        assert locked is False and reason == ""
        assert api.hits == 1

    def test_locked_vault_is_read_from_api(self, stub_api):
        api = _StubAPI('{"locked": true}')
        stub_api.append(api)
        locked, reason = sb.vault_state(env={"PINEAL_API_URL": api.url})
        assert locked is True and reason == ""

    def test_unreachable_api_is_locked_fail_closed(self):
        # Hiç dinlemeyen bir bağlantı noktası: cevap yok → kilitli.
        locked, reason = sb.vault_state(env={"PINEAL_API_URL": "http://127.0.0.1:1"})
        assert locked is True
        assert reason.startswith("vault_api_unreachable:")

    def test_remote_url_keeps_vault_locked(self):
        locked, reason = sb.vault_state(env={"PINEAL_API_URL": "https://uzak.example.com"})
        assert locked is True and reason == "non_local_api_url"

    def test_broken_json_is_locked(self, stub_api):
        api = _StubAPI("{bu bozuk")
        stub_api.append(api)
        locked, reason = sb.vault_state(env={"PINEAL_API_URL": api.url})
        assert locked is True and reason == "vault_api_bad_json"

    def test_unexpected_shape_is_locked(self, stub_api):
        api = _StubAPI('{"locked": "false"}')
        stub_api.append(api)
        locked, reason = sb.vault_state(env={"PINEAL_API_URL": api.url})
        assert locked is True and reason == "vault_api_bad_shape"

    def test_http_error_status_is_reported(self, stub_api):
        api = _StubAPI('{"locked": false}', status=500)
        stub_api.append(api)
        locked, reason = sb.vault_state(env={"PINEAL_API_URL": api.url})
        assert locked is True and reason == "vault_api_status:500"

    def test_redirect_to_remote_is_not_followed(self, stub_api):
        # Yerel uç 302 ile uzak adrese yönlendirirse: takip YOK, istek orada bitmez.
        api = _StubAPI("", status=302, location="https://uzak.example.com/status")
        stub_api.append(api)
        locked, reason = sb.vault_state(env={"PINEAL_API_URL": api.url})
        assert locked is True
        assert reason == "vault_api_status:302"

    def test_repeated_calls_use_short_cache(self, stub_api):
        api = _StubAPI('{"locked": false}')
        stub_api.append(api)
        env = {"PINEAL_API_URL": api.url}
        sb.vault_state(env=env)
        sb.vault_state(env=env)
        assert api.hits == 1  # bayat cevapla uzun süre koşulmaz ama her çağrıda da sorulmaz

    def test_cache_is_dropped_when_cleared(self, stub_api):
        api = _StubAPI('{"locked": false}')
        stub_api.append(api)
        env = {"PINEAL_API_URL": api.url}
        sb.vault_state(env=env)
        sb.clear_vault_cache()
        sb.vault_state(env=env)
        assert api.hits == 2

    def test_client_id_is_sent_to_api(self, stub_api):
        seen: dict = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                seen["path"] = self.path
                body = json.dumps({"locked": False}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            sb.vault_state(
                env={
                    "PINEAL_API_URL": f"http://127.0.0.1:{server.server_port}",
                    "PINEAL_MCP_CLIENT_ID": "operator",
                }
            )
            assert "client_id=operator" in seen["path"]
        finally:
            server.shutdown()
            server.server_close()


class TestRateLimiter:
    def test_window_slides(self):
        limiter = sb.SlidingWindowLimiter(limit=2, window_seconds=10)
        assert limiter.allow("t", now=0.0) is True
        assert limiter.allow("t", now=1.0) is True
        assert limiter.allow("t", now=2.0) is False  # kota doldu
        assert limiter.allow("t", now=11.5) is True  # pencere kaydı

    def test_limits_are_per_key(self):
        limiter = sb.SlidingWindowLimiter(limit=1, window_seconds=60)
        assert limiter.allow("a", now=0.0) is True
        assert limiter.allow("b", now=0.0) is True
        assert limiter.allow("a", now=0.0) is False

    def test_env_parsing(self):
        limiter = sb.limiter_from_env({"PINEAL_MCP_RATE_LIMIT": "3", "PINEAL_MCP_RATE_WINDOW": "5"})
        assert limiter.limit == 3 and limiter.window == 5.0

    def test_broken_env_falls_back_to_safe_default(self):
        limiter = sb.limiter_from_env({"PINEAL_MCP_RATE_LIMIT": "abc", "PINEAL_MCP_RATE_WINDOW": ""})
        assert limiter.limit == 20 and limiter.window == 60.0


class TestMinorDeclaration:
    def test_undeclared_subject_is_not_minor(self):
        assert sb.minor_case_for("hedef", {}) is None

    def test_declared_subject_is_flagged_minor(self):
        case = sb.minor_case_for("cocuk", {"PINEAL_MCP_MINOR_SUBJECTS": "a, cocuk ,b"})
        assert case is not None and case.subject_is_minor is True
        # Beyan "izin" değildir: onay bağlamı taşınmaz → kapı reddeder.
        from agent_core.safety.minor_gate import MinorGate

        assert MinorGate().evaluate(case).allowed is False

    def test_matching_is_case_insensitive(self):
        assert sb.minor_case_for("Cocuk", {"PINEAL_MCP_MINOR_SUBJECTS": "cocuk"}) is not None


def test_status_snapshot_is_honest(monkeypatch, stub_api):
    api = _StubAPI('{"locked": true}')
    stub_api.append(api)
    snapshot = sb.status_snapshot({"PINEAL_API_URL": api.url, "PINEAL_MCP_CLIENT_ID": "op"})
    assert snapshot["vault_locked"] is True
    assert snapshot["client_id"] == "op"
    assert snapshot["api_reason"] is None
