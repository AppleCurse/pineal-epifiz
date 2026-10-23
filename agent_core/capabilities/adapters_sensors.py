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
import logging
import os
import shlex
import shutil
import signal
import subprocess
from urllib.parse import urlsplit
from typing import Any

from agent_core.capabilities.egress import httpx, open_client  # noqa: F401  (test yamaları httpx adını modulede bekler)

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

_AGENT_REACH_ALLOWED_DOMAINS = (
    "x.com",
    "twitter.com",
    "reddit.com",
    "youtube.com",
    "youtu.be",
    "github.com",
    "bilibili.com",
)
_AGENT_REACH_MAX_STDOUT_BYTES = 1_000_000
_AGENT_REACH_MAX_STDERR_BYTES = 64_000

__all__ = [
    "XTwscrapeCapability",
    "InstagrapiCapability",
    "AgentReachCapability",
    "SearXNGCapability",
]


def _truncate(value: str, limit: int = 480) -> str:
    text = (value or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


#: [P0 · DENETİM 2026-10-16 · Bulgu B-4] twscrape `API()` varsayılan olarak
#: ÇALIŞMA DİZİNİNE `accounts.db` yazıyordu → depo kökü kirleniyordu
#: (envanter testi kırmızıya dönüyordu). Yol artık YAPILANDIRILABİLİR:
#:   * `PINEAL_X_ACCOUNTS_DB` → tam yol (en yüksek öncelik)
#:   * varsayılan → `./cache/x_accounts.db` (`.gitignore`'daki `cache/` altında)
_X_ACCOUNTS_DB_ENV = "PINEAL_X_ACCOUNTS_DB"
_X_ACCOUNTS_DB_DEFAULT = os.path.join("cache", "x_accounts.db")


def _x_accounts_db_path() -> str:
    """twscrape hesap havuzu DB yolunu çözer (varsayılan: cache/ altında)."""
    configured = (os.getenv(_X_ACCOUNTS_DB_ENV) or "").strip()
    path = configured or _X_ACCOUNTS_DB_DEFAULT
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    return path


async def _x_pool_state(api: Any) -> dict[str, Any] | None:
    """Hesap havuzunun gerçek durumunu ölçer (aktif oturum sayısı).

    Havuz boşsa "hedef yok" değil, "oturum yok" denmelidir.

    ``None`` döner → havuz ÖLÇÜLEMEDİ (ör. `pool` parametresini kabul etmeyen
    bir sahte/eskiden kalan twscrape). Bu durumda `no_session_pool` kapısı
    UYGULANMAZ: ölçülmeyen bir şey "yok" diye yazılmaz.
    """
    pool = getattr(api, "pool", None)
    getter = getattr(pool, "get_all", None)
    if getter is None:
        return None
    total = 0
    active = 0
    readable = True
    try:
        accounts = await getter()
    except Exception as exc:  # pragma: no cover - bozuk/eksik DB
        readable = False
        logger.debug("twscrape hesap havuzu okunamadı: %s", type(exc).__name__)
        accounts = []
    for account in accounts or ():
        total += 1
        if getattr(account, "active", False):
            active += 1
    return {
        "accounts_total": total,
        "accounts_active": active,
        "pool_readable": readable,
        "accounts_db": getattr(pool, "_db_file", "") or "",
    }


def _make_twscrape_api(API: Any, db_path: str) -> Any:
    """twscrape API nesnesini kurar — hesap DB'si yapılandırılabilir yoldadır.

    `pool` parametresini kabul etmeyen (sahte/eskiden kalan) uygulamalar için
    geriye dönük uyum: sıradan kurucuya düşülür.
    """
    try:
        return API(pool=db_path)
    except TypeError:
        logger.debug("twscrape API 'pool' parametresini kabul etmiyor; varsayılan kurucu kullanılıyor")
        return API()


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
        # [2026-10-23 · B1/B2 DERSİ] `availability()` KAPI kararı VERMEZ:
        # `ENABLE_X_SENSOR` kararı `PolicyKernel`'e aittir (tek gerçek).
        # Burada iki kez kontrol edilince onayla açılan kapı yine
        # `gate_disabled` dönüyordu — yetenek "açık" görünürken kalıcı kapalı.
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
            api = _make_twscrape_api(API, _x_accounts_db_path())
            # [P0 · DENETİM 2026-10-16 · Bulgu B-1] Boş hesap havuzunda
            # twscrape "kullanıcı yok" (user_not_found) döner — bu YANLIŞTIR:
            # hedef değil, oturum havuzu yok. Kaynak gerçeği ayrı kanal olarak
            # ölçülür: havuz boşsa sebep `no_session_pool` olur.
            pool_state = await _x_pool_state(api)
            if pool_state is not None and pool_state["accounts_active"] == 0:
                return CapabilityResult(
                    capability_id=self.id,
                    available=False,
                    unavailable_reason="no_session_pool",
                    error=None,
                    notes={
                        "accounts_total": pool_state["accounts_total"],
                        "accounts_active": 0,
                        "accounts_db": pool_state["accounts_db"],
                    },
                )
            user = await api.user_by_login(username)
            if user is None:
                return CapabilityResult(
                    capability_id=self.id, available=False, unavailable_reason="user_not_found"
                )
            # [2026-10-23 · KABLO] Profil biyografisi taşınır: içindeki adresler
            # (`detected_urls`) derin taramaya gider. twscrape sürümleri alanı
            # `description` ya da `rawDescription` diye adlandırıyor; ikisi de
            # yoksa "" (uydurma biyografi YOK).
            bio = str(
                getattr(user, "description", "") or getattr(user, "rawDescription", "") or ""
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
            payload={
                "platform": "x",
                "username": username,
                "series": series,
                "bio": bio,
            },
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
        # [2026-10-23] Kapı kararı `PolicyKernel`'de (bkz. X sensörü notu).
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
        # [2026-10-23 · TEK AYAR] Ghost kazıyıcı ve bu ikinci kaynak AYNI
        # operatör tavanını kullanır (`PINEAL_IG_MAX_POSTS`, varsayılan 48).
        # Önceden ghost 12, bu yol 20 ile sabitti: iki yol farklı sınırla aynı
        # işi yapıyordu. Çağıran `limit` verirse o kazanır.
        from agent_core.scraper.instagram_ghost import _ig_max_posts

        limit = int(ctx.params.get("limit") or _ig_max_posts())

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


def agent_reach_command() -> list[str] | None:
    """agent-reach CLI'ını çözer: önce ``PINEAL_AGENT_REACH_CMD``, sonra PATH.

    [2026-10-14 · CANLI KANIT] Neden env gerekli: RUNBOOK'taki
    ``npm i -g agent-reach`` komutu artık AYNI ADLI BAŞKA bir projeyi kuruyor
    (Nostr ajan ağı; ölçüldü: npm agent-reach@0.3.4). Kör
    ``shutil.which("agent-reach")`` yanlış aracı "hazır" sayabilir. Operatör
    gerçek CLI'ın yolunu açıkça işaret eder; eski davranış (PATH araması)
    korunur — tıpkı ``PINEAL_HARVESTER_CMD`` / ``PINEAL_TRANSCRIBE_CMD`` gibi.
    """
    raw = os.getenv("PINEAL_AGENT_REACH_CMD", "").strip()
    if raw:
        try:
            parts = shlex.split(raw)
        except ValueError:
            return None  # bozuk tırnak: PATH'e düşmeyiz
        if not parts:
            return None
        head = parts[0]
        if os.path.isabs(head) or "/" in head or "\\" in head:
            return parts if os.path.exists(head) else None
        return parts if shutil.which(head) else None
    found = shutil.which("agent-reach")
    return [found] if found else None


# ----------------------------------------------------------- Agent-Reach
class AgentReachCapability(BaseCapability):
    """Agent-Reach (MIT) — Twitter/Reddit/YouTube/GitHub/Bilibili okuma, ücretsiz.

    Harici CLI olarak çağrılır (`agent-reach read <url>`): kod Pineal'e gömülmez.
    Çocuk süreç ayrı argümanlarla başlatılır; URL yalnız desteklenen public host
    allowlist'inden geçer. CLI'ın kendi DNS/redirect trafiği pinlenemediğinden,
    bu yetenek yalnız operatörün ENABLE_AGENT_REACH opt-in'iyle çalışır.
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
        if agent_reach_command() is None:
            return Availability.unavailable("dependency_missing:agent-reach")
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        raw_target = ctx.subject or ctx.params.get("url") or ""
        if not isinstance(raw_target, str):
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="invalid_target"
            )
        target = raw_target.strip()
        if not target or len(target) > 2048:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="invalid_target"
            )
        try:
            parsed = urlsplit(target)
            _ = parsed.port
            host = (parsed.hostname or "").rstrip(".").lower()
        except ValueError:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="invalid_target"
            )
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not host
            or parsed.username is not None
            or parsed.password is not None
        ):
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="invalid_target"
            )
        if not any(host == domain or host.endswith(f".{domain}") for domain in _AGENT_REACH_ALLOWED_DOMAINS):
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="unsupported_host"
            )
        from agent_core.utils.security import is_safe_url

        if not await asyncio.to_thread(is_safe_url, target):
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="ssrf_blocked"
            )
        command = agent_reach_command()
        if command is None:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason="dependency_missing:agent-reach",
            )

        class _OutputLimitExceeded(Exception):
            pass

        proc = None
        reader_tasks: list[asyncio.Task] = []

        async def read_limited(stream, maximum: int) -> bytes:
            output = bytearray()
            while True:
                chunk = await stream.read(min(65_536, maximum + 1 - len(output)))
                if not chunk:
                    return bytes(output)
                output.extend(chunk)
                if len(output) > maximum:
                    raise _OutputLimitExceeded()

        async def stop_process() -> None:
            if proc is None:
                return
            if proc.returncode is None:
                try:
                    pid = getattr(proc, "pid", None)
                    if os.name != "nt" and pid is not None:
                        os.killpg(pid, signal.SIGKILL)
                    else:
                        proc.kill()
                except ProcessLookupError:
                    pass
                except OSError:
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
            for task in reader_tasks:
                if not task.done():
                    task.cancel()
            if reader_tasks:
                await asyncio.gather(*reader_tasks, return_exceptions=True)
            if proc.returncode is None:
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except BaseException:
                    pass

        try:
            loop = asyncio.get_running_loop()
            started = loop.time()
            process_options = {
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.PIPE,
            }
            if os.name == "nt":
                process_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                process_options["start_new_session"] = True
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *command, "read", target, **process_options
                ),
                timeout=self.timeout_seconds,
            )
            if proc.stdout is None or proc.stderr is None:
                raise RuntimeError("agent-reach output pipes unavailable")
            remaining = max(0.001, self.timeout_seconds - (loop.time() - started))
            reader_tasks = [
                asyncio.create_task(read_limited(proc.stdout, _AGENT_REACH_MAX_STDOUT_BYTES)),
                asyncio.create_task(read_limited(proc.stderr, _AGENT_REACH_MAX_STDERR_BYTES)),
                asyncio.create_task(proc.wait()),
            ]
            # [E7-muaf] The outer process boundary translates reader exceptions
            # (including output-limit violations) into an unavailable result.
            stdout, stderr, _ = await asyncio.wait_for(
                asyncio.gather(*reader_tasks), timeout=remaining
            )
        except asyncio.CancelledError:
            try:
                await asyncio.shield(stop_process())
            except BaseException:
                pass
            raise
        except asyncio.TimeoutError:
            await stop_process()
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="timeout"
            )
        except FileNotFoundError:
            await stop_process()
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason="dependency_missing:agent-reach",
            )
        except _OutputLimitExceeded:
            await stop_process()
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="output_too_large"
            )
        except Exception as exc:
            await stop_process()
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason="process_error",
                error=type(exc).__name__,
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

        try:
            raw_max_chars = ctx.params.get("max_chars") or 20_000
            max_chars = 20_000 if isinstance(raw_max_chars, bool) else int(raw_max_chars)
        except (TypeError, ValueError):
            max_chars = 20_000
        max_chars = max(1, min(max_chars, 100_000))
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
        raw_query = ctx.subject or ctx.params.get("query") or ""
        if not isinstance(raw_query, str):
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="invalid_query"
            )
        query = raw_query.strip()
        if not query or len(query) > 1000:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="invalid_query"
            )
        base = os.environ["SEARXNG_BASE_URL"].rstrip("/")
        try:
            limit = int(ctx.params.get("limit") or 10)
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(limit, 50))

        try:
            async with open_client(
                purpose="sensor",
                target=base,
                timeout=self.timeout_seconds,
                trust_env=False,
                follow_redirects=False,
            ) as client:
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
        except (ValueError, UnicodeDecodeError):
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="invalid_json"
            )

        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="invalid_response"
            )
        results = payload["results"][:limit]
        items = []
        for row in results:
            if not isinstance(row, dict):
                continue
            raw_url = row.get("url")
            raw_title = row.get("title")
            raw_content = row.get("content")
            url = raw_url.strip() if isinstance(raw_url, str) else ""
            title = raw_title.strip() if isinstance(raw_title, str) else ""
            content_source = raw_content if isinstance(raw_content, str) and raw_content.strip() else title
            content = content_source.strip() if isinstance(content_source, str) else ""
            try:
                parsed_url = urlsplit(url)
                _ = parsed_url.port
                valid_url = (
                    parsed_url.scheme.lower() in {"http", "https"}
                    and bool(parsed_url.hostname)
                    and parsed_url.username is None
                    and parsed_url.password is None
                )
            except ValueError:
                valid_url = False
            if not valid_url or not content:
                continue
            url = parsed_url.geturl()
            items.append(
                make_evidence(
                    content=_truncate(content),
                    source_engine="searxng",
                    epistemic_type="observation",
                    provenance_refs=[url],
                    scope={"kind": "search_result", "title": title},
                    source_metrics={"engine": row.get("engine")},
                )
            )

        if results and not items:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="invalid_results"
            )

        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=tuple(items),
            payload={"query": query, "count": len(items), "results": results},
            notes={"count": len(items)},
        )
