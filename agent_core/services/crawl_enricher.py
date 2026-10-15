"""Crawl4AI markdown extraction over the pinned, bounded web transport.

The crawler's own HTTP/browser network stack is deliberately not used here:
preflight `is_safe_url()` alone cannot pin the address used by a second client.
HTML is fetched through `safe_get()` (DNS pinning + redirect validation), then
Crawl4AI's MarkdownGenerator parses the already-downloaded document locally.
Browser/JavaScript rendering is unavailable until its network can be constrained
with the same guarantees.
"""
from __future__ import annotations

import asyncio
import logging
import os
from html.parser import HTMLParser
from typing import Optional

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS = 8000
MAX_MAX_CHARS = 50000
DEFAULT_TIMEOUT = 20
MAX_TIMEOUT = 120
DEFAULT_MAX_BYTES = 4_000_000
DEFAULT_RESEARCH_LIMIT = 2
MAX_RESEARCH_LIMIT = 5


class CrawlFetchResult(BaseModel):
    requested_url: str
    available: bool = False
    provider: str = "crawl4ai"
    reason: Optional[str] = None
    url: str = ""                       # safe fetch'in raporladığı nihai URL
    title: str = ""
    markdown: str = ""                  # LLM-dostu metin (env ile kırpılır)
    status_code: Optional[int] = None
    error_detail: Optional[str] = None
    model_config = ConfigDict(extra="forbid")


class _TitleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.parts.append(data)


def _env_int(name: str, default: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(1, min(value, maximum))


def is_enabled() -> bool:
    return os.getenv("ENABLE_CRAWL4AI", "false").lower() == "true"


def research_limit() -> int:
    """_run_public_web_research içinde kaç eşleşen sonucun çekileceği."""
    return _env_int("CRAWL4AI_RESEARCH_LIMIT", DEFAULT_RESEARCH_LIMIT,
                    MAX_RESEARCH_LIMIT)


def _classify_error(message: str) -> str:
    low = (message or "").lower()
    if any(
        marker in low
        for marker in (
            "executable doesn't exist",
            "playwright install",
            "looks like playwright",
            "browsertype.launch",
        )
    ):
        return "browser_missing"
    return "fetch_error"


def _parse_html(html: str, base_url: str) -> tuple[str, str]:
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

    generated = DefaultMarkdownGenerator().generate_markdown(
        input_html=html,
        base_url=base_url,
        citations=False,
    )
    markdown = getattr(generated, "raw_markdown", "") or ""
    if markdown.startswith("Error converting HTML to markdown:"):
        raise ValueError("MARKDOWN_CONVERSION_FAILED")
    title_parser = _TitleParser()
    title_parser.feed(html)
    title = " ".join(" ".join(title_parser.parts).split())
    return markdown, title


async def fetch_readable(url: str) -> CrawlFetchResult:
    """Fetch public HTML safely, then convert it to markdown locally."""
    if not is_enabled():
        return CrawlFetchResult(requested_url=url, available=False, reason="disabled")

    clean = (url or "").strip()
    if not clean.startswith(("http://", "https://")):
        return CrawlFetchResult(requested_url=url, available=False, reason="invalid_url")
    from agent_core.capabilities.egress import httpx
    from agent_core.scraper.vault_gate import VaultLockedError
    from agent_core.services.safe_web_fetch import SafeWebFetchError, fetch_safe_html
    from agent_core.utils.security import UnsafeURLError, is_safe_url

    # A quick rejection improves feedback; fetch_safe_html resolves again and
    # pins the actual connection, so this check is never treated as the control.
    if not is_safe_url(clean):
        return CrawlFetchResult(requested_url=clean, available=False, reason="ssrf_blocked")
    try:
        import importlib.util

        if importlib.util.find_spec("crawl4ai.markdown_generation_strategy") is None:
            return CrawlFetchResult(
                requested_url=clean, available=False, reason="library_missing"
            )
    except (ImportError, ModuleNotFoundError, ValueError):
        return CrawlFetchResult(requested_url=clean, available=False, reason="library_missing")

    renderer = os.getenv("CRAWL4AI_RENDERER", "http").lower()
    if renderer not in ("http", "browser"):
        renderer = "http"
    if renderer == "browser":
        return CrawlFetchResult(
            requested_url=clean,
            available=False,
            reason="browser_renderer_disabled_safe_transport_unavailable",
        )

    timeout = _env_int("CRAWL4AI_TIMEOUT", DEFAULT_TIMEOUT, MAX_TIMEOUT)
    max_chars = _env_int("CRAWL4AI_MAX_CHARS", DEFAULT_MAX_CHARS, MAX_MAX_CHARS)
    try:
        fetched = await asyncio.wait_for(
            fetch_safe_html(clean, timeout_seconds=timeout, max_bytes=DEFAULT_MAX_BYTES),
            timeout=timeout + 2,
        )
        markdown, title = await asyncio.wait_for(
            asyncio.to_thread(_parse_html, fetched.html, fetched.final_url),
            timeout=max(1, timeout),
        )
    except asyncio.TimeoutError:
        return CrawlFetchResult(requested_url=clean, available=False, reason="timeout")
    except UnsafeURLError:
        return CrawlFetchResult(requested_url=clean, available=False, reason="ssrf_blocked")
    except VaultLockedError:
        return CrawlFetchResult(requested_url=clean, available=False, reason="vault_locked")
    except SafeWebFetchError as exc:
        return CrawlFetchResult(
            requested_url=clean, available=False, reason=exc.code.lower()
        )
    except httpx.TimeoutException:
        return CrawlFetchResult(requested_url=clean, available=False, reason="timeout")
    except httpx.HTTPStatusError as exc:
        return CrawlFetchResult(
            requested_url=clean,
            available=False,
            reason="http_error",
            status_code=exc.response.status_code,
        )
    except httpx.RequestError as exc:
        return CrawlFetchResult(
            requested_url=clean,
            available=False,
            reason="network_error",
            error_detail=type(exc).__name__,
        )
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.split(".")[0] == "crawl4ai":
            return CrawlFetchResult(requested_url=clean, available=False,
                                    reason="library_missing")
        return CrawlFetchResult(
            requested_url=clean,
            available=False,
            reason="dependency_broken",
            error_detail=f"{type(exc).__name__}: {str(exc)[:180]}",
        )
    except ImportError as exc:
        return CrawlFetchResult(
            requested_url=clean,
            available=False,
            reason="dependency_broken",
            error_detail=f"{type(exc).__name__}: {str(exc)[:180]}",
        )
    except Exception as exc:
        reason = _classify_error(str(exc))
        return CrawlFetchResult(
            requested_url=clean,
            available=False,
            reason=reason,
            error_detail=f"{type(exc).__name__}: {str(exc)[:180]}",
        )

    markdown = (markdown or "").strip()
    if not markdown:
        return CrawlFetchResult(
            requested_url=clean,
            available=False,
            reason="empty_text",
            url=fetched.final_url,
            status_code=fetched.status_code,
        )
    if len(markdown) > max_chars:
        marker = " …[kırpıldı]"
        if max_chars <= len(marker):
            markdown = markdown[:max_chars]
        else:
            markdown = markdown[:max_chars - len(marker)].rstrip() + marker
    return CrawlFetchResult(
        requested_url=clean,
        available=True,
        reason=None,
        url=fetched.final_url,
        title=title,
        markdown=markdown,
        status_code=fetched.status_code,
    )
