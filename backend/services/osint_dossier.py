"""Açık kaynak (OSINT) dosyası — ``api.run_mission`` içinden çıkarıldı.

[API-BÖLME 7 · 2026-11-11] ``run_mission`` 439 satırlık tek bloktu ve
``backend/api.py`` ratchet tavanının (5760) üstündeydi. Kural "satır eklemek
yerine MODÜL ÇIKAR": açık kaynak dosyası yolu buraya taşındı; davranış
BİREBİR korunur.

Sözleşme:
    - Uydurma profil YOK: arama motoru çökerse profil "doğrulanmadı" işaretlenir
      (``build_dossier_failure_profile``) ve kanal defterine ``failed`` yazılır.
    - Biyografiden çıkan gerçek isim/bağlı hesap adayları arama sorgularına
      eklenir; sonuçlar tier'lanır (tam eşleşme → parça eşleşmesi).
    - Biyografideki işletme hesapları kazınır; gizli hesapta yalnızca
      kurtarılabilen alanlar (bio/takipçi/takip) saklanır.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from agent_core.domain.channel_status import failed as channel_failed
from agent_core.scraper.instagram_ghost import (
    InsufficientEvidenceError as ScraperInsufficientEvidenceError,
)
from agent_core.task_executor import InsufficientEvidenceError
from backend.services.web_dossier import (
    build_dossier_failure_profile,
    build_dossier_profile,
    build_snippets,
    dossier_channel_rows,
)

__all__ = ["OSINTResult", "run_osint_dossier", "summarize_osint_search_results"]


@dataclass
class OSINTResult:
    """Açık kaynak dosyasının sonucu (kanal defteri satırları dâhil)."""

    clean_u: str = ""
    channel_rows: list[Any] = field(default_factory=list)
    error_type: str = ""


async def run_osint_dossier(
    *,
    url: str,
    effective_type: str,
    x_sensor_reason: str,
    target_profile: dict,
    executor: Any,
    scrape_instagram: Callable[..., Awaitable[dict]],
    cookie: Any,
    log: Callable[[str, str], None],
) -> OSINTResult:
    """Hedef için açık kaynak dosyası üret; ``target_profile`` YERİNDE güncellenir."""
    channel_rows: list[Any] = []
    result = OSINTResult(channel_rows=channel_rows)
    from agent_core.services.profile_router import classify_url

    clean_u = (
        classify_url(url).handle
        or (url.rstrip("/").split("/")[-1] if "/" in url else url).lstrip("@").strip()
    )
    result.clean_u = clean_u
    if effective_type == "x":
        log("INFO", f"UPLINK: Hedefe sızılıyor -> {url} [X · açık kaynak dosyası]")
    else:
        log("INFO", f"UPLINK: Hedefe sızılıyor -> {url} [{effective_type.upper()}]")
    log("INFO", f"AÇIK KAYNAK VE OSINT: {clean_u} için veriler taranıyor...")
    try:
        # [ZİNCİRLEME OSINT] Hedefin biyografisinden ve profilinden çıkan gerçek isim ve bağlı hesaplar (@handle):
        recovered_bio = target_profile.get("bio") or ""
        recovered_name = (target_profile.get("name") or "").strip()
        bio_handles = [h.lstrip("@").strip() for h in re.findall(r"@[A-Za-z0-9_.-]+", recovered_bio) if len(h) > 2]
        # Biyografiden linktree / beacons / harici link aggregators tespiti:
        bio_links = re.findall(
            r"(?:https?://)?(?:www\.)?(?:linktr\.ee|beacons\.ai|taplink\.cc|bio\.link|carrd\.co)/[A-Za-z0-9_.-]+",
            recovered_bio,
            re.IGNORECASE,
        )
        if bio_links:
            clean_links = [l if l.startswith("http") else f"https://{l}" for l in bio_links]
            log("INFO", f"ZİNCİRLEME BAĞLANTI TESPİT EDİLDİ (Linktree/Beacons): {', '.join(clean_links)}")

        # Biyografiden gerçek isim adaylarını bul (örn. "Kübra Cebi"):
        name_candidates = []
        if recovered_name and recovered_name.lower() != clean_u.lower():
            name_candidates.append(recovered_name)
        for line in recovered_bio.splitlines():
            clean_line = re.sub(r"[^\w\s]", "", line).strip()
            parts = clean_line.split()
            if 1 < len(parts) <= 3 and not any(kw in clean_line.lower() for kw in ["takip", "specialist", "artist", "inci"]):
                if clean_line not in name_candidates:
                    name_candidates.append(clean_line)

        # Temel kullanıcı adı sorguları:
        queries = [
            f"{clean_u} instagram",
            f"{clean_u} linkedin twitter",
            f"{clean_u} facebook reddit",
            f"{clean_u} threads",
            f"{clean_u}",
        ]

        # Tespit edilen gerçek isim varsa LinkedIn, Facebook, Reddit ve genel web aramaları ekle:
        for cand_name in name_candidates[:2]:
            queries.append(f"{cand_name} linkedin")
            queries.append(f"{cand_name} facebook")
            queries.append(f"{cand_name} reddit")
            log("INFO", f"HEDEF GERÇEK İSİM TESPİT EDİLDİ: '{cand_name}' (LinkedIn, Facebook, Reddit taramasına alındı)")

        # Biyografiden çıkan iş/ikinci hesapları ve Threads aramalarını ekle:
        for bh in bio_handles[:3]:
            if bh.lower() != clean_u.lower():
                queries.append(f"{bh} instagram")
                log("INFO", f"ZİNCİRLEME HEDEF TESPİT EDİLDİ: @{bh} (Açık kaynak araştırmasına dahil edildi)")

        # Biyografide meslek/lokasyon varsa ek sorgu:
        specialty_matches = re.findall(r'(?:esthetician|makeup|kuaför|güzellik|estetisyen|artist)', recovered_bio, re.IGNORECASE)
        if specialty_matches:
            spec_term = specialty_matches[0]
            queries.append(f"{clean_u} {spec_term}")
            if name_candidates:
                queries.append(f"{name_candidates[0]} {spec_term}")

        search_tasks = [executor.search_engine.search(q, num_results=6) for q in queries]
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

        all_raw_results, web_search_status_record = summarize_osint_search_results(
            search_results
        )
        web_search_status = web_search_status_record["status"]
        unique_search_errors = web_search_status_record["errors"]
        available_queries = web_search_status_record["queries_available"]
        if web_search_status in {"UNAVAILABLE", "PARTIAL"}:
            log("WARNING",
                f"WEB ARAMA: {web_search_status}; "
                f"{available_queries}/{len(search_tasks)} sorgu kullanılabilir, "
                f"{len(all_raw_results)} kaynak; hata kodları: "
                f"{', '.join(unique_search_errors[:5]) or 'yok'}.",
            )

        target_parts = [p.lower() for p in clean_u.split() if len(p) > 1]
        for c_name in name_candidates:
            target_parts.extend([p.lower() for p in c_name.split() if len(p) > 1])
        name_full = clean_u.lower()
        cand_lowers = [c.lower() for c in name_candidates]
        tier1 = []
        tier2 = []
        tier3 = []
        for r in all_raw_results:
            text_blob = f"{r.content or ''} {r.source_url or ''}".lower()
            if name_full in text_blob or any(cn in text_blob for cn in cand_lowers):
                tier1.append(r)
            elif all(p in text_blob for p in target_parts[:2]):
                tier2.append(r)
            elif any(p in text_blob for p in target_parts):
                tier3.append(r)

        ordered_results = (tier1 + tier2 + tier3) or all_raw_results
        snippets = build_snippets(ordered_results)

        found_profiles = [url] if classify_url(url).runnable else []
        for cl in (clean_links if 'clean_links' in locals() else []):
            if cl not in found_profiles:
                found_profiles.append(cl)
        for r in (ordered_results + all_raw_results):
            u = r.source_url or ""
            if classify_url(u).runnable and u not in found_profiles:
                found_profiles.append(u)

        if found_profiles:
            log("INFO", f"HEDEF PROFİLLERİ TESPİT EDİLDİ: {', '.join(found_profiles[:3])}")

        display_user = f"@{clean_u.replace(' ', '_').lower()}" if " " in clean_u else f"@{clean_u}"
        dossier_data = build_dossier_profile(
            display_user=display_user,
            clean_u=clean_u,
            snippets=snippets,
            found_profiles=found_profiles,
            web_search=web_search_status_record,
            x_sensor_reason=x_sensor_reason,
        )
        # Eğer hedefin profilinden (örn. gizli hesap başlığından) bio/takipçi kurtarıldıysa ezme:
        if recovered_bio:
            dossier_data["bio"] = recovered_bio
        if target_profile.get("followers") is not None:
            dossier_data["followers"] = target_profile.get("followers")
        if target_profile.get("following") is not None:
            dossier_data["following"] = target_profile.get("following")
        target_profile.update(dossier_data)

        # [FAZ 1 · ZİNCİRLEME İŞLETMELERİ KAZIMA]
        # Biyografiden çıkan iş/ikinci hesaplar (@bangskuafor, @kubra_beauty_ vb.) açıksa hafifçe kazı:
        business_entities = target_profile.setdefault("business_entities", [])
        for bh in bio_handles[:2]:
            if bh.lower() != clean_u.lower():
                bh_url = f"https://www.instagram.com/{bh}/"
                log("INFO", f"ZİNCİRLEME PROFİL İNCELENİYOR: @{bh} -> {bh_url}")
                try:
                    bh_data = await asyncio.wait_for(
                        scrape_instagram(bh_url, cookie, log=lambda lvl, msg: None),
                        timeout=25.0,
                    )
                    business_entities.append({
                        "handle": f"@{bh}",
                        "url": bh_url,
                        "bio": bh_data.get("bio", ""),
                        "followers": bh_data.get("followers"),
                        "following": bh_data.get("following"),
                        "post_count": len(bh_data.get("posts") or []),
                        "posts": (bh_data.get("posts") or [])[:5],
                        "is_private": bh_data.get("is_private", False),
                    })
                    log("INFO",
                        f"ZİNCİRLEME İŞLETME KAZINDI: @{bh} ({len(bh_data.get('posts') or [])} gönderi, "
                        f"takipçi={bh_data.get('followers')})"
                    )
                except (InsufficientEvidenceError, ScraperInsufficientEvidenceError) as b_exc:
                    # Gizli işletme hesabıysa bile başlığı/biyografisi varsa kurtar:
                    b_priv = getattr(b_exc, "profile_update", None) or {}
                    if b_priv:
                        business_entities.append({
                            "handle": f"@{bh}",
                            "url": bh_url,
                            "bio": b_priv.get("bio", ""),
                            "followers": b_priv.get("followers"),
                            "following": b_priv.get("following"),
                            "post_count": 0,
                            "is_private": True,
                        })
                    log("INFO", f"ZİNCİRLEME PROFİL GİZLİ/SINIRLI: @{bh}")
                except Exception as b_err:
                    log("WARNING", f"ZİNCİRLEME PROFİL ATLANDI: @{bh} ({type(b_err).__name__})")

        channel_rows.extend(
            dossier_channel_rows(
                web_search_status=web_search_status,
                snippet_count=len(snippets),
                found_profile_count=len(found_profiles),
                queries_available=available_queries,
                queries_requested=len(search_tasks),
            )
        )
        log("INFO",
            f"TELEMETRİ: {len(snippets)} arama sonucu (snippet) bulundu, "
            f"{len(found_profiles)} profil URL'si tespit edildi — "
            "derin tarama görev sırasında koşacak (kanal defteri orada yazılır).",
        )
    except Exception as se:
        log("WARNING", f"OSINT ARAMA UYARISI: {se}")
        result.error_type = type(se).__name__
        channel_rows.append(channel_failed("search.web", reason=result.error_type))
        target_profile.update(
            build_dossier_failure_profile(
                clean_u=clean_u, error_type=result.error_type
            )
        )

    return result


def summarize_osint_search_results(search_results: list[Any]) -> tuple[list[Any], dict[str, Any]]:
    """Keep provider failures distinct from a successful empty web search."""
    if not search_results:
        return [], {
            "status": "NOT_REQUESTED",
            "available": False,
            "queries_requested": 0,
            "queries_available": 0,
            "result_count": 0,
            "errors": [],
        }
    all_results: list[Any] = []
    seen_urls: set[str] = set()
    errors: list[str] = []
    available_queries = 0
    for outcome in search_results:
        if isinstance(outcome, asyncio.CancelledError):
            raise outcome
        if isinstance(outcome, BaseException):
            if isinstance(outcome, Exception):
                errors.append(type(outcome).__name__)
                continue
            raise outcome
        if not getattr(outcome, "available", False):
            errors.append(
                str(getattr(outcome, "error", None) or getattr(outcome, "status", "unavailable"))
            )
            continue
        available_queries += 1
        if getattr(outcome, "error", None):
            errors.append(str(outcome.error))
        for result in getattr(outcome, "results", []) or []:
            source_url = getattr(result, "source_url", None)
            content = getattr(result, "content", None)
            if (
                not isinstance(source_url, str)
                or not source_url.strip()
                or not isinstance(content, str)
                or not content.strip()
            ):
                errors.append("INVALID_PROVIDER_RESULT")
                continue
            source_url = source_url.strip()
            if source_url in seen_urls:
                continue
            seen_urls.add(source_url)
            all_results.append(result)

    unique_errors = sorted(set(errors))
    if available_queries == 0:
        status = "UNAVAILABLE"
    elif unique_errors:
        status = "PARTIAL"
    else:
        status = "OK" if all_results else "NO_RESULTS"
    return all_results, {
        "status": status,
        "available": available_queries > 0,
        "queries_requested": len(search_results),
        "queries_available": available_queries,
        "result_count": len(all_results),
        "errors": unique_errors,
    }
