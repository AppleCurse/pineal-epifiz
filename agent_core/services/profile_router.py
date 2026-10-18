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
    diğer                     → yol yok + sebep
"""

from __future__ import annotations

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

#: X'in rezerv yolları (giriş, keşfet...) — `platform_registry` de eler.
_LINKEDIN_PREFIXES = ("in", "pub", "company", "school", "showcase")

_GENERIC_SOCIAL_RESERVED = frozenset({
    "login", "logout", "signup", "register", "explore", "search", "settings",
    "privacy", "policy", "terms", "help", "about", "home", "messages",
    "notifications", "feed", "watch", "live", "foryou", "following",
    "trending", "topics", "collections", "events", "marketplace", "directory",
    "videos", "clips", "shots", "galleries", "pin", "ideas", "today",
})

_KNOWN_SOCIAL_DOMAINS = (
    "instagram.com", "instagr.am", "x.com", "twitter.com",
    "linkedin.com", "facebook.com", "fb.com", "tiktok.com",
    "youtube.com", "threads.net", "github.com", "reddit.com",
    "pinterest.com", "twitch.tv", "t.me", "telegram.me",
    "vk.com", "medium.com", "snapchat.com", "steamcommunity.com",
    "linktr.ee", "behance.net", "dribbble.com",
)


def _is_domain(host: str, *domains: str) -> bool:
    return any(host == d or host.endswith(f".{d}") for d in domains)


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
    """Sosyal medya profil URL'si → ``extractor.identity.socid``."""
    host = _host(url)
    segments = _segments(url)
    if not segments:
        return None
    first = segments[0]
    first_low = first.lower()
    handle = ""
    platform = PLATFORM_SOCIAL
    if _is_domain(host, "linkedin.com"):
        if len(segments) < 2 or first_low not in _LINKEDIN_PREFIXES:
            return None
        handle = segments[1]
        platform = PLATFORM_LINKEDIN
    elif _is_domain(host, "facebook.com", "fb.com"):
        if first_low in _FACEBOOK_RESERVED:
            return None
        handle = first
    elif _is_domain(host, "reddit.com"):
        if len(segments) < 2 or first_low not in ("user", "u"):
            return None
        handle = segments[1]
    elif _is_domain(host, "youtube.com"):
        if first.startswith("@"):
            handle = first[1:]
        elif len(segments) >= 2 and first_low in ("c", "user", "channel"):
            handle = segments[1]
        else:
            return None
    elif _is_domain(host, "steamcommunity.com"):
        if len(segments) < 2 or first_low not in ("id", "profiles"):
            return None
        handle = segments[1]
    elif _is_domain(host, "snapchat.com"):
        if first_low == "add" and len(segments) >= 2:
            handle = segments[1]
        elif first.startswith("@"):
            handle = first[1:]
        else:
            return None
    elif _is_domain(host, "t.me", "telegram.me"):
        if first_low in ("joinchat", "addstickers", "share", "proxy", "iv", "login"):
            return None
        handle = segments[1] if (first_low == "s" and len(segments) >= 2) else first
    elif _is_domain(
        host,
        "tiktok.com", "threads.net", "github.com", "pinterest.com",
        "twitch.tv", "vk.com", "medium.com", "linktr.ee",
        "behance.net", "dribbble.com",
    ):
        if first_low in _GENERIC_SOCIAL_RESERVED:
            return None
        if _is_domain(host, "github.com") and len(segments) > 1:
            return None
        handle = first
    else:
        return None
    handle = handle.strip().lstrip("@")
    if not handle or "/" in handle:
        return None
    return ProfileRoute(
        url=url,
        platform=platform,
        handle=handle,
        capability_id=CAPABILITY_SOCID,
        subject=url,
        params={"url": url},
        runnable=True,
    )


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
    host = _host(raw)
    if _is_domain(host, *_KNOWN_SOCIAL_DOMAINS):
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
