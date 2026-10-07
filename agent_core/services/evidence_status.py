"""Kanonik kanıt durumu sözleşmesi.

Arayüzler bir görevin ``status`` alanından "başarılı" anlamı çıkarmamalıdır.
Özellikle ``halted_evidence`` ve ``completed_no_decision`` yolları kullanıcıya
aynı, açık uyarıyı göstermelidir. Bu modül backend ve testlerin paylaşacağı
küçük, JSON-uyumlu bir sınıflandırıcıdır; kanıt üretmez ve puan uydurmaz.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

INSUFFICIENT_EVIDENCE_CODE = "insufficient_evidence"
INSUFFICIENT_EVIDENCE_LABEL = "YETERSİZ KANIT"
EVIDENCE_PENDING_CODE = "pending"
EVIDENCE_AVAILABLE_CODE = "available"
EVIDENCE_UNAVAILABLE_CODE = "unavailable"

_INSUFFICIENT_PIPELINE_STATES = frozenset({
    "halted_evidence",
    "halted_frequency",
})


def _value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _iter_runs(runs: Any) -> Iterable[Mapping[str, Any]]:
    values = runs.values() if isinstance(runs, Mapping) else (runs or [])
    for run in values:
        if isinstance(run, Mapping):
            yield run
        elif run is not None:
            dump = getattr(run, "model_dump", None)
            if callable(dump):
                value = dump(mode="json")
                if isinstance(value, Mapping):
                    yield value


def _has_decision_grade_run(runs: Any) -> bool:
    for run in _iter_runs(runs):
        status = _value(run.get("status"))
        if status != "completed" or run.get("decision_grade", True) is False:
            continue
        # A producer explicitly saying data_confidence=false is not evidence.
        summary = run.get("output_summary")
        if isinstance(summary, Mapping) and summary.get("data_confidence") is False:
            continue
        return True
    return False


def classify_evidence_status(
    *,
    status: Any = None,
    halted_reason: Any = None,
    runs: Any = None,
    evidence_chain: Any = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Return a stable UI status without inferring confidence from silence.

    ``halted_evidence`` is an explicit fail-closed decision. A pipeline made
    only of ``completed_no_decision`` runs is also insufficient. Other states
    remain pending/available rather than being relabelled as a failure.
    """
    state = _value(status)
    explicit_reason = str(reason or halted_reason or "").strip()
    insufficient = state in _INSUFFICIENT_PIPELINE_STATES
    if not insufficient and state == "partially_completed":
        insufficient = not _has_decision_grade_run(runs)
    if not insufficient and state == "completed_no_decision":
        insufficient = True
    if not insufficient and state in {"completed", "partially_completed"}:
        # A non-empty run set containing no decision-grade run is still an
        # insufficient result, even if the pipeline wrapper says completed.
        run_values = list(_iter_runs(runs))
        if run_values and not _has_decision_grade_run(run_values):
            insufficient = True
        # An explicit chain with no records is not a successful evidence result.
        if isinstance(evidence_chain, (list, tuple)) and not evidence_chain:
            insufficient = True

    if insufficient:
        return {
            "code": INSUFFICIENT_EVIDENCE_CODE,
            "label": INSUFFICIENT_EVIDENCE_LABEL,
            "severity": "warning",
            "reason": explicit_reason or "Karar üretmek için doğrulanabilir kanıt bulunamadı.",
            "decision_grade": False,
        }
    if state in {"processing", "initialized", "awaiting_authorization", ""}:
        return {
            "code": EVIDENCE_PENDING_CODE,
            "label": "KANIT BEKLENİYOR",
            "severity": "info",
            "reason": explicit_reason,
            "decision_grade": False,
        }
    if state in {"failed", "halted_critical", "minor_blocked"}:
        return {
            "code": EVIDENCE_UNAVAILABLE_CODE,
            "label": "KANIT DURUMU BELİRSİZ",
            "severity": "error",
            "reason": explicit_reason or "Teknik hata nedeniyle kanıt durumu belirlenemedi.",
            "decision_grade": False,
        }
    return {
        "code": EVIDENCE_AVAILABLE_CODE,
        "label": "KANIT DURUMU KAYITLI",
        "severity": "ok",
        "reason": explicit_reason,
        "decision_grade": _has_decision_grade_run(runs),
    }


__all__ = [
    "INSUFFICIENT_EVIDENCE_CODE",
    "INSUFFICIENT_EVIDENCE_LABEL",
    "EVIDENCE_UNAVAILABLE_CODE",
    "classify_evidence_status",
]
