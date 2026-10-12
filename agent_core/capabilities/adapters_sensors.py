"""FAZ A · RETİNA (2) — SENSÖRLER: X, Instagram ikinci kaynak, ücretsiz okuma.

    sensor.x.twscrape        → X/Twitter DELİĞİNİ KAPATIR (MIT, çoklu hesap
                               + gömülü rate-limit). Operatörün kendi hesabı.
    sensor.ig.instagrapi     → Instagram İKİNCİ KAYNAK (Playwright engellenirse
                               sensör düşmez). Asla birincil yol değil.
    sensor.web.agent_reach   → Twitter/Reddit/YouTube/GitHub/Bilibili okuma;
                               tek CLI, **sıfır API ücreti**.
    sensor.search.searxng    → anahtarsız metasearch (AGPL-3.0 → AYRI SERVİS;
                               kod gömülmez, yalnız HTTP ile çağrılır).

Ortak dürüstlük sözleşmesi:
- Kimlik bilgileri yalnızca env/vault'ta; log, telemetri, kanıt ve rapora
  **asla** yazılmaz.
- Kütüphane/servis/kapı yok → `available=False` + makine-okunur sebep.
- Her satır kanıt: `EvidenceItem` (kaynak bağlantısı + zaman + çıkarıcı).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from typing import Any

import httpx

from agent_core.capabilities.adapters_osint import _flag, _module_available
from agent_core.capabilities.base import (
    Availability,
    BaseCapability,
    CapabilityContext,
    CapabilityKind,
    CapabilityResult,
    make_evidence,
)

logger = logging.getLogger(__name__)

__all__ = [
    "XTwscrapeCapability",
    "InstagrapiCapability",
    "AgentReachCapability",
    "SearXNGCapability",
]


def _truncate(value: str, limit: int = 480) -> str:
    text = (value or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


# --------------------------------------------------------------------- X
class XTwscrapeCapability(BaseCapability):
    """X/Twitter sensörü — twscrape (MIT).

    K2 kararı: operatörün **kendi** hesabıyla, kayıtlı ve izlenebilir.
    Kapılar: kasa + hız + `ENABLE_X_SENSOR`.
    """

    id = "sensor.x.twscrape"
    kind = CapabilityKind.SENSOR
    license = "MIT"
    gates = frozenset({"vault", "rate", "ENABLE_X_SENSOR"})
    timeout_seconds = 60.0
    description = "X/Twitter gönderi akışı (gerçek zaman serisi; Frequency motorunu besler)."

    def availability(self) -> Availability:
        if not _flag("ENABLE_X_SENSOR"):
            return Availability.unavailable("gate_disabled:ENABLE_X_SENSOR")
        if not _module_available("twscrape"):
            return Availability.unavailable("dependency_missing:twscrape")
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        username = (ctx.subject or ctx.params.get("username") or "").strip().lstrip("@")
        if not username:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="invalid_username"
            )
        limit = int(ctx.params.get("limit") or 50)

        try:
            from twscrape import API, gather  # lazy import
        except Exception as exc:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason="dependency_missing:twscrape",
                error=type(exc).__name__,
            )

        try:
            api = API()
            user = await api.user_by_login(username)
            if user is None:
                return CapabilityResult(
                    capability_id=self.id, available=False, unavailable_reason="user_not_found"
                )
            # [E7-muaf] twscrape'in KENDİ gather'ı (asyncio değil) ve zaten
            # tek çağrı; hatası aşağıdaki try/except ile dürüst
            # CapabilityResult(available=False) hâline gelir.
            tweets = await gather(api.user_tweets(user.id, limit=limit))
        except asyncio.TimeoutError:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="timeout"
            )
        except Exception as exc:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason="scrape_error",
                error=type(exc).__name__,
            )

        items = []
        series: list[dict[str, Any]] = []
        for tweet in tweets or []:
            tweet_id = str(getattr(tweet, "id", "") or "")
            url = f"https://x.com/{username}/status/{tweet_id}" if tweet_id else ""
            date = getattr(tweet, "date", None)
            metrics = {
                "like_count": getattr(tweet, "likeCount", None),
                "retweet_count": getattr(tweet, "retweetCount", None),
                "reply_count": getattr(tweet, "replyCount", None),
                "quote_count": getattr(tweet, "quoteCount", None),
            }
            content = getattr(tweet, "rawContent", "") or ""
            if not content.strip():
                continue
            items.append(
                make_evidence(
                    content=f"X post by @{username}: {_truncate(content)}",
                    source_engine="twscrape",
                    epistemic_type="observation",
                    provenance_refs=[url] if url else [],
                    observed_at=date,
                    scope={"kind": "social_post", "platform": "x"},
                    source_metrics={"tweet_id": tweet_id, **metrics},
                )
            )
            series.append(
                {
                    "created_at": date.isoformat() if date is not None else None,
                    "text": content,
                    "url": url,
                    **metrics,
                }
            )

        if not items:
            return CapabilityResult(
                capability_id=self.id,
                available=True,
                items=(),
                notes={"empty": True},
            )

        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=tuple(items),
            payload={"platform": "x", "username": username, "series": series},
            notes={"post_count": len(items)},
        )


# ------------------------------------------------------------- Instagram
class InstagrapiCapability(BaseCapability):
    """Instagram ikinci kaynak — instagrapi.

    Birincil yol `agent_core/scraper/instagram_ghost.py` (Playwright) olarak
    kalır. Bu adaptör yalnızca yedek/çapraz teyit içindir: private API kırılgandır.
    """

    id = "sensor.ig.instagrapi"
    kind = CapabilityKind.SENSOR
    license = "NOASSERTION (yalnız ikinci kaynak; hukuki inceleme notu)"
    gates = frozenset({"vault", "rate", "ENABLE_IG_SECONDARY"})
    timeout_seconds = 90.0
    description = "Instagram ikinci kaynak: Playwright engellenirse sensör düşmez."

    def availability(self) -> Availability:
        if not _flag("ENABLE_IG_SECONDARY"):
            return Availability.unavailable("gate_disabled:ENABLE_IG_SECONDARY")
        if not _module_available("instagrapi"):
            return Availability.unavailable("dependency_missing:instagrapi")
        if not (os.getenv("IG_USERNAME", "").strip() and os.getenv("IG_PASSWORD", "")):
            return Availability.unavailable("credentials_missing:IG_USERNAME/IG_PASSWORD")
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        username = (ctx.subject or ctx.params.get("username") or "").strip().lstrip("@")
        if not username:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="invalid_username"
            )
        limit = int(ctx.params.get("limit") or 20)

        def _work() -> dict[str, Any]:
            from instagrapi import Client  # lazy import

            client = Client()
            client.login(os.environ["IG_USERNAME"], os.environ["IG_PASSWORD"])
            user_id = client.user_id_from_username(username)
            info = client.user_info(user_id)
            medias = client.user_medias(user_id, limit)
            return {
                "username": username,
                "user_id": user_id,
                "full_name": getattr(info, "full_name", "") or "",
                "biography": getattr(info, "biography", "") or "",
                "followers": getattr(info, "follower_count", None),
                "following": getattr(info, "following_count", None),
                "is_private": bool(getattr(info, "is_private", False)),
                "media_count": getattr(info, "media_count", None),
                "posts": [
                    {
                        "id": str(getattr(m, "id", "") or ""),
                        "code": getattr(m, "code", "") or "",
                        "caption": (getattr(m, "caption_text", "") or ""),
                        "taken_at": m.taken_at.isoformat() if getattr(m, "taken_at", None) else None,
                        "like_count": getattr(m, "like_count", None),
                        "comment_count": getattr(m, "comment_count", None),
                        "media_type": getattr(m, "media_type", None),
                    }
                    for m in medias or []
                ],
            }

        try:
            data = await asyncio.wait_for(
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
                unavailable_reason="scrape_error",
                error=type(exc).__name__,
            )

        profile_url = f"https://www.instagram.com/{username}/"
        bio = (data.get("biography") or "").strip()
        items = [
            make_evidence(
                content=(
                    f"Instagram profile @{username}"
                    + (f" ({data['full_name']})" if data.get("full_name") else "")
                    + (f": {_truncate(bio)}" if bio else "")
                ),
                source_engine="instagrapi",
                epistemic_type="observation",
                provenance_refs=[profile_url],
                scope={"kind": "profile", "platform": "instagram", "source_role": "secondary"},
                source_metrics={
                    "followers": data.get("followers"),
                    "following": data.get("following"),
                    "media_count": data.get("media_count"),
                    "is_private": data.get("is_private"),
                },
            )
        ]
        for post in data.get("posts") or []:
            caption = (post.get("caption") or "").strip()
            if not caption:
                continue
            url = f"https://www.instagram.com/p/{post['code']}/" if post.get("code") else profile_url
            items.append(
                make_evidence(
                    content=f"Instagram post by @{username}: {_truncate(caption)}",
                    source_engine="instagrapi",
                    epistemic_type="observation",
                    provenance_refs=[url],
                    scope={"kind": "social_post", "platform": "instagram"},
                    source_metrics={
                        "like_count": post.get("like_count"),
                        "comment_count": post.get("comment_count"),
                        "taken_at": post.get("taken_at"),
                    },
                )
            )

        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=tuple(items),
            payload=data,
            notes={"post_count": len(data.get("posts") or [])},
        )


# ----------------------------------------------------------- Agent-Reach
class AgentReachCapability(BaseCapability):
    """Agent-Reach (MIT) — Twitter/Reddit/YouTube/GitHub/Bilibili okuma, ücretsiz.

    Harici CLI olarak çağrılır (`agent-reach read <url>`): Pineal'in içine kod
    gömülmez, süreç izole kalır, API ücreti yoktur.
    """

    id = "sensor.web.agent_reach"
    kind = CapabilityKind.EXTRACTOR
    license = "MIT (harici CLI süreci)"
    gates = frozenset({"vault", "ENABLE_AGENT_REACH"})
    timeout_seconds = 60.0
    description = "Twitter/Reddit/YouTube/GitHub okuma — sıfır API ücreti (harici CLI)."

    def availability(self) -> Availability:
        if not _flag("ENABLE_AGENT_REACH"):
            return Availability.unavailable("gate_disabled:ENABLE_AGENT_REACH")
        if shutil.which("agent-reach") is None:
            return Availability.unavailable("dependency_missing:agent-reach")
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        target = (ctx.subject or ctx.params.get("url") or "").strip()
        if not target:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="invalid_target"
            )

        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "agent-reach",
                    "read",
                    target,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=self.timeout_seconds,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="timeout"
            )
        except FileNotFoundError:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason="dependency_missing:agent-reach",
            )

        if proc.returncode != 0:
            detail = (stderr or b"").decode("utf-8", "replace").strip()[:200]
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason="read_failed",
                notes={"stderr": detail},
            )

        text = (stdout or b"").decode("utf-8", "replace").strip()
        if not text:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="empty_text"
            )

        max_chars = int(ctx.params.get("max_chars") or 20_000)
        content = text if len(text) <= max_chars else text[:max_chars].rstrip() + " …[kırpıldı]"
        item = make_evidence(
            content=content,
            source_engine="agent_reach",
            epistemic_type="observation",
            provenance_refs=[target],
            scope={"kind": "web_text", "via": "agent-reach"},
            source_metrics={"chars": len(text)},
        )
        return CapabilityResult(
            capability_id=self.id, available=True, items=(item,), notes={"chars": len(text)}
        )


# -------------------------------------------------------------- SearXNG
class SearXNGCapability(BaseCapability):
    """SearXNG — anahtarsız metasearch (AGPL-3.0 → ayrı servis, kod gömülmez).

    Yalnızca HTTP ile konuşur: `SEARXNG_BASE_URL` (örn. http://127.0.0.1:8080).
    Servis yoksa dürüst `available=False`; asla boş sonuç uydurulmaz.
    """

    id = "sensor.search.searxng"
    kind = CapabilityKind.SENSOR
    license = "AGPL-3.0 (ayrı servis — kod gömülmez, HTTP ile çağrılır)"
    gates = frozenset({"vault", "ENABLE_SEARXNG"})
    timeout_seconds = 30.0
    description = "Anahtarsız metasearch; arama maliyetini ve sağlayıcı bağımlılığını kırar."

    def availability(self) -> Availability:
        if not _flag("ENABLE_SEARXNG"):
            return Availability.unavailable("gate_disabled:ENABLE_SEARXNG")
        if not os.getenv("SEARXNG_BASE_URL", "").strip():
            return Availability.unavailable("config_missing:SEARXNG_BASE_URL")
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        query = (ctx.subject or ctx.params.get("query") or "").strip()
        if not query:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="invalid_query"
            )
        base = os.environ["SEARXNG_BASE_URL"].rstrip("/")
        limit = int(ctx.params.get("limit") or 10)

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(
                    f"{base}/search",
                    params={"q": query, "format": "json", "safesearch": "0"},
                )
        except Exception as exc:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason="service_unreachable",
                error=type(exc).__name__,
            )

        if response.status_code != 200:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=f"http_{response.status_code}",
            )

        try:
            payload = response.json()
        except json.JSONDecodeError:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="invalid_json"
            )

        results = list(payload.get("results") or [])[:limit]
        items = []
        for row in results:
            url = (row.get("url") or "").strip()
            content = (row.get("content") or row.get("title") or "").strip()
            if not url or not content:
                continue
            items.append(
                make_evidence(
                    content=_truncate(content),
                    source_engine="searxng",
                    epistemic_type="observation",
                    provenance_refs=[url],
                    scope={"kind": "search_result", "title": (row.get("title") or "").strip()},
                    source_metrics={"engine": row.get("engine")},
                )
            )

        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=tuple(items),
            payload={"query": query, "count": len(items), "results": results},
            notes={"count": len(items)},
        )
