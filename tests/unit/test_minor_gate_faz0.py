"""ÇOCUK KIRMIZI ÇİZGİSİ — kabul testleri (Faz 0).

Ürün kuralı:
    18 yaş altı = çocuktur. Normalde HİÇ ARAŞTIRILAMAZ.
    TEK istisna kayıp/yaralanma vakası; o da ancak şu 4 şartla:
    aile bilgisi + net sebep + doğrulama + konsorsiyum onayı (en az 2).

Bu dosya, o kuralın kodda gerçekten çalıştığını kanıtlar. Yetişkin için
sistemin HİÇBİR engel koymadığını da ayrıca test eder.
"""

from __future__ import annotations

import json

import pytest

from agent_core.capabilities import (
    CapabilityContext,
    CapabilityRegistry,
    PolicyState,
    bootstrap,
    run_capability,
)
from agent_core.safety import (
    MIN_COUNCIL_APPROVALS,
    MinorCaseContext,
    MinorCaseLedger,
    MinorGate,
)


def _approved_case(**over) -> MinorCaseContext:
    """Dört şartı da sağlayan kayıp çocuk vakası."""
    base = dict(
        subject_is_minor=True,
        case_type="missing_or_harm",
        family_notified=True,
        reason="Çocuk 3 gündür kayıp; aile karakola başvurdu, dosya no 2026/4471.",
        verified=True,
        council_approvals=("operatör", "konsey_uye_1", "konsey_uye_2"),
        case_id="case-2026-4471",
    )
    base.update(over)
    return MinorCaseContext(**base)


# ------------------------------------------------------------------ kilit
def test_minor_blocked_when_no_council_approval():
    case = _approved_case(council_approvals=("operatör",))  # tek onay
    decision = MinorGate().evaluate(case)
    assert decision.allowed is False
    assert decision.reason_code == "council_approval_missing"
    assert str(MIN_COUNCIL_APPROVALS) in decision.detail


def test_minor_blocked_when_family_not_informed():
    decision = MinorGate().evaluate(_approved_case(family_notified=False))
    assert decision.allowed is False
    assert decision.reason_code == "family_not_notified"


def test_minor_blocked_when_reason_not_clear():
    decision = MinorGate().evaluate(_approved_case(reason="kayıp"))
    assert decision.allowed is False
    assert decision.reason_code == "reason_missing"


def test_minor_blocked_when_not_verified():
    decision = MinorGate().evaluate(_approved_case(verified=False))
    assert decision.allowed is False
    assert decision.reason_code == "not_verified"


def test_minor_blocked_for_non_missing_case_type():
    decision = MinorGate().evaluate(_approved_case(case_type="profile"))
    assert decision.allowed is False
    assert decision.reason_code == "case_type_not_allowed"


def test_minor_allowed_when_all_four_conditions_met():
    decision = MinorGate().evaluate(_approved_case())
    assert decision.allowed is True
    assert decision.reason_code == "approved"


def test_adult_is_never_blocked():
    decision = MinorGate().evaluate(MinorCaseContext(subject_is_minor=False))
    assert decision.allowed is True
    assert decision.reason_code == "not_minor"


def test_no_case_context_means_no_child_lock():
    assert MinorGate().evaluate(None).allowed is True


# --------------------------------------------------- runner üzerinden küresel kilit
@pytest.mark.asyncio
async def test_runner_blocks_every_capability_for_unapproved_minor_case():
    """Kilit küreseldir: hiçbir yetenek, hiçbir kapı kombinasyonuyla atlayamaz."""
    reg = CapabilityRegistry()
    bootstrap(reg)
    state = PolicyState(
        vault_locked=False,
        enabled_flags={"ENABLE_MAIGRET": True, "ENABLE_HOLEHE": True},
        minor_case=MinorCaseContext(subject_is_minor=True, case_type="missing_or_harm"),
    )
    for cap in reg:
        result = await run_capability(
            cap.id, CapabilityContext(subject="cocuk_hedef"), registry=reg, state=state
        )
        assert result.denied_by == "minor_safe", f"{cap.id} çocuk kilidini atladı"
        assert result.items == ()
        assert result.unavailable_reason.startswith("minor:")


@pytest.mark.asyncio
async def test_runner_allows_approved_missing_child_case():
    """Kayıp çocuk vakası, 4 şart tamamsa ARAŞTIRILABİLİR (istisna çalışır)."""
    reg = CapabilityRegistry()
    bootstrap(reg)
    state = PolicyState(
        vault_locked=False,
        enabled_flags={"ENABLE_HOLEHE": True},
        minor_case=_approved_case(),
    )
    result = await run_capability(
        "sensor.identity.holehe",
        CapabilityContext(subject="kayip_cocuk@example.com"),
        registry=reg,
        state=state,
    )
    # Kilit açıldı: artık politikaya/uygunluğa bakılır, "minor:" engeli yoktur.
    assert result.denied_by != "minor_safe"
    assert not str(result.unavailable_reason).startswith("minor:")


@pytest.mark.asyncio
async def test_vault_still_rules_over_approved_minor_case():
    """Kasa kapalıysa onaylı vaka bile koşamaz (kilit, kasayı ezmez)."""
    reg = CapabilityRegistry()
    bootstrap(reg)
    state = PolicyState(vault_locked=True, minor_case=_approved_case())
    result = await run_capability(
        "extractor.identity.socid",
        CapabilityContext(subject="https://x.com/kayip"),
        registry=reg,
        state=state,
    )
    assert result.denied_by == "vault"
    assert result.items == ()


@pytest.mark.asyncio
async def test_adult_case_runs_without_any_child_lock():
    """Yetişkin için sistem engel koymaz: sonuç 'minor:' ile başlamaz."""
    reg = CapabilityRegistry()
    bootstrap(reg)
    state = PolicyState(
        vault_locked=False,
        minor_case=MinorCaseContext(subject_is_minor=False),
    )
    result = await run_capability(
        "extractor.identity.socid", CapabilityContext(subject=""), registry=reg, state=state
    )
    assert result.denied_by != "minor_safe"


# -------------------------------------------------------------------- kayıt
def test_ledger_records_denied_minor_attempt_without_raw_identity(tmp_path):
    ledger = MinorCaseLedger(tmp_path / "ledger" / "minor-cases.jsonl")
    case = _approved_case(council_approvals=("tek_kisi",))
    decision = MinorGate().evaluate(case)
    entry = ledger.record(case, decision, capability_id="sensor.x", subject="Ahmet Yılmaz")

    assert entry["allowed"] is False
    assert entry["reason_code"] == "council_approval_missing"
    assert "Ahmet" not in json.dumps(entry, ensure_ascii=False)  # ham kimlik yok
    assert entry["subject_ref"].startswith("sha256:")
    assert entry["approvals"] == ["tek_kisi"]

    lines = (tmp_path / "ledger" / "minor-cases.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["reason_code"] == "council_approval_missing"


def test_ledger_records_approved_case_with_approvals(tmp_path):
    ledger = MinorCaseLedger(tmp_path / "minor.jsonl")
    case = _approved_case()
    entry = ledger.record(case, MinorGate().evaluate(case), capability_id="sensor.x", subject="x")
    assert entry["allowed"] is True
    assert entry["case_id"] == "case-2026-4471"
    assert len(entry["approvals"]) >= MIN_COUNCIL_APPROVALS
