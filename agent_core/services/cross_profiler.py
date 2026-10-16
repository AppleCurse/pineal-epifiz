"""Çapraz profilleme motoru — farklı platformlardaki hesapları deterministik olarak eşleştirir.

Neden (P2 Denetimi 2026-10-16 · Soru 1A):
    "Çapraz profilleme: farklı platform hesaplarını eşleştiren kod gerçekten var mı?"
    -> Eski kodda bu kabiliyet YOKTU.

Bu modül:
    1. Hedef profil, tespit edilen URL'ler, OSINT ayak izi ve SOCID kimliklerinden
       hesap adaylarını toplar.
    2. Deterministik kurallarla (tam kullanıcı adı, normalleştirilmiş kullanıcı adı,
       biyografi bağlantısı, SOCID kimlik özniteliği) platformlar arası eşleştirme yapar.
    3. Her eşleşme için epistemic_type="inference" olan mühürlü `EvidenceItem` üretir.
       (Çapraz eşleştirme bir GÖZLEM değil, ÇIKARIMDIR — epistemic dürüstlük).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from agent_core.capabilities.base import make_evidence
from agent_core.domain.evidence_models import EvidenceItem

logger = logging.getLogger(__name__)

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


class CrossProfileMatch(BaseModel):
    """İki platform hesabı arasındaki deterministik eşleşme."""

    source_platform: str
    source_handle: str
    source_url: str = ""
    target_platform: str
    target_handle: str
    target_url: str = ""
    match_method: str  # "exact_handle" | "normalized_handle" | "cross_link" | "socid_attribute"
    confidence: float = Field(ge=0.0, le=1.0)
    epistemic_type: str = "inference"
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


def correlate_profiles(
    target_profile: Dict[str, Any] | None,
    osint_footprint: Dict[str, Any] | None = None,
) -> CrossProfileCorrelation:
    """Hedef verilerini analiz ederek çapraz platform hesap korelasyonunu çıkarır."""
    tp = target_profile if isinstance(target_profile, dict) else {}
    osint = osint_footprint if isinstance(osint_footprint, dict) else {}

    # 1. Hesap adaylarını topla
    # Format: list of dict(platform, handle, url, origin)
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
    if primary_handle:
        _register(primary_plat, primary_handle, "", "primary_target")

    # Tespit edilen URL'ler
    for u in tp.get("detected_urls") or []:
        if isinstance(u, str):
            p, h, url_str = _detect_platform_and_handle(u)
            if h and p != "unknown":
                _register(p, h, url_str, "detected_url")

    # SOCID kimlikleri
    for sid in tp.get("socid_identities") or []:
        if isinstance(sid, dict):
            fields = sid.get("fields") or {}
            source_url = sid.get("url") or ""
            p, _, _ = _detect_platform_and_handle(source_url)
            for k in ("username", "user_id", "login", "screen_name", "account"):
                val = fields.get(k)
                if isinstance(val, str) and val.strip():
                    _register(p, val.strip(), source_url, "socid_identity")

    # OSINT / Maigret bulunan siteler
    u_scan = osint.get("username_scan") or {}
    if isinstance(u_scan, dict):
        for site in u_scan.get("found_sites") or []:
            site_name = site.get("site") or site.get("name") or ""
            site_url = site.get("url") or ""
            if site_name:
                p, h, url_str = _detect_platform_and_handle(site_url)
                if not h:
                    h = primary_handle
                _register(p if p != "unknown" else site_name.lower(), h, url_str, "username_scan")

    # 2. İkili karşılaştırma ve eşleştirme
    matches: List[CrossProfileMatch] = []
    matched_pairs: Set[Tuple[Tuple[str, str], Tuple[str, str]]] = set()

    bio_text = str(tp.get("bio") or "").lower()

    for i in range(len(accounts)):
        for j in range(i + 1, len(accounts)):
            a1 = accounts[i]
            a2 = accounts[j]

            # Aynı platform içindeki iki hesap arası eşleşme aranmaz
            if a1["platform"] == a2["platform"] and a1["platform"] != "primary":
                continue

            pair_key = (
                (a1["platform"], a1["handle"]),
                (a2["platform"], a2["handle"]),
            )
            if pair_key in matched_pairs:
                continue

            h1, h2 = a1["handle"], a2["handle"]
            p1, p2 = a1["platform"], a2["platform"]

            method = None
            conf = 0.0

            # Kural 1: Biyografide doğrudan çapraz bağlantı
            if a1["url"] and a1["url"].lower() in bio_text:
                method = "cross_link"
                conf = 0.95
            elif a2["url"] and a2["url"].lower() in bio_text:
                method = "cross_link"
                conf = 0.95
            # Kural 2: Tam kullanıcı adı eşleşmesi
            elif h1.lower() == h2.lower():
                method = "exact_handle"
                conf = 0.85
            # Kural 3: Normalize edilmiş kullanıcı adı eşleşmesi
            elif _normalize_handle(h1) == _normalize_handle(h2) and len(_normalize_handle(h1)) >= 4:
                method = "normalized_handle"
                conf = 0.70

            if method and conf >= 0.70:
                matched_pairs.add(pair_key)
                matches.append(
                    CrossProfileMatch(
                        source_platform=p1,
                        source_handle=h1,
                        source_url=a1["url"],
                        target_platform=p2,
                        target_handle=h2,
                        target_url=a2["url"],
                        match_method=method,
                        confidence=conf,
                        epistemic_type="inference",
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
        ev = make_evidence(
            content=(
                f"Çapraz profil korelasyonu: {m.source_platform}/@{m.source_handle} ile "
                f"{m.target_platform}/@{m.target_handle} eşleşti "
                f"(yöntem: {m.match_method}, hesaplanan korelasyon güveni: {m.confidence:.2f})"
            ),
            source_engine="cross_profiler",
            epistemic_type="inference",
            provenance_refs=ref_urls,
            scope={
                "kind": "cross_profile_correlation",
                "platform_a": m.source_platform,
                "platform_b": m.target_platform,
                "handle_a": m.source_handle,
                "handle_b": m.target_handle,
                "match_method": m.match_method,
            },
            confidence=m.confidence,
            source_metrics={"confidence": m.confidence, "method": m.match_method},
        )
        items.append(ev)

    return CrossProfileCorrelation(
        matches=matches,
        items=items,
        cluster_count=len(matches),
    )
