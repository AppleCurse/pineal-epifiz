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

__all__ = ["HandleProbeCapability"]


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


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
        if not _flag("ENABLE_CROSS_PLATFORM"):
            return Availability.unavailable("gate_disabled:ENABLE_CROSS_PLATFORM")
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
