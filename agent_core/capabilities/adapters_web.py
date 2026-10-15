"""FAZ A · RETİNA (1) — TEMİZ METİN OMURGASI.

Üç kademeli tek arayüz. Amaç: `QuoteGuard` ve `AutonomousVerifier`'ın
"alıntı kaynakta birebir var mı?" kontrolünün beslendiği metin, her seferinde
aynı temiz kaynaktan gelsin.

    extractor.web.trafilatura  → hafif, hızlı, birincil (Apache-2.0)
    extractor.web.crawl4ai     → güvenli HTTP HTML→Markdown, ikinci (Apache-2.0)
    extractor.web.scrapling    → indirilen HTML için yerel parser, üçüncü (BSD-3-Clause)
    sensor.web.agent_reach     → sosyal/medya (X, Reddit, YouTube, GitHub),
                                 harici CLI, dördüncü ve SON kademe (MIT)

Dürüstlük sözleşmesi (değişmedi):
- Kütüphane yok / kapı kapalı / ağ yok / boş sonuç → `available=False` +
  makine-okunur sebep. **Uydurma metin üretilmez.**
- URL preflight kontrolünden geçer; gerçek HTTP bağlantısı DNS-pinned `safe_get`
  ile yapılır. Trafilatura/Scrapling/Crawl4AI yalnız indirilen HTML'i ayrıştırır;
  kendi ağ istemcileri çağrılmaz.
- Çıktı daima `EvidenceItem`: kaynak bağlantısı, alınma zamanı, çıkarıcı adı.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent_core.capabilities.adapters_osint import _flag, _module_available
from agent_core.capabilities.base import (
    Availability,
    BaseCapability,
    CapabilityContext,
    CapabilityKind,
    CapabilityResult,
    make_evidence,
)
from agent_core.utils.security import UnsafeURLError, is_safe_url

logger = logging.getLogger(__name__)

__all__ = [
    "TrafilaturaCapability",
    "Crawl4AICapability",
    "ScraplingCapability",
    "WEB_EXTRACTION_ORDER",
    "extract_web_text",
]

#: Düşüş sırası (tek kaynak: buradan okunur; ikinci bir sıra listesi YOKTUR).
#: Son kademe `sensor.web.agent_reach`: normal çıkarıcıların alamadığı sosyal
#: platform sayfalarını harici CLI ile okur (kapısı ayrı: ENABLE_AGENT_REACH).
WEB_EXTRACTION_ORDER: tuple[str, ...] = (
    "extractor.web.trafilatura",
    "extractor.web.crawl4ai",
    "extractor.web.scrapling",
    "sensor.web.agent_reach",
)

DEFAULT_MAX_CHARS = 20_000


def _language_scope(text: str, engine: str, url: str) -> dict[str, Any]:
    """[FAZ D · D4] Çıkarılan metnin dili kanıt kapsamına işlenir.

    Tespit deterministiktir (model/ağ yok) ve çıkarıcıyı ASLA bozmaz:
    ölçüm patlasa bile kapsam `language=unknown` + sebeple dürüst kalır.
    Ölçüm, kokpitteki DİL pilinin beslendiği SON kayıttır.
    """
    from agent_core.services.language import detect_language, record_finding

    try:
        finding = detect_language(text)
    except Exception:  # tespit çıkarıcıyı düşürmez; sessizlik de yok
        logger.error("Dil tespiti hatası — kapsam language=unknown (engine=%s)", engine, exc_info=True)
        return {"language": "unknown", "language_reason": "detect_error"}
    record_finding(finding, source_engine=engine, url=url)
    scope: dict[str, Any] = {
        "language": finding.language,
        "language_confidence": finding.confidence,
    }
    if finding.reason:
        scope["language_reason"] = finding.reason
    return scope


def _clamp(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + " …[kırpıldı]"


def _guard(url: str) -> tuple[bool, str]:
    """Preflight guard; the actual connection is revalidated and DNS-pinned."""
    if not url or not isinstance(url, str) or not url.strip():
        return False, "invalid_url"
    if not url.lower().startswith(("http://", "https://")):
        return False, "invalid_scheme"
    if not is_safe_url(url):
        return False, "ssrf_blocked"
    return True, ""


async def _fetch_html(url: str, capability_id: str, timeout_seconds: float):
    """Use the pinned transport; parser libraries must never fetch URLs."""
    from agent_core.capabilities.egress import httpx
    from agent_core.scraper.vault_gate import VaultLockedError
    from agent_core.services.safe_web_fetch import SafeWebFetchError, fetch_safe_html

    try:
        return await fetch_safe_html(url, timeout_seconds=timeout_seconds), None
    except asyncio.CancelledError:
        raise
    except UnsafeURLError:
        reason = "ssrf_blocked"
    except VaultLockedError:
        reason = "vault_locked"
    except SafeWebFetchError as exc:
        reason = exc.code.lower()
    except httpx.TimeoutException:
        reason = "timeout"
    except httpx.HTTPStatusError:
        reason = "http_error"
    except httpx.RequestError as exc:
        return None, CapabilityResult(
            capability_id=capability_id,
            available=False,
            unavailable_reason="network_error",
            error=type(exc).__name__,
        )
    except Exception as exc:
        return None, CapabilityResult(
            capability_id=capability_id,
            available=False,
            unavailable_reason="fetch_error",
            error=type(exc).__name__,
        )
    return None, CapabilityResult(
        capability_id=capability_id, available=False, unavailable_reason=reason
    )


class TrafilaturaCapability(BaseCapability):
    """HTML → temiz metin/markdown (trafilatura · Apache-2.0 · hafif birincil)."""

    id = "extractor.web.trafilatura"
    kind = CapabilityKind.EXTRACTOR
    license = "Apache-2.0"
    gates = frozenset({"vault"})
    timeout_seconds = 30.0
    description = "Sayfadan çöp etiketleri ayıklayıp temiz metin çıkarır (birincil)."

    def availability(self) -> Availability:
        if not _module_available("trafilatura"):
            return Availability.unavailable("dependency_missing:trafilatura")
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        url = (ctx.subject or ctx.params.get("url") or "").strip()
        ok, reason = _guard(url)
        if not ok:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason=reason
            )

        loop = asyncio.get_running_loop()
        started = loop.time()
        try:
            fetched, failure = await asyncio.wait_for(
                _fetch_html(url, self.id, self.timeout_seconds), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="timeout"
            )
        if failure is not None:
            return failure

        def _work(downloaded_html: str) -> tuple[str, str]:
            import trafilatura  # lazy: parser only; network is handled by safe_get

            text = trafilatura.extract(
                downloaded_html,
                output_format="markdown",
                include_comments=False,
                include_tables=True,
                favor_recall=True,
            ) or ""
            title = ""
            try:
                meta = trafilatura.extract_metadata(downloaded_html)
                if meta is not None:
                    title = (getattr(meta, "title", "") or "").strip()
            except Exception:  # metadata opsiyoneldir; metin varsa devam
                logger.debug("metadata çıkarımı başarısız — title boş bırakıldı", exc_info=True)
            return text, title

        try:
            remaining = max(0.001, self.timeout_seconds - (loop.time() - started))
            text, title = await asyncio.wait_for(
                asyncio.to_thread(_work, fetched.html), timeout=remaining
            )
        except asyncio.TimeoutError:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="timeout"
            )
        except Exception as exc:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason="extract_error",
                error=type(exc).__name__,
            )

        if not text.strip():
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="empty_text"
            )

        max_chars = int(ctx.params.get("max_chars") or DEFAULT_MAX_CHARS)
        final_url = fetched.final_url
        lang_scope = _language_scope(text, "trafilatura", final_url)
        item = make_evidence(
            content=_clamp(text, max_chars),
            source_engine="trafilatura",
            epistemic_type="observation",
            provenance_refs=[final_url],
            scope={"kind": "web_text", "title": title, **lang_scope},
            source_metrics={"chars": len(text), "truncated": len(text) > max_chars},
        )
        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=(item,),
            payload={"url": final_url, "title": title, "text": text},
            notes={
                "chars": len(text),
                "title": title,
                "language": lang_scope.get("language"),
            },
        )


class Crawl4AICapability(BaseCapability):
    """Crawl4AI markdown parser — ikinci kademe (Apache-2.0).

    HTML `safe_get` ile indirilir ve Crawl4AI'nin dönüştürücüsüne yerel veri
    olarak verilir. Crawler/browser ağ istemcileri kullanılmaz; JS renderer,
    DNS pinlenebilir bir transport kurulana dek fail-closed kapalıdır.
    """

    id = "extractor.web.crawl4ai"
    kind = CapabilityKind.EXTRACTOR
    license = "Apache-2.0"
    #: [DENETİM 2026-10-14 · B15] Bayrak BEYAN EDİLİR: `availability()` kapıyı
    #: servis üzerinden (`crawl_enricher.is_enabled()`) okuyordu ama omurga
    #: kapı kümesinde yazmıyordu → çekirdek "izinli" derken yetenek "kapalı"
    #: diyordu (çelişki). Artık kernel de aynı bayrağı görür: kapalıysa
    #: `gate_disabled:ENABLE_CRAWL4AI`, açıksa availability kararı verir.
    gates = frozenset({"ENABLE_CRAWL4AI", "vault"})
    timeout_seconds = 60.0
    description = "Güvenli indirilen HTML'i Crawl4AI markdown'a dönüştürür (ikinci kademe)."

    def availability(self) -> Availability:
        try:
            from agent_core.services import crawl_enricher
        except Exception:
            return Availability.unavailable("dependency_missing:crawl4ai")
        if not crawl_enricher.is_enabled():
            return Availability.unavailable("gate_disabled:ENABLE_CRAWL4AI")
        if not _module_available("crawl4ai.markdown_generation_strategy"):
            return Availability.unavailable("dependency_missing:crawl4ai")
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        url = (ctx.subject or ctx.params.get("url") or "").strip()
        ok, reason = _guard(url)
        if not ok:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason=reason
            )

        from agent_core.services import crawl_enricher

        result = await crawl_enricher.fetch_readable(url)
        if not getattr(result, "available", False):
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=f"crawl_unavailable:{getattr(result, 'reason', None)}",
                payload=result,
            )

        markdown = getattr(result, "markdown", "") or ""
        if not markdown.strip():
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="empty_text"
            )

        max_chars = int(ctx.params.get("max_chars") or DEFAULT_MAX_CHARS)
        final_url = getattr(result, "url", "") or url
        lang_scope = _language_scope(markdown, "crawl4ai", final_url)
        item = make_evidence(
            content=_clamp(markdown, max_chars),
            source_engine="crawl4ai",
            epistemic_type="observation",
            provenance_refs=[final_url],
            scope={
                "kind": "web_text",
                "title": getattr(result, "title", "") or "",
                "status_code": getattr(result, "status_code", None),
                **lang_scope,
            },
            source_metrics={"chars": len(markdown)},
        )
        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=(item,),
            payload=result,
            notes={
                "title": getattr(result, "title", ""),
                "language": lang_scope.get("language"),
            },
        )


class ScraplingCapability(BaseCapability):
    """Scrapling Selector — üçüncü kademe, yerel HTML ayrıştırma (BSD-3-Clause).

    SSRF güvenliği için Scrapling'in kendi Fetcher/anti-bot ağ taşıması
    kullanılmaz; sayfa `safe_get` ile indirilir, Selector yalnız HTML'i işler.
    """

    id = "extractor.web.scrapling"
    kind = CapabilityKind.EXTRACTOR
    license = "BSD-3-Clause"
    gates = frozenset({"vault", "ENABLE_SCRAPLING"})
    timeout_seconds = 45.0
    description = "Adaptif kazıma: site değişse de kırılmaz (üçüncü kademe)."

    def availability(self) -> Availability:
        if not _flag("ENABLE_SCRAPLING"):
            return Availability.unavailable("gate_disabled:ENABLE_SCRAPLING")
        if not _module_available("scrapling"):
            return Availability.unavailable("dependency_missing:scrapling")
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        url = (ctx.subject or ctx.params.get("url") or "").strip()
        ok, reason = _guard(url)
        if not ok:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason=reason
            )

        loop = asyncio.get_running_loop()
        started = loop.time()
        try:
            fetched, failure = await asyncio.wait_for(
                _fetch_html(url, self.id, self.timeout_seconds), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="timeout"
            )
        if failure is not None:
            return failure

        def _work(html: str, source_url: str) -> str:
            from scrapling import Selector

            page = Selector(html, url=source_url, adaptive=False)
            getter = getattr(page, "get_all_text", None)
            if callable(getter):
                try:
                    return getter(separator="\n", strip=True) or ""
                except TypeError:
                    return getter() or ""
            return getattr(page, "text", "") or ""

        try:
            remaining = max(0.001, self.timeout_seconds - (loop.time() - started))
            text = await asyncio.wait_for(
                asyncio.to_thread(_work, fetched.html, fetched.final_url), timeout=remaining
            )
        except asyncio.TimeoutError:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="timeout"
            )
        except Exception as exc:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason="extract_error",
                error=type(exc).__name__,
            )

        if not (text or "").strip():
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="empty_text"
            )

        max_chars = int(ctx.params.get("max_chars") or DEFAULT_MAX_CHARS)
        final_url = fetched.final_url
        lang_scope = _language_scope(text, "scrapling", final_url)
        item = make_evidence(
            content=_clamp(text, max_chars),
            source_engine="scrapling",
            epistemic_type="observation",
            provenance_refs=[final_url],
            scope={"kind": "web_text", **lang_scope},
            source_metrics={"chars": len(text)},
        )
        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=(item,),
            notes={"chars": len(text), "language": lang_scope.get("language")},
        )


async def extract_web_text(
    url: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    order: tuple[str, ...] = WEB_EXTRACTION_ORDER,
    registry: Any = None,
    state: Any = None,
) -> CapabilityResult:
    """Tek çağrıda temiz metin: sırayla dener, ilk **kanıt üreten** sonucu döner.

    Hiçbiri üretemezse sonucu uydurmaz: son yeteneğin makine-okunur sebebini ve
    tüm denemelerin izini (`attempts`) döner. Sıra listesi `WEB_EXTRACTION_ORDER`
    içindeki tek kaynaktır.
    """
    from agent_core.capabilities.base import CapabilityContext
    from agent_core.capabilities.runner import CapabilityRunner

    runner = CapabilityRunner(registry=registry)
    attempts: list[dict[str, Any]] = []
    last: CapabilityResult | None = None

    for cap_id in order:
        result = await runner.run(
            cap_id,
            CapabilityContext(subject=url, params={"max_chars": max_chars}),
            state=state,
        )
        attempts.append(
            {
                "capability_id": cap_id,
                "ok": result.ok,
                "reason": result.unavailable_reason,
                "error": result.error,
            }
        )
        if result.ok:
            result.notes = {**result.notes, "attempts": attempts}
            return result
        last = result

    if last is None:  # pragma: no cover - order boşaltılırsa
        return CapabilityResult(
            capability_id="extractor.web",
            available=False,
            unavailable_reason="no_extractor_configured",
        )
    last.notes = {**last.notes, "attempts": attempts}
    return last
