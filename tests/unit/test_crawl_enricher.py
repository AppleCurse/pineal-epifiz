"""Crawl4AI entegrasyon sözleşme testleri (FAZ 4).

İlkeler:
- Kapı (ENABLE_CRAWL4AI) kapalıyken davranış ESKİSİ GİBİ (pipeline değişmez).
- Kütüphane/tarayıcı/ağ/timeout hatalarında dürüst `available:false` + sebep;
  ASLA uydurma içerik yok.
- HTML fetch pinned transport ile yapılır; parser haricî ağ açmaz.
- renderer=browser, ağ adresi sabitlenemediği için dürüstçe kapalıdır.
- Public-web araştırma zenginleştirmesi: yalnız available=True sonuçlar
  `crawl` alanına girer; kapalıyken matched sonuçlar birebir aynı kalır.
- quote_guard korpusu: yalnız gerçek çekilmiş metin (`public_web_sources`)
  eklenir; alan yoksa korpus birebir aynı kalır.
"""
import asyncio
import importlib.util

import pytest

from agent_core.services import crawl_enricher, safe_web_fetch
from agent_core.services.safe_web_fetch import SafeHTML
from agent_core.utils import security
from agent_core.services.crawl_enricher import (
    CrawlFetchResult,
    _classify_error,
    fetch_readable,
)
from agent_core.services.quote_guard import guard_report
from agent_core.services.search_engine import SearchOutcome, SearchResult
from backend.api import _run_public_web_research


def _res(url="https://example.com/a", available=True, markdown="içerik", **kw):
    return CrawlFetchResult(
        requested_url=url, available=available,
        url=kw.get("url", url), title=kw.get("title", "T"),
        markdown=markdown, status_code=kw.get("status_code", 200),
    )


def _mock_safe_stack(monkeypatch, *, html="<html><title>Başlık</title><p>İçerik</p></html>", markdown="# İçerik", title="Başlık"):
    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(security, "is_safe_url", lambda _url: True)

    async def _fetch(url, **_kwargs):
        return SafeHTML(
            requested_url=url,
            final_url=url,
            html=html,
            content_type="text/html",
            status_code=200,
            bytes_read=len(html.encode("utf-8")),
        )

    monkeypatch.setattr(safe_web_fetch, "fetch_safe_html", _fetch)
    monkeypatch.setattr(crawl_enricher, "_parse_html", lambda *_args: (markdown, title))


class TestGate:
    @pytest.mark.asyncio
    async def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("ENABLE_CRAWL4AI", raising=False)
        res = await fetch_readable("https://example.com/a")
        assert res.available is False
        assert res.reason == "disabled"
        assert res.markdown == ""

    @pytest.mark.asyncio
    async def test_gate_on_uses_pinned_fetch_then_local_markdown_parser(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
        _mock_safe_stack(monkeypatch)
        called = {}
        real_parse = crawl_enricher._parse_html

        def _parse(html, url):
            called["parse"] = (html, url)
            return real_parse(html, url)

        monkeypatch.setattr(crawl_enricher, "_parse_html", _parse)
        res = await fetch_readable("https://example.com/a")
        assert called["parse"][0].startswith("<html>")
        assert called["parse"][1] == "https://example.com/a"
        assert res.available is True
        assert res.title == "Başlık"
        assert res.markdown == "# İçerik"


class TestHonestContract:
    @pytest.mark.asyncio
    async def test_invalid_url(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
        for bad in ("", "not-a-url", "ftp://x/y"):
            res = await fetch_readable(bad)
            assert res.available is False
            assert res.reason == "invalid_url"

    @pytest.mark.asyncio
    async def test_ssrf_blocked(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
        monkeypatch.setattr(importlib.util, "find_spec", lambda _name: object())
        monkeypatch.setattr(security, "is_safe_url", lambda _url: False)
        res = await fetch_readable("http://127.0.0.1:8000/secret")
        assert res.available is False
        assert res.reason == "ssrf_blocked"

    @pytest.mark.asyncio
    async def test_library_missing_is_reported_before_network(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
        monkeypatch.setattr(importlib.util, "find_spec", lambda _name: None)
        monkeypatch.setattr(
            safe_web_fetch,
            "fetch_safe_html",
            lambda *_args, **_kwargs: pytest.fail("network must not run without parser"),
        )
        res = await fetch_readable("https://example.com/a")
        assert res.available is False
        assert res.reason == "library_missing"

    @pytest.mark.asyncio
    async def test_installed_parser_import_failure_is_not_called_missing(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
        _mock_safe_stack(monkeypatch)

        def _broken_parser(*_args):
            raise ImportError("installed crawl4ai runtime is broken")

        monkeypatch.setattr(crawl_enricher, "_parse_html", _broken_parser)
        res = await fetch_readable("https://example.com/a")
        assert res.available is False
        assert res.reason == "dependency_broken"
        assert res.error_detail.startswith("ImportError:")

    @pytest.mark.asyncio
    async def test_browser_renderer_fails_closed_without_pinned_browser_transport(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
        monkeypatch.setenv("CRAWL4AI_RENDERER", "browser")
        _mock_safe_stack(monkeypatch)
        res = await fetch_readable("https://example.com/a")
        assert res.available is False
        assert res.reason == "browser_renderer_disabled_safe_transport_unavailable"

    @pytest.mark.asyncio
    async def test_generic_error_is_fetch_error(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
        _mock_safe_stack(monkeypatch)

        async def _boom(url, **_kwargs):
            raise ConnectionError("bağlantı reddedildi (dürüst ağ yokluğu)")

        monkeypatch.setattr(safe_web_fetch, "fetch_safe_html", _boom)
        res = await fetch_readable("https://example.com/a")
        assert res.reason == "fetch_error"
        assert res.available is False

    @pytest.mark.asyncio
    async def test_timeout_is_honest(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
        _mock_safe_stack(monkeypatch)

        async def _slow(url, **_kwargs):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(safe_web_fetch, "fetch_safe_html", _slow)
        res = await fetch_readable("https://example.com/a")
        assert res.reason == "timeout"

    @pytest.mark.asyncio
    async def test_failed_http_fetch_is_not_fabricated_as_empty_content(self, monkeypatch):
        from httpx import HTTPStatusError, Request, Response

        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
        _mock_safe_stack(monkeypatch)
        response = Response(403, request=Request("GET", "https://example.com/a"))

        async def _fail(url, **_kwargs):
            raise HTTPStatusError("Access denied", request=response.request, response=response)

        monkeypatch.setattr(safe_web_fetch, "fetch_safe_html", _fail)
        res = await fetch_readable("https://example.com/a")
        assert res.available is False
        assert res.reason == "http_error"
        assert res.status_code == 403
        assert res.markdown == ""

    def test_classify_error_markers(self):
        assert _classify_error("Executable doesn't exist at /x") == "browser_missing"
        assert _classify_error("run `playwright install`") == "browser_missing"
        assert _classify_error("connection refused") == "fetch_error"
        assert _classify_error("") == "fetch_error"

    @pytest.mark.asyncio
    async def test_markdown_capped_by_env(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
        monkeypatch.setenv("CRAWL4AI_MAX_CHARS", "100")
        _mock_safe_stack(monkeypatch, markdown="x" * 30000, title="T")
        res = await fetch_readable("https://example.com/a")
        assert len(res.markdown) == 100


class _FakeSearch:
    def __init__(self, outcome):
        self._outcome = outcome

    async def search(self, query, num_results=5):
        return self._outcome


def _engine(*urls):
    return _FakeSearch(SearchOutcome(results=[
        SearchResult(query="x", content=f"alper {u} hakkında",
                     source_url=u, provider="tavily")
        for u in urls
    ], status="OK", available=True))


class TestResearchWiring:
    """The API preserves search availability separately from a successful empty result."""

    @pytest.mark.asyncio
    async def test_unavailable_search_is_distinct_from_successful_empty_search(self):
        failed = await _run_public_web_research(
            "https://x.com/alper",
            _FakeSearch(SearchOutcome(
                results=[], status="UNAVAILABLE", error="TIMEOUT", available=False
            )),
        )
        assert failed["status"] == "unavailable"
        assert failed["available"] is False
        assert failed["search_outcome"] == {
            "status": "UNAVAILABLE", "available": False, "error": "TIMEOUT"
        }

        empty = await _run_public_web_research(
            "https://x.com/alper",
            _FakeSearch(SearchOutcome(results=[], status="NO_RESULTS", available=True)),
        )
        assert empty["status"] == "no_results"
        assert empty["available"] is True
        assert empty["search_outcome"]["status"] == "NO_RESULTS"
        assert empty["search_outcome"]["available"] is True

        class _ExplodingSearch:
            async def search(self, *_args, **_kwargs):
                raise RuntimeError("provider detail must not be exposed")

        raised = await _run_public_web_research("https://x.com/alper", _ExplodingSearch())
        assert raised["status"] == "unavailable"
        assert raised["search_outcome"]["error"] == "RuntimeError"

    @staticmethod
    def _open_vault(client_id="crawl-test") -> str:
        from backend.api import get_room

        get_room(client_id)["vault"]["ig_sessionid"] = "test-session"
        return client_id

    @pytest.fixture(autouse=True)
    def _hermetic_guard(self, monkeypatch):
        """SSRF guard'ı DNS'e bakar; hermetik testte ağ YOK sayılır.

        Guard'ın kendisi ayrı testlerin konusudur; burada amaç omurganın kademe
        seçimi ve dürüst alan sözleşmesidir.
        """
        from agent_core.capabilities import adapters_web

        monkeypatch.setattr(adapters_web, "is_safe_url", lambda url: True)

    @pytest.mark.asyncio
    async def test_vault_locked_blocks_all_extractors(self, monkeypatch):
        """Kasa kapalı: omurga hiçbir kademeyi koşturmaz, alan eklenmez."""
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
        monkeypatch.setattr(crawl_enricher, "fetch_readable",
                            lambda *a, **k: pytest.fail("kasa kapalıyken çağrılmamalı"))
        research = await _run_public_web_research(
            "https://x.com/alper",
            _engine("https://blog.example.com/alper"),
            client_id="locked-room")
        assert research["status"] == "ok"
        assert all("crawl" not in m for m in research["results"])

    @pytest.mark.asyncio
    async def test_gate_off_keeps_results_unchanged(self, monkeypatch):
        monkeypatch.delenv("ENABLE_CRAWL4AI", raising=False)
        research = await _run_public_web_research(
            "https://x.com/alper",
            _engine("https://blog.example.com/alper", "https://blog.example.com/alper2"),
            client_id=self._open_vault())
        assert research["status"] == "ok"
        assert all("crawl" not in m for m in research["results"])
        assert "temiz metin" not in research["note"]

    @pytest.mark.asyncio
    async def test_gate_on_attaches_only_available_crawls(self, monkeypatch):
        from agent_core.capabilities import adapters_web

        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
        monkeypatch.setattr(
            adapters_web,
            "_module_available",
            lambda name: name == "crawl4ai.markdown_generation_strategy",
        )

        async def _fake(url, renderer=None, timeout=None):
            if "secret-error" in url:
                return CrawlFetchResult(requested_url=url, available=False,
                                        reason="fetch_error")
            return _res(url=url)

        monkeypatch.setattr(crawl_enricher, "fetch_readable", _fake)
        research = await _run_public_web_research(
            "https://x.com/alper",
            _engine("https://blog.example.com/alper",
                    "https://blog.example.com/secret-error-alper",
                    "https://blog.example.com/alper-üçüncü"),
            client_id=self._open_vault())
        items = research["results"]
        assert len(items) == 3
        # HANGİ kademenin ürettiği kayıtta yazar (görünürlük).
        assert items[0]["crawl"]["provider"] == "extractor.web.crawl4ai"
        assert items[0]["crawl"]["text"] == "içerik"
        assert items[0]["crawl"]["evidence_ids"]
        assert "crawl" not in items[1]  # kalkışıldı, hata verdi → alan EKLENMEZ
        assert "crawl" not in items[2]  # default limit (2) aşıldı → kalkışılmadı
        assert "1 sonuca temiz metin çekildi" in research["note"]

    @pytest.mark.asyncio
    async def test_research_limit_env(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
        monkeypatch.setenv("CRAWL4AI_RESEARCH_LIMIT", "99999")
        assert crawl_enricher.research_limit() == crawl_enricher.MAX_RESEARCH_LIMIT


class TestQuoteGuardCorpus:
    QUOTE = "hava koşulları kış görsünüyor"

    def _report(self):
        return {"reality_findings": [
            {"topic": "tatil", "evidence_quotes": [self.QUOTE]},
        ], "contradictions": []}

    def _input(self, **kw):
        data = {"target_profile": {"bio": "alper'in profili", "posts": []}}
        data.update(kw)
        return data

    def test_public_web_source_makes_real_quote_pass(self):
        report, stats = guard_report(self._report(), self._input(
            public_web_sources=[{"url": "https://blog.example.com/alper",
                                 "text": f"Blog yazısında {self.QUOTE} ifadesi geçiyor."}]))
        assert stats["kept"] == 1
        assert stats["dropped_fake_quote"] == 0
        assert report["reality_findings"][0]["evidence_quotes"] == [self.QUOTE]

    def test_without_public_web_sources_guard_unchanged(self):
        report, stats = guard_report(self._report(), self._input())
        assert stats["kept"] == 0
        assert stats["dropped_fake_quote"] == 1  # mevcut anti-halüsinasyon davranışı

    def test_malformed_sources_ignored(self):
        _, stats = guard_report(self._report(), self._input(
            public_web_sources=["düz string", {"text": "   "}, None, 42]))
        assert stats["kept"] == 0  # yalnız dict + boş olmayan text kabul


class TestEndpoint:
    def test_endpoint_disabled_by_default(self, monkeypatch, vault_open):
        """[E5 sözleşme değişikliği] Motor kapalıyken 200 DEĞİL 400.

        Gerekçe `test_maigret_scanner.py`'deki eş testle aynı; ayrıntılı
        sözleşme `tests/unit/test_experimental_engine_contract.py`'de.
        """
        from fastapi.testclient import TestClient
        from backend.api import app

        monkeypatch.delenv("ENABLE_CRAWL4AI", raising=False)
        with TestClient(app) as client:
            r = client.post("/api/experimental/crawl/fetch",
                            json={"url": "https://example.com/a"})
        assert r.status_code == 400
        body = r.json()
        assert body["error"]["code"] == "MOTOR_UNAVAILABLE"
        assert body["error"]["reason"] == "disabled"
        # Dürüst sözleşme korunur: sağlayıcı ve sebep hâlâ gövdede.
        assert body["reason"] == "disabled"
        assert body["provider"] == "crawl4ai"

    def test_endpoint_ssrf_blocked(self, monkeypatch, vault_open):
        from fastapi.testclient import TestClient
        from backend.api import app

        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
        monkeypatch.setattr(
            "backend.api.check_startup_dependencies",
            lambda: {"status": "ready", "error_code": None, "dependencies": []},
        )
        with TestClient(app) as client:
            r = client.post("/api/experimental/crawl/fetch",
                            json={"url": "http://169.254.169.254/latest/meta-data"})
        assert r.status_code == 200
        assert r.json()["reason"] == "ssrf_blocked"
