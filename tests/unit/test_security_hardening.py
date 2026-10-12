import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agent_core.schemas.telemetry import ErrorHaltEvent, Severity
from agent_core.services.canonical_memory import CanonicalMemory
from agent_core.utils import security
from agent_core.utils.security import (
    SecurityConfigurationError,
    UnsafeURLError,
    redact_text,
    resolve_public_url,
    safe_child_path,
    safe_get,
)
from backend import api


PUBLIC_IP = "93.184.216.34"


def _resolver(addresses):
    def resolve(_host, port, family, socktype):
        return [
            (socket_family, socktype, 6, "", (address, port))
            for socket_family, address in addresses
        ]

    return resolve


def test_development_open_auth_is_explicit_in_startup_health(monkeypatch):
    monkeypatch.setenv("PINEAL_ENV", "development")
    monkeypatch.delenv("PINEAL_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("PINEAL_TOKEN", raising=False)

    with TestClient(api.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["security"] == {
        "environment": "development",
        "auth_required": False,
        "auth_state": "DISABLED_DEVELOPMENT_ONLY",
        "warning_code": "AUTH_DISABLED_DEVELOPMENT_ONLY",
    }


def test_production_without_token_cannot_start(monkeypatch):
    monkeypatch.setenv("PINEAL_ENV", "production")
    monkeypatch.delenv("PINEAL_TOKEN", raising=False)
    monkeypatch.delenv("PINEAL_REQUIRE_AUTH", raising=False)

    with pytest.raises(SecurityConfigurationError) as raised:
        with TestClient(api.app):
            pass

    assert raised.value.error_code == "PRODUCTION_AUTH_REQUIRED"
    assert api.app.state.startup_health["error_code"] == "PRODUCTION_AUTH_REQUIRED"


def test_production_without_spend_cap_cannot_start(monkeypatch):
    """[AUDIT S1] production + OPENROUTER_MAX_SPEND_USD 0/tanimsiz → acilis RED.

    Cap 0 = sinirsiz LLM harcamasi (runtime enforce cap yoksa devre disi).
    /health 'degraded' uyarisi bu sinif icin yetersizdi (P2-10 sinifi)."""
    monkeypatch.setenv("PINEAL_ENV", "production")
    monkeypatch.setenv("PINEAL_TOKEN", "production-test-token-which-is-long")
    monkeypatch.setenv("OPENROUTER_MAX_SPEND_USD", "0")

    with pytest.raises(SecurityConfigurationError) as raised:
        with TestClient(api.app):
            pass
    assert raised.value.error_code == "PRODUCTION_SPEND_CAP_REQUIRED"
    assert api.app.state.startup_health["error_code"] == "PRODUCTION_SPEND_CAP_REQUIRED"


def test_production_missing_spend_cap_env_cannot_start(monkeypatch):
    """env degiskeni tamamen YOKSE de ayni sonuc (varsayilan 0 = sinirsiz)."""
    monkeypatch.setenv("PINEAL_ENV", "production")
    monkeypatch.setenv("PINEAL_TOKEN", "production-test-token-which-is-long")
    monkeypatch.delenv("OPENROUTER_MAX_SPEND_USD", raising=False)

    with pytest.raises(SecurityConfigurationError) as raised:
        with TestClient(api.app):
            pass
    assert raised.value.error_code == "PRODUCTION_SPEND_CAP_REQUIRED"


def test_development_without_spend_cap_still_starts(monkeypatch):
    """Kapı yalnız PRODUCTION içindir; development + cap 0 etkilenmez."""
    monkeypatch.setenv("PINEAL_ENV", "development")
    monkeypatch.delenv("PINEAL_TOKEN", raising=False)
    monkeypatch.delenv("PINEAL_REQUIRE_AUTH", raising=False)
    monkeypatch.setenv("OPENROUTER_MAX_SPEND_USD", "0")

    with TestClient(api.app) as client:
        response = client.get("/health")
    assert response.status_code == 200


def test_production_with_token_enforces_api_auth(monkeypatch):
    token = "production-test-token-which-is-long"
    monkeypatch.setenv("PINEAL_ENV", "production")
    monkeypatch.setenv("PINEAL_TOKEN", token)
    monkeypatch.setenv("OPENROUTER_MAX_SPEND_USD", "10")  # [AUDIT S1] prod: cap zorunlu

    with TestClient(api.app) as client:
        denied = client.get("/api/telemetry", params={"client_id": "prod_auth"})
        allowed = client.get(
            "/api/telemetry",
            params={"client_id": "prod_auth"},
            headers={"X-API-Key": token},
        )

    assert denied.status_code == 401
    assert allowed.status_code == 200


def test_websocket_auth_uses_first_message_not_url(monkeypatch):
    token = "websocket-secret-token"
    monkeypatch.setenv("PINEAL_ENV", "development")
    monkeypatch.setenv("PINEAL_TOKEN", token)

    with TestClient(api.app) as client:
        with client.websocket_connect("/ws/ws_secure") as websocket:
            websocket.send_json({"type": "auth", "token": token})
            assert websocket.receive_json() == {"type": "auth_ok"}

        with pytest.raises(WebSocketDisconnect) as raised:
            with client.websocket_connect("/ws/ws_denied") as websocket:
                websocket.send_json({"type": "auth", "token": "wrong"})
                websocket.receive_json()
        assert raised.value.code == 1008


def test_url_validation_rejects_private_if_any_dns_answer_is_private():
    resolver = _resolver([
        (2, PUBLIC_IP),
        (2, "10.0.0.7"),
    ])

    with pytest.raises(UnsafeURLError, match="NON_PUBLIC_ADDRESS"):
        resolve_public_url("https://public.example/profile", resolver=resolver)


def test_url_validation_is_fail_closed_for_dns_and_url_tricks():
    def unresolved(*_args):
        raise OSError("dns unavailable")

    with pytest.raises(UnsafeURLError, match="DNS_RESOLUTION_FAILED"):
        resolve_public_url("https://missing.example/path", resolver=unresolved)
    for value in (
        "file:///etc/passwd",
        "http://user:pass@example.com/",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data",
    ):
        with pytest.raises(UnsafeURLError):
            resolve_public_url(value)


@pytest.mark.asyncio
async def test_safe_get_pins_validated_dns_address(monkeypatch):
    real_resolve = security.resolve_public_url
    monkeypatch.setattr(
        security,
        "resolve_public_url",
        lambda url: real_resolve(url, resolver=_resolver([(2, PUBLIC_IP)])),
    )
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, text="ok")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await safe_get(client, "https://public.example/data")

    assert response.status_code == 200
    assert str(requests[0].url) == f"https://{PUBLIC_IP}/data"
    assert requests[0].headers["host"] == "public.example"
    assert requests[0].extensions["sni_hostname"] == "public.example"


@pytest.mark.asyncio
async def test_safe_get_blocks_redirect_to_private_address_before_second_request(monkeypatch):
    real_resolve = security.resolve_public_url

    def controlled_resolve(url):
        if "public.example" in url:
            return real_resolve(url, resolver=_resolver([(2, PUBLIC_IP)]))
        return real_resolve(url)

    monkeypatch.setattr(security, "resolve_public_url", controlled_resolve)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/admin"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(UnsafeURLError, match="NON_PUBLIC_ADDRESS"):
            await safe_get(client, "https://public.example/start")

    assert len(requests) == 1


def test_safe_child_path_rejects_traversal_and_outside_symlink(tmp_path):
    storage = tmp_path / "memory"
    storage.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("secret", encoding="utf-8")
    (storage / "linked.json").symlink_to(outside)

    with pytest.raises(ValueError, match="PATH_TRAVERSAL_BLOCKED"):
        safe_child_path(str(storage), "../outside.json")
    with pytest.raises(ValueError, match="PATH_TRAVERSAL_BLOCKED"):
        safe_child_path(str(storage), "linked.json")

    memory = CanonicalMemory(str(storage))
    with pytest.raises(ValueError, match="PATH_TRAVERSAL_BLOCKED"):
        memory.get_task_memory("linked")


def test_secret_redaction_covers_environment_bearer_keys_and_cookies(monkeypatch):
    arbitrary_token = "totally-arbitrary-production-token"
    monkeypatch.setenv("PINEAL_TOKEN", arbitrary_token)
    text = (
        f"token={arbitrary_token} Authorization: Bearer bearer-secret-123 "
        "api_key=sk-or-v1-SUPERSECRET123 auth_token=COOKIESECRET456"
    )

    redacted = redact_text(text)

    assert arbitrary_token not in redacted
    assert "bearer-secret-123" not in redacted
    assert "SUPERSECRET123" not in redacted
    assert "COOKIESECRET456" not in redacted
    assert redacted.count("[REDACTED]") >= 4


def test_event_and_log_bus_redact_secrets_before_queueing(monkeypatch):
    client_id = "redaction_bus"
    secret = "arbitrary-event-secret"
    monkeypatch.setenv("PINEAL_TOKEN", secret)
    room = api.get_room(client_id)

    api.broadcast_log(client_id, "ERROR", f"provider failed with {secret}")
    api.broadcast_event(client_id, ErrorHaltEvent(
        task_id="secret_task",
        agent_name="agent",
        error_code="PROVIDER_ERROR",
        error_message=f"Authorization: Bearer {secret}",
        severity=Severity.Critical,
    ))

    queued = list(room["queue"]._queue)
    assert secret not in repr(queued)
    assert "[REDACTED]" in repr(queued)


def test_experimental_rate_limit_is_bounded(monkeypatch):
    monkeypatch.setenv("PINEAL_ENV", "development")
    monkeypatch.delenv("PINEAL_TOKEN", raising=False)
    monkeypatch.setitem(api.RATE_LIMITS, "experimental", (1, 60))
    api._rate_buckets.clear()

    with TestClient(api.app) as client:
        first = client.post("/api/experimental/shadow/analyze", json={})
        second = client.post("/api/experimental/shadow/analyze", json={})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "RATE_LIMITED"


def test_task_timeout_and_retry_configuration_is_hard_bounded(monkeypatch):
    monkeypatch.setenv("PINEAL_TASK_TIMEOUT_SECONDS", "999999")
    monkeypatch.setenv("PINEAL_TASK_MAX_ATTEMPTS", "999")
    assert api._bounded_env_int("PINEAL_TASK_TIMEOUT_SECONDS", 300, 1, 1800) == 1800
    assert api._bounded_env_int("PINEAL_TASK_MAX_ATTEMPTS", 3, 1, 3) == 3

    monkeypatch.setenv("PINEAL_TASK_TIMEOUT_SECONDS", "not-an-int")
    assert api._bounded_env_int("PINEAL_TASK_TIMEOUT_SECONDS", 300, 1, 1800) == 300
