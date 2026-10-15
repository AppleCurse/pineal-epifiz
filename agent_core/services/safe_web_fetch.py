"""Bounded public-web fetches through the DNS-pinning egress primitive.

All generic web extractors should parse the returned HTML locally rather than
letting an extractor library create its own network client. `safe_get` pins the
resolved public address and validates every redirect before connecting.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urlsplit

from agent_core.capabilities.egress import open_client
from agent_core.utils.security import UnsafeURLError, safe_get


MAX_HTML_BYTES = 4_000_000
_ALLOWED_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml", "text/plain"})


class SafeWebFetchError(RuntimeError):
    """A bounded safe fetch failed for a stable, machine-readable reason."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SafeHTML:
    requested_url: str
    final_url: str
    html: str
    content_type: str
    status_code: int
    bytes_read: int


async def fetch_safe_html(
    url: str,
    *,
    timeout_seconds: float = 20.0,
    max_bytes: int = MAX_HTML_BYTES,
) -> SafeHTML:
    """GET a public HTML page via a DNS-pinned request and bounded stream."""
    try:
        parsed = urlsplit(url)
    except (TypeError, ValueError) as exc:
        raise SafeWebFetchError("INVALID_URL") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise SafeWebFetchError("INVALID_URL")
    if parsed.username is not None or parsed.password is not None:
        raise SafeWebFetchError("INVALID_URL")
    try:
        max_bytes = max(1, min(int(max_bytes), MAX_HTML_BYTES))
    except (TypeError, ValueError):
        max_bytes = MAX_HTML_BYTES

    target = f"{parsed.scheme.lower()}://{parsed.netloc}"
    async with open_client(purpose="scraper", target=target, timeout=timeout_seconds) as client:
        try:
            response = await asyncio.wait_for(
                safe_get(
                    client,
                    url,
                    headers={"User-Agent": "PinealResearchBot/1.0"},
                    max_redirects=3,
                    stream=True,
                ),
                timeout=timeout_seconds,
            )
        except UnsafeURLError:
            raise
        except asyncio.TimeoutError as exc:
            raise SafeWebFetchError("TIMEOUT") from exc

        try:
            response.raise_for_status()
            content_type = (response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
            if content_type and content_type not in _ALLOWED_CONTENT_TYPES:
                raise SafeWebFetchError("UNSUPPORTED_CONTENT_TYPE")
            content_length = response.headers.get("content-length")
            try:
                if content_length and int(content_length) > max_bytes:
                    raise SafeWebFetchError("RESPONSE_TOO_LARGE")
            except ValueError:
                pass

            body = bytearray()
            try:
                async with asyncio.timeout(timeout_seconds):
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            raise SafeWebFetchError("RESPONSE_TOO_LARGE")
            except TimeoutError as exc:
                raise SafeWebFetchError("TIMEOUT") from exc
            if not body:
                raise SafeWebFetchError("EMPTY_RESPONSE")

            charset = response.charset_encoding or "utf-8"
            try:
                html = bytes(body).decode(charset, errors="replace")
            except LookupError:
                html = bytes(body).decode("utf-8", errors="replace")
            final_url = str(response.extensions.get("pineal_original_url") or url)
            return SafeHTML(
                requested_url=url,
                final_url=final_url,
                html=html,
                content_type=content_type,
                status_code=response.status_code,
                bytes_read=len(body),
            )
        finally:
            await response.aclose()
