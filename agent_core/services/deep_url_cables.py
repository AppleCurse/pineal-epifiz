"""Derin tarama kablosu — "bulunan adres" → "gerçekten taranan profil".

Neden bu modül var? (2026-10-23 ölçümü)
    Kazıyıcı Instagram bio'sundaki Linktree/X/Threads bağlantılarını
    ``external_urls`` içinde topluyordu, ama ``ig_target_profile_update``
    bunları ``target_profile``'a YAZMIYORDU. Görev yürütücüsü derin taramayı
    yalnız ``target_profile["detected_urls"]`` üzerinden başlattığı için bio
    linkleri sessizce çöp oluyordu. Aynı delik X tarafında da vardı: gönderi
    metinlerindeki adresler hiç ayrıştırılmıyordu.

    Bu modül birleştirme kuralını TEK yere alır; yürütücü (``task_executor``)
    ve testler AYNI fonksiyonu kullanır. Böylece "kablo bağlı" iddiası grep
    ile değil, veri akışıyla doğrulanabilir.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

__all__ = ["merge_detected_profile_urls", "MAX_DETECTED_URLS"]

#: Görev başına derin taramaya verilecek en fazla adres (kota/rate nezaketi).
MAX_DETECTED_URLS = 16


def _as_urls(value: Any) -> List[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(v) for v in value if isinstance(v, str) and v.strip()]


def merge_detected_profile_urls(
    target_profile: Optional[Dict[str, Any]],
    osint_footprint: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """``target_profile`` + OSINT bulgularından KOŞULABİLİR derin tarama listesi.

    Sözleşme:
      * ``target_profile["detected_urls"]`` (bio/gönderi kaynaklı) korunur ve
        OSINT kullanıcı-adı taramasının bulduğu adreslerle birleştirilir.
      * Yalnız ``classify_url(...).runnable`` olan yollar girer: sınıflandırıcı
        profili tanımıyorsa adres TARANMAZ (yanlış hedefe koşu yok).
      * Sıra korunur, tekrarlar atılır, üst sınır ``MAX_DETECTED_URLS``.
      * Kasa/kapı kararı burada VERİLMEZ; bu fonksiyon saf bir kablodur.
    """
    from agent_core.services.profile_router import classify_url

    profile = target_profile if isinstance(target_profile, dict) else {}
    osint = osint_footprint if isinstance(osint_footprint, dict) else {}

    candidates: List[str] = _as_urls(profile.get("detected_urls"))
    # [2026-10-23] Bio/gönderi ham listesi de kabloya girer: kazıyıcı
    # `external_urls` doldurup `detected_urls` boş bırakmışsa (eski payload,
    # gizli profil kurtarma yolu) bağlantılar yine de taranır.
    candidates.extend(_as_urls(profile.get("external_urls")))

    username_scan = osint.get("username_scan") or {}
    if isinstance(username_scan, dict):
        for site in username_scan.get("found_sites") or []:
            if isinstance(site, dict):
                candidates.append(str(site.get("url") or ""))
    handle_probe = osint.get("handle_probe") or {}
    if isinstance(handle_probe, dict):
        for site in handle_probe.get("found_sites") or []:
            if isinstance(site, dict):
                candidates.append(str(site.get("url") or ""))

    out: List[str] = []
    for url in candidates:
        if not url or url in out:
            continue
        try:
            if not classify_url(url).runnable:
                continue
        except Exception:
            continue
        out.append(url)
        if len(out) >= MAX_DETECTED_URLS:
            break
    return out
