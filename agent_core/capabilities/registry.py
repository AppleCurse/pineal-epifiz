"""CapabilityRegistry — yetenek envanterinin TEK kaynağı.

Kural [009] (duplication dersi): "bu yetenek var mı / açık mı?" sorusunun
ikinci bir cevabı olamaz. Env anahtarı okuyan, config'den bayrak çeken veya
doğrudan import deneyen ikinci bir katman YARATILMAZ (C8 ölü-anahtar
denetiminin bulduğu sapma riskinin aynısı).

Kayıt anında doğrulama yapılır: kimliği bozuk, türü tanımsız veya sözleşmeyi
karşılamayan yetenek kaydedilmez — hata kurulum anında, sessizlik değil.
"""

from __future__ import annotations

import asyncio
import re
import threading
from typing import Any, Iterable

from agent_core.capabilities.base import Availability, BaseCapability, Capability, CapabilityKind
from agent_core.capabilities.policy import PolicyKernel, PolicyState

__all__ = ["CapabilityRegistry", "default_registry", "bootstrap"]

_ID_RE = re.compile(r"^[a-z0-9]+(\.[a-z0-9_]+){1,4}$")


class CapabilityRegistry:
    """İplik-güvenli yetenek kayıt defteri."""

    def __init__(self) -> None:
        self._caps: dict[str, Capability] = {}
        self._lock = threading.RLock()

    # --- yazma -----------------------------------------------------------
    def register(self, capability: Capability, *, replace: bool = False) -> None:
        """Yeteneği kaydeder. Aynı kimlik ikinci kez gelirse hata (tek kaynak)."""
        if not isinstance(capability, Capability) and not isinstance(capability, BaseCapability):
            raise TypeError(
                f"register: {type(capability).__name__} Capability sözleşmesini karşılamıyor"
            )
        cap_id = getattr(capability, "id", "") or ""
        if not _ID_RE.match(cap_id):
            raise ValueError(
                "register: geçersiz capability id; 'küçük.noktalı' sözdizimi gerekir "
                f"(örn. 'sensor.x.twscrape'), gelen={cap_id!r}"
            )
        kind = getattr(capability, "kind", None)
        if not isinstance(kind, CapabilityKind):
            raise ValueError(f"register: {cap_id} kind alanı CapabilityKind olmalı")
        with self._lock:
            if cap_id in self._caps and not replace:
                raise ValueError(
                    f"register: '{cap_id}' zaten kayıtlı (ikinci kaynak yasak; "
                    "replace=True yalnız test içindir)"
                )
            self._caps[cap_id] = capability

    def unregister(self, cap_id: str) -> None:
        with self._lock:
            self._caps.pop(cap_id, None)

    def clear(self) -> None:
        """Yalnız testler için: defteriyi boşaltır."""
        with self._lock:
            self._caps.clear()

    # --- okuma -----------------------------------------------------------
    def has(self, cap_id: str) -> bool:
        with self._lock:
            return cap_id in self._caps

    def get(self, cap_id: str) -> Capability:
        """Yeteneği döndürür; yoksa bilinen kimlikleri da listeleyen hata verir."""
        with self._lock:
            cap = self._caps.get(cap_id)
        if cap is None:
            known = ", ".join(sorted(self._caps)) or "(boş)"
            raise KeyError(f"capability yok: {cap_id!r} — kayıtlı yetenekler: {known}")
        return cap

    def ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._caps))

    def by_kind(self, kind: CapabilityKind) -> tuple[Capability, ...]:
        with self._lock:
            return tuple(c for c in self._caps.values() if getattr(c, "kind", None) is kind)

    def __len__(self) -> int:
        with self._lock:
            return len(self._caps)

    def __iter__(self):
        with self._lock:
            return iter(tuple(self._caps.values()))

    # --- durum -----------------------------------------------------------
    def status(
        self,
        state: PolicyState | None = None,
        *,
        kernel: PolicyKernel | None = None,
    ) -> list[dict[str, Any]]:
        """UI/telemetri için yetenek durum tablosu (sıralı, deterministik).

        Her satır: id, kind, license, available, reason, gates, policy_allowed,
        policy_reason, local_available/local_reason, verification.
        ``available`` is effective when state is supplied; without state it is
        local-only. Kullanılamayan yetenek için sebep MAKİNE-OKUNUR döner;
        asla "çalıştı" gibi bir görüntü üretilmez.
        """
        kernel = kernel or PolicyKernel()
        rows: list[dict[str, Any]] = []
        for cap in sorted(self._caps.values(), key=lambda c: c.id):
            try:
                avail: Availability = cap.availability()
                reason = None if avail.available else (avail.reason or "unavailable")
                available = bool(avail.available)
            except Exception as exc:  # availability() asla patlamamalı; patlarsa dürüst ret
                available, reason = False, f"availability_error:{type(exc).__name__}"
            decision = kernel.evaluate(getattr(cap, "gates", frozenset()), state) if state else None
            # With an explicit policy state, `available` means EFFECTIVE static
            # readiness, not merely "the Python package exists". Keep the local
            # result separately for diagnostics. Async preflight refines this;
            # a static table never claims live execution verification.
            policy_allowed = None if decision is None else decision.allowed
            effective = available and policy_allowed is not False
            effective_reason = reason
            if decision is not None and not decision.allowed:
                effective_reason = f"policy:{decision.reason}"
            verification = "static"
            if effective and getattr(cap, "requires_preflight", False):
                effective = False
                effective_reason = "preflight_required"
                verification = "required"
            rows.append(
                {
                    "id": cap.id,
                    "kind": getattr(cap, "kind", CapabilityKind.SENSOR).value,
                    "license": getattr(cap, "license", "unknown"),
                    "available": effective if state is not None else available,
                    "reason": effective_reason if state is not None else reason,
                    "local_available": available,
                    "local_reason": reason,
                    "verification": verification,
                    "live_execution_verified": False,
                    "gates": sorted(getattr(cap, "gates", frozenset())),
                    "policy_allowed": None if decision is None else decision.allowed,
                    "policy_reason": None if decision is None else decision.reason,
                    "policy_gate": None if decision is None else decision.gate,
                }
            )
        return rows

    async def readiness(
        self, state: PolicyState, *, kernel: PolicyKernel | None = None,
    ) -> list[dict[str, Any]]:
        """Effective readiness using the SAME policy/preflight path as run().

        Local checks only; does not scan targets, spend API credits or assert
        that a remote service works. Service probes belong to the explicit audit.
        """
        from agent_core.capabilities.runner import CapabilityRunner
        runner = CapabilityRunner(registry=self, kernel=kernel)
        rows = self.status(state, kernel=kernel)
        for row in rows:
            cap = self.get(row["id"])
            # Local-only preflight diagnostics are safe to measure even when
            # policy denies execution. They never call run() or a target.
            minor_case = getattr(state, "minor_case", None)
            minor_blocked = bool(minor_case is not None and getattr(minor_case, "subject_is_minor", True))
            if getattr(cap, "requires_preflight", False) and row["local_available"] is True and not minor_blocked:
                try:
                    local_ready = await asyncio.wait_for(cap.preflight(), timeout=10.0)
                    row["local_preflight_available"] = bool(local_ready.available)
                    row["local_preflight_reason"] = local_ready.reason
                except asyncio.TimeoutError:
                    row["local_preflight_available"] = False
                    row["local_preflight_reason"] = "preflight_timeout"
                except Exception as exc:
                    row["local_preflight_available"] = False
                    row["local_preflight_reason"] = f"preflight_error:{type(exc).__name__}"
            if row["policy_allowed"] is not True or row["local_available"] is not True:
                continue
            result = await runner.preflight(row["id"], state=state)
            row["available"] = result.available
            row["reason"] = result.unavailable_reason
            row["verification"] = "preflight"
            row["denied_by"] = result.denied_by
        return rows


#: Süreç genelinde tek kayıt defteri. Doldurma ``bootstrap()`` ile açıkça yapılır
#: (import yan etkisi yok — testler ve CI deterministik kalır).
default_registry = CapabilityRegistry()


def bootstrap(
    registry: CapabilityRegistry | None = None,
    capabilities: Iterable[Capability] | None = None,
) -> CapabilityRegistry:
    """Yerleşik adaptörleri kaydeder (tekrar çağrıldığında güvenle atlar)."""
    # DİKKAT: `registry or default_registry` YAZILMAZ — boş registry'nin
    # __len__'i 0'dır ve `or` onu yanlışlıkla varsayılanla değiştirir (ikinci
    # kaynak sapması). Açık None kontrolü zorunludur.
    reg = registry if registry is not None else default_registry
    if capabilities is None:
        from agent_core.capabilities.adapters_identity import (
            HandleProbeCapability,
            PhoneProbeCapability,
        )
        from agent_core.capabilities.adapters_osint import (
            HoleheCapability,
            MaigretCapability,
            SocidCapability,
        )
        from agent_core.capabilities.adapters_sensors import (
            AgentReachCapability,
            InstagrapiCapability,
            SearXNGCapability,
            XTwscrapeCapability,
        )
        from agent_core.capabilities.adapters_company import (
            CompanyHarvesterCapability,
            CompanyPeopleCapability,
            CompanySeoCapability,
        )
        from agent_core.capabilities.adapters_jury import LocalJuryCapability
        from agent_core.capabilities.adapters_media import (
            MediaFetchCapability,
            MediaFramesCapability,
            MediaSimilarityCapability,
            MediaTranscriptCapability,
        )
        from agent_core.capabilities.adapters_report_factory import (
            ReportDiagramCapability,
            ReportPdfCapability,
            ReportVideoCapability,
        )
        from agent_core.capabilities.adapters_report import ReportScriptCapability
        from agent_core.capabilities.adapters_voice import (
            LocalSTTCapability,
            LocalTTSCapability,
        )
        from agent_core.capabilities.adapters_web import (
            Crawl4AICapability,
            ScraplingCapability,
            TrafilaturaCapability,
        )
        from agent_core.capabilities.adapters_language import (
            LanguageDetectCapability,
            LocalTranslateCapability,
        )

        capabilities = (
            # --- kimlik / OSINT
            MaigretCapability(),
            HoleheCapability(),
            SocidCapability(),
            # [2026-10-23] native çapraz platform yoklaması (paket gerektirmez);
            # maigret kapalıyken de IG/FB/Threads/X... araması gerçekten koşar.
            HandleProbeCapability(),
            # [2026-10-25] native telefon numarası OSINT ve varlık yoklaması
            PhoneProbeCapability(),
            # --- temiz metin omurgası (sıra: trafilatura → crawl4ai → scrapling)
            TrafilaturaCapability(),
            Crawl4AICapability(),
            ScraplingCapability(),
            # --- sensörler
            XTwscrapeCapability(),
            InstagrapiCapability(),
            AgentReachCapability(),
            SearXNGCapability(),
            # --- ses (FAZ C · C2/C3/C4): yerel TTS + STT + sesli rapor
            LocalTTSCapability(),
            LocalSTTCapability(),
            ReportScriptCapability(),
            # --- dil (FAZ D · D4): tespit deterministik, çeviri yerel
            LanguageDetectCapability(),
            LocalTranslateCapability(),
            # --- yerel jüri (FAZ D · D2): karar makineden çıkmaz, maliyet 0
            LocalJuryCapability(),
            # --- kurum hedefi (FAZ D · D6): theHarvester + açık SEO + kişi künyesi
            CompanyHarvesterCapability(),
            CompanySeoCapability(),
            CompanyPeopleCapability(),
            # --- rapor fabrikası (FAZ D · D5): pdf · diyagram · video + mühür
            ReportPdfCapability(),
            ReportDiagramCapability(),
            ReportVideoCapability(),
            # --- medya adli hattı (FAZ D · D3): indir · kare · yazı · benzerlik
            MediaFetchCapability(),
            MediaFramesCapability(),
            MediaTranscriptCapability(),
            MediaSimilarityCapability(),
        )
    for cap in capabilities:
        if reg.has(cap.id):
            continue
        reg.register(cap)
    return reg
