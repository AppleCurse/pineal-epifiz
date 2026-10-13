import asyncio
import logging
import os
import re
from typing import Callable, List, Optional
from urllib.parse import urlencode

from httpx import AsyncClient, HTTPStatusError, RequestError, Timeout, TimeoutException
from pydantic import BaseModel, ConfigDict

# [AUDIT 2026-10-08 · E-GÖZ1-3] Sağlayıcı çağrıları merkezi istemci
# (build_secure_client) + SSRF kapısı (safe_get/safe_post) üzerinden çıkar.
from agent_core.utils.security import build_secure_client, safe_get, safe_post

logger = logging.getLogger(__name__)

class SearchResult(BaseModel):
    query: str
    content: str
    source_url: str
    provider: str = "unknown"
    model_config = ConfigDict(extra="forbid")

class SearchOutcome(BaseModel):
    """Provider availability is distinct from a legitimate empty search."""
    results: List[SearchResult] = []
    # OK, PARTIAL, NO_RESULTS, UNAVAILABLE, VAULT_LOCKED
    status: str = "NO_RESULTS"
    error: Optional[str] = None
    available: bool = True
    model_config = ConfigDict(extra="forbid")


#: Kasa kilitliyken dönen dürüst durum. `NO_RESULTS` DEĞİLDİR: "aradık, bir
#: şey bulamadık" ile "kasa kilitli olduğu için HİÇ ARAMADIK" aynı şey değil.
VAULT_LOCKED_STATUS = "VAULT_LOCKED"
VAULT_LOCKED_ERROR = "vault_locked"


class SearchEngine:
    """
    3 Kaynaklı Eşzamanlı Arama ve Doğrulama Motoru (Tavily + SerpAPI + Exa + DuckDuckGo).
    Tüm sağlayıcı çağrıları tek paylaşımlı httpx.AsyncClient üzerinden yapılır
    (connection pooling — bolt async-http-pool çalışması).

    KASA MANDALI (Tüzük Md.4): kasa kilitliyse bu motor DIŞARIYA HİÇ ÇIKMAZ.
    Eskiden yalnız SearXNG omurga yeteneği kapıdan geçiyor, Tavily/SerpAPI/Exa
    ve "ücretsiz" DuckDuckGo yolu kasa kilidine BAKMADAN doğrudan httpx ile
    dışarı çıkıyordu (koddaki eski itiraf: "Ücretsiz DuckDuckGo yolu bugünkü
    davranışını korur"). Bu bir delikti: kasa "kilitli" görünürken arama
    trafiği dışarı sızıyordu. Artık karar, herhangi bir istemci
    oluşturulmadan ÖNCE verilir.
    """
    def __init__(
        self,
        tavily_key: Optional[str] = None,
        serpapi_key: Optional[str] = None,
        exa_key: Optional[str] = None,
        vault_state: Optional[Callable[[], bool]] = None,
    ):
        self.tavily_key = os.getenv("TAVILY_API_KEY") if tavily_key is None else (tavily_key if tavily_key != "" else None)
        self.serpapi_key = os.getenv("SERPAPI_API_KEY") if serpapi_key is None else (serpapi_key if serpapi_key != "" else None)
        self.exa_key = os.getenv("EXA_API_KEY") if exa_key is None else (exa_key if exa_key != "" else None)
        # [FAZ A · A4] Yetenek omurgasının politika durumu. Dışarıdan (api.py)
        # yazılır; yazılmadıysa ücretsiz yedekler (DuckDuckGo/SearXNG) mevcut
        # davranışla aynı şekilde çalışır — kasa kararını bu sınıf uydurmaz.
        self.policy: dict = {}
        # Canlı kasa mandalı (True = kasa AÇIK). Verilmezse `policy` anlık
        # görüntüsüne düşülür; o da yoksa DAR TARAF: kilitli.
        self._vault_state = vault_state

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

    def set_vault_state(self, vault_state: Optional[Callable[[], bool]]) -> None:
        """Canlı kasa mandalını bağlar (``True`` dönerse kasa AÇIK)."""
        self._vault_state = vault_state

    def vault_locked(self) -> bool:
        """Kasa kilitli mi? Kararın TEK yeri.

        Öncelik: (1) canlı mandal, (2) ``set_policy`` anlık görüntüsü,
        (3) hiçbiri yoksa **KİLİTLİ** (dar taraf — ``capabilities/state.py``
        doktrini: belirsizlik asla gevşek tarafa yorumlanmaz).
        """
        if self._vault_state is not None:
            try:
                return not bool(self._vault_state())
            except Exception:
                # Sessiz yutma YOK: mandal okunamıyorsa bu bir arızadır,
                # loglanır ve dar tarafa (kilitli) düşülür.
                logger.error(
                    "KASA MANDALI OKUNAMADI — dar taraf: KİLİTLİ (dış arama reddedilecek)",
                    exc_info=True,
                )
                return True
        if "vault_locked" in self.policy:
            return bool(self.policy["vault_locked"])
        return True

    async def search(self, query: str, num_results: int = 5) -> SearchOutcome:
        # ── KASA MANDALI — HER ŞEYDEN ÖNCE ────────────────────────────────
        # Kasa kilitliyse TEK BİR bayt bile dışarı çıkmaz: httpx istemcisi
        # HİÇ OLUŞTURULMAZ, hiçbir sağlayıcı (ücretli veya "ücretsiz")
        # çağrılmaz. Dürüst cevap: aramadık, çünkü kasa kilitli.
        if self.vault_locked():
            logger.warning(
                "KASA KİLİTLİ: dış arama reddedildi (sağlayıcı isteği oluşturulmadı) query=%r",
                (query or "")[:64],
            )
            return SearchOutcome(
                results=[],
                status=VAULT_LOCKED_STATUS,
                error=VAULT_LOCKED_ERROR,
                available=False,
            )

        # One shared client for all providers in this query (pooling);
        # per-provider availability is reported via SearchOutcome.
        async with build_secure_client(timeout=Timeout(10.0)) as client:
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
                # Tek kaynak: `vault_locked()` (canlı mandal → policy → dar taraf).
                vault_locked=self.vault_locked(),
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
        if isinstance(error, TimeoutException):
            return "TIMEOUT"
        if isinstance(error, HTTPStatusError):
            code = error.response.status_code
            if code in (401, 403):
                return "AUTH_FAILED"
            if code == 429:
                return "RATE_LIMITED"
            return "PROVIDER_ERROR"
        if isinstance(error, RequestError):
            return "NETWORK_ERROR"
        return "PROVIDER_ERROR"

    async def _search_tavily(self, query: str, num_results: int, client: Optional[AsyncClient] = None) -> List[SearchResult]:
        url = "https://api.tavily.com/search"
        from agent_core.utils.security import is_safe_url
        if not is_safe_url(url):
            return []
        payload = {"api_key": self.tavily_key, "query": query, "max_results": num_results}
        try:
            if client is not None:
                res = await safe_post(client, url, json=payload)
            else:
                async with build_secure_client(timeout=Timeout(10.0)) as _client:
                    res = await safe_post(_client, url, json=payload)
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

    async def _search_serpapi(self, query: str, num_results: int, client: Optional[AsyncClient] = None) -> List[SearchResult]:
        url = "https://serpapi.com/search"
        from agent_core.utils.security import is_safe_url
        if not is_safe_url(url):
            return []
        params = {"api_key": self.serpapi_key, "q": query, "num": num_results, "engine": "google"}
        pinned_url = f"{url}?{urlencode(params)}"
        try:
            if client is not None:
                res = await safe_get(client, pinned_url)
            else:
                async with build_secure_client(timeout=Timeout(10.0)) as _client:
                    res = await safe_get(_client, pinned_url)
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

    async def _search_exa(self, query: str, num_results: int, client: Optional[AsyncClient] = None) -> List[SearchResult]:
        url = "https://api.exa.ai/search"
        from agent_core.utils.security import is_safe_url
        if not is_safe_url(url):
            return []
        headers = {"x-api-key": self.exa_key, "Content-Type": "application/json"}
        payload = {"query": query, "numResults": num_results}
        try:
            if client is not None:
                res = await safe_post(client, url, headers=headers, json=payload)
            else:
                async with build_secure_client(timeout=Timeout(10.0)) as _client:
                    res = await safe_post(_client, url, headers=headers, json=payload)
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

    async def _search_duckduckgo(self, query: str, num_results: int, client: Optional[AsyncClient] = None) -> List[SearchResult]:
        url = "https://html.duckduckgo.com/html/"
        from agent_core.utils.security import is_safe_url
        if not is_safe_url(url):
            return []
        data = {"q": query}
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        try:
            if client is not None:
                res = await safe_post(client, url, data=data, headers=headers)
            else:
                async with build_secure_client(timeout=Timeout(10.0)) as _client:
                    res = await safe_post(_client, url, data=data, headers=headers)
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
