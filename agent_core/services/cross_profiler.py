"""P2 · ÇAPRAZ PROFİLLEME — farklı platform hesaplarını deterministik eşleştir.

Neden (denetim 2026-10-16 · Bulgu 4 / P2 maddesi 11):
    Denetimde çapraz profilleme kodu **YOKTU**: "farklı platform hesaplarını
    eşleştiren kod gerçekten var mı?" sorusunun cevabı hayırdı.

Bu modül üç şey yapar:
    1. Hedef profille ilgili hesap adaylarını toplar (birincil hedef, tespit
       edilen URL'ler, OSINT/maigret ayak izi).
    2. **Yalnız deterministik** sinyallerle eşleştirir:
         a. ``exact_handle``         — birebir aynı kullanıcı adı
         b. ``normalized_handle``    — nokta/altçizgi/ tire varyantı
         c. ``self_declared_link``   — hedefin biyografisindeki bağlantı
         d. ``shared_platform_id``   — socid'in iki URL'de okuduğu ortak kimlik
    3. Her eşleşme için mühürlü ``EvidenceItem`` üretir.

DÜRÜSTLÜK SÖZLEŞMESİ:
    * Bir eşleşme bir **ÇIKARIMDIR** (``epistemic_type="inference"``), gözlem
      değildir.
    * Sayı **olasılık DEĞİLDİR**: eşleşmenin "kanıt kapsamı"dır — hangi
      kimlik boyutlarının kaç kanıtla desteklendiğinin özeti. Bu yüzden
      ``EvidenceItem.confidence`` **boş** bırakılır (domain sözleşmesi:
      "source scores must remain in source_metrics") ve sayı
      ``source_metrics["coverage"]`` + ``scope["confidence_label"]="kapsam"``
      altında, etiketiyle taşınır.
    * Alt dize eşleşmesi **yoktur**: "x.com/alice" ile "x.com/alicexyz"
      birbirinin alt dizesi olsa da eşleşme sayılmaz.
    * socid kimlik alanları **kullanıcı adı sayılmaz**: "user_id=42" ile
      başka bir platformdaki "@42" hesabı eşleşmez (rastgele çakışma riski).
    * Aynı platform içindeki iki hesap "çapraz profil" eşleşmesi sayılmaz.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Set, Tuple
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from agent_core.capabilities.base import make_evidence
from agent_core.domain.evidence_models import EvidenceItem
from agent_core.services.confidence import normalize_confidence

logger = logging.getLogger(__name__)

__all__ = [
    "CrossProfileCorrelation",
    "CrossProfileMatch",
    "SIGNAL_WEIGHTS",
    "correlate_profiles",
]

PLATFORM_DOMAINS = {
    "instagram": ("instagram.com", "instagr.am"),
    "x": ("x.com", "twitter.com"),
    "github": ("github.com",),
    "linkedin": ("linkedin.com",),
    "reddit": ("reddit.com",),
    "facebook": ("facebook.com", "fb.com"),
    "youtube": ("youtube.com", "youtu.be"),
    "telegram": ("t.me", "telegram.me"),
    "tiktok": ("tiktok.com",),
}

#: Kimlik kanıtının boyutları ve ağırlıkları.
#:
#: Ağırlıklar **olasılık değil**, "bu boyut eşleşmeyi ne kadar güçlü destekliyor"
#: sorusunun **belgelenmiş** cevabıdır. Toplam 1.00'dir; bir eşleşmenin
#: "kanıt kapsamı" = yanan boyutların ağırlık toplamıdır.
SIGNAL_WEIGHTS: Dict[str, float] = {
    # Hedef KENDİ bağlantısını bırakmış: en güçlü beyan.
    "self_declared_link": 0.45,
    # Birebir aynı kullanıcı adı.
    "exact_handle": 0.30,
    # Nokta/altçizgi/tire varyantı (daha zayıf).
    "normalized_handle": 0.15,
    # socid'in iki URL'de okuduğu ortak kimlik alanı.
    "shared_platform_id": 0.10,
}

#: Herhangi bir boyut tek başına eşleşme için yeterlidir; eşik koymuyoruz
#: çünkü her sinyal zaten deterministik ve kanıtlıdır. Ancak **jenerik**
#: kullanıcı adları (aşağıdaki liste) eşleşme üretmez.
_MIN_HANDLE_LEN = 3
_MIN_NORMALIZED_LEN = 5
_GENERIC_HANDLES = frozenset({
    "admin", "login", "home", "index", "about", "user", "users", "profile",
    "search", "explore", "settings", "help", "support", "contact", "privacy",
    "terms", "legal", "news", "blog", "shop", "store", "cart", "p", "reel",
    "reels", "stories", "share", "sharer", "sharee", "shareurl", "photo",
    "video", "watch", "media", "embed", "null", "undefined", "test",
})

#: Biyografideki bağlantıları bulmak için (http/https).
_URL_RE = re.compile(r"https?://[^\s<>\"'\)\]]+", re.IGNORECASE)


class CrossProfileMatch(BaseModel):
    """İki platform hesabı arasındaki deterministik eşleşme."""

    source_platform: str
    source_handle: str
    source_url: str = ""
    target_platform: str
    target_handle: str
    target_url: str = ""
    match_method: str
    #: **Kapsam** skoru (olasılık DEĞİLDİR) — bkz. ``SIGNAL_WEIGHTS``.
    coverage: float = Field(ge=0.0, le=1.0)
    #: Skorun etiketi: kanıt "kapsam"ıdır, olasılık değildir.
    confidence_label: str = "kapsam"
    epistemic_type: str = "inference"
    #: Hangi boyutların yandığı (kanıt izi).
    signals: List[str] = Field(default_factory=list)
    match_details: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class CrossProfileCorrelation(BaseModel):
    """Tüm çapraz profil analizi sonucu."""

    matches: List[CrossProfileMatch] = Field(default_factory=list)
    items: List[EvidenceItem] = Field(default_factory=list)
    cluster_count: int = 0

    model_config = ConfigDict(extra="forbid")


def _normalize_handle(handle: str) -> str:
    """Kullanıcı adını noktalama ve altçizgiden arındırarak normalize eder."""
    raw = (handle or "").strip().lstrip("@").lower()
    return re.sub(r"[._\-]", "", raw)


def _is_generic_handle(handle: str) -> bool:
    """Jenerik/rezerv kullanıcı adı → eşleşme üretmez."""
    raw = (handle or "").strip().lstrip("@").lower()
    if not raw or len(raw) < _MIN_HANDLE_LEN:
        return True
    return raw in _GENERIC_HANDLES


def _detect_platform_and_handle(url_or_handle: str) -> Tuple[str, str, str]:
    """URL veya koldan platform adı, kullanıcı adı ve temiz URL çıkarır."""
    s = (url_or_handle or "").strip()
    if not s:
        return "unknown", "", ""

    if "://" in s or "/" in s:
        parsed = urlsplit(s if "://" in s else f"https://{s}")
        host = (parsed.hostname or "").lower()
        path = parsed.path.strip("/")
        segments = [seg for seg in path.split("/") if seg]

        for plat, domains in PLATFORM_DOMAINS.items():
            if any(host == d or host.endswith(f".{d}") for d in domains):
                if plat == "linkedin":
                    if segments and segments[0] in ("in", "pub") and len(segments) > 1:
                        return plat, segments[1], s
                elif plat == "youtube":
                    if segments and segments[0].startswith("@"):
                        return plat, segments[0].lstrip("@"), s
                elif segments:
                    handle = segments[0].lstrip("@")
                    # Rezerv segmentleri filtrele
                    if handle.lower() not in {"p", "reel", "stories", "login", "home", "search", "explore"}:
                        return plat, handle, s
        if segments:
            return host or "web", segments[0].lstrip("@"), s
        return host or "web", "", s

    # Çıplak handle
    return "primary", s.lstrip("@"), ""


def _normalize_url(url: str) -> str:
    """URL'yi karşılaştırma biçimine indirger (alt dize eşleşmesi olmaz).

    * şema düşer (``https://`` == ``http://``)
    * ``www.`` düşer
    * host küçük harf olur
    * sondaki ``/`` düşer
    * sorgu/fragment düşer
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (parsed.path or "").rstrip("/")
    return f"{host}{path}".lower()


def _extract_links(text: str) -> List[str]:
    """Metindeki http(s) bağlantılarını çıkarır."""
    return [m.group(0).rstrip(".,);") for m in _URL_RE.finditer(text or "")]


def _id_claims(identities: Any) -> Dict[str, Dict[str, str]]:
    """socid kimlik kayıtlarından URL → {alan: değer} haritası.

    Kimlik alanları **kullanıcı adı değildir**; yalnız "iki URL'de aynı okunan
    kimlik" sinyali için kullanılır.
    """
    claims: Dict[str, Dict[str, str]] = {}
    for sid in identities or ():
        if not isinstance(sid, dict):
            continue
        url = str(sid.get("url") or "").strip()
        fields = sid.get("fields") or {}
        if not url or not isinstance(fields, dict):
            continue
        picked: Dict[str, str] = {}
        for key in ("user_id", "uid", "id", "account_id", "numeric_id"):
            value = fields.get(key)
            if isinstance(value, str) and value.strip():
                picked[key] = value.strip()
        if picked:
            claims[url] = picked
    return claims


def correlate_profiles(
    target_profile: Dict[str, Any] | None,
    osint_footprint: Dict[str, Any] | None = None,
) -> CrossProfileCorrelation:
    """Hedef verilerini analizerek çapraz platform hesap korelasyonunu çıkarır."""
    tp = target_profile if isinstance(target_profile, dict) else {}
    osint = osint_footprint if isinstance(osint_footprint, dict) else {}

    # 1. Hesap adayları — yalnız BİLİNEN platformlar (jenerik "web" hesapları
    #    yanlış eşleşme üretir).
    accounts: List[Dict[str, str]] = []
    seen_pairs: Set[Tuple[str, str]] = set()

    def _register(plat: str, h: str, u: str, origin: str):
        plat = plat.lower()
        h = h.strip().lstrip("@").lower()
        if not h or (plat, h) in seen_pairs:
            return
        seen_pairs.add((plat, h))
        accounts.append({"platform": plat, "handle": h, "url": u, "origin": origin})

    # Ana hedef
    primary_handle = str(tp.get("username") or tp.get("name") or "").strip().lstrip("@")
    primary_plat = str(tp.get("platform") or "primary").lower()
    if primary_handle and not _is_generic_handle(primary_handle):
        _register(primary_plat, primary_handle, "", "primary_target")

    # Tespit edilen URL'ler (bulunan profiller)
    for u in tp.get("detected_urls") or []:
        if isinstance(u, str):
            p, h, url_str = _detect_platform_and_handle(u)
            if h and p in PLATFORM_DOMAINS and not _is_generic_handle(h):
                _register(p, h, url_str, "detected_url")

    # OSINT / Maigret bulunan siteler
    u_scan = osint.get("username_scan") or {}
    if isinstance(u_scan, dict):
        for site in u_scan.get("found_sites") or []:
            if not isinstance(site, dict):
                continue
            site_url = site.get("url") or ""
            site_name = site.get("site") or site.get("name") or ""
            p, h, url_str = _detect_platform_and_handle(site_url)
            if not h:
                h = primary_handle
            if not h or _is_generic_handle(h):
                continue
            _register(p if p in PLATFORM_DOMAINS else str(site_name or p).lower(), h, url_str, "username_scan")

    # socid kimlik iddiaları (kullanıcı adı DEĞİL — yalnız kimlik sinyali)
    claims = _id_claims(tp.get("socid_identities"))

    # 2. İkili karşılaştırma ve eşleştirme
    matches: List[CrossProfileMatch] = []
    matched_pairs: Set[Tuple[Tuple[str, str], Tuple[str, str]]] = set()

    bio_text = str(tp.get("bio") or "")
    bio_links = {_normalize_url(link) for link in _extract_links(bio_text)}
    bio_links.discard("")

    for i in range(len(accounts)):
        for j in range(i + 1, len(accounts)):
            a1 = accounts[i]
            a2 = accounts[j]

            # Aynı platform içindeki iki hesap "çapraz profil" değildir.
            if a1["platform"] == a2["platform"]:
                continue

            pair_key = (
                (a1["platform"], a1["handle"]),
                (a2["platform"], a2["handle"]),
            )
            if pair_key in matched_pairs:
                continue

            h1, h2 = a1["handle"], a2["handle"]
            p1, p2 = a1["platform"], a2["platform"]
            signals: List[str] = []

            # Sinyal (a)+(b): kullanıcı adı (birebir / varyant)
            if h1 == h2 and not _is_generic_handle(h1):
                signals.append("exact_handle")
            elif (
                len(_normalize_handle(h1)) >= _MIN_NORMALIZED_LEN
                and _normalize_handle(h1) == _normalize_handle(h2)
                and not _is_generic_handle(h1)
            ):
                signals.append("normalized_handle")

            # Sinyal (c): hedef biyografisinde birebir bağlantı
            # (alt dize değil — URL'nin KENDİSİ biyografide geçiyor olmalı)
            for acc in (a1, a2):
                norm = _normalize_url(acc.get("url") or "")
                if norm and norm in bio_links:
                    if "self_declared_link" not in signals:
                        signals.append("self_declared_link")
                    break

            # Sinyal (d): socid ortak kimlik alanı
            c1 = claims.get(a1.get("url") or "") or {}
            c2 = claims.get(a2.get("url") or "") or {}
            for key, value in c1.items():
                other = c2.get(key)
                if other and other == value and len(value) >= 3:
                    signals.append("shared_platform_id")
                    break

            if not signals:
                continue

            matched_pairs.add(pair_key)
            coverage = sum(SIGNAL_WEIGHTS.get(name, 0.0) for name in signals)
            # Kapsam skoru da aynı sözleşmeye tabidir: sonlu ve [0,1].
            coverage, _valid = normalize_confidence(min(max(coverage, 0.0), 1.0))
            matches.append(
                CrossProfileMatch(
                    source_platform=p1,
                    source_handle=h1,
                    source_url=a1["url"],
                    target_platform=p2,
                    target_handle=h2,
                    target_url=a2["url"],
                    match_method=signals[0],
                    coverage=coverage,
                    signals=signals,
                    match_details={
                        "a1_origin": a1["origin"],
                        "a2_origin": a2["origin"],
                    },
                )
            )

    # 3. EvidenceItem'ları mühürle
    items: List[EvidenceItem] = []
    for m in matches:
        ref_urls = [u for u in (m.source_url, m.target_url) if u]
        signal_text = ", ".join(m.signals)
        ev = make_evidence(
            content=(
                f"Çapraz profil korelasyonu: {m.source_platform}/@{m.source_handle} ile "
                f"{m.target_platform}/@{m.target_handle} eşleşti "
                f"(sinyal: {signal_text}; kanıt kapsamı: {m.coverage:.2f} — olasılık DEĞİLDİR)"
            ),
            source_engine="cross_profiler",
            epistemic_type="inference",
            provenance_refs=ref_urls,
            scope={
                "kind": "cross_profile_correlation",
                "confidence_label": "kapsam",
                "platform_a": m.source_platform,
                "platform_b": m.target_platform,
                "handle_a": m.source_handle,
                "handle_b": m.target_handle,
                "match_method": m.match_method,
                "signals": list(m.signals),
            },
            # Alan sözleşmesi: "Calibrated confidence only; source scores must
            # remain in source_metrics." → kalibre edilmemiş skor buraya GİRMEZ.
            confidence=None,
            source_metrics={
                "coverage": m.coverage,
                "coverage_label": "kapsam",
                "signals": list(m.signals),
                "method": m.match_method,
                "coverage_is_probability": False,
            },
        )
        items.append(ev)

    return CrossProfileCorrelation(
        matches=matches,
        items=items,
        cluster_count=len(matches),
    )
