import asyncio
import os
import re
import httpx
from typing import List, Optional
from pydantic import BaseModel, ConfigDict

class SearchResult(BaseModel):
    query: str
    content: str
    source_url: str
    provider: str = "unknown"
    model_config = ConfigDict(extra="forbid")

class SearchOutcome(BaseModel):
    """Provider availability is distinct from a legitimate empty search."""
    results: List[SearchResult] = []
    status: str = "NO_RESULTS"  # OK, PARTIAL, NO_RESULTS, UNAVAILABLE
    error: Optional[str] = None
    available: bool = True
    model_config = ConfigDict(extra="forbid")

class SearchEngine:
    """
    3 Kaynaklı Eşzamanlı Arama ve Doğrulama Motoru (Tavily + SerpAPI + Exa + DuckDuckGo).
    Tüm sağlayıcı çağrıları tek paylaşımlı httpx.AsyncClient üzerinden yapılır
    (connection pooling — bolt async-http-pool çalışması).
    """
    def __init__(self, tavily_key: Optional[str] = None, serpapi_key: Optional[str] = None, exa_key: Optional[str] = None):
        self.tavily_key = os.getenv("TAVILY_API_KEY") if tavily_key is None else (tavily_key if tavily_key != "" else None)
        self.serpapi_key = os.getenv("SERPAPI_API_KEY") if serpapi_key is None else (serpapi_key if serpapi_key != "" else None)
        self.exa_key = os.getenv("EXA_API_KEY") if exa_key is None else (exa_key if exa_key != "" else None)
        # [FAZ A · A4] Yetenek omurgasının politika durumu. Dışarıdan (api.py)
        # yazılır; yazılmadıysa ücretsiz yedekler (DuckDuckGo/SearXNG) mevcut
        # davranışla aynı şekilde çalışır — kasa kararını bu sınıf uydurmaz.
        self.policy: dict = {}

    def set_keys(self, tavily: Optional[str] = None, serpapi: Optional[str] = None, exa: Optional[str] = None):
        if tavily is not None:
            self.tavily_key = tavily if tavily != "" else None
        if serpapi is not None:
            self.serpapi_key = serpapi if serpapi != "" else None
        if exa is not None:
            self.exa_key = exa if exa != "" else None

    def set_policy(self, policy: dict) -> None:
        """Kasa/hız gerçeğini omurgaya taşır (tek kaynak: api.py interlock'u)."""
        self.policy = dict(policy or {})

    async def search(self, query: str, num_results: int = 5) -> SearchOutcome:
        # One shared client for all providers in this query (pooling);
        # per-provider availability is reported via SearchOutcome.
        async with httpx.AsyncClient(timeout=10.0) as client:
            tasks = []
            if self.tavily_key:
                tasks.append(self._search_tavily(query, num_results, client=client))
            if self.serpapi_key:
                tasks.append(self._search_serpapi(query, num_results, client=client))
            if self.exa_key:
                tasks.append(self._search_exa(query, num_results, client=client))

            # Eğer hiç anahtar yoksa ücretsiz yedekler devreye girer:
            # [FAZ A · A4] SearXNG (kendi sunucun, anahtarsız, omurgadan) +
            # mevcut DuckDuckGo yolu. SearXNG kapalıysa davranış ESKİSİ GİBİ.
            if not tasks:
                if self._searxng_enabled():
                    tasks.append(self._search_searxng(query, num_results))
                tasks.append(self._search_duckduckgo(query, num_results, client=client))

            results_lists = await asyncio.gather(*tasks, return_exceptions=True)

        merged: List[SearchResult] = []
        errors = []
        seen_urls = set()
        for res in results_lists:
            if isinstance(res, list):
                for item in res:
                    if item.source_url not in seen_urls:
                        seen_urls.add(item.source_url)
                        merged.append(item)
            elif isinstance(res, BaseException):
                errors.append(self._error_code(res))

        if merged:
            return SearchOutcome(
                results=merged[:num_results * 2],
                status="PARTIAL" if errors else "OK",
                error=",".join(sorted(set(errors))) or None,
                available=True,
            )
        if errors:
            return SearchOutcome(results=[], status="UNAVAILABLE", error=",".join(sorted(set(errors))), available=False)
        return SearchOutcome(results=[], status="NO_RESULTS", available=True)

    def _searxng_enabled(self) -> bool:
        """SearXNG yedeği açık mı? (kapı: ENABLE_SEARXNG + SEARXNG_BASE_URL)."""
        return os.getenv("ENABLE_SEARXNG", "false").lower() == "true" and bool(
            os.getenv("SEARXNG_BASE_URL", "").strip()
        )

    async def _search_searxng(self, query: str, num_results: int) -> List[SearchResult]:
        """[FAZ A · A4] Anahtarsız metasearch — capability omurgasından koşar.

        Ayrı servis (AGPL-3.0): kod gömülmez, yalnız HTTP. Servis yoksa/ulaşılamazsa
        boş liste döner (görev hatası değil, sessiz yedek) — asıl sözleşme
        korunur: sonuç yoksa `NO_RESULTS`, bulgu UYDURULMAZ.
        """
        from agent_core.capabilities import (
            CapabilityContext,
            bootstrap,
            run_capability,
        )
        from agent_core.capabilities.state import policy_state

        bootstrap()
        result = await run_capability(
            "sensor.search.searxng",
            CapabilityContext(subject=query, params={"limit": num_results}),
            state=policy_state(
                vault_locked=bool(self.policy.get("vault_locked", False)),
                rate_ok=self.policy.get("rate_ok"),
            ),
        )
        if not result.ok:
            return []
        rows: List[SearchResult] = []
        for item in result.items:
            refs = list(getattr(item, "provenance_refs", []) or [])
            if not refs:
                continue
            rows.append(
                SearchResult(
                    query=query,
                    content=item.content,
                    source_url=refs[0],
                    provider="searxng",
                )
            )
        return rows

    @staticmethod
    def _error_code(error: BaseException) -> str:
        if isinstance(error, httpx.TimeoutException):
            return "TIMEOUT"
        if isinstance(error, httpx.HTTPStatusError):
            code = error.response.status_code
            if code in (401, 403):
                return "AUTH_FAILED"
            if code == 429:
                return "RATE_LIMITED"
            return "PROVIDER_ERROR"
        if isinstance(error, httpx.RequestError):
            return "NETWORK_ERROR"
        return "PROVIDER_ERROR"

    async def _search_tavily(self, query: str, num_results: int, client: Optional[httpx.AsyncClient] = None) -> List[SearchResult]:
        url = "https://api.tavily.com/search"
        from agent_core.utils.security import is_safe_url
        if not is_safe_url(url):
            return []
        payload = {"api_key": self.tavily_key, "query": query, "max_results": num_results}
        try:
            if client is not None:
                res = await client.post(url, json=payload)
            else:
                async with httpx.AsyncClient(timeout=10.0) as _client:
                    res = await _client.post(url, json=payload)
                res.raise_for_status()
            if res.status_code == 200:
                data = res.json()
                return [
                    SearchResult(query=query, content=r.get("content", ""), source_url=r.get("url", ""), provider="tavily")
                    for r in data.get("results", [])
                ]
            res.raise_for_status()
        except Exception:
            raise
        return []

    async def _search_serpapi(self, query: str, num_results: int, client: Optional[httpx.AsyncClient] = None) -> List[SearchResult]:
        url = "https://serpapi.com/search"
        from agent_core.utils.security import is_safe_url
        if not is_safe_url(url):
            return []
        params = {"api_key": self.serpapi_key, "q": query, "num": num_results, "engine": "google"}
        try:
            if client is not None:
                res = await client.get(url, params=params)
            else:
                async with httpx.AsyncClient(timeout=10.0) as _client:
                    res = await _client.get(url, params=params)
                res.raise_for_status()
            if res.status_code == 200:
                data = res.json()
                return [
                    SearchResult(query=query, content=r.get("snippet", ""), source_url=r.get("link", ""), provider="serpapi")
                    for r in data.get("organic_results", [])
                ]
            res.raise_for_status()
        except Exception:
            raise
        return []

    async def _search_exa(self, query: str, num_results: int, client: Optional[httpx.AsyncClient] = None) -> List[SearchResult]:
        url = "https://api.exa.ai/search"
        from agent_core.utils.security import is_safe_url
        if not is_safe_url(url):
            return []
        headers = {"x-api-key": self.exa_key, "Content-Type": "application/json"}
        payload = {"query": query, "numResults": num_results}
        try:
            if client is not None:
                res = await client.post(url, headers=headers, json=payload)
            else:
                async with httpx.AsyncClient(timeout=10.0) as _client:
                    res = await _client.post(url, headers=headers, json=payload)
                res.raise_for_status()
            if res.status_code == 200:
                data = res.json()
                return [
                    SearchResult(query=query, content=r.get("text", r.get("title", "")), source_url=r.get("url", ""), provider="exa")
                    for r in data.get("results", [])
                ]
            res.raise_for_status()
        except Exception:
            raise
        return []

    async def _search_duckduckgo(self, query: str, num_results: int, client: Optional[httpx.AsyncClient] = None) -> List[SearchResult]:
        url = "https://html.duckduckgo.com/html/"
        from agent_core.utils.security import is_safe_url
        if not is_safe_url(url):
            return []
        data = {"q": query}
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        try:
            if client is not None:
                res = await client.post(url, data=data, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=10.0) as _client:
                    res = await _client.post(url, data=data, headers=headers)
                res.raise_for_status()
            if res.status_code == 200:
                html = res.text
                results = []
                links = re.findall(r'<a class="result__url" href="([^"]+)">([^<]+)</a>', html)
                snippets = re.findall(r'<a class="result__snippet[^>]*>([^<]+)</a>', html)
                for i, (href, raw_url) in enumerate(links[:num_results]):
                    snippet = snippets[i] if i < len(snippets) else query
                    results.append(SearchResult(query=query, content=snippet.strip(), source_url=raw_url.strip(), provider="duckduckgo"))
                return results
            res.raise_for_status()
        except Exception:
            raise
        return []
