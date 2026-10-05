"""Capability Spine (Faz 0) kabul testleri.

Bu dosya, yıldız depo karar ağacındaki Faz 0 "Definition of Done" maddelerini
kilitler:

    1. Registry tek kaynak: kimlik doğrulama, tekrar kayıt reddi, sözleşme kontrolü
    2. PolicyKernel fail-closed: bilinmeyen kapı = ret, kasa kapalı = ret
    3. Runner: bilinmeyen yetenek / ret / unavailable / timeout / hata → 0 kanıt
    4. Kanıt mührü: üretilen her kayıt EvidenceItem şemasını geçer
    5. Eşdeğerlik: adaptörler eski tarayıcılarla aynı dürüst sonucu verir
       (Faz 0.2 taşıması bitene kadar çift-kaynak sapmasını önler)

Hiçbir test ağa çıkmaz, hiçbir test gerçek OSINT sağlayıcısı çağırmaz.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from agent_core.capabilities import (
    Availability,
    BaseCapability,
    CapabilityContext,
    CapabilityKind,
    CapabilityRegistry,
    CapabilityResult,
    PolicyKernel,
    PolicyState,
    bootstrap,
    make_evidence,
    run_capability,
)
from agent_core.capabilities.adapters_osint import (
    HoleheCapability,
    MaigretCapability,
    SocidCapability,
)
from agent_core.capabilities.runner import CapabilityRunner

EVIDENCE_ID_RE = re.compile(r"^ev_[0-9a-f]{20}$")


# ---------------------------------------------------------------- yardımcılar
class _DummyCapability(BaseCapability):
    """Test çifti: davranışı dışarıdan ayarlanabilir."""

    def __init__(
        self,
        cap_id: str = "test.dummy",
        *,
        gates=frozenset(),
        available: bool = True,
        reason: str | None = None,
        items=(),
        raise_exc: BaseException | None = None,
        sleep: float = 0.0,
        bad_result: bool = False,
    ) -> None:
        self.id = cap_id
        self.kind = CapabilityKind.ANALYZER
        self.license = "MIT"
        self.gates = frozenset(gates)
        self._available = available
        self._reason = reason
        self._items = tuple(items)
        self._raise = raise_exc
        self._sleep = sleep
        self._bad_result = bad_result

    def availability(self) -> Availability:
        return Availability(self._available, self._reason)

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        if self._sleep:
            await asyncio.sleep(self._sleep)
        if self._raise is not None:
            raise self._raise
        if self._bad_result:
            return {"items": []}  # sözleşme ihlali: CapabilityResult değil
        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=self._items,
            notes={"echo": ctx.subject},
        )


def _evidence(**kwargs):
    return make_evidence(content="örnek kanıt", source_engine="test_engine", **kwargs)


# ------------------------------------------------------- 1) registry tek kaynak
def test_registry_rejects_invalid_id():
    reg = CapabilityRegistry()
    with pytest.raises(ValueError, match="geçersiz capability id"):
        reg.register(_DummyCapability(cap_id="BÜYÜK HARF"))


def test_registry_rejects_duplicate_id():
    reg = CapabilityRegistry()
    reg.register(_DummyCapability())
    with pytest.raises(ValueError, match="zaten kayıtlı"):
        reg.register(_DummyCapability())


def test_registry_rejects_contract_violation():
    class _Broken:
        id = "test.broken"

    reg = CapabilityRegistry()
    with pytest.raises(TypeError, match="Capability sözleşmesi"):
        reg.register(_Broken())  # type: ignore[arg-type]


def test_registry_rejects_bad_kind():
    reg = CapabilityRegistry()
    cap = _DummyCapability(cap_id="test.badkind")
    cap.kind = "sensor"  # type: ignore[assignment]  # CapabilityKind değil
    with pytest.raises(ValueError, match="CapabilityKind"):
        reg.register(cap)


def test_registry_status_reports_machine_readable_reason():
    reg = CapabilityRegistry()
    reg.register(_DummyCapability())
    reg.register(_DummyCapability(cap_id="test.off", available=False, reason="dependency_missing:x"))
    rows = reg.status()
    assert [r["id"] for r in rows] == ["test.dummy", "test.off"]
    off = rows[1]
    assert off["available"] is False
    assert off["reason"] == "dependency_missing:x"


def test_registry_status_survives_availability_crash():
    class _Boom(BaseCapability):
        id = "test.boom"
        kind = CapabilityKind.SENSOR

        def availability(self):
            raise RuntimeError("patladı")

        async def run(self, ctx):
            return CapabilityResult(capability_id=self.id, available=True)

    reg = CapabilityRegistry()
    reg.register(_Boom())
    row = reg.status()[0]
    assert row["available"] is False
    assert row["reason"] == "availability_error:RuntimeError"


# ---------------------------------------------------------- 2) politika çekirdeği
def test_policy_denies_unknown_gate_fail_closed():
    kernel = PolicyKernel()
    decision = kernel.evaluate(frozenset({"gelecegin_kapisi"}), PolicyState())
    assert decision.allowed is False
    assert decision.reason == "unknown_gate"


def test_policy_denies_vault_locked():
    kernel = PolicyKernel()
    decision = kernel.evaluate(frozenset({"vault"}), PolicyState(vault_locked=True))
    assert decision.allowed is False
    assert decision.reason == "vault_locked"


def test_policy_denies_disabled_env_flag():
    kernel = PolicyKernel()
    denied = kernel.evaluate(frozenset({"ENABLE_X"}), PolicyState())
    assert denied.allowed is False and denied.reason == "gate_disabled"
    allowed = kernel.evaluate(frozenset({"ENABLE_X"}), PolicyState(enabled_flags={"ENABLE_X": True}))
    assert allowed.allowed is True


def test_policy_rate_unknown_is_denied():
    kernel = PolicyKernel()
    assert kernel.evaluate(frozenset({"rate"}), PolicyState()).reason == "rate_state_missing"
    assert kernel.evaluate(frozenset({"rate"}), PolicyState(rate_ok=True)).allowed is True


def test_policy_budget():
    kernel = PolicyKernel()
    assert kernel.evaluate(frozenset({"budget"}), PolicyState(spent_usd=2.0, budget_usd=1.0)).reason == (
        "budget_exhausted"
    )


def test_no_consent_gate_exists():
    """Karar mercii operatördür: hedef rızası diye bir kapı YOKTUR.
    Eski bir yetenek 'consent' bildirirse bilinmeyen kapı sayılır ve çalışmaz."""
    kernel = PolicyKernel()
    assert "consent" not in kernel.KNOWN_GATES
    decision = kernel.evaluate(frozenset({"consent"}), PolicyState())
    assert decision.allowed is False
    assert decision.reason == "unknown_gate"


# ------------------------------------------------------------------ 3) koşucu
@pytest.mark.asyncio
async def test_runner_unknown_capability_is_not_an_exception():
    result = await run_capability("sensor.yok.boyle", registry=CapabilityRegistry())
    assert result.available is False
    assert result.unavailable_reason == "unknown_capability"
    assert result.items == ()


@pytest.mark.asyncio
async def test_runner_denied_by_policy_gate():
    reg = CapabilityRegistry()
    reg.register(_DummyCapability(gates=frozenset({"vault"})))
    result = await run_capability("test.dummy", registry=reg, state=PolicyState(vault_locked=True))
    assert result.available is False
    assert result.denied_by == "vault"
    assert result.unavailable_reason == "policy:vault_locked"
    assert result.items == ()


@pytest.mark.asyncio
async def test_runner_unavailable_capability_produces_no_evidence():
    reg = CapabilityRegistry()
    reg.register(_DummyCapability(available=False, reason="dependency_missing:maigret"))
    result = await run_capability("test.dummy", registry=reg)
    assert result.ok is False
    assert result.unavailable_reason == "dependency_missing:maigret"
    assert result.items == ()


@pytest.mark.asyncio
async def test_runner_timeout_is_fail_closed():
    reg = CapabilityRegistry()
    reg.register(_DummyCapability(sleep=0.2))
    result = await run_capability(
        "test.dummy",
        CapabilityContext(timeout_seconds=0.01),
        registry=reg,
    )
    assert result.available is False
    assert result.unavailable_reason == "timeout"
    assert result.items == ()


@pytest.mark.asyncio
async def test_runner_exception_is_fail_closed():
    reg = CapabilityRegistry()
    reg.register(_DummyCapability(raise_exc=RuntimeError("sağlayıcı çöktü")))
    result = await run_capability("test.dummy", registry=reg)
    assert result.available is False
    assert result.unavailable_reason == "run_error"
    assert result.error == "RuntimeError"
    assert result.items == ()


@pytest.mark.asyncio
async def test_runner_rejects_contract_violating_result():
    reg = CapabilityRegistry()
    reg.register(_DummyCapability(bad_result=True))
    result = await run_capability("test.dummy", registry=reg)
    assert result.unavailable_reason == "contract_violation"
    assert result.items == ()


@pytest.mark.asyncio
async def test_runner_success_carries_evidence_and_duration():
    reg = CapabilityRegistry()
    item = _evidence(provenance_refs=["https://example.com/x"])
    reg.register(_DummyCapability(items=(item,)))
    result = await run_capability("test.dummy", CapabilityContext(subject="hedef"), registry=reg)
    assert result.ok is True
    assert result.items[0].evidence_id == item.evidence_id
    assert result.notes["echo"] == "hedef"
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_runner_emit_receives_telemetry_dict():
    seen = []
    reg = CapabilityRegistry()
    reg.register(_DummyCapability(items=(_evidence(),)))
    runner = CapabilityRunner(registry=reg, emit=seen.append)
    await runner.run("test.dummy")
    assert seen and seen[0]["capability_id"] == "test.dummy"
    assert seen[0]["evidence_count"] == 1


# -------------------------------------------------------------- 4) kanıt mührü
def test_make_evidence_conforms_to_schema():
    item = _evidence(provenance_refs=["https://example.com/p"], epistemic_type="observation")
    assert EVIDENCE_ID_RE.match(item.evidence_id)
    assert item.epistemic_type == "observation"
    assert item.source_engine == "test_engine"
    assert item.provenance_refs == ["https://example.com/p"]
    assert item.observed_at is not None


def test_make_evidence_rejects_empty_content():
    with pytest.raises(ValueError, match="content boş"):
        make_evidence(content="   ", source_engine="x")


def test_make_evidence_rejects_bad_epistemic_type():
    with pytest.raises(ValueError, match="epistemic_type"):
        make_evidence(content="x", source_engine="x", epistemic_type="tahmin")


# ------------------------------------------- 5) OSINT adaptörleri + eşdeğerlik
def test_bootstrap_is_idempotent_and_registers_osint_adapters():
    reg = CapabilityRegistry()
    bootstrap(reg)
    first = reg.ids()
    bootstrap(reg)  # ikinci çağrı sapma yaratmamalı
    assert first == reg.ids()
    assert "sensor.identity.maigret" in first
    assert "sensor.identity.holehe" in first
    assert "extractor.identity.socid" in first


def test_gated_adapters_report_gate_disabled(monkeypatch):
    monkeypatch.delenv("ENABLE_MAIGRET", raising=False)
    monkeypatch.delenv("ENABLE_HOLEHE", raising=False)
    assert MaigretCapability().availability().reason == "gate_disabled:ENABLE_MAIGRET"
    assert HoleheCapability().availability().reason == "gate_disabled:ENABLE_HOLEHE"


@pytest.mark.asyncio
async def test_maigret_adapter_matches_legacy_scanner_when_gate_closed(monkeypatch):
    """Eşdeğerlik: kapı kapalıyken adaptör, eski tarayıcıyla aynı sonucu verir."""
    monkeypatch.delenv("ENABLE_MAIGRET", raising=False)
    from agent_core.services import maigret_scanner

    legacy = await maigret_scanner.scan_username("ornek_kullanici")
    ctx = CapabilityContext(subject="ornek_kullanici")
    adapted = await MaigretCapability().run(ctx)

    assert legacy.available is False
    assert adapted.available is False
    assert adapted.unavailable_reason == f"scan_unavailable:{legacy.reason}"
    assert adapted.items == ()  # kanıt uydurulmadı
    assert adapted.payload is not None


@pytest.mark.asyncio
async def test_holehe_adapter_matches_legacy_scanner_when_gate_closed(monkeypatch):
    monkeypatch.delenv("ENABLE_HOLEHE", raising=False)
    from agent_core.services import holehe_scanner

    legacy = await holehe_scanner.scan_email("ornek@example.com")
    adapted = await HoleheCapability().run(CapabilityContext(subject="ornek@example.com"))

    assert legacy.available is False
    assert adapted.available is False
    assert adapted.unavailable_reason == f"scan_unavailable:{legacy.reason}"
    assert adapted.items == ()


@pytest.mark.asyncio
async def test_socid_adapter_matches_legacy_extractor_on_invalid_url():
    from agent_core.services import socid_enricher

    legacy = await socid_enricher.extract_profile("")
    adapted = await SocidCapability().run(CapabilityContext(subject=""))

    assert legacy.available is False
    assert adapted.available is False
    assert adapted.unavailable_reason == f"extract_unavailable:{legacy.reason}"


@pytest.mark.asyncio
async def test_maigret_adapter_emits_evidence_for_hits(monkeypatch):
    """Bulgu varsa kanıt üretilir; provenance ve kapsam şemaya uyar."""
    monkeypatch.setenv("ENABLE_MAIGRET", "true")
    from agent_core.services import maigret_scanner

    class _Hit:
        site = "example"
        url = "https://example.com/ornek_kullanici"

    class _Scan:
        available = True
        reason = None
        provider = "maigret"
        found_sites = [_Hit()]
        scanned_count = 100
        error_count = 0

    async def _fake_scan(username, **_kwargs):
        return _Scan()

    monkeypatch.setattr(maigret_scanner, "scan_username", _fake_scan)
    monkeypatch.setattr(
        "agent_core.capabilities.adapters_osint._module_available", lambda _name: True
    )

    result = await MaigretCapability().run(CapabilityContext(subject="ornek_kullanici"))
    assert result.ok is True
    item = result.items[0]
    assert EVIDENCE_ID_RE.match(item.evidence_id)
    assert item.source_engine == "maigret"
    assert item.provenance_refs == ["https://example.com/ornek_kullanici"]
    assert item.scope == {"kind": "identity_presence", "site": "example"}


@pytest.mark.asyncio
async def test_maigret_adapter_emits_reliable_absence_only_when_zero_errors(monkeypatch):
    from agent_core.services import maigret_scanner

    class _Scan:
        available = True
        reason = None
        provider = "maigret"
        found_sites = []

        def __init__(self, scanned, errors):
            self.scanned_count = scanned
            self.error_count = errors

    async def _fake_scan(username, **_kwargs):
        return _Scan(100, 0)

    monkeypatch.setattr(maigret_scanner, "scan_username", _fake_scan)
    clean = await MaigretCapability().run(CapabilityContext(subject="yok_kullanici"))
    assert len(clean.items) == 1
    assert clean.items[0].epistemic_type == "absence"

    async def _fake_scan_errors(username, **_kwargs):
        return _Scan(100, 7)

    monkeypatch.setattr(maigret_scanner, "scan_username", _fake_scan_errors)
    noisy = await MaigretCapability().run(CapabilityContext(subject="yok_kullanici"))
    assert noisy.items == ()  # hatalı taramada "yok" iddia edilmez


# ------------------------------------------- 6) tüzük ↔ kod bağı (Madde 4/5/7)
@pytest.mark.asyncio
async def test_person_data_capabilities_carry_vault_gate():
    """Tüzük Madde 4: OPERATÖR mandalı (kasa) her kişi-verisi yeteneğinde zorunludur.
    Hedef rızası kapısı YOKTUR — karar mercii operatördür."""
    reg = CapabilityRegistry()
    bootstrap(reg)
    identity_caps = [
        cap for cap in reg if cap.id.startswith(("sensor.identity", "extractor.identity"))
    ]
    assert identity_caps, "kimlik yeteneği bulunamadı — test yanlış daralmış"
    for cap in identity_caps:
        assert "vault" in cap.gates, f"{cap.id}: kasa kapısı yok (Tüzük Md.4)"
        assert "consent" not in cap.gates, f"{cap.id}: hedef rıza kapısı geri gelmiş"


@pytest.mark.asyncio
async def test_vault_lock_blocks_every_registered_capability():
    """Tüzük Md.4: kasa kilitliyken kayıtlı hiçbir yetenek koşamaz (istisna yok)."""
    reg = CapabilityRegistry()
    bootstrap(reg)
    for cap in reg:
        result = await run_capability(
            cap.id,
            CapabilityContext(subject="hedef"),
            registry=reg,
            state=PolicyState(vault_locked=True),
        )
        assert result.denied_by == "vault", f"{cap.id} kasa kilidini atladı"
        assert result.items == ()
