"""P1 · PROFİL YÖNLENDİRME — bulunan URL → doğru yetenek.

Neden (denetim 2026-10-16 · Bulgu 1 + Bulgu 3):
    Arama sonucunda bulunan profil URL'leri toplanıyordu
    (``backend/api.py`` → ``found_profiles`` → ``target_profile.detected_urls``)
    ama **hiçbir sensöre/ajan gitmiyordu**: yalnız ekranda chip olarak
    listeleniyordu. Aynı anda ``extractor.identity.socid`` capability'si
    **ölü kod**du (tek eşleşme: tanım satırı).

    Bu modül iki işi birden yapar:
      1. Bir profil URL'sini **doğru yeteneğe** bağlar (saf sınıflandırma).
      2. Yeteneğin çağrı sözleşmesini (hangi parametre, hangi konu) **yanında**
         taşır; koşum modülü jenerik kalır.

Sözleşme:
    * **SAF**: ağ çağrısı YOK, dosya yazımı YOK, global durum YOK.
    * Sınıflandırma **host** tabanlıdır (alt dize eşleşmesi değil):
      ``instagram.com.evil.example`` bir Instagram profili DEĞİLDİR.
    * Profil OLMAYAN adres (etiket, gönderi, giriş, rezerv yol) **yol yok**
      olarak döner: ``runnable=False`` + ``reason`` (sessizce düşürülmez).
    * Platform sınıflandırması ``agent_core.services.platform_registry``
      tarafından yapılır; burada **kopya yazılmaz** (tek doğruluk kaynağı).

Yol tablosu (tasarım kararı):
    instagram profil URL'si   → ``sensor.ig.instagrapi``
    x / twitter profil URL'si → ``sensor.x.twscrape``
    linkedin / facebook profil → ``extractor.identity.socid``
    diğer bilinen sosyal profil URL'leri (tiktok, youtube, threads,
    github, reddit, pinterest, twitch, telegram, medium, vk,
    snapchat, steam, behance, dribbble, linktr.ee) → ``extractor.identity.socid``
    diğer                     → yol yok + sebep
"""

from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict

from agent_core.services.platform_registry import extract_username, extract_x_username

__all__ = [
    "CAPABILITY_INSTAGRAM",
    "CAPABILITY_SOCID",
    "CAPABILITY_X",
    "PLATFORM_INSTAGRAM",
    "PLATFORM_LINKEDIN",
    "PLATFORM_SOCIAL",
    "PLATFORM_UNSUPPORTED",
    "PLATFORM_X",
    "REASON_NOT_A_PROFILE",
    "REASON_UNSUPPORTED",
    "ProfileRoute",
    "classify_url",
    "plan_for_urls",
]

CAPABILITY_INSTAGRAM = "sensor.ig.instagrapi"
CAPABILITY_SOCID = "extractor.identity.socid"
CAPABILITY_X = "sensor.x.twscrape"

PLATFORM_INSTAGRAM = "instagram"
PLATFORM_LINKEDIN = "linkedin"
PLATFORM_SOCIAL = "social"
PLATFORM_UNSUPPORTED = "unsupported"
PLATFORM_X = "x"

REASON_NOT_A_PROFILE = "not_a_profile_url"
REASON_UNSUPPORTED = "unsupported_platform"

#: Profil olmayan yol segmentleri (Facebook/LinkedIn) — yanlış hedef yasağı.
_FACEBOOK_RESERVED = frozenset({
    "login", "logout", "signup", "pages", "groups", "events", "marketplace",
    "watch", "help", "privacy", "policy", "terms", "settings", "home",
    "profile.php", "photo.php", "share.php", "search", "messages", "friends",
})

#: X'in rezerv yolları (giriş, keşfet...) — ``platform_registry`` de eler.
_LINKEDIN_PREFIXES = ("in", "pub", "company", "school", "showcase")

#: [P10 · 2026-10-18] Çapraz platform profil tablosu.
#: Her satır: (host sonu, iki segmentli profil önekleri, rezerv
#: kelimeler, platform etiketi).
#:
#: Biçim kuralları (fail-closed — shape bilinmiyorsa kabul YOK):
#:   * Tek segment            → ``host/kullanici`` (facebook, tiktok,
#:     github, pinterest, twitch, medium, vk, snapchat, behance,
#:     dribbble, linktr.ee, telegram; ``@`` ön eki de kabul edilir)
#:   * Önek kümesi boş değil  → ``host/öneki/kullanici``
#:     (linkedin ``in/``, reddit ``user/``, snapchat ``add/``,
#:     steam ``id|profiles/``, youtube ``c|user|channel/``)
#: * Eşleşme TAM EŞİTTİR ya da ``.son`` sonekıyladır:
#:   ``evilinkedin.com`` linkedin DEĞİLDİR (N4 dersinin çapraz
#:   platform geneli; [023] yanlış hedef yasağı).
#: * Rezerv kelimeler profil OLMAYAN yolları reddeder (login, watch,
#:   tag, user...): kullanıcı adı shape'ı da charset ile sınırlanır.
_SOCIAL_HANDLE_RE = re.compile(r"^[A-Za-z0-9._-]{1,39}$")

_TIKTOK_RESERVED = frozenset({
    "login", "signup", "trending", "discover", "explore", "upload",
    "settings", "tag", "video", "music", "search", "live", "about",
})
_YOUTUBE_RESERVED = frozenset({
    "watch", "shorts", "results", "feed", "playlists", "trending",
    "live", "login", "signup", "settings", "search", "about",
    # kendi önek kelimeleri: host/c tek segmenti profil DEĞİL
    "c", "user", "channel",
})
_YOUTUBE_PREFIXES = ("c", "user", "channel")
_THREADS_RESERVED = frozenset({"login", "signup", "explore", "settings", "search"})
_GITHUB_RESERVED = frozenset({
    "login", "signup", "features", "settings", "explore", "marketplace",
    "topics", "collections", "organizations", "site", "pricing",
    "security", "join", "about", "blog", "readme", "new", "pulls",
    "issues", "sponsors",
})
_PINTEREST_RESERVED = frozenset({
    "login", "signup", "explore", "create", "search", "pin-builder",
    "about", "business", "careers",
})
_TWITCH_RESERVED = frozenset({
    "directory", "discover", "login", "signup", "settings", "products",
    "brand", "careers", "creator-dashboard", "moderation", "dashboard",
    "search", "videos", "top",
})
_MEDIUM_RESERVED = frozenset({
    "login", "signup", "topics", "tag", "search", "write", "newsletter",
    "about", "policies",
})
_VK_RESERVED = frozenset({"login", "signup", "feed", "messages", "settings", "help", "search", "about"})
_LINKEDIN_RESERVED = frozenset({
    "login", "signup", "help", "settings", "search", "jobs", "talent",
    "sales", "learning", "events", "groups", "articles", "pulse",
    "directory",
    # kendi önek kelimeleri: host/in tek segmenti profil DEĞİL
    "in", "pub", "company", "school", "showcase",
})
_BEHANCE_RESERVED = frozenset({"login", "signup", "explore", "search", "about", "careers", "blog"})
_DRIBBBLE_RESERVED = frozenset({"login", "signup", "shots", "explore", "search", "about", "blog", "jobs", "designers"})
_LINKTREE_RESERVED = frozenset({"login", "signup", "pricing", "features", "about"})
_TELEGRAM_RESERVED = frozenset({"login", "signup", "s"})  # /s/ herkese açık grup ≠ profil

_SOCIAL_HOST_TABLE: tuple[tuple[str, tuple[str, ...], frozenset[str], str], ...] = (
    ("linkedin.com", _LINKEDIN_PREFIXES, _LINKEDIN_RESERVED, PLATFORM_LINKEDIN),
    ("facebook.com", (), _FACEBOOK_RESERVED, PLATFORM_SOCIAL),
    ("fb.com", (), _FACEBOOK_RESERVED, PLATFORM_SOCIAL),
    ("tiktok.com", (), _TIKTOK_RESERVED, PLATFORM_SOCIAL),
    ("youtube.com", _YOUTUBE_PREFIXES, _YOUTUBE_RESERVED, PLATFORM_SOCIAL),
    ("threads.net", (), _THREADS_RESERVED, PLATFORM_SOCIAL),
    ("threads.com", (), _THREADS_RESERVED, PLATFORM_SOCIAL),
    ("github.com", (), _GITHUB_RESERVED, PLATFORM_SOCIAL),
    ("reddit.com", ("user",), frozenset({"user"}), PLATFORM_SOCIAL),
    ("pinterest.com", (), _PINTEREST_RESERVED, PLATFORM_SOCIAL),
    ("twitch.tv", (), _TWITCH_RESERVED, PLATFORM_SOCIAL),
    ("medium.com", (), _MEDIUM_RESERVED, PLATFORM_SOCIAL),
    ("vk.com", (), _VK_RESERVED, PLATFORM_SOCIAL),
    ("snapchat.com", ("add",), frozenset({"add"}), PLATFORM_SOCIAL),
    ("steamcommunity.com", ("id", "profiles"), frozenset({"id", "profiles"}), PLATFORM_SOCIAL),
    ("behance.net", (), _BEHANCE_RESERVED, PLATFORM_SOCIAL),
    ("dribbble.com", (), _DRIBBBLE_RESERVED, PLATFORM_SOCIAL),
    ("linktr.ee", (), _LINKTREE_RESERVED, PLATFORM_SOCIAL),
    ("t.me", (), _TELEGRAM_RESERVED, PLATFORM_SOCIAL),
    ("telegram.me", (), _TELEGRAM_RESERVED, PLATFORM_SOCIAL),
)

#: Sınıflandırıcısı bilinen tüm sosyal hostları (tek kaynak: tablo + IG/X).
_KNOWN_SOCIAL_HOSTS: tuple[str, ...] = tuple(
    sorted({suffix for suffix, _, _, _ in _SOCIAL_HOST_TABLE}
           | {"instagram.com", "x.com", "twitter.com"})
)


def _host(url: str) -> str:
    """URL'den host (küçük harf, port atılmış)."""
    raw = (url or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    return (parts.hostname or "").lower().rstrip(".")


def _segments(url: str) -> list[str]:
    raw = (url or "").strip()
    if "://" not in raw:
        raw = f"https://{raw}"
    try:
        parts = urlsplit(raw)
    except ValueError:
        return []
    return [s for s in (parts.path or "").split("/") if s]


class ProfileRoute(BaseModel):
    """Bir profil URL'sinin nereye bağlanacağı (saf sınıflandırma sonucu)."""

    url: str
    platform: str = PLATFORM_UNSUPPORTED
    handle: str = ""
    capability_id: str = ""
    subject: str = ""
    params: dict[str, Any] = {}
    reason: str = ""
    runnable: bool = False

    model_config = ConfigDict(extra="forbid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "platform": self.platform,
            "handle": self.handle,
            "capability_id": self.capability_id,
            "reason": self.reason,
            "runnable": self.runnable,
        }


def _instagram_route(url: str) -> ProfileRoute | None:
    """Instagram profil URL'si → ``sensor.ig.instagrapi`` (yoksa None)."""
    username = extract_username(url)
    if not username:
        return None
    return ProfileRoute(
        url=url,
        platform=PLATFORM_INSTAGRAM,
        handle=username,
        capability_id=CAPABILITY_INSTAGRAM,
        subject=username,
        params={"username": username, "limit": 20},
        runnable=True,
    )


def _x_route(url: str) -> ProfileRoute | None:
    """X / Twitter profil URL'si → ``sensor.x.twscrape`` (yoksa None)."""
    handle = extract_x_username(url)
    if not handle:
        return None
    return ProfileRoute(
        url=url,
        platform=PLATFORM_X,
        handle=handle,
        capability_id=CAPABILITY_X,
        subject=handle,
        params={"limit": 50},
        runnable=True,
    )


def _social_route(url: str) -> ProfileRoute | None:
    """Bilinen sosyal medya profil URL'si → ``extractor.identity.socid``.

    [P10] Kabul kümesi ``_SOCIAL_HOST_TABLE``'dan gelir (tek
    doğruluk kaynağı). Eşleşme tam host + nokta sınırıdır; profil
    shape'ı (tek segment / önekli iki segment) ve rezerv kelime
    kuralları sağlanmazsa ``None`` — çağıran yolu "koşulamaz"
    olarak raporlar, tahmin üretmez.
    """
    host = _host(url)
    segments = _segments(url)
    if not segments:
        return None
    for suffix, prefixes, reserved, platform in _SOCIAL_HOST_TABLE:
        if not (host == suffix or host.endswith("." + suffix)):
            continue
        if len(segments) == 1:
            handle = segments[0].lstrip("@")
        elif (
            len(segments) == 2
            and prefixes
            and segments[0].lower() in prefixes
        ):
            handle = segments[1]
        else:
            return None
        handle = handle.strip()
        # socid profil sayfasının tam adresini ister (kimlik alanları
        # URL'den çıkarılır); handle shape'ı da doğrulanır.
        if (
            handle
            and handle.lower() not in reserved
            and _SOCIAL_HANDLE_RE.match(handle)
        ):
            return ProfileRoute(
                url=url,
                platform=platform,
                handle=handle,
                capability_id=CAPABILITY_SOCID,
                subject=url,
                params={"url": url},
                runnable=True,
            )
        return None  # host tanındı ama yol profil shape'ı değil
    return None


def classify_url(url: str) -> ProfileRoute:
    """Tek bir URL'yi sınıflandırır (ağ YOK, yan etki YOK).

    Dönen yol:
        * ``runnable=True``  → koşulabilir (capability_id + subject hazır)
        * ``runnable=False`` → yol yok; ``reason`` nedenini söyler
    """
    raw = (url or "").strip()
    if not raw:
        return ProfileRoute(url=raw, reason=REASON_UNSUPPORTED)
    if not raw.lower().startswith(("http://", "https://")):
        return ProfileRoute(url=raw, reason=REASON_NOT_A_PROFILE)

    for builder in (_instagram_route, _x_route, _social_route):
        route = builder(raw)
        if route is not None:
            return route

    # Bilinen bir platformun PROFİL OLMAYAN adresi → sebep "profil değil".
    # [P10] eşleşme tam host + nokta sınırı (N4): `evilgithub.com`
    # github'un "profil değil" raporunu aldırmayacak — bilinmeyen
    # host olarak "desteklenmiyor" der.
    host = _host(raw)
    if any(
        host == domain or host.endswith("." + domain)
        for domain in _KNOWN_SOCIAL_HOSTS
    ):
        return ProfileRoute(url=raw, platform=PLATFORM_UNSUPPORTED, reason=REASON_NOT_A_PROFILE)
    return ProfileRoute(url=raw, platform=PLATFORM_UNSUPPORTED, reason=REASON_UNSUPPORTED)


def plan_for_urls(urls: Iterable[str], *, limit: int = 3) -> list[ProfileRoute]:
    """URL listesini yol planına çevirir (tekrar yok, sıra korunur, ``limit`` uygulanır).

    Boş/tekrar eden/geçersiz adresler **sessizce atılmaz**: her biri için
    ``runnable=False`` + ``reason`` içeren bir plan satırı üretilir; çağıran
    bunları kanal defterine "koşmadı + sebep" olarak yazar.
    """
    plan: list[ProfileRoute] = []
    seen: set[str] = set()
    for raw in urls or ():
        url = (raw or "").strip()
        if not url:
            continue
        if url in seen:
            continue
        seen.add(url)
        plan.append(classify_url(url))
        if limit and len(plan) >= int(limit):
            break
    return plan
