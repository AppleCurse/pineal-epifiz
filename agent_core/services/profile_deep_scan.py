"""P1 · PROFİL DERİNLEŞTİRME — bulunan profilleri yeteneklerle gerçekten kazı.

Neden (denetim 2026-10-16 · Bulgu 1 + Bulgu 3):
    Bulunan profil URL'leri hiçbir yere deşilmiyordu. Bu modül, URL'leri
    :mod:`agent_core.services.profile_router` ile sınıflandırıp **ilgili
    yeteneği** ``CapabilityRunner`` üzerinden koşar ve sonucu üç kanala yazar:

      1. **Kanal durumu** (P0 sözleşmesi): ``ok`` / ``not_run``+sebep / ``failed``
      2. **Kanıt**: yeteneğin ürettiği ``EvidenceItem``'lar
      3. **Kazınan alanlar**: yalnız GERÇEKTEN kazanmışsa (``scraped``)

Sözleşme:
    * **Tek koşum geçidi**: ``CapabilityRunner`` (:mod:`agent_core.capabilities.runner`).
      Yetenekler doğrudan çağrılmaz; politika kapıları, çocuk kilidi ve
      timeout aynı yerden uygulanır.
    * **Egress bozulmaz**: bu modül ``httpx`` import ETMEZ; dışa çıkış yalnız
      yeteneğin kendi ``egress.open_client`` çağrısıyla olur.
    * **Kapı zayıflatılmaz**: ``state`` çağırandan gelir (kasa/hız durumu
      kaybolmaz); kapı kapalıysa yetenek koşmaz.
    * **Sessiz düşüş yok**: sensör kapalıysa ``not_run`` + makine-okunur sebep
      yazılır; ``posts`` boş kalır, snippet'a sessizce inilmez.
    * **Boş liste dönmez**: her planlanan adres için **bir** kanal satırı üretilir.
    * **Kimlik karıştırma yok**: bulunan (eşleşen) profil ile hedefin AYNI
      kişi olduğu kanıtlanmadan bulunan profilin gönderileri hedefin
      ``posts`` alanına YAZILMAZ; ``profiles`` altında AYRI tutulur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from agent_core.capabilities.base import CapabilityContext
from agent_core.capabilities.runner import CapabilityRunner
from agent_core.domain.channel_status import ChannelRun, failed, not_run, ok
from agent_core.domain.content_basis import CONTENT_BASIS_NONE, CONTENT_BASIS_PLATFORM
from agent_core.domain.evidence_models import EvidenceItem
from agent_core.services.profile_router import ProfileRoute

__all__ = [
    "CHANNEL_DEEP_SCAN",
    "DeepScanResult",
    "normalize_profile",
    "run_detected_profiles",
    "run_plan",
]

#: Derin taramanın ortak kanal adı (plan satırı başına ayrıntı `detail` içinde).
CHANNEL_DEEP_SCAN = "profile.deep_scan"

#: Platform gösterimi (kanıt/UI dili).
_PLATFORM_LABEL = {
    "instagram": "instagram",
    "x": "x",
    "linkedin": "linkedin",
    "social": "social",
}


def _channel_for(route: ProfileRoute) -> str:
    """Kanal adı: yetenek varsa yeteneğin id'si, yoksa ortak kanal."""
    return route.capability_id or CHANNEL_DEEP_SCAN


def _row_for_capability(route: ProfileRoute, result: Any) -> ChannelRun:
    """Capability sonucunu P0 kanal durumuna çevirir.

    * Yetenek koştu ve kanıt üretti → ``ok``
    * Yetenek koştu ama kanıt üretmedi → ``ok`` + "0 kanıt" (P0: "boş sonuç"
      ayrı bir hata DEĞİLDİR; "bulunamadı" demek de değildir)
    * Yetenek çalışmadı → ``not_run`` + MAKİNE-OKUNUR sebep
    * Yetenek koştu ve hata verdi → ``failed``
    """
    channel = _channel_for(route)
    available = bool(getattr(result, "available", False))
    error = getattr(result, "error", None)
    reason = getattr(result, "unavailable_reason", None) or ""
    items = list(getattr(result, "items", ()) or ())
    detail = f"{route.url} — {route.handle}" if route.handle else route.url

    if available and error is None:
        return ok(channel, detail=f"{detail} · {len(items)} kanıt")
    if error:
        return failed(channel, reason=str(error), detail=detail)
    return not_run(channel, reason=str(reason or "unavailable"), detail=detail)


def _row_for_unroutable(route: ProfileRoute) -> ChannelRun:
    """Yol bulunamadı → ``not_run`` + sebep (sessizce düşürülmez)."""
    return not_run(
        CHANNEL_DEEP_SCAN,
        reason=str(route.reason or "unsupported_platform"),
        detail=route.url,
    )


def _as_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return dict(payload)
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        try:
            return dict(payload.model_dump())
        except Exception:  # pragma: no cover - savunmacı
            return {}
    return {}


def _instagram_fragment(payload: dict[str, Any]) -> dict[str, Any]:
    """instagrapi payload'ı → hedef profil alanları (yalnız kazanılmış veri)."""
    posts: list[str] = []
    post_times: list[str] = []
    posts_meta: list[dict[str, Any]] = []
    post_types: list[str] = []
    for media in payload.get("posts") or ():
        if not isinstance(media, dict):
            continue
        caption = str(media.get("caption") or "").strip()
        posts.append(caption)
        post_times.append(str(media.get("taken_at") or ""))
        posts_meta.append(
            {
                "like_count": media.get("like_count"),
                "comment_count": media.get("comment_count"),
                "media_id": media.get("id"),
            }
        )
        post_types.append(str(media.get("media_type") or ""))
    return {
        "platform": "instagram",
        "username": str(payload.get("username") or ""),
        "bio": str(payload.get("biography") or ""),
        "posts": posts,
        "post_times": post_times,
        "posts_meta": posts_meta,
        "post_types": post_types,
        "post_evidence_types": ["platform_post" for _ in posts],
        "content_basis": CONTENT_BASIS_PLATFORM if posts else CONTENT_BASIS_NONE,
        "images": [],
        "followers": payload.get("followers"),
        "following": payload.get("following"),
        "is_private": payload.get("is_private"),
    }


def _x_fragment(payload: dict[str, Any]) -> dict[str, Any]:
    """twscrape payload'ı → hedef profil alanları (yalnız kazanılmış veri)."""
    posts: list[str] = []
    post_times: list[str] = []
    posts_meta: list[dict[str, Any]] = []
    for entry in payload.get("series") or ():
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        posts.append(text)
        post_times.append(str(entry.get("created_at") or ""))
        posts_meta.append(
            {
                "like_count": entry.get("like_count"),
                "comment_count": entry.get("reply_count"),
                "retweet_count": entry.get("retweet_count"),
                "quote_count": entry.get("quote_count"),
            }
        )
    return {
        "platform": "x",
        "username": str(payload.get("username") or ""),
        "bio": "",
        "posts": posts,
        "post_times": post_times,
        "posts_meta": posts_meta,
        "post_types": ["text" for _ in posts],
        "post_evidence_types": ["platform_post" for _ in posts],
        "content_basis": CONTENT_BASIS_PLATFORM if posts else CONTENT_BASIS_NONE,
        "images": [],
        "followers": None,
        "following": None,
        "is_private": None,
    }


def _identity_fragment(payload: dict[str, Any]) -> dict[str, Any]:
    """socid payload'ı → kimlik alanları (gönderi YOK; kanıt ayrı taşınır)."""
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        fields = {}
    return {
        "platform": "identity",
        "username": "",
        "bio": "",
        "posts": [],
        "post_times": [],
        "posts_meta": [],
        "post_types": [],
        "post_evidence_types": [],
        "content_basis": CONTENT_BASIS_NONE,
        "images": [],
        "followers": None,
        "following": None,
        "is_private": None,
        "identity_fields": fields,
    }


def normalize_profile(capability_id: str, payload: Any) -> dict[str, Any]:
    """Yetenek payload'ını **ortak** hedef profil parçasına çevirir.

    Dönen sözlük ``target_profile`` alan sözleşmesine uyar
    (``posts``/``post_times``/``posts_meta``/``post_types``/
    ``post_evidence_types``/``content_basis``/``followers``/...). Bilinmeyen
    yetenek için boş (ama GEÇERLİ) parça döner — veri uydurulmaz.
    """
    data = _as_dict(payload)
    if capability_id == "sensor.ig.instagrapi":
        return _instagram_fragment(data)
    if capability_id == "sensor.x.twscrape":
        return _x_fragment(data)
    if capability_id == "extractor.identity.socid":
        return _identity_fragment(data)
    return _identity_fragment({})


@dataclass
class DeepScanResult:
    """Derin taramanın toplu sonucu."""

    channel_runs: list[ChannelRun] = field(default_factory=list)
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    #: url → yeteneğin ürettiği ham payload (yalnız GERÇEKTEN koşanlar)
    scraped: dict[str, Any] = field(default_factory=dict)
    #: url → çalıştırılan yeteneğin id'si
    capability_used: dict[str, str] = field(default_factory=dict)
    #: url → normalize edilmiş profil parçası (yalnız GERÇEKTEN koşanlar)
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: sınıflandırma planı (url → yol) — sıra korunur
    plan: list[ProfileRoute] = field(default_factory=list)

    @property
    def scanned_urls(self) -> list[dict[str, Any]]:
        """UI/telemetri için düz liste (kanal + sebep + gönderi sayısı).

        Her plan satırı için **bir** kayıt üretilir (koşan da koşmayan da):
        "bulunamadı" ile "koşmadı" ayrımı kaybolmaz.
        """
        rows: list[dict[str, Any]] = []
        for index, route in enumerate(self.plan):
            run = self.channel_runs[index] if index < len(self.channel_runs) else None
            fragment = self.profiles.get(route.url) or {}
            rows.append(
                {
                    "url": route.url,
                    "platform": _PLATFORM_LABEL.get(route.platform, route.platform),
                    "handle": route.handle,
                    "capability_id": route.capability_id or None,
                    "status": run.status if run is not None else "not_run",
                    "reason": run.reason if run is not None else "not_planned",
                    "detail": run.detail if run is not None else None,
                    "post_count": len(fragment.get("posts") or []),
                }
            )
        return rows

    def has_evidence(self) -> bool:
        return bool(self.evidence_items)


async def run_plan(
    routes: Sequence[ProfileRoute],
    *,
    state: Any = None,
    runner: CapabilityRunner | None = None,
) -> DeepScanResult:
    """Yol planını yetenekler üzerinden koşar (kanal + kanıt + kazınan alanlar).

    Args:
        routes: :func:`agent_core.services.profile_router.plan_for_urls` çıktısı.
        state: :func:`agent_core.capabilities.state.policy_state` çıktısı —
            çağıranın kasa/hız durumu **aktarılır** (kapı zayıflatılmaz).
        runner: test için sahte koşucu (varsayılan: gerçek ``CapabilityRunner``).
    """
    active = runner if runner is not None else CapabilityRunner()
    out = DeepScanResult()

    if runner is None:
        # Kayıtlı yetenekler boşsa koşum "capability yok" diye bitecek:
        # omurga kaydı TEK yoldan yapılır (registry.bootstrap).
        from agent_core.capabilities import bootstrap

        bootstrap()

    for route in routes or ():
        out.plan.append(route)
        if not getattr(route, "runnable", False):
            out.channel_runs.append(_row_for_unroutable(route))
            continue

        ctx = CapabilityContext(
            subject=str(getattr(route, "subject", "") or ""),
            params=dict(getattr(route, "params", {}) or {}),
        )
        result = await active.run(route.capability_id, ctx, state=state)

        out.channel_runs.append(_row_for_capability(route, result))
        items = list(getattr(result, "items", ()) or ())
        if items:
            out.evidence_items.extend(items)
        payload = getattr(result, "payload", None)
        if getattr(result, "available", False) and payload is not None:
            out.scraped[route.url] = payload
            out.capability_used[route.url] = route.capability_id
            out.profiles[route.url] = normalize_profile(route.capability_id, payload)

    return out


async def run_detected_profiles(
    urls: Iterable[str],
    *,
    state: Any = None,
    limit: int = 3,
    runner: CapabilityRunner | None = None,
) -> DeepScanResult:
    """Bulunan profil URL'lerini sınıflandırır ve **gerçekten** kazıma yollar.

    Boş URL listesi → boş sonuç döner (çağıran bunu "kanal çalışmadı" diye
    raporlamak zorunda değil; raporlayan yol kendi kanal satırını yazar).
    """
    from agent_core.services.profile_router import plan_for_urls

    routes = plan_for_urls(urls, limit=limit)
    if not routes:
        return DeepScanResult()
    return await run_plan(routes, state=state, runner=runner)
