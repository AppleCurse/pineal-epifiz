"""`TaskContract` artık ÜRETİMDE: her ajan mührü sözleşme taşır.

[2026-10-23] Ölçüm: `TaskContract` (agent_core/domain/responsibility.py)
yalnız testlerden çağrılıyordu — "0 production reference" dedektörü haklıydı.
Silmedik: sözleşme, Sorumluluk Zinciri mührünün parçası oldu. Bu testler
"bağlandı" iddiasını kilitler:

  1. Mühür `integrity.contract` alanını taşır (hangi kriterlerle kapandığı
     denetimde görünür).
  2. Sözleşme alanları koşunun GERÇEK durumundan türetilir (uydurma kriter yok).
  3. Eksik sözleşme hâlâ fail-closed: `ensure_complete` ValueError atar.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_core.domain.responsibility import TaskContract, build_trail


def _executor():
    from agent_core.task_executor import PinealExecutor

    executor = object.__new__(PinealExecutor)
    executor._log = lambda *_a, **_k: None
    return executor


def test_trail_carries_a_complete_contract():
    executor = _executor()
    run = SimpleNamespace(task_id="op_123", status="completed", confidence=0.8, error_code=None)
    trail = executor._responsibility_trail(
        agent_name="osint_investigator", run=run, claimed="analiz tamamlandı",
    )
    contract = trail["integrity"]["contract"]
    assert contract["task_id"] == "op_123"
    assert contract["agent_id"] == "osint_investigator"
    # Kabul kriteri koşunun GERÇEK durumunu söyler (uydurma başarı değil).
    assert "completed" in contract["acceptance_criteria"][0]
    assert contract["forbidden_behaviors"], "sözleşme yasak davranış taşımıyor"


def test_contract_reflects_failure_status_honestly():
    executor = _executor()
    run = SimpleNamespace(task_id="op_err", status="error", confidence=None, error_code="X1")
    trail = executor._responsibility_trail(
        agent_name="human_behavior", run=run, claimed="hata", evidence_recorded=False,
    )
    assert "error" in trail["integrity"]["contract"]["acceptance_criteria"][0]
    # Dürüst hata iddiası ihlal DEĞİLDİR (ceza yalnız sahte başarıya).
    assert not trail["integrity"].get("violation")

    # Buna karşılık kanıtsız "tamam" iddiası mühür tarafından reddedilir.
    fake_success = executor._responsibility_trail(
        agent_name="human_behavior", run=run, claimed="completed", evidence_recorded=False,
    )
    assert fake_success["integrity"].get("violation"), (
        "kanıtsız başarı mühürde ihlal olarak görünmedi"
    )


def test_missing_task_id_does_not_produce_fabricated_contract():
    executor = _executor()
    run = SimpleNamespace(task_id=None, status="completed", confidence=1.0, error_code=None)
    trail = executor._responsibility_trail(agent_name="x", run=run, claimed="tamam")
    # task_id yoksa uydurulmaz; açık bir yer tutucu yazılır.
    assert trail["integrity"]["contract"]["task_id"] == "task"


@pytest.mark.parametrize("field,value", [
    ("task_id", "  "),
    ("acceptance_criteria", []),
    ("required_inputs", []),
    ("evidence_output", []),
])
def test_incomplete_contract_still_fails_closed(field, value):
    payload = {
        "task_id": "op_1", "agent_id": "agent",
        "acceptance_criteria": ["kriter"], "required_inputs": ["girdi"],
        "forbidden_behaviors": ["uydurma"], "success_condition": "ok",
        "failure_condition": "blocked", "evidence_output": ["kanıt"],
    }
    payload[field] = value
    with pytest.raises(ValueError):
        TaskContract(**payload).ensure_complete()


def test_build_trail_still_uses_the_eight_field_contract():
    """Mühür şeması bozulmadı: sözleşme `extra_integrity` içinde taşınır."""
    trail = build_trail(claimed="ok", evidence_recorded=True)
    assert set(trail.model_dump()) >= {
        "attempted_paths", "blockers", "support_requested", "missing",
        "next_action", "integrity", "sealed_at",
    }
