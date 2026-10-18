"""Web dosyası (open-source dossier) — hedef profili ve kanal durumu.

[API-BÖLME 3 · 2026-10-16] Bu modül, ``backend/api.py`` tek-modül tavanı
(``tests/unit/test_api_monolith_ratchet.py``; kural: satır eklemek yerine
MODÜL ÇIKAR — ``docs/reports/API_MONOLITH_SPLIT_PLAN.md`` §4) gereği
ayrıldı. Bağımlılıklar ENJEKTE edilmez; bu modül ``backend.api``'yi içe
aktarmaz (dairesel bağımlılık yok).

Sözleşme (denetim 2026-10-16 · Bulgu 2 — "arama sonucu ≠ gönderi"):

* Arama motorundan gelen snippet'lar ``posts`` alanına YAZILMAZ.
  ``posts`` yalnız platformdan KAZINMIŞ gönderileri taşır.
* Snippet'lar ``search_snippets`` altında, kanıt tipiyle birlikte durur:
  ``{"text": ..., "provider": ..., "source_url": ...}``.
* ``content_basis`` corpus'un ne olduğunun TEK beyanıdır
  (``search_snippet`` | ``platform_post`` | ``mixed`` | ``none``).
* Bulunan profil URL'leri ``detected_urls`` altındadır ve KAZINMAMIŞTIR;
  "bağlandı" diye sunulmaz.
* Kanal durumu (koştu / ÇALIŞMADI+sebep) aynı yerden üretilir; boş liste
  dönmek yasaktır.
"""

from __future__ import annotations

from typing import Any, Iterable

from agent_core.domain.channel_status import ChannelRun, not_run, ok
from agent_core.domain.content_basis import CONTENT_BASIS_NONE, CONTENT_BASIS_SEARCH

__all__ = [
    "build_dossier_profile",
    "build_dossier_failure_profile",
    "dossier_channel_rows",
    "x_sensor_channel_rows",
    "instagram_channel_rows",
    "build_snippets",
]


def build_snippets(results: Iterable[Any]) -> list[dict[str, Any]]:
    """Arama sonuçlarını YAPILANDIRILMIŞ snippet listesine çevirir.

    Uzunluğu 20 karakterin altındaki sonuçlar anlamsız sayılır (aynı eşik
    daha önce de uygulanıyordu) ve atlanır.
    """
    snippets: list[dict[str, Any]] = []
    for result in results or ():
        content = (getattr(result, "content", None) or "").strip()
        if not content or len(content) <= 20:
            continue
        snippets.append(
            {
                "text": content,
                "provider": str(getattr(result, "provider", "") or ""),
                "source_url": getattr(result, "source_url", None) or "",
            }
        )
    return snippets


def build_dossier_profile(
    *,
    display_user: str,
    clean_u: str,
    snippets: list[dict[str, Any]],
    found_profiles: list[str],
    web_search: dict[str, Any] | None = None,
    x_sensor_reason: str = "",
) -> dict[str, Any]:
    """Web dosyası hedef profilinin alanlarını kurar (dürüst sözleşme).

    * ``bio`` boş kalır: arama snippet'i biyografi DEĞİLDİR.
    * ``followers``/``following`` ``None`` = ölçülmedi (0 ölçümdür).
    * ``posts`` boş: snippet "gönderi" değildir.
    * ``scanned_urls``/``scanned_profiles`` burada **boş** başlar: derin tarama
      bu katmanda KOŞMAZ (tek koşum yolu: görev yürütücüsü →
      ``deep_profile_resolver``). Görev sırasında doldurulur. **Hedefin
      ``posts`` alanına hiçbir zaman YAZILMAZ**: bulunan profil ile hedefin
      aynı kişi olduğu kanıtlanmamıştır (P0 kuralı: "bulundu" ≠ "hedef").
    """
    scanned_urls: list[dict[str, Any]] = []
    scanned_profiles: dict[str, dict[str, Any]] = {}
    return {
        "username": display_user,
        "name": clean_u,
        "bio": "",
        "posts": [],
        "post_times": [],
        "posts_meta": [],
        "post_types": [],
        "post_evidence_types": [],
        "search_snippets": snippets,
        "content_basis": CONTENT_BASIS_SEARCH if snippets else CONTENT_BASIS_NONE,
        "images": [],
        "followers": None,
        "following": None,
        "is_private": None,
        "detected_urls": found_profiles,
        # [P1 · 2026-10-16] Bulunan profillerin gerçek kazım defteri.
        "scanned_urls": scanned_urls,
        "scanned_profiles": scanned_profiles,
        "web_search": web_search or {},
        "platform": "web_dossier",
        "sensor_note": (
            f"X sensörü kanıt üretemedi: {x_sensor_reason}"
            if x_sensor_reason
            else "Açık kaynak dosyası: platform sensörüyle kazınmadı."
        ),
    }


def build_dossier_failure_profile(*, clean_u: str, error_type: str) -> dict[str, Any]:
    """Arama başarısız olduğunda dürüst (boş) profil döner."""
    return {
        "username": f"@{clean_u}",
        "name": clean_u,
        "bio": "",
        "posts": [],
        "post_times": [],
        "posts_meta": [],
        "post_types": [],
        "post_evidence_types": [],
        "search_snippets": [],
        "content_basis": CONTENT_BASIS_NONE,
        "images": [],
        "followers": None,
        "following": None,
        "is_private": None,
        "platform": "web_dossier",
        "sensor_note": f"Açık kaynak araması başarısız: {error_type}",
    }


def dossier_channel_rows(
    *,
    web_search_status: str,
    snippet_count: int,
    found_profile_count: int,
    queries_available: int = 0,
    queries_requested: int = 0,
) -> list[ChannelRun]:
    """Web dosyası kanallarının durum satırları (boş liste yasak).

    Bulunan profil URL'leri varsa "henüz kazınmadı" satırı yazılır: derin tarama
    bu katmanda koşmaz, **görev yürütücüsünde** koşar (tek koşum yolu) ve
    oradaki gerçek satırlar bu yer tutucuyu **değiştirir**. Arama kanalı satırı
    (``search.web``) her zaman korunur.
    """
    rows: list[ChannelRun] = []
    if str(web_search_status).upper() in {"UNAVAILABLE", "PARTIAL"}:
        rows.append(
            not_run(
                "search.web",
                reason=f"search_{str(web_search_status).lower()}",
                detail=f"{queries_available}/{queries_requested} sorgu kullanılabilir",
            )
        )
    else:
        rows.append(
            ok(
                "search.web",
                detail=(
                    f"{snippet_count} arama sonucu (snippet) — "
                    "platform gönderisi DEĞİLDİR"
                ),
            )
        )
    if found_profile_count:
        # Bulunan profil URL'leri henüz KAZINMADI; "bağlandı" diye sunulmaz.
        # (Görev yürütücüsü bu satırı gerçek koşu satırlarıyla değiştirir.)
        rows.append(
            not_run(
                "profile.deep_scan",
                reason="not_attempted",
                detail=f"{found_profile_count} profil URL'si bulundu; henüz kazınmadı",
            )
        )
    return rows


def x_sensor_channel_rows(
    *,
    ok_detail: str = "",
    reason: str = "",
    machine_reason: str = "",
) -> list[ChannelRun]:
    """X sensörü kanal durumu (koştu / ÇALIŞMADI+sebep)."""
    if not reason:
        return [ok("sensor.x.twscrape", detail=ok_detail)]
    return [
        not_run(
            "sensor.x.twscrape",
            reason=str(machine_reason or reason),
            detail=reason if machine_reason else None,
        )
    ]


def instagram_channel_rows(*, post_count: int) -> list[ChannelRun]:
    """Instagram kazıma kanal durumu."""
    return [ok("sensor.ig.primary", detail=f"{post_count} gönderi")]
