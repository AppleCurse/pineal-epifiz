"""Yetki verilmiş alternatif: kanıt kaynaklı public-web araması.

[API-BÖLME 4 · 2026-10-16] Bu gövde ``backend/api.py`` tek-modül tavanından
çıkarıldı (``tests/unit/test_api_monolith_ratchet.py``; kural: satır eklemek
yerine MODÜL ÇIKAR — ``docs/reports/API_MONOLITH_SPLIT_PLAN.md`` §4).
``backend/api.py`` bu modülü **yeniden ihraç eder**; dış sözleşme değişmedi.

Bağımlılıklar ENJEKTE edilir:
  * ``search_engine`` → arama sağlayıcısı (çağıran verir)
  * ``vault_locked``  → kasa mandalının durumu (çağıran verir; varsayılan
    KİLİTLİ = fail-closed). Bu modül ``backend.api``'yi içe aktarmaz.

Sözleşme (sahte veri YASAK):
  * Biyografi/gönderi/kişilik ÜRETİLMEZ; yalnızca gerçek arama kayıtları döner.
  * Subject matching: hedef kullanıcı adı geçmeyen sonuçlar düşürülür.
  * Sağlayıcı yok/çöktü -> available=False; sonuç yok -> no_results.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Dict

from agent_core.services import crawl_enricher, socid_enricher

logger = logging.getLogger(__name__)

__all__ = ["extract_handle_from_url", "run_public_web_research"]


def extract_handle_from_url(url: str) -> str:
    """X/Instagram URL'sinden kullanıcı adı (subject) çıkarır."""
    import re
    if not url:
        return ""
    needle = re.search(r"(?:instagram\.com|x\.com|twitter\.com)/([^/?#]+)", url)
    if needle:
        return needle.group(1).strip().lstrip("@").lower()
    return url.split("?")[0].rstrip("/").split("/")[-1].replace("@", "").lower()


def _vault_locked(client_id: str, vault_locked_fn: Callable[[str], bool] | None) -> bool:
    """Kasa mandalı: True = KİLİTLİ (dış dünyaya çıkış yok).

    Bağımlılık ENJEKTE edilir: ``vault_locked_fn`` verilirse o kullanılır
    (``backend/api.py`` kendi ``_check_vault_interlock``'ını verir → modül
    ``backend.api``'ye bağımlı olmaz). Verilmezse **geriye dönük uyum** için
    oda kasa durumu tembel import ile okunur (dairesel bağımlılık YOK:
    import anında değil, çağrı anında çözülür).
    """
    if vault_locked_fn is not None:
        return bool(vault_locked_fn(client_id))
    from backend.api import _check_vault_interlock

    return not _check_vault_interlock(client_id)


async def run_public_web_research(
    url: str,
    search_engine: Any,
    client_id: str = "default",
    *,
    vault_locked_fn: Callable[[str], bool] | None = None,
) -> Dict[str, Any]:
    """Yetki verilmiş alternatif: kanıt kaynaklı public-web araması.

    Sözleşme (sahte veri YASAK):
    - Biyografi/gönderi/kişilik ÜRETİLMEZ; yalnızca gerçek arama kayıtları
      döner (source_url + provider + content).
    - Subject matching: hedef kullanıcı adı kaynak URL'sinde veya içeriğinde
      geçmeyen sonuçlar düşürülür (yanlış kişi eşleşmesi engeli).
    - Sağlayıcı yok/çöktü -> available=False; sonuç yok -> no_results.
    """
    handle = extract_handle_from_url(url)
    if not handle:
        return {
            "status": "invalid_target", "available": False,
            "query": "", "results": [], "matched_username": "",
            "total_results_searched": 0,
            "search_outcome": {
                "status": "NOT_REQUESTED", "available": False, "error": None,
            },
            "searched_at": datetime.now().isoformat(),
            "note": "URL'den hedef kullanıcı adı çıkarılamadı.",
        }

    query = f'"{handle}"'
    try:
        outcome = await search_engine.search(query, num_results=8)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return {
            "status": "unavailable", "available": False, "query": query,
            "results": [], "matched_username": handle,
            "total_results_searched": 0,
            "search_outcome": {
                "status": "UNAVAILABLE", "available": False,
                "error": type(exc).__name__,
            },
            "searched_at": datetime.now().isoformat(),
            "note": f"Arama çağrısı başarısız: {type(exc).__name__}.",
        }

    search_outcome = {
        "status": getattr(outcome, "status", "UNKNOWN"),
        "available": bool(getattr(outcome, "available", False)),
        "error": getattr(outcome, "error", None),
    }
    if not search_outcome["available"]:
        return {
            "status": "unavailable", "available": False, "query": query,
            "results": [], "matched_username": handle,
            "total_results_searched": 0,
            "search_outcome": search_outcome,
            "searched_at": datetime.now().isoformat(),
            "note": getattr(outcome, "error", None) or "Arama sağlayıcısı kullanılamadı.",
        }

    raw = getattr(outcome, "results", []) or []
    matched = [
        {
            "source_url": r.source_url,
            "provider": r.provider,
            "content": r.content,
            "subject_match": True,
        }
        for r in raw
        if handle in (r.source_url or "").lower()
        or handle in (r.content or "").lower()
    ]
    # socid-extractor zenginleştirmesi: eşleşen kaynak URL'lerden kararlı kimlik
    # kaydı çıkmaya çalışılır. Kütüphane yok/ağ yok/kayıt yoksa alan EKLENMEZ —
    # sonuç sözleşmesi bozulmaz (dürüst boş).
    try:
        socid_records = await socid_enricher.enrich_urls(
            [m["source_url"] for m in matched], limit=3
        )
        by_url = {r.source_url: r for r in socid_records}
        for m in matched:
            rec = by_url.get(m["source_url"])
            if rec is not None:
                m["socid"] = rec.model_dump()
        if socid_records:
            socid_note = f" {len(socid_records)} sonuçtan yapılandırılmış kimlik kaydı çıkarıldı."
        else:
            socid_note = ""
    except Exception as exc:  # zenginleştirme asıl sonucu asla bozmasın
        logger.warning("socid enrichment skipped: %s: %s", type(exc).__name__, str(exc)[:80])
        socid_note = ""
    # [FAZ A · Retina] TEMİZ METİN OMURGASI. Eskiden tek bir crawl4ai çağrısı
    # vardı ve yalnız ENABLE_CRAWL4AI açıkken çalışıyordu. Artık üç kademeli
    # omurga devrede: trafilatura → crawl4ai → scrapling. İlk KANIT ÜRETEN
    # kademe sonucu verir; hiçbiri üretemezse alan uydurma metinle DOLDURULMAZ
    # (sebep + deneme izi yazılır). Tek arayüz: capabilities.extract_web_text.
    crawl_note = ""
    try:
        from agent_core.capabilities import bootstrap as _caps_bootstrap
        from agent_core.capabilities.adapters_web import extract_web_text
        from agent_core.capabilities.state import policy_state

        _caps_bootstrap()
        web_state = policy_state(vault_locked=_vault_locked(client_id, vault_locked_fn))
        if matched:
            crawled = 0
            for m in matched[:crawl_enricher.research_limit()]:
                result = await extract_web_text(m["source_url"], state=web_state)
                if result.ok:
                    # payload kademeye göre değişir (pydantic kayıt veya dict);
                    # ikisi de desteklenir, erişim güvenli.
                    payload_raw = result.payload
                    title = (
                        payload_raw.get("title", "") if isinstance(payload_raw, dict)
                        else getattr(payload_raw, "title", "") or ""
                    )
                    m["crawl"] = {
                        "available": True,
                        # HANGİ kademenin ürettiği kayıtta yazar (görünürlük).
                        "provider": result.capability_id,
                        "requested_url": m["source_url"],
                        "title": title,
                        "text": result.items[0].content if result.items else "",
                        "evidence_ids": [i.evidence_id for i in result.items],
                        "attempts": result.notes.get("attempts", []),
                    }
                    crawled += 1
                else:
                    # Dürüst boş (sözleşme korunur): çekilemeyen sonuca `crawl`
                    # alanı EKLENMEZ; sebep yalnız logda (uydurma metin yok).
                    logger.info(
                        "web extraction failed for %s: %s (attempts=%s)",
                        m["source_url"], result.unavailable_reason,
                        result.notes.get("attempts", []),
                    )
            if crawled:
                crawl_note = f" {crawled} sonuca temiz metin çekildi (omurga: trafilatura → crawl4ai → scrapling)."
    except Exception as exc:  # zenginleştirme asıl sonucu asla bozmasın
        logger.warning("web extraction skipped: %s: %s", type(exc).__name__, str(exc)[:80])

    if matched:
        status = "ok"
        note = f"{len(matched)}/{len(raw)} sonuç hedef kullanıcı adıyla eşleşti." + socid_note + crawl_note
    elif raw:
        status = "no_subject_match"
        note = f"Arama yapıldı ({len(raw)} sonuç) ama hiçbiri hedef kullanıcı adıyla eşleşmedi; sonuç gösterilmiyor (yanlış kişi eşleşmesi engeli)."
    else:
        status = "no_results"
        note = "Arama yapıldı, hiç sonuç döndü."

    return {
        "status": status,
        "available": True,
        "query": query,
        "search_outcome": search_outcome,
        "results": matched,
        "matched_username": handle,
        "total_results_searched": len(raw),
        "searched_at": datetime.now().isoformat(),
        "note": note,
    }
