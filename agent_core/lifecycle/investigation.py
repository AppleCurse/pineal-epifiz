"""Soruşturma döngüsü — raporun "bilmiyorum"larını kapatmayı DENER, uydurmaz.

Neden var? Tek geçişli hat, ölçemediği şeyi ``unknowns`` listesine yazıp
susuyordu. Susmak dürüst ama yetersiz: eksik olan kanıt çoğu zaman **ikinci bir
bakışla** elde edilebilir (daha geniş kare örneklemi, daha uzun indirme
bütçesi). Bu modül o ikinci bakışı *sınırlı, deterministik ve kayıtlı* yapar.

Tasarım sözleşmesi:

    * **Soru raporun kendisinden türetilir** — kişiye özel kural yok. Aynı
      rapor her zaman aynı soruları, aynı sırada üretir (``q_<12 hex>``).
    * **Sonda (probe) yoksa soru AÇIK kalır.** Cevabı olmayan soruyu
      "cevaplandı" saymak, ölçülmemiş bir şeyi ölçülmüş gibi göstermek olurdu.
    * **Sonda kanıt getirmezse başarı değildir**: ``no_new_evidence``.
    * **Döngü sınırlıdır**: tur sayısı, soru sayısı ve soru başına süre tavanlı.
      Sonda hatası döngüyü durdurmaz; ``failed`` olarak kaydedilir.
    * **Teşhis yok**: soru metinleri yalnız ölçüm durumunu anlatır
      ("hangi sinyalde kaç gözlem var"), yorum katmanı eklemez.

Tüketici: ``agent_core.task_executor`` (``_investigate_life_rupture``).
Test: ``tests/lifecycle/test_investigation.py``.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Optional, Sequence

from agent_core.lifecycle import visual_frames as _visual_frames

__all__ = [
    "DEFAULT_MAX_QUESTIONS",
    "DEFAULT_MAX_ROUNDS",
    "DEFAULT_QUESTION_TIMEOUT_SECONDS",
    "FRAME_SIGNAL_PREFIX",
    "InvestigationConfig",
    "InvestigationQuestion",
    "InvestigationResult",
    "InvestigationRound",
    "MIN_BASELINE_OBSERVATIONS",
    "PROBE_FOR_KIND",
    "ProbeOutcome",
    "plan_questions",
    "run_investigation",
]

#: Kare sinyalleri tek ölçülebilir zamanlı görsel kaynaktır. Önek ELLE
#: yazılmaz: ``visual_frames``teki tek beyandan türetilir (statik sinyal
#: taraması yarım adı "spec'i olmayan sinyal" sanmasın).
FRAME_SIGNAL_PREFIX: str = _visual_frames.FRAME_SIGNAL_PREFIX

#: Baseline'da bu sayının altı "seyrek" sayılır: sapma iddiası kurulamaz.
MIN_BASELINE_OBSERVATIONS = 8

DEFAULT_MAX_QUESTIONS = 6
DEFAULT_MAX_ROUNDS = 2
DEFAULT_QUESTION_TIMEOUT_SECONDS = 20.0

#: Hangi soru türü hangi sondayla kapatılabilir. ``None`` = sonda YOK.
PROBE_FOR_KIND: dict[str, Optional[str]] = {
    "frame_coverage_gap": "frame_window",
    "frame_baseline_sparse": "frame_window",
    "timestamp_conflict": "timestamp_crosscheck",
    "visual_axis_suppressed": None,
    "independence_unresolved": None,
    "medium_change_unknown": None,
}

ProbeCallable = Callable[..., Awaitable["ProbeOutcome"]]


@dataclass(frozen=True)
class InvestigationConfig:
    """Döngünün sert sınırları — sınırsız soruşturma yok."""

    max_questions: int = DEFAULT_MAX_QUESTIONS
    max_rounds: int = DEFAULT_MAX_ROUNDS
    question_timeout_seconds: float = DEFAULT_QUESTION_TIMEOUT_SECONDS
    total_timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        if self.max_questions < 0 or self.max_rounds < 0:
            raise ValueError("soruşturma sınırları negatif olamaz")
        if self.question_timeout_seconds <= 0 or self.total_timeout_seconds <= 0:
            raise ValueError("soru ve toplam zaman aşımı pozitif olmalı")


@dataclass(frozen=True)
class InvestigationQuestion:
    """Kapatılmayı bekleyen tek bir ölçüm boşluğu."""

    question_id: str
    kind: str
    subject: str
    reason: str
    probe: Optional[str] = None
    severity: int = 1
    window: Optional[tuple[Optional[str], Optional[str]]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "kind": self.kind,
            "subject": self.subject,
            "reason": self.reason,
            "probe": self.probe,
            "severity": self.severity,
            "window": list(self.window) if self.window else None,
        }


@dataclass(frozen=True)
class ProbeOutcome:
    """Sondanın dürüst cevabı.

    ``status``: ``resolved`` (boşluk kapandı), ``no_new_evidence`` (denendi,
    yeni kanıt yok), ``failed`` (hata), ``not_applicable`` (sonda bu soruya
    uygun değil). Yeni kare varsa ``frames`` alanında taşınır.
    """

    status: str
    detail: str = ""
    observations_added: int = 0
    frames: Sequence[Mapping[str, Any]] = field(default_factory=tuple)


@dataclass
class InvestigationRound:
    """Tek turun kaydı: ne soruldu, ne cevap geldi."""

    index: int
    asked: list[str] = field(default_factory=list)
    outcomes: dict[str, str] = field(default_factory=dict)
    observations_added: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "asked": list(self.asked),
            "outcomes": dict(self.outcomes),
            "observations_added": self.observations_added,
        }


@dataclass
class InvestigationResult:
    """Soruşturmanın mühürlenebilir özeti."""

    questions: list[InvestigationQuestion] = field(default_factory=list)
    rounds: list[InvestigationRound] = field(default_factory=list)
    resolved: list[str] = field(default_factory=list)
    still_unknown: list[str] = field(default_factory=list)
    extra_frames: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def closed(self) -> bool:
        return not self.still_unknown

    def to_dict(self) -> dict[str, Any]:
        return {
            "questions": [question.to_dict() for question in self.questions],
            "rounds": [item.to_dict() for item in self.rounds],
            "resolved": list(self.resolved),
            "still_unknown": list(self.still_unknown),
            "extra_frame_count": len(self.extra_frames),
            "diagnostics": dict(self.diagnostics),
        }


def _question_id(kind: str, subject: str) -> str:
    """Deterministik soru kimliği (rastgelelik yok)."""
    digest = hashlib.sha256(f"{kind}|{subject}".encode("utf-8")).hexdigest()[:12]
    return f"q_{digest}"


def _as_mapping(report: Any) -> Mapping[str, Any]:
    if isinstance(report, Mapping):
        return report
    dumped = getattr(report, "model_dump", None)
    if callable(dumped):
        payload = dumped(mode="json")
        return payload if isinstance(payload, Mapping) else {}
    return {}


def plan_questions(report: Any, *, max_questions: int = DEFAULT_MAX_QUESTIONS) -> list[InvestigationQuestion]:
    """Rapordaki ölçüm boşluklarını sıralı sorulara çevirir.

    Sıra deterministiktir: (önem azalan, tür, konu). Aynı rapor → aynı liste.
    """
    payload = _as_mapping(report)
    questions: dict[str, InvestigationQuestion] = {}

    def _add(kind: str, subject: str, reason: str, severity: int) -> None:
        question = InvestigationQuestion(
            question_id=_question_id(kind, subject),
            kind=kind,
            subject=subject,
            reason=reason,
            probe=PROBE_FOR_KIND.get(kind),
            severity=severity,
        )
        questions.setdefault(question.question_id, question)

    baseline_start = payload.get("baseline_window_start")
    baseline_end = payload.get("baseline_window_end")

    for row in payload.get("data_coverage") or []:
        if not isinstance(row, Mapping):
            continue
        signal_id = str(row.get("signal_id") or "")
        if not signal_id.startswith(FRAME_SIGNAL_PREFIX):
            # Kare dışı sinyallerin boşluğu bu modülün konusu değil: sonda yok.
            continue
        comparison = int(row.get("comparison_observations") or 0)
        baseline = int(row.get("baseline_observations") or 0)
        if comparison == 0:
            _add(
                "frame_coverage_gap",
                signal_id,
                f"karşılaştırma penceresinde 0 gözlem (baseline {baseline})",
                3,
            )
        elif baseline < MIN_BASELINE_OBSERVATIONS:
            _add(
                "frame_baseline_sparse",
                signal_id,
                f"baseline seyrek: {baseline} < {MIN_BASELINE_OBSERVATIONS}",
                2,
            )

    for entry in payload.get("excluded_evidence") or []:
        if not isinstance(entry, Mapping):
            continue
        text = f"{entry.get('reason', '')} {entry.get('detail', '')}".lower()
        if "timestamp" in text or "zaman" in text:
            _add(
                "timestamp_conflict",
                str(entry.get("signal_id") or entry.get("source") or "post_timestamp"),
                "zaman damgası doğrulanamadı; kare bu kanıta dayanamaz",
                3,
            )

    for axis in payload.get("axes") or []:
        if not isinstance(axis, Mapping):
            continue
        if axis.get("state") != "suppressed":
            continue
        _add(
            "visual_axis_suppressed",
            str(axis.get("axis") or "axis"),
            str(axis.get("reason") or "eksen bastırıldı"),
            1,
        )

    for unknown in payload.get("unknowns") or []:
        text = str(unknown)
        lowered = text.lower()
        if "bağımsızlık" in lowered:
            _add("independence_unresolved", text[:80], text, 2)
        elif "üretim biçimi" in lowered or "medium" in lowered:
            _add("medium_change_unknown", text[:80], text, 2)

    ordered = sorted(questions.values(), key=lambda q: (-q.severity, q.kind, q.subject))
    if max_questions >= 0:
        ordered = ordered[:max_questions]
    result = []
    for question in ordered:
        if question.kind in ("frame_coverage_gap", "frame_baseline_sparse"):
            result.append(
                InvestigationQuestion(
                    question_id=question.question_id,
                    kind=question.kind,
                    subject=question.subject,
                    reason=question.reason,
                    probe=question.probe,
                    severity=question.severity,
                    window=(baseline_start, baseline_end),
                )
            )
        else:
            result.append(question)
    return result


def _normalise_outcome(outcome: Any) -> ProbeOutcome:
    """Sonda sözleşmeye uymazsa ``failed`` sayılır (sessiz başarı yok)."""
    if isinstance(outcome, ProbeOutcome):
        if outcome.status in {"resolved", "no_new_evidence", "failed", "not_applicable"}:
            return outcome
        return ProbeOutcome(status="failed", detail=f"bilinmeyen durum: {outcome.status}")
    return ProbeOutcome(status="failed", detail=f"geçersiz sonda çıktısı: {type(outcome).__name__}")


async def run_investigation(
    report: Any,
    *,
    probes: Mapping[str, ProbeCallable],
    config: Optional[InvestigationConfig] = None,
    questions: Optional[Sequence[InvestigationQuestion]] = None,
    reassess: Optional[Callable[[InvestigationResult], Any]] = None,
    on_round: Optional[Callable[[InvestigationResult], None]] = None,
) -> InvestigationResult:
    """Sınırlı soruşturma döngüsü.

    Her turda kapatılmamış sorular sırayla sorulur. İsteğe bağlı yeniden
    değerlendirme, yeni kanıttan ölçümü günceller ve sınırlı yeni sorular planlar.
    Tur sonunda **hiçbir** yeni gözlem gelmediyse döngü durur (``stop_reason="no_new_evidence"``). Sondası
    olmayan sorular hiç sorulmaz; ``still_unknown`` altında gerekçeleriyle kalır.
    """
    config = config or InvestigationConfig()
    planned = list(questions) if questions is not None else plan_questions(
        report, max_questions=config.max_questions
    )
    result = InvestigationResult(questions=planned)
    result.diagnostics.update(
        {
            "planned_question_count": len(planned),
            "probe_names": sorted(probes),
            "rounds_run": 0,
            "probes_run": 0,
            "stop_reason": "",
        }
    )

    pending = [question for question in planned if question.probe in probes]
    unresolved_reasons: dict[str, str] = {
        question.question_id: (
            "sonda kayıtlı değil" if question.probe is None else f"sonda yok: {question.probe}"
        )
        for question in planned
        if question.probe not in probes
    }

    seen_frame_ids: set[str] = set()
    deadline = asyncio.get_running_loop().time() + config.total_timeout_seconds
    if not planned:
        stop_reason = "no_questions"
    elif not pending:
        # Soru var, sonda yok: soru AÇIK kalır (sessizce "kapandı" sayılmaz).
        stop_reason = "no_probe_registered"
    else:
        stop_reason = ""

    for index in range(config.max_rounds):
        if not pending:
            break
        round_record = InvestigationRound(index=index)
        answered: set[str] = set()
        timed_out = False
        for question in pending[:config.max_questions]:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                timed_out = True
                break
            probe = probes.get(question.probe or "")
            if probe is None:  # pragma: no cover - pending bunu garanti eder
                continue
            round_record.asked.append(question.question_id)
            result.diagnostics["probes_run"] += 1
            try:
                timeout = min(config.question_timeout_seconds, remaining)
                raw = await asyncio.wait_for(
                    probe(question, budget_seconds=timeout), timeout=timeout,
                )
                outcome = _normalise_outcome(raw)
            except asyncio.TimeoutError:
                outcome = ProbeOutcome(status="failed", detail="question_timeout")
            except Exception as error:  # noqa: BLE001 — sonda hatası döngüyü durdurmaz
                outcome = ProbeOutcome(status="failed", detail=f"{type(error).__name__}: {error}"[:160])

            round_record.outcomes[question.question_id] = outcome.status
            if outcome.status == "resolved" and reassess is None:
                answered.add(question.question_id)
                result.resolved.append(question.question_id)
            else:
                if outcome.status == "resolved":
                    round_record.outcomes[question.question_id] = "pending_reassessment"
                unresolved_reasons[question.question_id] = outcome.detail or (
                    "yeniden değerlendirme gerekli" if outcome.status == "resolved" else outcome.status
                )
            for frame in outcome.frames:
                if not isinstance(frame, Mapping):
                    continue
                frame_id = str(frame.get("frame_id") or "")
                if not frame_id or frame_id in seen_frame_ids:
                    continue
                seen_frame_ids.add(frame_id)
                result.extra_frames.append(dict(frame))
                round_record.observations_added += 1
        result.rounds.append(round_record)
        result.diagnostics["rounds_run"] = index + 1
        pending = [question for question in pending if question.question_id not in answered]
        if reassess is not None and round_record.observations_added:
            try:
                updated = _as_mapping(reassess(result))
                coverage = {str(row.get("signal_id")): row for row in updated.get("data_coverage", [])
                            if isinstance(row, Mapping)}
                for question in pending:
                    row = coverage.get(question.subject)
                    if not row:
                        continue  # Missing data is not a resolution.
                    comparison = int(row.get("comparison_observations") or 0)
                    baseline = int(row.get("baseline_observations") or 0)
                    closed = ((question.kind == "frame_coverage_gap" and comparison > 0)
                              or (question.kind == "frame_baseline_sparse"
                                  and comparison > 0 and baseline >= MIN_BASELINE_OBSERVATIONS))
                    if closed:
                        answered.add(question.question_id)
                        result.resolved.append(question.question_id)
                        round_record.outcomes[question.question_id] = "resolved"
                pending = [q for q in pending if q.question_id not in answered]
                known_ids = {q.question_id for q in planned}
                for question in plan_questions(updated, max_questions=config.max_questions):
                    if question.question_id in result.resolved:
                        # A shifted measurement window can make a former gap recur.
                        result.resolved.remove(question.question_id)
                        if question.probe in probes and all(q.question_id != question.question_id for q in pending):
                            pending.append(question)
                        unresolved_reasons[question.question_id] = "yeni ölçümle tekrar açık"
                        continue
                    if question.question_id in known_ids or len(planned) >= config.max_questions * config.max_rounds:
                        continue
                    planned.append(question)
                    known_ids.add(question.question_id)
                    if question.probe in probes:
                        pending.append(question)
                    else:
                        unresolved_reasons[question.question_id] = "sonda kayıtlı değil"
            except Exception as error:  # Fail closed: no inferred resolution.
                unresolved_reasons.update({q.question_id: "yeniden değerlendirme başarısız: "
                                           + type(error).__name__ for q in pending})
                stop_reason = "reassessment_failed"
        result.still_unknown = [f"{q.question_id}:{q.subject}:{unresolved_reasons.get(q.question_id, 'açık')}"
                                for q in planned if q.question_id not in result.resolved]
        if on_round is not None:
            result.diagnostics["stop_reason"] = "in_progress"
            on_round(result)
        if stop_reason == "reassessment_failed":
            break
        if timed_out or asyncio.get_running_loop().time() >= deadline:
            stop_reason = "total_timeout"
            break
        if round_record.observations_added == 0:
            stop_reason = "no_new_evidence"
            break
        if not pending:
            stop_reason = ("all_questions_resolved" if not result.still_unknown
                           else "no_more_actionable_questions")
            break
    else:
        if pending and config.max_rounds == 0:
            stop_reason = "round_budget_zero"
        elif pending:
            stop_reason = "round_budget_exhausted"

    if not stop_reason:
        stop_reason = "all_attempted_questions_answered" if not pending else "round_budget_exhausted"

    result.still_unknown = [
        f"{question.question_id}:{question.subject}:{unresolved_reasons.get(question.question_id, 'açık')}"
        for question in planned
        if question.question_id not in result.resolved
    ]
    result.extra_frames.sort(key=lambda frame: (str(frame.get("observed_at")), str(frame.get("frame_id"))))
    result.diagnostics["planned_question_count"] = len(planned)
    result.diagnostics["extra_frame_count"] = len(result.extra_frames)
    result.diagnostics["resolved_count"] = len(result.resolved)
    result.diagnostics["still_unknown_count"] = len(result.still_unknown)
    result.diagnostics["stop_reason"] = stop_reason
    return result
