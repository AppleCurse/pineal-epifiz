"""P1 · DERİN PROFİL ÇÖZÜMLEME — bulunan profil URL'leri → yetenek omurgası.

Neden (P1 Denetimi 2026-10-16 · Bağlantı Denetimi 1A):
    Arama sonucunda tespit edilen profil URL'leri (``target_profile.detected_urls``)
    yalnız UI'a taşınıyor, hiçbir yetenek omurgasına veya kanıt zincirine
    aktarılmıyordu.

Bu modül **TEK giriş noktasıdır**. İçinde iki katman vardır:

    1. :mod:`agent_core.services.profile_router` → **saf** sınıflandırma
       (URL → hangi yetenek; ağ YOK). Bilinen sosyal platform dışındaki profil
       adresleri genel kimlik çıkarıcıya (``extractor.identity.socid``)
       yönlendirilir; profil OLMAYAN adresler (gönderi/etiket/giriş) yola
       bağlanmaz ve sebebiyle "koşmadı" diye raporlanır.
    2. :mod:`agent_core.services.profile_deep_scan` → **tek koşum geçidi**
       (``CapabilityRunner``): politika kapıları, çocuk kilidi, timeout aynı
       yerden uygulanır.

Sözleşme:
    * **Kasa kilitliyken hiçbir yetenek koşmaz** → tek satır ``not_run`` +
      sebep ``vault_locked``.
    * **Kapalı kapı sessizce yutulmaz**: sensör/çıkarıcı kapalıysa satır
      ``not_run`` + MAKİNE-OKUNUR sebep yazar (``policy:gate_disabled``...).
    * **Bir adres = bir yetenek çağrısı**: aynı profil iki kez kazınmaz.
    * **Kimlik karıştırma yok**: bulunan profilin gönderileri hedefin ``posts``
      alanına yazılmaz; ``scanned_urls``/``scanned_profiles`` altında ayrı
      durur.
    * **Dış sözleşme korunur**: :func:`resolve_deep_profiles` üçlü döner
      ``(kanıtlar, kanal satırları, kimlik kayıtları)``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Tuple

from agent_core.capabilities import adapters_osint, bootstrap, run_capability
from agent_core.capabilities.state import policy_state, with_operator_consent
from agent_core.domain.channel_status import ChannelRun, not_run, ok
from agent_core.domain.evidence_models import EvidenceItem
from agent_core.safety import coerce_minor_case
from agent_core.services.profile_deep_scan import DeepScanResult, run_plan
from agent_core.services.profile_router import (
    CAPABILITY_SOCID,
    REASON_UNSUPPORTED,
    ProfileRoute,
    classify_url,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CHANNEL_DEEP_SCAN",
    "DEFAULT_MAX_RESOLVE",
    "DeepProfileResolution",
    "resolve_deep_profiles",
    "resolve_deep_profiles_detailed",
]

#: Derin taramanın ortak kanal adı.
CHANNEL_DEEP_SCAN = "profile.deep_scan"

DEFAULT_MAX_RESOLVE = 5


def _build_policy_state(payload: Dict[str, Any] | None = None):
    """Görev payload'ından politika durumunu üretir (tek kaynak: state.py).

    Kasa/hız/çocuk durumu **aktarılır** — kapı zayıflatılmaz. Hız durumu
    payload'da yoksa ``None`` kalır ve hız kapısı RET eder (fail-closed).
    """
    overrides = (payload or {}).get("policy") or {}
    state = policy_state(
        vault_locked=bool(overrides.get("vault_locked", True)),
        rate_ok=overrides.get("rate_ok"),
        minor_case=coerce_minor_case(overrides.get("minor_case")),
    )
    # [2026-10-23 · ÖLÜ KAPI] Operatör çapraz arama için onay verdiyse
    # Instagram/X sensörleri de o görevde açılır (env'de AÇIKÇA kapatılmadıysa).
    # Kasa ve hız kapıları ETKİLENMEZ.
    return with_operator_consent(state, bool(overrides.get("cross_platform_authorized")))


def _plan(urls: Sequence[str], limit: int) -> list[ProfileRoute]:
    """URL listesini yol planına çevirir (saf — ağ YOK).

    * Bilinen platform profili (Instagram/X) → o platformun sensörü.
    * LinkedIn/Facebook profili → ``extractor.identity.socid``.
    * Başka bir profil adresi (ör. ``github.com/kullanici``) → genel kimlik
      çıkarıcı (``extractor.identity.socid``).
    * Profil OLMAYAN adres → yol yok + sebep (sessizce atılmaz).
    """
    plan: list[ProfileRoute] = []
    seen: set[str] = set()
    for raw in urls or ():
        url = (raw or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        route = classify_url(url)
        if not route.runnable and route.reason == REASON_UNSUPPORTED:
            # Genel profil adresi: kimlik çıkarıcıya yönlendir.
            route = ProfileRoute(
                url=url,
                platform="web",
                handle="",
                capability_id=CAPABILITY_SOCID,
                subject=url,
                params={"url": url},
                runnable=True,
            )
        plan.append(route)
        if limit and len(plan) >= int(limit):
            break
    return plan


class _RunCapabilityRunner:
    """Motoru ``run_capability`` üzerinden koşar (tek koşum geçidi).

    ``run_capability`` **modül seviyesinde** çağrılır: sözleşme tek yerden
    gelir ve testler bu yolu değiştirerek motoru sahte yeteneklerle
    besleyebilir.
    """

    async def run(self, capability_id: str, ctx: Any, state: Any = None):
        return await run_capability(capability_id, ctx, state=state)


def _fields_of(record: Any) -> dict[str, Any]:
    """socid kaydından kimlik alanlarını çıkarır (yoksa boş)."""
    if isinstance(record, dict):
        fields = record.get("fields")
    else:
        fields = getattr(record, "fields", None)
    return dict(fields) if isinstance(fields, dict) else {}


def _provider_of(record: Any) -> str:
    if isinstance(record, dict):
        provider = record.get("provider")
    else:
        provider = getattr(record, "provider", None)
    return str(provider or "socid_extractor")


def _identities(result: DeepScanResult, plan: Sequence[ProfileRoute]) -> list[dict[str, Any]]:
    """Kimlik çıkarıcıdan **gerçekten** kimlik alanı gelen adresler."""
    out: list[dict[str, Any]] = []
    for route in plan:
        if route.capability_id != CAPABILITY_SOCID:
            continue
        record = result.scraped.get(route.url)
        if record is None:
            continue
        fields = _fields_of(record)
        if not fields:
            continue
        out.append(
            {
                "url": route.url,
                "provider": _provider_of(record),
                "fields": fields,
            }
        )
    return out


def _summary_row(
    result: DeepScanResult,
    plan: Sequence[ProfileRoute],
    identities: Sequence[dict[str, Any]],
) -> ChannelRun:
    """Toplam kanal satırı (``profile.deep_scan``).

    Dürüstlük: "koşmadı" ile "kazınamadı" ayrımı korunur. Kimlik kaydı
    çıkmadıysa ve motor da bir şey koşmadıysa satır ``not_run`` + sebep
    olur (sessizce "ok" yazılmaz).
    """
    if not plan:
        return not_run(CHANNEL_DEEP_SCAN, reason="no_profile_urls", detail="profil URL'si yok")
    if identities:
        return ok(
            CHANNEL_DEEP_SCAN,
            detail=f"{len(identities)}/{len(plan)} profilden kimlik kaydı çıkarıldı",
        )
    ran = [run for run in result.channel_runs if run.status == "ok"]
    if ran:
        return ok(
            CHANNEL_DEEP_SCAN,
            detail=f"{len(plan)} profil URL'si tarandı (0 çıkarılan alan)",
        )
    reasons = [str(run.reason) for run in result.channel_runs if run.reason]
    return not_run(
        CHANNEL_DEEP_SCAN,
        reason=reasons[0] if reasons else "not_attempted",
        detail=f"{len(plan)} profil URL'si planlandı; hiçbiri kazınamadı",
    )


@dataclass
class DeepProfileResolution:
    """Derin profil çözümlemesinin tam çıktısı."""

    items: list[EvidenceItem] = field(default_factory=list)
    channel_runs: list[ChannelRun] = field(default_factory=list)
    identities: list[dict[str, Any]] = field(default_factory=list)
    #: url → durum/sebep (UI/telemetri defteri)
    scanned_urls: list[dict[str, Any]] = field(default_factory=list)
    #: url → kazanılan profil parçası (yalnız GERÇEKTEN koşanlar)
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)


async def resolve_deep_profiles_detailed(
    detected_urls: List[str] | None,
    payload: Dict[str, Any] | None = None,
    max_urls: int = DEFAULT_MAX_RESOLVE,
) -> DeepProfileResolution:
    """Bulunan profil URL'lerini yetenek omurgasıyla çözer (ayrıntılı çıktı)."""
    raw_urls = [u for u in (detected_urls or []) if isinstance(u, str) and u.strip()]
    if not raw_urls:
        return DeepProfileResolution()

    targets = raw_urls[:max_urls]
    state = _build_policy_state(payload)

    # 1) Kasa kilitliyse hiçbir dış yetenek koşamaz (fail-closed).
    if state.vault_locked:
        return DeepProfileResolution(
            channel_runs=[
                not_run(
                    CHANNEL_DEEP_SCAN,
                    reason="vault_locked",
                    detail=f"{len(targets)} profil URL'si bulundu ancak kasa kilitli",
                )
            ]
        )

    plan = _plan(targets, max_urls)

    # 2) Kimlik çıkarıcı gerekiyorsa ve paket kurulu değilse dürüstçe reddet.
    needs_socid = any(route.capability_id == CAPABILITY_SOCID for route in plan)
    if needs_socid and not adapters_osint._module_available("socid_extractor"):
        return DeepProfileResolution(
            channel_runs=[
                not_run(
                    CHANNEL_DEEP_SCAN,
                    reason="dependency_missing:socid_extractor",
                    detail="socid_extractor paketi kurulu değil; profil kimliği çıkarılamadı",
                )
            ]
        )

    # 3) Tek koşum geçidi: registry tek yerden beslenir, motor koşar.
    bootstrap()
    result = await run_plan(plan, state=state, runner=_RunCapabilityRunner())

    identities = _identities(result, plan)
    rows: list[ChannelRun] = list(result.channel_runs)
    rows.append(_summary_row(result, plan, identities))

    return DeepProfileResolution(
        items=list(result.evidence_items),
        channel_runs=rows,
        identities=identities,
        scanned_urls=result.scanned_urls,
        profiles=dict(result.profiles),
    )


async def resolve_deep_profiles(
    detected_urls: List[str] | None,
    payload: Dict[str, Any] | None = None,
    max_urls: int = DEFAULT_MAX_RESOLVE,
) -> Tuple[List[EvidenceItem], List[ChannelRun], List[Dict[str, Any]]]:
    """Uyumlu üçlü: ``(kanıtlar, kanal satırları, kimlik kayıtları)``."""
    resolution = await resolve_deep_profiles_detailed(
        detected_urls, payload=payload, max_urls=max_urls
    )
    return resolution.items, resolution.channel_runs, resolution.identities
