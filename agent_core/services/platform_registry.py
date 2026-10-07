"""Platform karar merkezi — TEK sahiplik ([023]/[049]/W4.2).

Bu modül platform routing + Instagram kazıma + glue mapping'in tek kaynağıdır:
- backend/api.py run_mission burayı kullanır
- scripts/run_task.py (Rust TaskManager'ın standart girişi) burayı kullanır

Kural ([009] duplication dersi): ikinci bir platform-karar/scraper katmanı
YARATILMAZ. Rust tarafı platform seçmez; karar burada verilir.

Sözleşme (sahte veri YASAK):
- Tanınmayan platform -> "unsupported_web"; URL segmenti Instagram adı sanılıp
  yanlış hedef kazınmaz.
- Kazıma kanıt üretemezse InsufficientEvidenceError yükselir; boş/sentetik
  profil ÜRETİLMEZ.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = ("instagram", "x", "cross")


def effective_scraper_type(url: str, requested: Optional[str] = None) -> str:
    """URL platformuna göre tarayıcı seç ([023] fix: platform registry).

    Instagram adresi X tarayıcısına gitmesin diye URL platform tespiti
    önceliklidir; ancak tanınmayan platformda kullanıcı seçimi GEÇERLİ
    DEĞİLDİR: URL'nin son path segmentini Instagram adı gibi kullanıp
    yanlış hedefi kazımak misattribution'dır. Tanınmayan platform ->
    unsupported_web (çağıran analizi başlatmadan durur).
    """
    req = (requested or "").strip().lower()
    u = (url or "").strip().lower()

    if not u:
        return "unsupported_web"

    if "instagram.com" in u:
        return "instagram"
    if "x.com" in u or "twitter.com" in u:
        return "x"

    # Bare username or @handle without a web domain
    if u.startswith("@") or ("://" not in u and "." not in u and "/" not in u):
        if req in ("x", "twitter"):
            return "x"
        if req in ("instagram", "ig"):
            return "instagram"
        return "cross"

    return "unsupported_web"


# [AUDIT P1-6] Yalnız GERÇEK profil URL'lerinden kullanıcı adı çıkarılır.
# Eskiden URL'nin SON path segmenti körlemesine hedef sanılıyordu:
# /p/CxYz123Ab/ -> "CxYz123Ab", /explore/tags/kedi/ -> "kedi",
# /accounts/login/ -> "login" — yani etiket/ID/login sayfaları "hedef
# kullanıcı" oluyor ve aynı adı taşıyan GERÇEK bir hesap varsa yanlış kişi
# sessizce kazınıyordu (kanıt zinciri başkasına ait oluyordu).
_RESERVED_IG_SEGMENTS = frozenset({
    "p", "reel", "reels", "explore", "stories", "accounts", "tv",
    "about", "developer", "legal", "press", "locations", "direct",
    "home", "search", "notifications", "settings", "terms", "privacy",
})
_IG_USERNAME = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def _is_instagram_host(host: str) -> bool:
    """[AUDIT N4] Yalnız GERÇEK Instagram hostları.

    Eski substring kontrolü (`"instagram.com" in host`) bakış benzeri
    hostları kabul ediyordu: `notinstagram.com`, `evilinstagram.com`,
    `www.instagram.com.evil.com` (ölçülen: 3/20 adversarial URL yanlış
    kabul). Kurallar: tam eşleşme YA da `.instagram.com` SONEK'i (bu,
    www.instagram.com dahil tüm meşru alt alanları kapsar; sahte hostlar
    sonekle bitmez).
    """
    return host == "instagram.com" or host.endswith(".instagram.com")


def extract_username(url: str) -> str:
    """Instagram PROFİL URL'sinden hedef kullanıcı adını çıkarır.

    Sözleşme: yalnız `instagram.com/<kullanici>` biçiminde TEK segmentli,
    rezerv olmayan ve geçerli karakter/uzunlukta URL'ler kullanıcı adı
    üretir. Profil-DIŞI her URL (post/reel/etiket/stories/login/host) ""
    döndürür; çağıran bu durumda kazımayı BAŞLATMAZ (yanlış hedef yasağı).
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    # [RÖNTGEN 2026-09-23] "@handle" kısayolu KALDIRILDI (P1-6 sözleşmesine
    # dönüş). Çıplak "@ornek" hangi platforma ait olduğunu SÖYLEMEZ; onu
    # Instagram hedefi saymak, [023]/P1-6'nın yasakladığı "tahmine dayalı
    # hedef" kapısını yeniden açıyordu: aynı adı taşıyan gerçek bir hesap
    # sessizce kazınır ve kanıt zinciri yanlış kişiye bağlanırdı. Üç denetim
    # kilidi de (tests/audit/test_auditor_round2_findings.py,
    # test_production_audit_findings.py P1-6, test_round3_residue_findings.py
    # N4) host'suz girdide "" ister. Operatör gerçekten Instagram hedeflemek
    # istiyorsa tam profil URL'si verir.
    if raw.startswith("@"):
        return ""
    if not raw.startswith(("http://", "https://")) and "instagram.com" in raw.lower():
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    host = (parts.hostname or "").lower().rstrip(".")
    if not _is_instagram_host(host):
        return ""
    segments = [s for s in parts.path.split("/") if s]
    if len(segments) != 1:
        return ""
    username = segments[0].lstrip("@").strip().lower()
    if not username or username in _RESERVED_IG_SEGMENTS:
        return ""
    if not _IG_USERNAME.match(username):
        return ""
    if username.startswith(".") or username.endswith(".") or ".." in username:
        return ""
    return username


def extract_x_username(url: str) -> str:
    """X / Twitter profil URL'sinden kullanıcı adını çıkarır."""
    raw = (url or "").strip()
    if not raw:
        return ""
    if raw.startswith("@"):
        return raw.lstrip("@").strip().lower()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    host = (parts.hostname or "").lower().rstrip(".")
    if host in ("x.com", "twitter.com") or host.endswith(".x.com") or host.endswith(".twitter.com"):
        segments = [s for s in parts.path.split("/") if s]
        if segments:
            u = segments[0].lstrip("@").strip().lower()
            if u not in ("home", "explore", "notifications", "messages", "search", "settings", "i"):
                return u
    return ""


def _min_scrape_confidence() -> float:
    """[AUDIT P1-7] Anti-halüsinasyon güven eşiği (env ile ayarlanabilir)."""
    try:
        return max(0.0, min(1.0, float(
            os.getenv("PINEAL_MIN_SCRAPER_CONFIDENCE", "0.6"))))
    except (TypeError, ValueError):
        return 0.6


def check_scrape_confidence(ig_scraper, ig_data, emit) -> float:
    """[AUDIT P1-7] Anti-halüsinasyon kapısı (ÜRETİM yolunda çağrılır).

    evaluate_confidence artık yalnız testte değil, kazıma zincirinde devrededir:
    kanıt zayıfsa (gizli/boş/zayıf profil) düşük güvenli profili işleme devam
    etmek yerine InsufficientEvidenceError ile görev HALT edilir. Dönen değer
    güven skorudur (telemetri/retrospektif için).
    """
    from agent_core.scraper.instagram_ghost import InsufficientEvidenceError
    min_confidence = _min_scrape_confidence()
    confidence = ig_scraper.evaluate_confidence(ig_data)
    emit("INFO", f"SCRAPER CONFIDENCE: {confidence:.2f} (min esik {min_confidence:.2f})")
    if confidence < min_confidence:
        raise InsufficientEvidenceError(
            f"Yetersiz kanit guveni: {confidence:.2f} < {min_confidence:.2f} "
            "(anti-halüsinasyon kapısı; sahte profil üretmiyorum)"
        )
    return confidence


def ig_target_profile_update(ig_data: Any) -> dict:
    """InstagramProfile -> target_profile payload alanları ([024]/[025]/[026] fix).

    Sözleşme (sahte veri YASAK):
    - Sentetik "Instagram Profili: ..." postu ÜRETİLMEZ; caption yoksa "" kalır.
    - posts / post_times / posts_meta AYNI post sırasıyla index-hizalıdır;
      frequency_engine index bazlı eşleştirme yapar, hizasız listeler
      caption'a başka postun zamanını yanlış eşleştirebilir.
    - [GÖREV 1] post_types AYNI hizaya katilir (image/video/carousel/reel;
      bilinmiyorsa "unknown"). posts_meta'nin anahtar kumesi DEGISTIRILMEZ
      ([025] esitlik kilidi); tur bilgisi bu yeni paralel listeden akar.
    - following=None "ölçülmedi" demektir; 0 ölçümdür, birbirine karışmaz.
    """
    posts = ig_data.posts or []
    return {
        "username": "@" + ig_data.username,
        "bio": ig_data.biography or "",
        "posts": [p.caption or "" for p in posts],
        # Zaman damgası yoksa "" (None değil): str() ile "None" metnine
        # dönüşüp quote_guard source'larına sızmasın.
        "post_times": [p.taken_at.isoformat() if p.taken_at else "" for p in posts],
        "posts_meta": [
            {"like_count": p.like_count, "comment_count": p.comment_count}
            for p in posts
        ],
        "post_types": [p.post_type or "unknown" for p in posts],
        "images": [p.display_url for p in posts],
        "followers": ig_data.follower_count or 0,
        "following": ig_data.following_count,  # None = ölçülmedi ([024])
        "is_private": ig_data.is_private,
    }


async def scrape_instagram(
    url: str,
    cookie: str = "",
    log: Optional[Callable[[str, str], None]] = None,
) -> Dict[str, Any]:
    """Instagram profilini kazır ve target_profile güncellemesini döndürür.

    Kanıt yoksa (private/login duvarı/rate-limit) InsufficientEvidenceError
    yükseltir — asla boş veya sentetik profil ÜRETİLMEZ.
    `log(level, msg)` isteğe bağlı telemetri callback'idir (WS broadcast / CLI stderr).
    """
    emit = log or (lambda level, msg: None)
    username = extract_username(url)
    if not username:
        # [AUDIT P1-6] Profil dışı URL (post/reel/etiket/login/host) artık
        # HİÇBİR hedefe çözümlenmez; kazıma başlatılmaz.
        from agent_core.scraper.instagram_ghost import InsufficientEvidenceError
        raise InsufficientEvidenceError(
            "URL bir Instagram PROFİLİ değil (yanlış hedef kazınmaz): "
            f"{(url or '')[:80]} — https://www.instagram.com/<kullanici> verin"
        )

    # [FAZ 5] STEALTH_PROVIDER seçici: default (env yok) = playwright_stealth
    # (bugünkü davranış); invisible/cloak yalnız binary operator tarafından
    # gösterildiyse available; kullanılamayan seçim dürüst loglanır ve tarama
    # stealthsiz devam eder (sahte gizlilik iddiası yok).
    from agent_core.services.stealth_provider import (
        apply_page_stealth,
        browser_kind,
        launch_overrides,
        resolve_stealth,
        use_invisible_module,
    )
    selection = resolve_stealth()
    emit("INFO", "STEALTH provider=%s available=%s%s" % (
        selection.provider, selection.available,
        (" reason=" + selection.reason) if selection.reason else "",
    ))

    if use_invisible_module(selection):
        from invisible_playwright.async_api import async_playwright as pw_factory
    else:
        from playwright.async_api import async_playwright as pw_factory

    async with pw_factory() as p:
        browser = None
        ctx = None
        page = None
        try:
            import os
            launch_kwargs = {"headless": True, "args": ["--disable-blink-features=AutomationControlled"]}
            if browser_kind(selection) == "chromium":
                chrome_paths = [
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
                ]
                for cp in chrome_paths:
                    if os.path.exists(cp):
                        launch_kwargs["executable_path"] = cp
                        break
            launch_kwargs.update(launch_overrides(selection))

            launcher = p.firefox if browser_kind(selection) == "firefox" else p.chromium
            browser = await launcher.launch(**launch_kwargs)
            ctx_kwargs = {"user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

            from agent_core.scraper.instagram_ghost import InstagramGhostScraper
            ctx = await browser.new_context(**ctx_kwargs)
            if cookie and "sessionid" in cookie:
                parsed = []
                for part in cookie.split(";"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        parsed.append({"name": k.strip(), "value": v.strip(), "domain": ".instagram.com", "path": "/"})
                if parsed:
                    await ctx.add_cookies(parsed)

            page = await ctx.new_page()
            # [FAZ 5] Yalnız page-bazlı sağlayıcı (playwright_stealth) burada
            # uygulanır; launch-level (invisible/cloak) başlatım katmanındadır.
            # Uygulama başarısızsa dürüst loglanır ve tarama stealthsiz sürer.
            if selection.kind == "page" and selection.available:
                applied, note = await apply_page_stealth(selection, page)
                if not applied:
                    emit("WARNING", f"STEALTH apply başarısız: {note}")
            ig_scraper = InstagramGhostScraper(vault_cookies={"sessionid": cookie} if cookie else None)
            ig_data = await ig_scraper.scrape_async(username, playwright_page=page)

            # [AUDIT P1-7] Anti-halüsinasyon kapısı ÜRETİMDE devrede (bkz.
            # check_scrape_confidence): kanıt zayıfsa düşük güvenli profil
            # yerine InsufficientEvidenceError -> görev HALT.
            check_scrape_confidence(ig_scraper, ig_data, emit)

            # [FAZ 1] Zamansal kapsama telemetrisi (salt gözlem; eşik/davranış değişmez).
            try:
                _posts = ig_data.posts or []
                _dated = sum(1 for p in _posts if p.taken_at is not None)
                _coverage = ig_scraper.temporal_coverage(ig_data)
                emit("INFO", f"SCRAPER TEMPORAL: {_dated}/{len(_posts)} post tarihli (kapsama {_coverage:.2f})")
            except Exception:
                logger.warning('Suppressed exception observed at agent_core/services/platform_registry.py:317 (pass)')

            # [024]/[025]/[026]: hizalı gerçek alanlar; sentetik post ÜRETİLMEZ.
            return ig_target_profile_update(ig_data)
        finally:
            for resource_name, resource in (("page", page), ("context", ctx), ("browser", browser)):
                if resource:
                    try:
                        await resource.close()
                    except Exception as cleanup_error:
                        emit("WARNING", f"SCRAPER CLEANUP: {resource_name} kapanamadı: {str(cleanup_error)[:80]}")


async def scrape_x(
    url: str,
    log: Optional[Callable[[str, str], None]] = None,
    *,
    limit: Optional[int] = None,
    vault_locked: bool = False,
    rate_ok: Optional[bool] = None,
) -> Dict[str, Any]:
    """X (Twitter) profilini kazır — **tek sahiplik** ([FAZ A · Retina]).

    Bugüne dek X'in sensörü yoktu: `effective_scraper_type` "x" döndürüyor,
    api.py ise arama snippet'lerini profil diye giydiriyordu (uydurma
    takipçi sayısı dâhil). Artık yol belli:

        platform_registry.scrape_x  →  capability spine  →  sensor.x.twscrape

    Yani X de Instagram gibi OMURGADAN geçer: kasa, hız, çocuk kilidi,
    politika kapıları ve timeout aynı yerden uygulanır. Yetenek kanıt
    üretemezse `InsufficientEvidenceError` yükselir — boş/uydurma profil
    ÜRETİLMEZ, çağıran görev dürüstçe durur.
    """
    from agent_core.scraper.instagram_ghost import InsufficientEvidenceError

    emit = log or (lambda level, msg: None)
    username = extract_x_username(url)
    if not username:
        raise InsufficientEvidenceError(
            "URL bir X PROFİLİ değil (yanlış hedef kazınmaz): "
            f"{(url or '')[:80]} — https://x.com/<kullanici> verin"
        )

    from agent_core.capabilities import CapabilityContext, bootstrap, run_capability
    from agent_core.capabilities.state import policy_state

    bootstrap()
    state = policy_state(vault_locked=vault_locked, rate_ok=rate_ok)
    result = await run_capability(
        "sensor.x.twscrape",
        CapabilityContext(
            subject=username,
            params={"limit": int(limit) if limit else 50},
        ),
        state=state,
    )

    if not result.ok:
        reason = result.unavailable_reason or "unknown"
        emit("WARNING", f"X SENSÖRÜ KANIT ÜRETEMEDİ: {reason}")

        # [FAZ A · A3] İKİNCİ OKUMA YOLU: agent-reach (harici CLI, ücretsiz).
        # twscrape hesap/kütüphane yokken X'i büsbütün kaybetmeyelim; kamuya
        # açık okuma yapılır. Zaman damgası YOKTUR — post_times boş kalır,
        # uydurma saat YAZILMAZ.
        fallback = await _x_via_agent_reach(url, username, state, emit)
        if fallback is not None:
            return fallback

        raise InsufficientEvidenceError(
            f"X sensörü kanıt üretemedi ({reason}); profil uydurulmadı."
        )

    series = list((result.payload or {}).get("series") or [])
    if not series:
        raise InsufficientEvidenceError(
            "X sensörü gönderi üretemedi (boş akış); profil uydurulmadı."
        )

    emit("INFO", f"SCRAPER X: {len(series)} gönderi (twscrape, gerçek zaman damgalı)")
    return x_target_profile_update(username, series)


async def _x_via_agent_reach(
    url: str,
    username: str,
    state: Any,
    emit: Callable[[str, str], None],
) -> Optional[Dict[str, Any]]:
    """X için ikinci okuma yolu: `sensor.web.agent_reach` (harici CLI, ücretsiz).

    twscrape yoksa/reddedilirse devreye girer. Çıktıda zaman damgası yoktur:
    frequency motoru için veri ÜRETMEYİZ, yalnız gerçek okunan metni taşırız.
    CLI kurulu değilse (varsayılan) sessizce `None` döner — kapı ayrıdır
    (`ENABLE_AGENT_REACH`), yani kurulmadan hiçbir şey değişmez.
    """
    from agent_core.capabilities import CapabilityContext, bootstrap, run_capability

    try:
        bootstrap()
        result = await run_capability(
            "sensor.web.agent_reach",
            CapabilityContext(subject=url),
            state=state,
        )
    except Exception as exc:  # yedek yol asıl kararı bozmasın
        emit("WARNING", f"AGENT-REACH yedeği koşamadı: {type(exc).__name__}")
        return None

    if not result.ok or not result.items:
        return None

    text = (result.items[0].content or "").strip()
    if not text:
        return None

    emit("INFO", f"SCRAPER X: agent-reach ile kamuya açık okuma ({len(text)} karakter)")
    profile = x_target_profile_update(username, [{"text": text, "created_at": ""}])
    profile["sensor"] = "agent_reach"
    profile["sensor_note"] = (
        "X akışı twscrape ile okunamadı; agent-reach ikinci yolu kullanıldı "
        "(zaman damgası yok — frequency motoru için veri üretilmedi)."
    )
    return profile


def x_target_profile_update(username: str, series: List[Dict[str, Any]]) -> Dict[str, Any]:
    """X gönderi serisini `target_profile` alanlarına çevirir.

    Sözleşme (sahte veri YASAK):
    - `post_times` GERÇEK zaman damgalarından gelir — Instagram yoluyla aynı
      hizada; frequency engine artık X için de gerçek veri görür.
    - `followers`/`following` ÖLÇÜLMEDİYSE `None` durur (0 = ölçüm, None =
      ölçülmedi; eski yolun uydurma 150'ü burada yoktur).
    - `bio` BOŞ kalır: X akışından biyografi çıkarılmadıysa "" yazılır,
      arama snippet'i biyografi diye sunulmaz.
    """
    posts: List[str] = []
    post_times: List[str] = []
    posts_meta: List[Dict[str, Any]] = []
    for entry in series:
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        posts.append(text)
        post_times.append(entry.get("created_at") or "")
        posts_meta.append(
            {
                "like_count": entry.get("like_count"),
                "comment_count": entry.get("reply_count"),
                "retweet_count": entry.get("retweet_count"),
                "quote_count": entry.get("quote_count"),
            }
        )

    return {
        "username": "@" + username.lstrip("@"),
        "name": username.lstrip("@"),
        "bio": "",
        "posts": posts,
        "post_times": post_times,
        "posts_meta": posts_meta,
        "post_types": ["text" for _ in posts],
        "images": [],
        "followers": None,   # ölçülmedi — uydurma sayı YOK
        "following": None,   # ölçülmedi
        "is_private": None,  # akış okunduysa False, aksi halde bilinmiyor
        "platform": "x",
    }


def build_user_context(
    rituals: List[str],
    playlist: List[str],
    envies: List[str],
) -> Dict[str, Any]:
    """Kullanıcı girdisinden payload'ın user_profile/user_context bölümlerini
    kurar ([009] sözleşmesi: boş girdi -> boş liste; örnek/placeholder ÜRETİLMEZ)."""
    return {
        "user_profile": {
            "private_rituals": rituals or [],
            "late_night_playlist": playlist or [],
            "secret_envies": envies or [],
        },
        "user_context": {
            "rituals": ", ".join(rituals or []),
            "playlist": ", ".join(playlist or []),
            "envies": ", ".join(envies or []),
        },
    }
