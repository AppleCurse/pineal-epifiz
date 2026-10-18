"""Bounded HTML reads use the pinned scraper transport and close responses."""
from contextlib import asynccontextmanager

import pytest

from agent_core.services import safe_web_fetch
from agent_core.services.safe_web_fetch import SafeWebFetchError, fetch_safe_html


class _Response:
    def __init__(self, body=b"<p>source</p>", *, content_type="text/html", status=200):
        self.body = body
        self.status_code = status
        self.headers = {"content-type": content_type}
        self.extensions = {"pineal_original_url": "https://public.example/final"}
        self.charset_encoding = "utf-8"
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")

    async def aiter_bytes(self):
        for index in range(0, len(self.body), 3):
            yield self.body[index:index + 3]

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_fetch_safe_html_uses_pinned_redirect_aware_transport(monkeypatch):
    response = _Response()
    seen = {}

    @asynccontextmanager
    async def fake_open_client(*, purpose, target, timeout):
        seen["client"] = (purpose, target, timeout)
        yield object()

    async def fake_safe_get(client, url, **kwargs):
        seen["request"] = (client, url, kwargs)
        return response

    monkeypatch.setattr(safe_web_fetch, "open_client", fake_open_client)
    monkeypatch.setattr(safe_web_fetch, "safe_get", fake_safe_get)
    result = await fetch_safe_html("https://public.example/start", timeout_seconds=4)

    assert result.final_url == "https://public.example/final"
    assert result.html == "<p>source</p>"
    assert result.bytes_read == len(b"<p>source</p>")
    assert seen["client"] == ("scraper", "https://public.example", 4)
    assert seen["request"][2]["stream"] is True
    assert seen["request"][2]["max_redirects"] == 3
    assert response.closed is True


@pytest.mark.asyncio
async def test_fetch_safe_html_rejects_over_limit_body_and_closes_response(monkeypatch):
    response = _Response(body=b"0123456789")

    @asynccontextmanager
    async def fake_open_client(**_kwargs):
        yield object()

    async def fake_safe_get(*_args, **_kwargs):
        return response

    monkeypatch.setattr(safe_web_fetch, "open_client", fake_open_client)
    monkeypatch.setattr(safe_web_fetch, "safe_get", fake_safe_get)

    with pytest.raises(SafeWebFetchError, match="RESPONSE_TOO_LARGE"):
        await fetch_safe_html("https://public.example/page", max_bytes=5)
    assert response.closed is True


@pytest.mark.asyncio
async def test_fetch_safe_html_rejects_non_html_content_type(monkeypatch):
    response = _Response(body=b"{}", content_type="application/json")

    @asynccontextmanager
    async def fake_open_client(**_kwargs):
        yield object()

    async def fake_safe_get(*_args, **_kwargs):
        return response

    monkeypatch.setattr(safe_web_fetch, "open_client", fake_open_client)
    monkeypatch.setattr(safe_web_fetch, "safe_get", fake_safe_get)

    with pytest.raises(SafeWebFetchError, match="UNSUPPORTED_CONTENT_TYPE"):
        await fetch_safe_html("https://public.example/data")
    assert response.closed is True
