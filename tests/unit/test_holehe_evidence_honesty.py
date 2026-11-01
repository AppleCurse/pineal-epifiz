"""holehe bulguları KANIT gibi sunulmamalı (yanlış pozitif ölçümü).

[2026-10-23 incelemesi] Operatörün ölçümü: holehe 100 sitenin 68'inde hata
verdi ve `test@example.com` gibi bir adres için 9 sitede "kayıtlı" dedi.
Buna rağmen adaptör her isabeti `epistemic_type="observation"` olarak
mühürlüyordu — yani üçüncü taraf iddiası, doğrulanmış gözlem gibi rapora
gidiyordu.

Yeni sözleşme:
  * isabet → `inference` (gözlem değil),
  * metin "reports ... (unverified)",
  * `source_metrics["verification"] == "unverified_third_party"`,
  * hata oranı yüksekse `reliability == "low"`,
  * sıfır hata + sıfır isabet → `absence` (yalnız bu durumda yokluk iddiası).
"""

from __future__ import annotations

import pytest


class _Hit:
    def __init__(self, site: str) -> None:
        self.site = site


class _Scan:
    def __init__(self, sites, scanned=100, errors=0) -> None:
        self.provider = "holehe"
        self.available = True
        self.reason = None
        self.scanned_count = scanned
        self.error_count = errors
        self.found_sites = [_Hit(s) for s in sites]


@pytest.mark.asyncio
async def test_holehe_hits_are_marked_as_unverified_inference(monkeypatch):
    from agent_core.capabilities.adapters_osint import HoleheCapability
    from agent_core.capabilities.base import CapabilityContext
    from agent_core.services import holehe_scanner

    async def _fake_scan(_email):
        return _Scan(["instagram.com", "twitter.com"], scanned=100, errors=68)

    monkeypatch.setattr(holehe_scanner, "scan_email", _fake_scan)
    result = await HoleheCapability().run(CapabilityContext(subject="test@example.com"))

    assert result.available is True
    assert len(result.items) == 2
    for item in result.items:
        assert item.epistemic_type == "inference", item.epistemic_type
        assert "unverified" in item.content
        assert item.source_metrics["verification"] == "unverified_third_party"
        # 68/100 hata → güvenilirlik "low" olarak İŞARETLENİR.
        assert item.source_metrics["reliability"] == "low"


@pytest.mark.asyncio
async def test_holehe_absence_claim_needs_zero_errors(monkeypatch):
    from agent_core.capabilities.adapters_osint import HoleheCapability
    from agent_core.capabilities.base import CapabilityContext
    from agent_core.services import holehe_scanner

    async def _clean(_email):
        return _Scan([], scanned=50, errors=0)

    monkeypatch.setattr(holehe_scanner, "scan_email", _clean)
    result = await HoleheCapability().run(CapabilityContext(subject="a@b.c"))
    assert [i.epistemic_type for i in result.items] == ["absence"]

    async def _noisy(_email):
        return _Scan([], scanned=50, errors=17)

    monkeypatch.setattr(holehe_scanner, "scan_email", _noisy)
    result = await HoleheCapability().run(CapabilityContext(subject="a@b.c"))
    # Hatalı taramada "kayıtlı değil" DENMEZ.
    assert result.items == ()
