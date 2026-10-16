"""Derin profil çözümleyici — bulunan profil URL'lerini yetenek omurgasına bağlar.

Neden (P1 Denetimi 2026-10-16 · Bağlantı Denetimi 1A):
    Açık kaynak aramasından tespit edilen profil URL'leri (detected_urls / found_profiles)
    yalnızca UI'a taşınıyor, hiçbir yetenek omurgasına veya kanıt zincirine
    aktarılmıyordu.

Bu modül:
    1. Her URL'nin platformunu tanır.
    2. URL'leri socid-extractor capability'si (extractor.identity.socid) üzerinden çözer.
    3. Çıkarılan kimlik alanlarını doğrulanmış `EvidenceItem` (epistemic_type="observation")
       olarak kanıt zincirine bağlar.
    4. Kanal durumunu dürüstçe (ok / not_run + sebep) üretir.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from agent_core.capabilities import CapabilityContext, bootstrap, run_capability, adapters_osint
from agent_core.capabilities.base import Availability, CapabilityResult
from agent_core.capabilities.state import policy_state
from agent_core.domain.channel_status import ChannelRun, failed, not_run, ok
from agent_core.domain.evidence_models import EvidenceItem
from agent_core.safety import coerce_minor_case

logger = logging.getLogger(__name__)

DEFAULT_MAX_RESOLVE = 5


def _build_policy_state(payload: Dict[str, Any] | None = None):
    """Görev payload'ından politika durumunu üretir (tek kaynak: state.py)."""
    overrides = (payload or {}).get("policy") or {}
    return policy_state(
        vault_locked=bool(overrides.get("vault_locked", True)),
        rate_ok=overrides.get("rate_ok"),
        minor_case=coerce_minor_case(overrides.get("minor_case")),
    )


async def resolve_deep_profiles(
    detected_urls: List[str] | None,
    payload: Dict[str, Any] | None = None,
    max_urls: int = DEFAULT_MAX_RESOLVE,
) -> Tuple[List[EvidenceItem], List[ChannelRun], List[Dict[str, Any]]]:
    """Tespit edilen profil URL'lerini socid-extractor omurgasından çözer.

    Dönen üçlü:
        - `evidence_items`: Kanıt zincirine eklenecek doğrulanmış EvidenceItem'lar.
        - `channel_runs`: Kanal durumu defterine eklenecek durum satırları.
        - `socid_identities`: Hedef profiline eklenecek yapılandırılmış kayıtlar.
    """
    raw_urls = [u for u in (detected_urls or []) if isinstance(u, str) and u.strip()]
    if not raw_urls:
        return [], [], []

    targets = raw_urls[:max_urls]
    state = _build_policy_state(payload)

    # 1. Kasa kilitli ise hiçbir dış yetenek koşamaz (fail-closed)
    if state.vault_locked:
        channel_row = not_run(
            "profile.deep_scan",
            reason="vault_locked",
            detail=f"{len(targets)} profil URL'si bulundu ancak kasa kilitli",
        )
        return [], [channel_row], []

    # 2. socid_extractor bağımlılığı yoksa dürüstçe raporla
    if not adapters_osint._module_available("socid_extractor"):
        channel_row = not_run(
            "profile.deep_scan",
            reason="dependency_missing:socid_extractor",
            detail=f"{len(targets)} profil URL'si çözülemedi: paket kurulu değil",
        )
        return [], [channel_row], []

    bootstrap()
    items: List[EvidenceItem] = []
    identities: List[Dict[str, Any]] = []
    extracted_count = 0
    errors: List[str] = []

    for url in targets:
        try:
            res: CapabilityResult = await run_capability(
                "extractor.identity.socid",
                CapabilityContext(subject=url),
                state=state,
            )
            if res.ok and res.items:
                for item in res.items:
                    if isinstance(item, EvidenceItem):
                        items.append(item)
                rec = res.payload
                fields = getattr(rec, "fields", {}) or {}
                if fields:
                    extracted_count += 1
                    identities.append({
                        "url": url,
                        "provider": getattr(rec, "provider", "socid_extractor"),
                        "fields": fields,
                    })
            elif not res.ok:
                errors.append(res.unavailable_reason or "unavailable")
        except Exception as exc:
            logger.warning("Deep profile resolve error for %s: %s", url, exc)
            errors.append(type(exc).__name__)

    if extracted_count > 0:
        channel_row = ok(
            "profile.deep_scan",
            detail=f"{extracted_count}/{len(targets)} profilden kimlik kaydı çıkarıldı",
        )
    elif errors and all("vault_locked" in e for e in errors):
        channel_row = not_run("profile.deep_scan", reason="vault_locked")
    elif errors and len(errors) == len(targets):
        channel_row = failed(
            "profile.deep_scan",
            reason=errors[0],
            detail=f"{len(targets)} profil URL'si denendi; hata alındı",
        )
    else:
        channel_row = ok(
            "profile.deep_scan",
            detail=f"{len(targets)} profil URL'si tarandı (0 çıkarılan alan)",
        )

    return items, [channel_row], identities
