"""Çok kaynaklı arama ve doğrulama motoru (Tavily + SerpAPI + Exa + DuckDuckGo/SearXNG).

``search`` çağrıları paralel yürütülür ve ``SearchOutcome`` döner: kaynak
KULLANILAMAZLIĞI, meşru BOŞ sonuçtan açıkça ayrılır (boş liste "sonuç yok"
diye yalan söylemez).

Kasa mandalı tek gerçek kaynaktan (``set_vault_state``) okunur: kasa kilitliyken
dış arama yapılmaz (``VAULT_LOCKED``). Anahtar yoksa ilgili sağlayıcı sessizce
atlanmaz, gerekçesi raporlanır.

Tüketici: ``agent_core/agents/*`` (autonomous_verifier, osint), task_executor.
Test: ``tests/unit/test_alternative_web_research.py``.
"""

import asyncio
import logging
import os
import re
from html import unescape
from urllib.parse import parse_qs, unquote, urljoin, urlsplit
from agent_core.capabilities.egress import open_client, httpx
from typing import Any, Callable, List, Optional
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

class SearchResult(BaseModel):
    query: str
    content: str
    source_url: str
    provider: str = "unknown"
    model_config = ConfigDict(extra="forbid")

class SearchOutcome(BaseModel):
    """Provider availability is distinct from a legitimate empty search."""
    results: List[SearchResult] = Field(default_factory=list)
    # OK, PARTIAL, NO_RESULTS, UNAVAILABLE, VAULT_LOCKED
    status: str = "NO_RESULTS"
    error: Optional[str] = None
    available: bool = True
    model_config = ConfigDict(extra="forbid")


#: Kasa kilitliyken dönen dürüst durum. `NO_RESULTS` DEĞİLDİR: "aradık, bir
#: şey bulamadık" ile "kasa kilitli olduğu için HİÇ ARAMADIK" aynı şey değil.
VAULT_LOCKED_STATUS = "VAULT_LOCKED"
VAULT_LOCKED_ERROR = "vault_locked"


class SearchProviderError(RuntimeError):
    """A provider failed; this is distinct from a legitimate empty result."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


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

    @staticmethod
    def _normalize_result_url(value: Any) -> Optional[str]:
        """Return a real HTTP(S) URL, decoding DuckDuckGo redirect links."""
        if not isinstance(value, str) or not value.strip():
            return None
        candidate = unescape(value.strip())
        if candidate.startswith("//"):
            candidate = "https:" + candidate
        elif candidate.startswith("/"):
            candidate = urljoin("https://duckduckgo.com", candidate)
        try:
            parsed = urlsplit(candidate)
        except ValueError:
            return None
        if parsed.scheme.lower() not in {"http", "https"}:
            if parsed.scheme:
                return None
            candidate = "https://" + candidate.lstrip("/")
            try:
                parsed = urlsplit(candidate)
            except ValueError:
                return None
        if (
            parsed.hostname in {"duckduckgo.com", "www.duckduckgo.com"}
            and parsed.path.rstrip("/") == "/l"
        ):
            targets = parse_qs(parsed.query).get("uddg", [])
            if targets:
                candidate = unquote(targets[0])
                try:
                    parsed = urlsplit(candidate)
                except ValueError:
                    return None
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
        return candidate

    @classmethod
    def _make_result(
        cls,
        query: str,
        content: Any,
        source_url: Any,
        provider: str,
    ) -> Optional[SearchResult]:
        if not isinstance(content, str) or not content.strip():
            return None
        normalized_url = cls._normalize_result_url(source_url)
        if normalized_url is None:
            return None
        return SearchResult(
            query=query,
            content=content.strip(),
            source_url=normalized_url,
            provider=provider,
        )

    async def search(self, query: str, num_results: int = 5) -> SearchOutcome:
        # ── KASA MANDALI — HER ŞEYDEN ÖNCE ────────────────────────────────
        # Kasa kilitliyse TEK BİR bayt bile dışarı çıkmaz: httpx istemcisi
        # HİÇ OLUŞTURULMAZ, hiçbir sağlayıcı (ücretli veya "ücretsiz")
        # çağrılmaz. Dürüst cevap: aramadık, çünkü kasa kilitli.
        if self.vault_locked():
            logger.warning(
                "KASA KİLİTLİ: dış arama reddedildi (sağlayıcı isteği oluşturulmadı; sorgu kaydı tutulmaz)"
            )
            return SearchOutcome(
                results=[],
                status=VAULT_LOCKED_STATUS,
                error=VAULT_LOCKED_ERROR,
                available=False,
            )

        if not isinstance(query, str) or not query.strip() or len(query) > 1000:
            return SearchOutcome(
                results=[], status="UNAVAILABLE", error="INVALID_QUERY", available=False
            )
        if (
            not isinstance(num_results, int)
            or isinstance(num_results, bool)
            or num_results < 1
        ):
            return SearchOutcome(
                results=[], status="UNAVAILABLE", error="INVALID_RESULT_LIMIT", available=False
            )
        query = query.strip()
        num_results = min(num_results, 10)

        # One shared client for all HTTP providers in this query (pooling).
        # Paid-provider errors trigger a second free-provider phase only when
        # none of the configured paid providers returned results. A successful
        # empty response remains NO_RESULTS and does not cause silent escalation.
        try:
            async with open_client(
                purpose="search",
                timeout=10.0,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                paid_tasks = []
                if self.tavily_key:
                    paid_tasks.append(self._search_tavily(query, num_results, client=client))
                if self.serpapi_key:
                    paid_tasks.append(self._search_serpapi(query, num_results, client=client))
                if self.exa_key:
                    paid_tasks.append(self._search_exa(query, num_results, client=client))

                errors: List[str] = []
                if paid_tasks:
                    primary_responses = await asyncio.gather(*paid_tasks, return_exceptions=True)
                    merged, errors = self._collect_provider_results(primary_responses)
                    if not merged and errors:
                        backup_tasks = self._free_search_tasks(query, num_results, client)
                        backup_responses = await asyncio.gather(*backup_tasks, return_exceptions=True)
                        backup_results, backup_errors = self._collect_provider_results(backup_responses)
                        merged.extend(backup_results)
                        errors.extend(backup_errors)
                else:
                    fallback_tasks = self._free_search_tasks(query, num_results, client)
                    fallback_responses = await asyncio.gather(*fallback_tasks, return_exceptions=True)
                    merged, errors = self._collect_provider_results(fallback_responses)
        except Exception as exc:
            from agent_core.scraper.vault_gate import VaultLockedError

            if not isinstance(exc, VaultLockedError):
                raise
            logger.warning("KASA KİLİTLENDİ: arama başlamadan egress reddedildi")
            return SearchOutcome(
                results=[], status=VAULT_LOCKED_STATUS, error=VAULT_LOCKED_ERROR, available=False
            )

        unique_errors = ",".join(sorted(set(errors))) or None
        if merged:
            return SearchOutcome(
                results=merged[:num_results * 2],
                status="PARTIAL" if unique_errors else "OK",
                error=unique_errors,
                available=True,
            )
        if unique_errors:
            return SearchOutcome(
                results=[], status="UNAVAILABLE", error=unique_errors, available=False
            )
        return SearchOutcome(results=[], status="NO_RESULTS", available=True)

    def _free_search_tasks(self, query: str, num_results: int, client: httpx.AsyncClient):
        """Create the explicitly configured keyless provider fallback phase."""
        tasks = []
        if self._searxng_enabled():
            tasks.append(self._search_searxng(query, num_results))
        tasks.append(self._search_duckduckgo(query, num_results, client=client))
        return tasks

    def _collect_provider_results(self, responses: list[Any]) -> tuple[List[SearchResult], List[str]]:
        merged: List[SearchResult] = []
        errors: List[str] = []
        seen_urls = set()
        for response in responses:
            if isinstance(response, asyncio.CancelledError):
                raise response
            if isinstance(response, list):
                for item in response:
                    if not isinstance(item, SearchResult):
                        errors.append("INVALID_PROVIDER_RESULT")
                        continue
                    normalized_url = self._normalize_result_url(item.source_url)
                    content = item.content.strip()
                    if normalized_url is None or not content:
                        errors.append("INVALID_PROVIDER_RESULT")
                        continue
                    if normalized_url not in seen_urls:
                        seen_urls.add(normalized_url)
                        if normalized_url != item.source_url or content != item.content:
                            item = item.model_copy(
                                update={"source_url": normalized_url, "content": content}
                            )
                        merged.append(item)
            elif isinstance(response, BaseException):
                if isinstance(response, Exception):
                    errors.append(self._error_code(response))
                else:
                    raise response
            else:
                errors.append("INVALID_PROVIDER_RESPONSE")
        return merged, errors

    def _searxng_enabled(self) -> bool:
        """SearXNG yedeği açık mı? (kapı: ENABLE_SEARXNG + SEARXNG_BASE_URL)."""
        return os.getenv("ENABLE_SEARXNG", "false").lower() == "true" and bool(
            os.getenv("SEARXNG_BASE_URL", "").strip()
        )

    async def _search_searxng(self, query: str, num_results: int) -> List[SearchResult]:
        """[FAZ A · A4] Anahtarsız metasearch — capability omurgasından koşar.

        Ayrı servis (AGPL-3.0): kod gömülmez, yalnız HTTP. Gerçek bir boş yanıt
        boş liste döner; servis/kapı hatası ise sınıflandırılmış hata olarak
        yükseltilir ki üst katman onu NO_RESULTS sanmasın.
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
        if (
            not getattr(result, "available", False)
            or getattr(result, "error", None)
            or getattr(result, "unavailable_reason", None)
        ):
            reason = (
                getattr(result, "unavailable_reason", None)
                or getattr(result, "error", None)
                or "unavailable"
            )
            code = re.sub(r"[^A-Z0-9]+", "_", str(reason).upper()).strip("_")
            raise SearchProviderError(f"SEARXNG_{code or 'UNAVAILABLE'}")
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
        if isinstance(error, SearchProviderError):
            return error.code
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
            raise SearchProviderError("TAVILY_UNSAFE_URL")
        payload = {"api_key": self.tavily_key, "query": query, "max_results": num_results}
        try:
            if client is not None:
                res = await client.post(url, json=payload)
            else:
                async with open_client(
                    purpose="search",
                    target=url,
                    timeout=10.0,
                    trust_env=False,
                    follow_redirects=False,
                ) as _client:
                    res = await _client.post(url, json=payload)
                res.raise_for_status()
            if res.status_code == 200:
                try:
                    data = res.json()
                except (ValueError, UnicodeDecodeError) as exc:
                    raise SearchProviderError("TAVILY_INVALID_JSON") from exc
                if not isinstance(data, dict) or not isinstance(data.get("results"), list):
                    raise SearchProviderError("TAVILY_INVALID_RESPONSE")
                rows = data["results"]
                results = [
                    result
                    for row in rows
                    if isinstance(row, dict)
                    for result in [
                        self._make_result(query, row.get("content"), row.get("url"), "tavily")
                    ]
                    if result is not None
                ]
                if rows and not results:
                    raise SearchProviderError("TAVILY_INVALID_RESULTS")
                return results
            res.raise_for_status()
        except Exception:
            raise
        return []

    async def _search_serpapi(self, query: str, num_results: int, client: Optional[httpx.AsyncClient] = None) -> List[SearchResult]:
        url = "https://serpapi.com/search"
        from agent_core.utils.security import is_safe_url
        if not is_safe_url(url):
            raise SearchProviderError("SERPAPI_UNSAFE_URL")
        params = {"api_key": self.serpapi_key, "q": query, "num": num_results, "engine": "google"}
        try:
            if client is not None:
                res = await client.get(url, params=params)
            else:
                async with open_client(
                    purpose="search",
                    target=url,
                    timeout=10.0,
                    trust_env=False,
                    follow_redirects=False,
                ) as _client:
                    res = await _client.get(url, params=params)
                res.raise_for_status()
            if res.status_code == 200:
                try:
                    data = res.json()
                except (ValueError, UnicodeDecodeError) as exc:
                    raise SearchProviderError("SERPAPI_INVALID_JSON") from exc
                if not isinstance(data, dict):
                    raise SearchProviderError("SERPAPI_INVALID_RESPONSE")
                rows = data.get("organic_results", [])
                if not isinstance(rows, list):
                    raise SearchProviderError("SERPAPI_INVALID_RESPONSE")
                results = [
                    result
                    for row in rows
                    if isinstance(row, dict)
                    for result in [
                        self._make_result(query, row.get("snippet"), row.get("link"), "serpapi")
                    ]
                    if result is not None
                ]
                if rows and not results:
                    raise SearchProviderError("SERPAPI_INVALID_RESULTS")
                return results
            res.raise_for_status()
        except Exception:
            raise
        return []

    async def _search_exa(self, query: str, num_results: int, client: Optional[httpx.AsyncClient] = None) -> List[SearchResult]:
        url = "https://api.exa.ai/search"
        from agent_core.utils.security import is_safe_url
        if not is_safe_url(url):
            raise SearchProviderError("EXA_UNSAFE_URL")
        headers = {"x-api-key": self.exa_key, "Content-Type": "application/json"}
        payload = {"query": query, "numResults": num_results}
        try:
            if client is not None:
                res = await client.post(url, headers=headers, json=payload)
            else:
                async with open_client(
                    purpose="search",
                    target=url,
                    timeout=10.0,
                    trust_env=False,
                    follow_redirects=False,
                ) as _client:
                    res = await _client.post(url, headers=headers, json=payload)
                res.raise_for_status()
            if res.status_code == 200:
                try:
                    data = res.json()
                except (ValueError, UnicodeDecodeError) as exc:
                    raise SearchProviderError("EXA_INVALID_JSON") from exc
                if not isinstance(data, dict) or not isinstance(data.get("results"), list):
                    raise SearchProviderError("EXA_INVALID_RESPONSE")
                rows = data["results"]
                results = [
                    result
                    for row in rows
                    if isinstance(row, dict)
                    for result in [
                        self._make_result(
                            query,
                            row.get("text") or row.get("title"),
                            row.get("url"),
                            "exa",
                        )
                    ]
                    if result is not None
                ]
                if rows and not results:
                    raise SearchProviderError("EXA_INVALID_RESULTS")
                return results
            res.raise_for_status()
        except Exception:
            raise
        return []

    async def _search_duckduckgo(self, query: str, num_results: int, client: Optional[httpx.AsyncClient] = None) -> List[SearchResult]:
        url = "https://html.duckduckgo.com/html/"
        from agent_core.utils.security import is_safe_url
        if not is_safe_url(url):
            raise SearchProviderError("DUCKDUCKGO_UNSAFE_URL")
        data = {"q": query}
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        try:
            if client is not None:
                res = await client.post(url, data=data, headers=headers)
            else:
                async with open_client(
                    purpose="search",
                    target=url,
                    timeout=10.0,
                    trust_env=False,
                    follow_redirects=False,
                ) as _client:
                    res = await _client.post(url, data=data, headers=headers)
                res.raise_for_status()
            if res.status_code == 200:
                html = res.text
                link_pattern = re.compile(
                    r'<a\b(?=[^>]*\bclass=["\'][^"\']*result__url[^"\']*["\'])'
                    r'(?=[^>]*\bhref=["\']([^"\']+)["\'])[^>]*>(.*?)</a>',
                    re.IGNORECASE | re.DOTALL,
                )
                links = [(match.group(1), match.group(2)) for match in link_pattern.finditer(html)]
                snippet_pattern = re.compile(
                    r'<a\b[^>]*class=["\'][^"\']*result__snippet[^"\']*["\'][^>]*>(.*?)</a>',
                    re.IGNORECASE | re.DOTALL,
                )
                title_pattern = re.compile(
                    r'<a\b[^>]*class=["\'][^"\']*result__a[^"\']*["\'][^>]*>(.*?)</a>',
                    re.IGNORECASE | re.DOTALL,
                )

                def clean_markup(value: str) -> str:
                    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()

                snippets = [clean_markup(value) for value in snippet_pattern.findall(html)]
                titles = [clean_markup(value) for value in title_pattern.findall(html)]
                results = []
                for index, (href, _display_url) in enumerate(links[:num_results]):
                    content = (
                        snippets[index] if index < len(snippets) and snippets[index]
                        else titles[index] if index < len(titles) else ""
                    )
                    result = self._make_result(query, content, href, "duckduckgo")
                    if result is not None:
                        results.append(result)
                if results:
                    return results
                lowered = html.lower()
                challenge_markers = (
                    "captcha", "anomaly detected", "bots use duckduckgo", "prove you're human",
                )
                code = (
                    "DUCKDUCKGO_CHALLENGE"
                    if any(marker in lowered for marker in challenge_markers)
                    else "DUCKDUCKGO_UNPARSEABLE_RESPONSE"
                )
                raise SearchProviderError(code)
            res.raise_for_status()
        except Exception:
            raise
        return []
