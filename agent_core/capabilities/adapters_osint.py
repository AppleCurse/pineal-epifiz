"""Faz 0 adaptörleri — mevcut OSINT tarayıcılarını tek sözleşmeye bağlar.

ÖNEMLİ (geçiş notu): Bu adaptörler mevcut tarayıcıları (``maigret_scanner``,
``holehe_scanner``, ``socid_enricher``) DEĞİŞTİRMEZ; onları spine üzerinden
çağırılabilir hâle getirir ve çıktılarını kanıt kaydına (``EvidenceItem``)
çevirir. Eski çağrı noktalarının (``backend/api.py``, ``osint_investigator``)
bu adaptörlere taşınması Faz 0.2'nin işidir; taşıma bitene kadar iki yolun
aynı sonucu verdiği ``tests/unit/test_capability_spine_faz0.py`` içindeki
eşdeğerlik testiyle korunur.

Dürüstlük sözleşmesi (değişmedi):
    - Kapı kapalı / kütüphane yok / ağ yok → ``available=False`` + sebep.
    - "Hiç iz yok" yalnızca tarama SIFIR HATA ile tamamlanırsa iddia edilir
      (``epistemic_type="absence"``); karışık hata durumunda kanıt üretilmez.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any

from agent_core.capabilities.base import (
    Availability,
    BaseCapability,
    CapabilityContext,
    CapabilityKind,
    CapabilityResult,
    make_evidence,
)

__all__ = ["MaigretCapability", "HoleheCapability", "SocidCapability"]


def _flag(name: str) -> bool:
    """Env anahtarı açık mı? ('1', 'true', 'yes', 'on' kabul)."""
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


class MaigretCapability(BaseCapability):
    """Kullanıcı adı varlık taraması (maigret · MIT · kapı: ENABLE_MAIGRET)."""

    id = "sensor.identity.maigret"
    kind = CapabilityKind.SENSOR
    license = "MIT"
    gates = frozenset({"vault", "ENABLE_MAIGRET"})
    timeout_seconds = 75.0
    description = "Kullanıcı adının 3300+ sitedeki varlığını tarar (kanıtlı)."

    def availability(self) -> Availability:
        if not _flag("ENABLE_MAIGRET"):
            return Availability.unavailable("gate_disabled:ENABLE_MAIGRET")
        if not _module_available("maigret"):
            return Availability.unavailable("dependency_missing:maigret")
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        from agent_core.services.maigret_scanner import scan_username

        username = (ctx.subject or ctx.params.get("username") or "").strip()
        scan = await scan_username(username)
        notes: dict[str, Any] = {
            "provider": getattr(scan, "provider", "maigret"),
            "scanned_count": getattr(scan, "scanned_count", 0),
            "error_count": getattr(scan, "error_count", 0),
        }

        if not getattr(scan, "available", False):
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=f"scan_unavailable:{getattr(scan, 'reason', None)}",
                payload=scan,
                notes=notes,
            )

        hits = list(getattr(scan, "found_sites", []) or [])
        items = []
        for hit in hits:
            url = getattr(hit, "url", "") or ""
            site = getattr(hit, "site", "") or ""
            items.append(
                make_evidence(
                    content=f"username '{username}' present on {site} ({url})".strip(),
                    source_engine="maigret",
                    epistemic_type="observation",
                    provenance_refs=[url] if url else [],
                    scope={"kind": "identity_presence", "site": site},
                    source_metrics={
                        "scanned_count": notes["scanned_count"],
                        "error_count": notes["error_count"],
                    },
                )
            )

        # Güvenilir yokluk: tarama tamamlandı + sıfır hata + sıfır eşleşme.
        if not items and notes["scanned_count"] and notes["error_count"] == 0:
            items.append(
                make_evidence(
                    content=(
                        f"username '{username}' not found in "
                        f"{notes['scanned_count']} scanned sites (zero errors)"
                    ),
                    source_engine="maigret",
                    epistemic_type="absence",
                    scope={"kind": "identity_absence"},
                    source_metrics={
                        "scanned_count": notes["scanned_count"],
                        "error_count": 0,
                    },
                )
            )

        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=tuple(items),
            payload=scan,
            notes=notes,
        )


class HoleheCapability(BaseCapability):
    """E-posta kayıt taraması (holehe · GPL-3.0 harici · kapı: ENABLE_HOLEHE)."""

    id = "sensor.identity.holehe"
    kind = CapabilityKind.SENSOR
    license = "GPL-3.0 (harici süreç/bağımlılık — kod gömülmez)"
    gates = frozenset({"vault", "consent", "ENABLE_HOLEHE"})
    timeout_seconds = 150.0
    description = "E-postanın hangi platformlarda kayıtlı olduğunu tarar (rıza zorunlu)."

    def availability(self) -> Availability:
        if not _flag("ENABLE_HOLEHE"):
            return Availability.unavailable("gate_disabled:ENABLE_HOLEHE")
        if not _module_available("holehe"):
            return Availability.unavailable("dependency_missing:holehe")
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        from agent_core.services.holehe_scanner import scan_email

        email = (ctx.subject or ctx.params.get("email") or "").strip()
        scan = await scan_email(email)
        notes: dict[str, Any] = {
            "provider": getattr(scan, "provider", "holehe"),
            "scanned_count": getattr(scan, "scanned_count", 0),
            "error_count": getattr(scan, "error_count", 0),
        }

        if not getattr(scan, "available", False):
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=f"scan_unavailable:{getattr(scan, 'reason', None)}",
                payload=scan,
                notes=notes,
            )

        items = []
        for hit in list(getattr(scan, "found_sites", []) or []):
            site = getattr(hit, "site", "") or ""
            items.append(
                make_evidence(
                    content=f"email '{email}' registered on {site}",
                    source_engine="holehe",
                    epistemic_type="observation",
                    scope={"kind": "identity_presence", "site": site},
                    source_metrics={
                        "scanned_count": notes["scanned_count"],
                        "error_count": notes["error_count"],
                    },
                )
            )

        if not items and notes["scanned_count"] and notes["error_count"] == 0:
            items.append(
                make_evidence(
                    content=(
                        f"email '{email}' not registered on "
                        f"{notes['scanned_count']} checked services (zero errors)"
                    ),
                    source_engine="holehe",
                    epistemic_type="absence",
                    scope={"kind": "identity_absence"},
                )
            )

        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=tuple(items),
            payload=scan,
            notes=notes,
        )


class SocidCapability(BaseCapability):
    """Profil URL'sinden kararlı kimlik alanları (socid-extractor · MIT).

    Dış ağ isteği gerektirdiği için ``vault`` kapısına bağlıdır: kasa kilitliyken
    bu yetenek koşamaz (Pineal'in kasa ilkesi — istisna yok).
    """

    id = "extractor.identity.socid"
    kind = CapabilityKind.EXTRACTOR
    license = "MIT"
    gates = frozenset({"vault"})
    timeout_seconds = 20.0
    description = "Profil URL'sinden sosyal kimlik alanlarını çıkarır (kanıtlı)."

    def availability(self) -> Availability:
        if not _module_available("socid_extractor"):
            return Availability.unavailable("dependency_missing:socid_extractor")
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        from agent_core.services.socid_enricher import extract_profile

        url = (ctx.subject or ctx.params.get("url") or "").strip()
        record = await extract_profile(url) if url else await extract_profile("")
        notes: dict[str, Any] = {
            "provider": getattr(record, "provider", "socid_extractor"),
            "source_url": getattr(record, "source_url", ""),
        }

        if not getattr(record, "available", False):
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=f"extract_unavailable:{getattr(record, 'reason', None)}",
                payload=record,
                notes=notes,
            )

        fields: dict[str, Any] = dict(getattr(record, "fields", {}) or {})
        if not fields:
            return CapabilityResult(
                capability_id=self.id,
                available=True,
                items=(),
                payload=record,
                notes={**notes, "empty_fields": True},
            )

        summary = ", ".join(f"{k}={v}" for k, v in sorted(fields.items())[:12])
        item = make_evidence(
            content=f"profile identity extracted from {url}: {summary}",
            source_engine="socid_extractor",
            epistemic_type="observation",
            provenance_refs=[url] if url else [],
            scope={"kind": "identity_fields", "field_count": len(fields)},
            source_metrics={"fields": sorted(fields)},
        )
        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=(item,),
            payload=record,
            notes=notes,
        )
