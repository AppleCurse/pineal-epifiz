"""Provider result validation and honest web fallback contracts."""

import asyncio

import pytest

from agent_core.services.search_engine import (
    SearchEngine,
    SearchOutcome,
    SearchProviderError,
    SearchResult,
)
from agent_core.utils import security
from backend.api import _summarize_osint_search_results


class _Response:
    def __init__(self, *, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Client:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, *args, **kwargs):
        return self.response

    async def get(self, *args, **kwargs):
        return self.response


@pytest.mark.asyncio
async def test_tavily_malformed_nonempty_results_are_provider_errors(monkeypatch):
    monkeypatch.setattr(security, "is_safe_url", lambda _url: True)
    engine = SearchEngine(tavily_key="test-key", serpapi_key="", exa_key="")

    with pytest.raises(SearchProviderError, match="TAVILY_INVALID_RESULTS"):
        await engine._search_tavily(
            "query",
            5,
            client=_Client(_Response(payload={"results": [{"content": "snippet"}]})),
        )

    assert await engine._search_tavily(
        "query", 5, client=_Client(_Response(payload={"results": []}))
    ) == []


@pytest.mark.asyncio
async def test_duckduckgo_redirect_href_is_source_url_not_display_label(monkeypatch):
    monkeypatch.setattr(security, "is_safe_url", lambda _url: True)
    html = """
      <a class="result__url" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Farticle">
        example.com › article
      </a>
      <a class="result__snippet">Evidence snippet from the actual page.</a>
    """
    engine = SearchEngine(tavily_key="", serpapi_key="", exa_key="")
    rows = await engine._search_duckduckgo(
        "query", 5, client=_Client(_Response(text=html))
    )
    assert len(rows) == 1
    assert rows[0].source_url == "https://example.com/article"
    assert rows[0].content == "Evidence snippet from the actual page."


@pytest.mark.asyncio
async def test_duckduckgo_does_not_invent_query_as_search_snippet(monkeypatch):
    monkeypatch.setattr(security, "is_safe_url", lambda _url: True)
    html = '<a class="result__url" href="https://example.com/article">example.com</a>'
    engine = SearchEngine(tavily_key="", serpapi_key="", exa_key="")

    with pytest.raises(SearchProviderError, match="DUCKDUCKGO_UNPARSEABLE_RESPONSE"):
        await engine._search_duckduckgo(
            "query text is not evidence", 5, client=_Client(_Response(text=html))
        )


@pytest.mark.asyncio
async def test_search_validates_query_without_overriding_vault_lock():
    locked = await SearchEngine(
        tavily_key="", serpapi_key="", exa_key="", vault_state=lambda: False
    ).search(" ")
    assert locked.status == "VAULT_LOCKED"

    invalid = await SearchEngine(
        tavily_key="", serpapi_key="", exa_key="", vault_state=lambda: True
    ).search(" ")
    assert invalid.status == "UNAVAILABLE"
    assert invalid.error == "INVALID_QUERY"

    invalid_limit = await SearchEngine(
        tavily_key="", serpapi_key="", exa_key="", vault_state=lambda: True
    ).search("valid", num_results=True)
    assert invalid_limit.error == "INVALID_RESULT_LIMIT"


@pytest.mark.asyncio
async def test_search_normalizes_leaf_vault_gate_race(monkeypatch):
    from agent_core.scraper.vault_gate import VaultLockedError
    import agent_core.services.search_engine as search_engine_module

    class _LockedClient:
        async def __aenter__(self):
            raise VaultLockedError("locked between policy check and client creation")

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(
        search_engine_module, "open_client", lambda **_kwargs: _LockedClient()
    )
    outcome = await SearchEngine(
        tavily_key="", serpapi_key="", exa_key="", vault_state=lambda: True
    ).search("valid")
    assert outcome.status == "VAULT_LOCKED"
    assert outcome.available is False


def test_provider_rows_are_normalized_and_invalid_rows_do_not_become_evidence():
    engine = SearchEngine(tavily_key="", serpapi_key="", exa_key="")
    redirect = SearchResult(
        query="q",
        content=" source snippet ",
        source_url="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa",
        provider="fake",
    )
    merged, errors = engine._collect_provider_results(
        [[redirect, SearchResult(query="q", content="", source_url="", provider="fake")]]
    )
    assert merged[0].source_url == "https://example.com/a"
    assert merged[0].content == "source snippet"
    assert errors == ["INVALID_PROVIDER_RESULT"]


def test_osint_caller_keeps_empty_search_distinct_from_outage_and_propagates_cancel():
    result = SearchResult(
        query="q", content="source snippet", source_url="https://example.com/a", provider="tavily"
    )
    merged, status = _summarize_osint_search_results(
        [
            SearchOutcome(results=[result], status="OK", available=True),
            SearchOutcome(results=[], status="UNAVAILABLE", error="TIMEOUT", available=False),
        ]
    )
    assert merged == [result]
    assert status == {
        "status": "PARTIAL",
        "available": True,
        "queries_requested": 2,
        "queries_available": 1,
        "result_count": 1,
        "errors": ["TIMEOUT"],
    }

    empty_results, empty_status = _summarize_osint_search_results(
        [SearchOutcome(results=[], status="NO_RESULTS", available=True)]
    )
    assert empty_results == []
    assert empty_status["status"] == "NO_RESULTS"
    assert empty_status["available"] is True

    not_requested, not_requested_status = _summarize_osint_search_results([])
    assert not_requested == []
    assert not_requested_status["status"] == "NOT_REQUESTED"

    with pytest.raises(asyncio.CancelledError):
        _summarize_osint_search_results([asyncio.CancelledError()])


@pytest.mark.asyncio
async def test_paid_provider_failure_runs_free_fallback_and_preserves_outage(monkeypatch):
    import agent_core.services.search_engine as search_engine_module

    client_options = {}

    def open_client(**kwargs):
        client_options.update(kwargs)
        return _Client(_Response())

    monkeypatch.setattr(search_engine_module, "open_client", open_client)
    engine = SearchEngine(
        tavily_key="configured-key", serpapi_key="", exa_key="", vault_state=lambda: True
    )
    monkeypatch.setattr(engine, "_searxng_enabled", lambda: True)
    calls = []

    async def paid_failure(query, limit, client=None):
        calls.append("tavily")
        raise SearchProviderError("TAVILY_TIMEOUT")

    async def searxng_failure(query, limit):
        calls.append("searxng")
        raise SearchProviderError("SEARXNG_DEPENDENCY_MISSING")

    async def free_result(query, limit, client=None):
        calls.append("duckduckgo")
        return [
            SearchResult(
                query=query,
                content="verified fallback snippet",
                source_url="https://example.org/evidence",
                provider="duckduckgo",
            )
        ]

    monkeypatch.setattr(engine, "_search_tavily", paid_failure)
    monkeypatch.setattr(engine, "_search_searxng", searxng_failure)
    monkeypatch.setattr(engine, "_search_duckduckgo", free_result)

    outcome = await engine.search("contract query")
    assert set(calls) == {"tavily", "searxng", "duckduckgo"}
    assert client_options["trust_env"] is False
    assert client_options["follow_redirects"] is False
    assert outcome.status == "PARTIAL"
    assert outcome.available is True
    assert outcome.results[0].provider == "duckduckgo"
    assert "TAVILY_TIMEOUT" in outcome.error
    assert "SEARXNG_DEPENDENCY_MISSING" in outcome.error


@pytest.mark.asyncio
async def test_successful_empty_paid_result_does_not_trigger_unrequested_fallback(monkeypatch):
    import agent_core.services.search_engine as search_engine_module

    monkeypatch.setattr(
        search_engine_module, "open_client", lambda **_kwargs: _Client(_Response())
    )
    engine = SearchEngine(
        tavily_key="configured-key", serpapi_key="", exa_key="", vault_state=lambda: True
    )

    async def paid_empty(query, limit, client=None):
        return []

    async def unexpected_fallback(*_args, **_kwargs):
        raise AssertionError("successful empty result must not escalate to free search")

    monkeypatch.setattr(engine, "_search_tavily", paid_empty)
    monkeypatch.setattr(engine, "_free_search_tasks", lambda *_args: [unexpected_fallback()])

    outcome = await engine.search("no results")
    assert outcome.status == "NO_RESULTS"
    assert outcome.available is True
    assert outcome.error is None
