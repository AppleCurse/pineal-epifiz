"""FAZ A · RETİNA (1) — TEMİZ METİN OMURGASI.

Üç kademeli tek arayüz. Amaç: `QuoteGuard` ve `AutonomousVerifier`'ın
"alıntı kaynakta birebir var mı?" kontrolünün beslendiği metin, her seferinde
aynı temiz kaynaktan gelsin.

    extractor.web.trafilatura  → hafif, hızlı, birincil (Apache-2.0)
    extractor.web.crawl4ai     → JS'li/ağır sayfa, ikinci (Apache-2.0, mevcut)
    extractor.web.scrapling    → adaptif, anti-bot, üçüncü (BSD-3-Clause)
    sensor.web.agent_reach     → sosyal/medya (X, Reddit, YouTube, GitHub),
                                 harici CLI, dördüncü ve SON kademe (MIT)

Dürüstlük sözleşmesi (değişmedi):
- Kütüphane yok / kapı kapalı / ağ yok / boş sonuç → `available=False` +
  makine-okunur sebep. **Uydurma metin üretilmez.**
- Her URL `agent_core.utils.security.is_safe_url` SSRF guard'ından geçer.
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
from agent_core.utils.security import is_safe_url

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
    except Exception as exc:  # tespit çıkarıcıyı düşürmez; sessizlik de yok
        # [AUDIT 2026-10-08 · E-GÖZ1-4] Hata yutulmuyor: iz (log) bırakılıyor,
        # gövde yine dürüst kalır (uydurma dil yok).
        logger.error("dil tespiti başarısız (detect_error): %s", exc, exc_info=True)
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
    """SSRF guard + temel doğrulama. (güvenli mi, sebep)"""
    if not url or not isinstance(url, str) or not url.strip():
        return False, "invalid_url"
    if not url.lower().startswith(("http://", "https://")):
        return False, "invalid_scheme"
    if not is_safe_url(url):
        return False, "ssrf_blocked"
    return True, ""


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

        def _work() -> tuple[str, str]:
            import trafilatura  # lazy: paket yoksa availability zaten ret döner

            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return "", ""
            text = trafilatura.extract(
                downloaded,
                output_format="markdown",
                include_comments=False,
                include_tables=True,
                favor_recall=True,
            ) or ""
            title = ""
            try:
                meta = trafilatura.extract_metadata(downloaded)
                if meta is not None:
                    title = (getattr(meta, "title", "") or "").strip()
            except Exception as exc:  # metadata opsiyoneldir; metin varsa devam
                # [AUDIT 2026-10-08 · E-GÖZ1-7] Başlıksız gelişin nedeni logdan
                # teşhis edilebilir; sessiz title="" yok.
                logger.debug("Metadata çıkarımı başarısız, başlık boş bırakıldı: %s", exc, exc_info=True)
                title = ""
            return text, title

        try:
            text, title = await asyncio.wait_for(
                asyncio.to_thread(_work), timeout=self.timeout_seconds
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
        lang_scope = _language_scope(text, "trafilatura", url)
        item = make_evidence(
            content=_clamp(text, max_chars),
            source_engine="trafilatura",
            epistemic_type="observation",
            provenance_refs=[url],
            scope={"kind": "web_text", "title": title, **lang_scope},
            source_metrics={"chars": len(text), "truncated": len(text) > max_chars},
        )
        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=(item,),
            payload={"url": url, "title": title, "text": text},
            notes={
                "chars": len(text),
                "title": title,
                "language": lang_scope.get("language"),
            },
        )


class Crawl4AICapability(BaseCapability):
    """crawl4ai sarmalayıcı — ikinci kademe (Apache-2.0, projede mevcut).

    Mevcut `services/crawl_enricher.py` kodunu DEĞİŞTİRMEZ; onu capability
    sözleşmesine bağlar. Böylece crawl4ai artık yalnız `api.py` içindeki tek
    çağrı noktasında değil, bütün ajanlar tarafından aynı arayüzle kullanılır.
    """

    id = "extractor.web.crawl4ai"
    kind = CapabilityKind.EXTRACTOR
    license = "Apache-2.0"
    gates = frozenset({"vault"})
    timeout_seconds = 60.0
    description = "JS'li/ağır sayfalar için tarayıcılı kazıma (ikinci kademe)."

    def availability(self) -> Availability:
        try:
            from agent_core.services import crawl_enricher
        except Exception:
            return Availability.unavailable("dependency_missing:crawl4ai")
        if not crawl_enricher.is_enabled():
            return Availability.unavailable("gate_disabled:ENABLE_CRAWL4AI")
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
    """Scrapling — üçüncü kademe, adaptif kazıma (BSD-3-Clause).

    Site yapısı değişince kırılmayan, anti-bot direnci olan kazıyıcı. Pineal'in
    en kırılgan noktası (selector'a bağlı Playwright) için son düşüş hattı.
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

        def _work() -> str:
            try:
                from scrapling.fetchers import Fetcher  # scrapling >= 0.9
            except ImportError:  # eski/sade paket düzeni
                from scrapling import Fetcher  # type: ignore[no-redef]
            page = Fetcher.get(url)
            getter = getattr(page, "get_all_text", None)
            if callable(getter):
                try:
                    return getter(separator="\n", strip=True) or ""
                except TypeError:
                    return getter() or ""
            text = getattr(page, "text", "") or getattr(page, "html_content", "") or ""
            return text

        try:
            text = await asyncio.wait_for(
                asyncio.to_thread(_work), timeout=self.timeout_seconds
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
        lang_scope = _language_scope(text, "scrapling", url)
        item = make_evidence(
            content=_clamp(text, max_chars),
            source_engine="scrapling",
            epistemic_type="observation",
            provenance_refs=[url],
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
