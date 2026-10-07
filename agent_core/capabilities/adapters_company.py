"""FAZ D · D6 — KURUM HEDEFİ adaptörleri: theHarvester · açık SEO · kişi künyesi.

Üç yetenek, tek omurga sözleşmesi:

    sensor.company.harvester → e-posta/alt alan adı/IP/URL (theHarvester CLI)
    sensor.company.seo       → kurumun KENDİ yayınladığı dosyalar (robots ·
                               sitemap · meta · security.txt · başlıklar)
    sensor.company.people    → yalnız kurumun kendi sayfalarındaki
                               YAPILANDIRILMIŞ kişi verisi (schema.org/Person)
                               + herkese açık mailto adresleri

Dürüstlük:
    * Uydurma metrik yok: SEO "puanı" hesaplanmaz; ölçülen yazılır.
    * Araç yok / ağ yok → `available=False` + makine-okunur sebep.
    * "Yok" iddiası yalnız kesin 404'te (`absence`); ağ hatası yokluğa
      çevrilmez, kanıt üretilmez.
    * Kişi avı değildir: ad + rol dışında hiçbir kişisel alan toplanmaz;
      kaynak URL her kanıt satırında görünür.
"""

from __future__ import annotations

from typing import Any

from agent_core.capabilities.adapters_osint import _flag
from agent_core.capabilities.base import (
    Availability,
    BaseCapability,
    CapabilityContext,
    CapabilityKind,
    CapabilityResult,
    make_evidence,
)
from agent_core.services import company_recon

__all__ = [
    "CompanyHarvesterCapability",
    "CompanySeoCapability",
    "CompanyPeopleCapability",
]

#: Kova başına kanıt tavanı (rapor okunur kalsın; aşan `truncated` ile işaretlenir).
BUCKET_LIMIT = 25

GATE_REASON = f"gate_disabled:{company_recon.GATE}"


def _domain_from(ctx: CapabilityContext) -> str:
    return company_recon.normalize_domain(ctx.subject or str(ctx.params.get("domain") or ""))


def _gate() -> Availability | None:
    if not _flag(company_recon.GATE):
        return Availability.unavailable(GATE_REASON)
    return None


class CompanyHarvesterCapability(BaseCapability):
    """theHarvester — arama motorlarından kurum künyesi (GPL-2.0 harici CLI)."""

    id = "sensor.company.harvester"
    kind = CapabilityKind.SENSOR
    license = "GPL-2.0 (harici CLI — kod gömülmez)"
    gates = frozenset({"vault", "rate", company_recon.GATE})
    timeout_seconds = 240.0
    description = (
        "Kurum/alan adı hedefi: arama motorlarından e-posta, alt alan adı, IP "
        "ve URL toplar (theHarvester). Araç yoksa dürüstçe kapalıdır."
    )

    def availability(self) -> Availability:
        blocked = _gate()
        if blocked:
            return blocked
        ok, reason = company_recon.harvester_availability()
        return Availability.ok() if ok else Availability.unavailable(reason)

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        domain = _domain_from(ctx)
        if not domain:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="invalid_domain"
            )
        scan = await company_recon.scan_company(
            domain,
            sources=str(ctx.params.get("sources") or ""),
            limit=int(ctx.params.get("limit") or 200),
        )
        base_notes = {
            "domain": domain,
            "sources": scan.sources,
            "duration_ms": scan.duration_ms,
            "keys_seen": list(scan.keys_seen),
            "counts": {
                "emails": len(scan.emails),
                "hosts": len(scan.hosts),
                "ips": len(scan.ips),
                "urls": len(scan.urls),
                "people": len(scan.people),
            },
        }
        if scan.stderr_tail:
            base_notes["stderr_tail"] = scan.stderr_tail[:200]
        if not scan.available:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=scan.reason,
                notes=base_notes,
            )

        items = []
        truncated: dict[str, bool] = {}
        for bucket, values in (
            ("emails", scan.emails),
            ("hosts", scan.hosts),
            ("ips", scan.ips),
            ("urls", scan.urls),
            ("people", scan.people),
        ):
            if len(values) > BUCKET_LIMIT:
                truncated[bucket] = True
            for value in values[:BUCKET_LIMIT]:
                items.append(
                    make_evidence(
                        content=f"Kurum künyesi ({bucket}): {value}",
                        source_engine="theHarvester",
                        provenance_refs=[f"theHarvester://{domain}/{bucket}"],
                        scope={
                            "domain": domain,
                            "bucket": bucket,
                            "tool": "theHarvester",
                            "sources": scan.sources,
                            "claim": "search_engine_listing",
                        },
                    )
                )

        if not items:
            # Tarama SIFIR HATA ile bitti ve hiçbir kova dolmadı: yokluk iddiası.
            items.append(
                make_evidence(
                    content=(
                        f"theHarvester: {domain} için kaynaklarda "
                        f"({scan.sources}) e-posta/alt alan adı/IP/URL kaydı bulunamadı."
                    ),
                    source_engine="theHarvester",
                    epistemic_type="absence",
                    provenance_refs=[f"theHarvester://{domain}"],
                    scope={"domain": domain, "sources": scan.sources, "claim": "absence"},
                )
            )

        base_notes["truncated"] = truncated
        base_notes["evidence_count"] = len(items)
        return CapabilityResult(capability_id=self.id, available=True, items=tuple(items), notes=base_notes)


class CompanySeoCapability(BaseCapability):
    """Açık SEO — kurumun kendi yayınladığı dosyalar; harici servis yok."""

    id = "sensor.company.seo"
    kind = CapabilityKind.SENSOR
    license = "dahili (yalnız HTTP GET + stdlib ayrıştırma)"
    gates = frozenset({"vault", company_recon.GATE})
    timeout_seconds = 120.0
    description = (
        "Kurumun açık izlenebilirlik verisi: robots.txt, sitemap.xml, ana sayfa "
        "meta/dil/canonical, security.txt ve güvenlik başlıkları. Puan uydurulmaz."
    )

    def availability(self) -> Availability:
        blocked = _gate()
        if blocked:
            return blocked
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        domain = _domain_from(ctx)
        if not domain:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="invalid_domain"
            )
        snapshot = await company_recon.seo_snapshot(domain)
        notes: dict[str, Any] = {
            "domain": domain,
            "base_url": snapshot.base_url,
            "scheme": snapshot.scheme,
            "checks": [
                {
                    "name": c.name,
                    "url": c.url,
                    "status": c.status,
                    "present": c.present,
                    "error": c.error,
                    "detail": c.detail,
                }
                for c in snapshot.checks
            ],
        }
        if not snapshot.available:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=snapshot.reason,
                notes=notes,
            )

        items = []
        errors = [f"{c.name}:{c.error or f'status:{c.status}'}" for c in snapshot.checks if not c.present and not c.absent]
        for check in snapshot.checks:
            if check.present:
                detail = check.detail
                if check.name == "homepage":
                    content = (
                        f"Kurum ana sayfası ({check.url}): başlık={detail.get('title') or '—'}; "
                        f"açıklama={detail.get('description') or '—'}; dil={detail.get('lang') or '—'}; "
                        f"canonical={detail.get('canonical') or '—'}"
                    )
                elif check.name == "robots":
                    content = (
                        f"robots.txt yayında ({check.url}): satır={detail.get('lines')}; "
                        f"sitemap={len(detail.get('sitemaps') or [])}; "
                        f"tamamen-kapalı={bool(detail.get('disallow_all'))}"
                    )
                elif check.name == "sitemap":
                    content = (
                        f"sitemap.xml yayında ({check.url}): tür={detail.get('kind')}; "
                        f"kayıt={detail.get('entries')}; ilk-lastmod={detail.get('first_lastmod') or '—'}"
                    )
                else:
                    content = (
                        f"security.txt yayında ({check.url}): "
                        f"iletişim={len(detail.get('contacts') or [])}; satır={detail.get('chars')}"
                    )
                items.append(
                    make_evidence(
                        content=content,
                        source_engine="company_seo",
                        provenance_refs=[check.url],
                        scope={"domain": domain, "check": check.name, "claim": "published_by_company"},
                    )
                )
            elif check.absent:
                items.append(
                    make_evidence(
                        content=f"{check.name} yayınlanmamış ({check.url} → 404).",
                        source_engine="company_seo",
                        epistemic_type="absence",
                        provenance_refs=[check.url],
                        scope={"domain": domain, "check": check.name, "claim": "absence"},
                    )
                )
            # Ağ hatası (status=0): ne varlık ne yokluk iddiası — yalnız notes.

        notes["errors"] = errors
        notes["evidence_count"] = len(items)
        return CapabilityResult(capability_id=self.id, available=True, items=tuple(items), notes=notes)


class CompanyPeopleCapability(BaseCapability):
    """Kurum künyesi: yalnız kurumun kendi sayfalarındaki yapılandırılmış kişi verisi."""

    id = "sensor.company.people"
    kind = CapabilityKind.SENSOR
    license = "dahili (yalnız HTTP GET + stdlib ayrıştırma)"
    gates = frozenset({"vault", company_recon.GATE})
    timeout_seconds = 120.0
    description = (
        "Kurumun kendi sayfalarında YAYINLADIĞI kişi künyesi (schema.org/Person: "
        "ad + rol) ve herkese açık iletişim adresleri. Kişi avı değildir."
    )

    def availability(self) -> Availability:
        blocked = _gate()
        if blocked:
            return blocked
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        domain = _domain_from(ctx)
        if not domain:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="invalid_domain"
            )
        scan = await company_recon.people_scan(
            domain, max_pages=int(ctx.params.get("max_pages") or 5)
        )
        notes: dict[str, Any] = {
            "domain": domain,
            "pages_checked": list(scan.pages_checked),
            "errors": list(scan.errors),
            "people_count": len(scan.people),
            "contact_count": len(scan.contacts),
        }
        if not scan.available:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=scan.reason,
                notes=notes,
            )

        items = []
        for row in scan.people[:BUCKET_LIMIT]:
            content = f"Kurum künyesi (kendi yayını): {row.name}"
            if row.role:
                content += f" — {row.role}"
            items.append(
                make_evidence(
                    content=content,
                    source_engine="company_people",
                    provenance_refs=[row.page],
                    scope={"domain": domain, "claim": "publicly_listed", "kind": "person"},
                )
            )
        for address in scan.contacts[:10]:
            items.append(
                make_evidence(
                    content=f"Kurum iletişim adresi (kendi sayfasından): {address}",
                    source_engine="company_people",
                    provenance_refs=list(scan.pages_checked[:1]),
                    scope={"domain": domain, "claim": "publicly_listed", "kind": "contact"},
                )
            )

        if not items and not scan.errors:
            # Sayfalar hatasız tarandı, yapılandırılmış kişi verisi yok: yokluk iddiası.
            items.append(
                make_evidence(
                    content=(
                        f"{domain}: kurumun kendi sayfalarında (taranan: "
                        f"{len(scan.pages_checked)} sayfa) yapılandırılmış kişi "
                        "künyesi (schema.org/Person) veya mailto adresi bulunamadı."
                    ),
                    source_engine="company_people",
                    epistemic_type="absence",
                    provenance_refs=list(scan.pages_checked[:5]),
                    scope={"domain": domain, "claim": "absence"},
                )
            )

        notes["evidence_count"] = len(items)
        return CapabilityResult(capability_id=self.id, available=True, items=tuple(items), notes=notes)
