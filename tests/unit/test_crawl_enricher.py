"""Crawl4AI entegrasyon sözleşme testleri (FAZ 4).

İlkeler:
- Kapı (ENABLE_CRAWL4AI) kapalıyken davranış ESKİSİ GİBİ (pipeline değişmez).
- Kütüphane/tarayıcı/ağ/timeout hatalarında dürüst `available:false` + sebep;
  ASLA uydurma içerik yok.
- renderer=http (default) tarayıcı binary'si gerektirmez; renderer=browser
  binary yoksa dürüst `browser_missing`.
- Public-web araştırma zenginleştirmesi: yalnız available=True sonuçlar
  `crawl` alanına girer; kapalıyken matched sonuçlar birebir aynı kalır.
- quote_guard korpusu: yalnız gerçek çekilmiş metin (`public_web_sources`)
  eklenir; alan yoksa korpus birebir aynı kalır.
"""
import asyncio

import pytest

from agent_core.services import crawl_enricher
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


class TestGate:
    @pytest.mark.asyncio
    async def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("ENABLE_CRAWL4AI", raising=False)
        res = await fetch_readable("https://example.com/a")
        assert res.available is False
        assert res.reason == "disabled"
        assert res.markdown == ""

    @pytest.mark.asyncio
    async def test_gate_on_runs_crawler(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
        called = {}

        async def _fake(url, renderer, timeout):
            called["ran"] = (url, renderer)
            return (True, url, "Başlık", "# İçerik", 200, "")

        monkeypatch.setattr(crawl_enricher, "_crawl_once", _fake)
        res = await fetch_readable("https://example.com/a")
        assert called["ran"][0] == "https://example.com/a"
        assert called["ran"][1] == "http"  # default renderer tarayıcı istemez
        assert res.available is True
        assert res.title == "Başlık"


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
        res = await fetch_readable("http://127.0.0.1:8000/secret")
        assert res.available is False
        assert res.reason == "ssrf_blocked"

    @pytest.mark.asyncio
    async def test_library_missing(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")

        async def _boom(url, renderer, timeout):
            raise ModuleNotFoundError("crawl4ai yok", name="crawl4ai")

        monkeypatch.setattr(crawl_enricher, "_crawl_once", _boom)
        res = await fetch_readable("https://example.com/a")
        assert res.available is False
        assert res.reason == "library_missing"

    @pytest.mark.asyncio
    async def test_installed_library_import_failure_is_not_called_missing(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")

        async def _boom(url, renderer, timeout):
            raise ImportError("installed crawl4ai runtime is broken")

        monkeypatch.setattr(crawl_enricher, "_crawl_once", _boom)
        res = await fetch_readable("https://example.com/a")
        assert res.available is False
        assert res.reason == "dependency_broken"
        assert res.error_detail.startswith("ImportError:")

    @pytest.mark.asyncio
    async def test_browser_missing_classified(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
        monkeypatch.setenv("CRAWL4AI_RENDERER", "browser")

        async def _boom(url, renderer, timeout):
            raise RuntimeError(
                "Executable doesn't exist at .../chromium. Please run playwright install")

        monkeypatch.setattr(crawl_enricher, "_crawl_once", _boom)
        res = await fetch_readable("https://example.com/a")
        assert res.available is False
        assert res.reason == "browser_missing"
        assert res.error_detail  # insan-notu mevcut ama makine sebep ayrı

    @pytest.mark.asyncio
    async def test_generic_error_is_fetch_error(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")

        async def _boom(url, renderer, timeout):
            raise ConnectionError("bağlantı reddedildi (dürüst ağ yokluğu)")

        monkeypatch.setattr(crawl_enricher, "_crawl_once", _boom)
        res = await fetch_readable("https://example.com/a")
        assert res.reason == "fetch_error"
        assert res.available is False

    @pytest.mark.asyncio
    async def test_timeout_is_honest(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")

        async def _slow(url, renderer, timeout):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(crawl_enricher, "_crawl_once", _slow)
        res = await fetch_readable("https://example.com/a")
        assert res.reason == "timeout"

    @pytest.mark.asyncio
    async def test_failed_result_classified_not_fabricated(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")

        async def _fail(url, renderer, timeout):
            return (False, url, "", "", 403, "Access denied")

        monkeypatch.setattr(crawl_enricher, "_crawl_once", _fail)
        res = await fetch_readable("https://example.com/a")
        assert res.available is False
        assert res.reason == "fetch_error"
        assert res.markdown == ""
        assert res.error_detail == "Access denied"

    def test_classify_error_markers(self):
        assert _classify_error("Executable doesn't exist at /x") == "browser_missing"
        assert _classify_error("run `playwright install`") == "browser_missing"
        assert _classify_error("connection refused") == "fetch_error"
        assert _classify_error("") == "fetch_error"

    @pytest.mark.asyncio
    async def test_markdown_capped_by_env(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
        monkeypatch.setenv("CRAWL4AI_MAX_CHARS", "100")

        async def _fake(url, renderer, timeout):
            return (True, url, "T", "x" * 30000, 200, "")

        monkeypatch.setattr(crawl_enricher, "_crawl_once", _fake)
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
    """[FAZ A] Zenginleştirme artık TEK crawl4ai çağrısı değil, üç kademeli
    temiz-metin omurgası: trafilatura → crawl4ai → scrapling
    (`capabilities.extract_web_text`). Sözleşme AYNEN korunur: çekilemeyen
    sonuca `crawl` alanı EKLENMEZ (dürüst boş), uydurma metin YOK.

    Kasa kapalıyken hiçbir kademe koşmaz: bu yüzden testler kendi odasının
    kasanı açar (`client_id`), interlock gerçeği tahmin edilmez.
    """

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
        monkeypatch.setenv("ENABLE_CRAWL4AI", "true")

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
