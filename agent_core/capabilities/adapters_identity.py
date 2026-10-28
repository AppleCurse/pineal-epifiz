"""Kimlik sensörü — native çapraz platform kullanıcı-adı yoklaması.

Neden bu adaptör var (2026-10-23):
    "X'te bulunan hedef Instagram/Facebook/Threads'te de aransın" beklentisi
    yalnız ``ENABLE_MAIGRET`` kapısına bağlıydı. Maigret varsayılan KAPALI
    olduğu için çapraz arama pratikte hiç koşmuyordu. Bu yetenek dış paket
    gerektirmez (httpx zaten var) ve kendi kapısıyla (``ENABLE_CROSS_PLATFORM``)
    çalışır; maigret açıksa ikisi birbirini TAMAMLAR, biri diğerini ezmez.

Dürüstlük:
    * 404/410 → `absent`; login duvarı/403/429 → `unknown` (ASLA "yok" değil).
    * Yokluk iddiası yalnız sıfır hata + sıfır bilinmeyen ile mümkün
      (`absence_claimable`), o zaman `epistemic_type="absence"` kanıtı üretilir.
    * Her istek egress omurgasından (`purpose="sensor"`) → kasa kapısı devrede.
"""

from __future__ import annotations

from typing import Any

from agent_core.capabilities.base import (
    Availability,
    BaseCapability,
    CapabilityContext,
    CapabilityKind,
    CapabilityResult,
    make_evidence,
)

__all__ = ["HandleProbeCapability", "PhoneProbeCapability"]


class HandleProbeCapability(BaseCapability):
    """Kullanıcı adının bilinen platformlardaki varlığını yoklar (native)."""

    id = "sensor.identity.handle_probe"
    kind = CapabilityKind.SENSOR
    license = "native"  # kendi kodumuz — harici lisans yükü yok
    # Kasa kapısı zorunlu (OSINT çıkışı); çapraz platform yetkisi ayrı kapı.
    gates = frozenset({"vault", "ENABLE_CROSS_PLATFORM"})
    timeout_seconds = 60.0
    description = (
        "Kullanıcı adını Instagram/Facebook/Threads/X/TikTok/GitHub/Reddit/"
        "Pinterest/YouTube/Telegram profil adreslerinde yoklar; "
        "404/410 dışındaki her belirsizlik 'unknown' raporlanır."
    )

    def availability(self) -> Availability:
        """Bağımlılık yok → her zaman ``ok``. Kapı kararı PolicyKernel'indir.

        [2026-10-23 · B1/B2 dersi] Eski adaptörler env bayrağını BURADA da
        okuyordu; sonuç "iki farklı gerçek" oluyordu: politika onayla kapıyı
        açsa bile `availability()` env'e bakıp `gate_disabled` diyebiliyordu.
        Bu yetenek native (dış paket yok) olduğu için bağımlılık denetimi
        gerekmez; `ENABLE_CROSS_PLATFORM` kapısını yalnız politika uygular ve
        ret sebebi `denied_by` alanında makine-okunur görünür.
        """
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        from agent_core.services.handle_probe import probe_handle

        username = (ctx.subject or ctx.params.get("username") or "").strip()
        result = await probe_handle(username)
        notes: dict[str, Any] = {
            "provider": result.provider,
            "scanned_count": result.scanned_count,
            "error_count": result.error_count,
            "unknown_count": result.unknown_count,
            "absence_claimable": result.absence_claimable,
            "elapsed_ms": result.elapsed_ms,
            "platforms": [p.platform for p in result.probes],
        }

        if not result.available:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=f"probe_unavailable:{result.reason}",
                payload=result,
                notes=notes,
            )

        evidence = []
        for hit in result.claimed:
            evidence.append(make_evidence(
                content=f"{hit.platform} profilinde '{result.requested_username}' adlı hesap yanıt verdi: {hit.url}",
                source_engine="handle_probe",
                epistemic_type="observation",
                scope={"platform": hit.platform, "url": hit.url, "http_status": hit.http_status},
                source_metrics={"http_status": hit.http_status, "provider": result.provider},
            ))

        # "Hiçbir yerde yok" YALNIZ kanıtlanabilir yoklukta iddia edilir.
        if not result.claimed and result.absence_claimable:
            evidence.append(make_evidence(
                content=(
                    f"'{result.requested_username}' için yoklanan {result.scanned_count} platformun "
                    "hiçbirinde 200 yanıtı alınmadı (404/410); hata veya belirsizlik yok."
                ),
                source_engine="handle_probe",
                epistemic_type="absence",
                scope={"username": result.requested_username, "platforms": notes["platforms"]},
                source_metrics={"scanned_count": result.scanned_count},
            ))

        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=tuple(evidence),
            payload=result,
            notes=notes,
        )


class PhoneProbeCapability(BaseCapability):
    """Telefon numarası format, şebeke ve açık OSINT varlık taraması (native)."""

    id = "sensor.identity.phone_probe"
    kind = CapabilityKind.SENSOR
    license = "native"
    gates = frozenset({"vault"})
    timeout_seconds = 30.0
    description = (
        "Telefon numarasını E.164 standardına çevirir, operatör/şebeke ve hat türünü "
        "çözümler, WhatsApp/Telegram doğrudan varlık protokollerini ve açık web dijital "
        "ayak izini tarar."
    )

    def availability(self) -> Availability:
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        from agent_core.services.phone_probe import probe_phone

        raw_phone = (ctx.subject or ctx.params.get("phone") or "").strip()
        auto_bridge = bool(ctx.params.get("auto_bridge", True))

        result = await probe_phone(raw_phone, auto_bridge_social=auto_bridge)
        notes: dict[str, Any] = {
            "e164": result.metadata.e164,
            "carrier": result.metadata.carrier_name,
            "country": result.metadata.country_name,
            "line_type": result.metadata.line_type,
            "is_valid": result.metadata.is_valid,
            "messaging_count": len(result.messaging_probes),
            "web_hits_count": len(result.web_footprint_hits),
            "associated_handles": result.associated_handles,
            "elapsed_ms": result.elapsed_ms,
        }

        evidence = []
        if result.metadata.is_valid:
            evidence.append(make_evidence(
                content=(
                    f"Telefon doğrulaması ({result.metadata.e164}): "
                    f"Şebeke={result.metadata.carrier_name}, Bölge={result.metadata.country_name}, "
                    f"Hat={result.metadata.line_type}"
                ),
                source_engine="phone_probe",
                epistemic_type="observation",
                scope={"e164": result.metadata.e164, "carrier": result.metadata.carrier_name},
                source_metrics={"is_valid": result.metadata.is_valid},
            ))

        for hit in result.web_footprint_hits:
            evidence.append(make_evidence(
                content=f"Numarayla ilişkili açık web izi: {hit.get('url')} - {hit.get('snippet')[:120]}",
                source_engine="phone_probe_web",
                epistemic_type="observation",
                scope={"url": hit.get("url")},
                source_metrics={"engine": hit.get("engine")},
            ))

        for sp in result.social_probes:
            evidence.append(make_evidence(
                content=f"Numarayla bağlantılı '{sp.get('handle')}' adı {sp.get('platform')} profilinde bulundu: {sp.get('url')}",
                source_engine="phone_social_bridge",
                epistemic_type="observation",
                scope={"platform": sp.get("platform"), "url": sp.get("url")},
                source_metrics={"http_status": sp.get("http_status")},
            ))

        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=tuple(evidence),
            payload=result,
            notes=notes,
        )

