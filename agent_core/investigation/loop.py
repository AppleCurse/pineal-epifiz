from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from agent_core.domain.evidence_models import EvidenceTimeline, EvidenceTimelineEntry
from agent_core.lifecycle.baseline_builder import (
    BaselineProfile,
    SignalObservation,
)
from agent_core.lifecycle.deviation_detector import (
    DeviationDetector,
    make_evidence_id,
)
from agent_core.lifecycle.rupture_engine import RuptureEngine
from agent_core.lifecycle.rupture_reporter import RuptureReport


class InvestigationRound(str, Enum):
    BROAD_RECON = "broad_recon"
    TARGETED_DRILL = "targeted_drill"
    FALSIFICATION = "falsification"


class HypothesisStatus(str, Enum):
    OPEN = "open"
    VERIFIED = "verified"
    FALSIFIED = "falsified"
    UNVERIFIED = "unverified"


class InquestVerdict(str, Enum):
    CONFIRMED = "confirmed"
    FALSIFIED = "falsified"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class MicroTaskCoordinate(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    target_entity: Optional[str] = None
    signal_type: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)


class MicroTask(BaseModel):
    task_id: str
    round_type: InvestigationRound
    target_agent: str
    hypothesis_id: str
    instruction: str
    coordinate: MicroTaskCoordinate
    is_falsification: bool = False


class InquestHypothesis(BaseModel):
    hypothesis_id: str
    question: str
    signal_type: str
    formulated_in_round: int
    status: HypothesisStatus = HypothesisStatus.OPEN
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    contradicting_evidence_ids: List[str] = Field(default_factory=list)
    epistemic_note: str = ""


class RoundSummary(BaseModel):
    round_number: int
    round_type: InvestigationRound
    dispatched_tasks_count: int
    observations_count: int
    new_evidence_count: int
    hypotheses_open: int
    hypotheses_resolved: int


class SealedInquestReport(BaseModel):
    inquest_id: str
    subject_id: str
    total_rounds: int
    verdict: InquestVerdict
    hypotheses: List[InquestHypothesis]
    evidence_timeline: EvidenceTimeline
    rupture_report: Optional[RuptureReport] = None
    sealed_at: datetime
    circuit_breaker_triggered: bool = False
    unresolved_questions: List[str] = Field(default_factory=list)
    round_history: List[RoundSummary] = Field(default_factory=list)


def make_hypothesis_id(question: str) -> str:
    digest = hashlib.sha256(question.strip().encode("utf-8")).hexdigest()[:12]
    return f"hyp_{digest}"


def make_task_id(hypothesis_id: str, round_type: str, agent: str) -> str:
    raw = f"{hypothesis_id}:{round_type}:{agent}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"mt_{digest}"


class LeadInquirer:
    """Soruşturan Beyin (Lead Inquirer).

    Hipotez kurar, hedefli mikro-görevler türetir, çürütme testlerini
    yürütür ve bulguları mühürler.
    """

    # ponytail: kural-tabanlı hipotez üretimi tavanı; LLM Socratic Inquirer entegrasyonu gerektiğinde genişletilir.
    def formulate_hypotheses(
        self,
        round_num: int,
        observations: List[SignalObservation],
        timeline: EvidenceTimeline,
    ) -> List[InquestHypothesis]:
        hypotheses: List[InquestHypothesis] = []
        seen_questions: set[str] = set()

        for entry in timeline.entries:
            sig_id = str(entry.source_metrics.get("signal_id") or "unknown_signal")
            if entry.epistemic_type == "absence":
                q = f"Hedefin {sig_id} sinyalindeki sessizlik ({entry.timeline_at.strftime('%Y-%m')}) harici kopuş mu?"
                if q not in seen_questions:
                    seen_questions.add(q)
                    hypotheses.append(
                        InquestHypothesis(
                            hypothesis_id=make_hypothesis_id(q),
                            question=q,
                            signal_type=sig_id,
                            formulated_in_round=round_num,
                            supporting_evidence_ids=[entry.evidence_id],
                            epistemic_note=f"Absence signal detected in round {round_num}",
                        )
                    )
            elif entry.epistemic_type == "observation":
                actor = entry.source_metrics.get("key_actor")
                if actor:
                    q = f"Aktör '{actor}' ile hedefin {sig_id} teması kırılma sebebi mi?"
                else:
                    obs_val = entry.source_metrics.get("observed_value")
                    val_str = f"{obs_val:.2f}" if isinstance(obs_val, (int, float)) else "belirsiz"
                    q = f"Hedefin {sig_id} sinyalindeki kayma ({val_str}) kalıcı mı?"
                if q not in seen_questions:
                    seen_questions.add(q)
                    hypotheses.append(
                        InquestHypothesis(
                            hypothesis_id=make_hypothesis_id(q),
                            question=q,
                            signal_type=sig_id,
                            formulated_in_round=round_num,
                            supporting_evidence_ids=[entry.evidence_id],
                            epistemic_note=f"Observation shift detected in round {round_num}",
                        )
                    )

        if not hypotheses and observations:
            for obs in observations:
                sig_id = obs.signal_id
                if obs.measurement_status == "absence":
                    q = f"Hedefin {sig_id} sinyalindeki sessizlik ({obs.timestamp.strftime('%Y-%m')}) harici kopuş mu?"
                else:
                    q = f"Hedefin {sig_id} sinyalindeki kayma ({obs.value:.2f}) kalıcı mı?"
                if q not in seen_questions:
                    seen_questions.add(q)
                    hypotheses.append(
                        InquestHypothesis(
                            hypothesis_id=make_hypothesis_id(q),
                            question=q,
                            signal_type=sig_id,
                            formulated_in_round=round_num,
                            supporting_evidence_ids=[],
                            epistemic_note=f"Raw observation shift detected in round {round_num}",
                        )
                    )

        return hypotheses

    def generate_targeted_tasks(
        self,
        hypotheses: List[InquestHypothesis],
        round_type: InvestigationRound,
    ) -> List[MicroTask]:
        tasks: List[MicroTask] = []
        for hyp in hypotheses:
            if hyp.status not in (HypothesisStatus.OPEN, HypothesisStatus.VERIFIED):
                continue
            if round_type == InvestigationRound.TARGETED_DRILL:
                agent = "vision" if "image" in hyp.signal_type or "visual" in hyp.signal_type else (
                    "timing" if "time" in hyp.signal_type or "silence" in hyp.signal_type else "network"
                )
                coord = MicroTaskCoordinate(
                    signal_type=hyp.signal_type,
                    parameters={"focus_question": hyp.question},
                )
                tasks.append(
                    MicroTask(
                        task_id=make_task_id(hyp.hypothesis_id, round_type.value, agent),
                        round_type=round_type,
                        target_agent=agent,
                        hypothesis_id=hyp.hypothesis_id,
                        instruction=f"Drill on {hyp.signal_type}: {hyp.question}",
                        coordinate=coord,
                        is_falsification=False,
                    )
                )
            elif round_type == InvestigationRound.FALSIFICATION:
                agent = "falsification_agent"
                coord = MicroTaskCoordinate(
                    signal_type=hyp.signal_type,
                    parameters={"search_counter_evidence_for": hyp.hypothesis_id},
                )
                tasks.append(
                    MicroTask(
                        task_id=make_task_id(hyp.hypothesis_id, round_type.value, agent),
                        round_type=round_type,
                        target_agent=agent,
                        hypothesis_id=hyp.hypothesis_id,
                        instruction=f"Seek counter-evidence for {hyp.question}",
                        coordinate=coord,
                        is_falsification=True,
                    )
                )
        return tasks

    def evaluate_round(
        self,
        round_num: int,
        hypotheses: List[InquestHypothesis],
        new_entries: List[EvidenceTimelineEntry],
        is_falsification_round: bool = False,
    ) -> None:
        for hyp in hypotheses:
            matched_entries = [
                e for e in new_entries if e.source_metrics.get("signal_id") == hyp.signal_type
            ]
            for entry in matched_entries:
                if entry.source_metrics.get("is_counter_evidence"):
                    hyp.contradicting_evidence_ids.append(entry.evidence_id)
                    hyp.status = HypothesisStatus.FALSIFIED
                    hyp.epistemic_note = f"Çürütüldü: karşıt kanıt {entry.evidence_id} bulundu."
                else:
                    if entry.evidence_id not in hyp.supporting_evidence_ids:
                        hyp.supporting_evidence_ids.append(entry.evidence_id)

            if is_falsification_round and hyp.status == HypothesisStatus.OPEN:
                if hyp.contradicting_evidence_ids:
                    hyp.status = HypothesisStatus.FALSIFIED
                elif hyp.supporting_evidence_ids:
                    hyp.status = HypothesisStatus.VERIFIED
                    hyp.epistemic_note = "Doğrulandı: çürütme turunda karşıt kanıt bulunamadı."
                else:
                    hyp.status = HypothesisStatus.UNVERIFIED
                    hyp.epistemic_note = "Doğrulanamadı: somut kanıt yetersiz."

    def circuit_breaker_check(self, new_evidence_count: int) -> bool:
        """Kural 3: Bir turda 0 yeni kanıt gelirse emniyet kilidi atar."""
        return new_evidence_count == 0

    def seal_verdict(
        self,
        subject_id: str,
        total_rounds: int,
        hypotheses: List[InquestHypothesis],
        timeline: EvidenceTimeline,
        rupture_report: Optional[RuptureReport],
        circuit_breaker: bool,
        round_history: List[RoundSummary],
    ) -> SealedInquestReport:
        unresolved: List[str] = []
        verified_count = 0
        falsified_count = 0

        for hyp in hypotheses:
            if hyp.status == HypothesisStatus.OPEN:
                hyp.status = HypothesisStatus.UNVERIFIED
                hyp.epistemic_note = "Soruşturma kapandı; kanıt yetersizliği nedeniyle açık kaldı."
            if hyp.status == HypothesisStatus.UNVERIFIED:
                unresolved.append(hyp.question)
            elif hyp.status == HypothesisStatus.VERIFIED:
                verified_count += 1
            elif hyp.status == HypothesisStatus.FALSIFIED:
                falsified_count += 1

        if falsified_count > 0 and verified_count == 0:
            verdict = InquestVerdict.FALSIFIED
        elif verified_count > 0 and falsified_count == 0 and not circuit_breaker:
            verdict = InquestVerdict.CONFIRMED
        else:
            verdict = InquestVerdict.INSUFFICIENT_EVIDENCE

        inquest_id = "inq_" + hashlib.sha256(
            f"{subject_id}:{total_rounds}:{len(timeline.entries)}".encode("utf-8")
        ).hexdigest()[:16]

        return SealedInquestReport(
            inquest_id=inquest_id,
            subject_id=subject_id,
            total_rounds=total_rounds,
            verdict=verdict,
            hypotheses=hypotheses,
            evidence_timeline=timeline,
            rupture_report=rupture_report,
            sealed_at=datetime.now(timezone.utc),
            circuit_breaker_triggered=circuit_breaker,
            unresolved_questions=unresolved,
            round_history=round_history,
        )


class InvestigationLoop:
    """Çok Turlu Soruşturma Motoru (Recursive Socratic Inquest).

    Kural 1: Tur 1 sonrası kör ajana izin verilmez; koordinat zorunludur.
    Kural 2: 'Eksik Parça' kapanmadan hüküm kurulamaz; açık soru listelenir.
    Kural 3: Maksimum 3 tur ve 0-kanıt circuit breaker.
    """

    def __init__(
        self,
        inquirer: Optional[LeadInquirer] = None,
        max_rounds: int = 3,
        detector: Optional[DeviationDetector] = None,
        rupture_engine: Optional[RuptureEngine] = None,
    ) -> None:
        self.inquirer = inquirer or LeadInquirer()
        self.max_rounds = min(max_rounds, 4)
        self.detector = detector
        self.rupture_engine = rupture_engine

    # ponytail: dispatch işlevi senkron çağrılır; asenkron I/O gerektiğinde async run_inquest eklenir.
    def run_inquest(
        self,
        subject_id: str,
        dispatcher: Callable[[InvestigationRound, List[MicroTask]], List[SignalObservation]],
        baseline_profile: Optional[BaselineProfile] = None,
        target_start: Optional[datetime] = None,
        target_end: Optional[datetime] = None,
    ) -> SealedInquestReport:
        now = datetime.now(timezone.utc)
        t_start = target_start or now
        t_end = target_end or now

        detector = self.detector or (
            DeviationDetector(baseline_profile) if baseline_profile else None
        )

        all_observations: List[SignalObservation] = []
        all_entries: List[EvidenceTimelineEntry] = []
        hypotheses: List[InquestHypothesis] = []
        round_history: List[RoundSummary] = []
        circuit_breaker_tripped = False

        # --- 1. TUR: GENİŞ KEŞİF (BROAD RECON) ---
        round_type = InvestigationRound.BROAD_RECON
        r1_obs = dispatcher(round_type, [])
        all_observations.extend(r1_obs)

        r1_timeline = EvidenceTimeline()
        if detector and r1_obs:
            r1_timeline = detector.detect(r1_obs, t_start, t_end)
        elif r1_obs:
            for obs in r1_obs:
                ep_type = "absence" if obs.measurement_status == "absence" else "observation"
                ev_id = make_evidence_id(obs.signal_id, obs.timestamp, obs.value, obs.source_ref)
                r1_timeline.entries.append(
                    EvidenceTimelineEntry(
                        evidence_id=ev_id,
                        timeline_at=obs.timestamp,
                        temporal_basis="observed_at",
                        epistemic_type=ep_type,
                        epistemic_note="Round 1 broad recon observation",
                        source_engine="investigation_loop",
                        content=f"Recon observation for {obs.signal_id}: {obs.value:.2f}",
                        source_metrics={"signal_id": obs.signal_id, "observed_value": obs.value},
                    )
                )
        all_entries.extend(r1_timeline.entries)

        hypotheses = self.inquirer.formulate_hypotheses(1, r1_obs, r1_timeline)
        round_history.append(
            RoundSummary(
                round_number=1,
                round_type=round_type,
                dispatched_tasks_count=0,
                observations_count=len(r1_obs),
                new_evidence_count=len(r1_timeline.entries),
                hypotheses_open=len([h for h in hypotheses if h.status == HypothesisStatus.OPEN]),
                hypotheses_resolved=len([h for h in hypotheses if h.status != HypothesisStatus.OPEN]),
            )
        )

        current_round = 1

        # --- 2. VE 3. TUR: NOKTA ATIŞI KAZI VE ÇÜRÜTME ---
        while current_round < self.max_rounds and not circuit_breaker_tripped:
            current_round += 1
            if current_round == 2:
                round_type = InvestigationRound.TARGETED_DRILL
            else:
                round_type = InvestigationRound.FALSIFICATION

            tasks = self.inquirer.generate_targeted_tasks(hypotheses, round_type)
            if not tasks:
                break

            # Kural 1: her mikro-görev koordinat taşımak zorundadır
            for t in tasks:
                if t.coordinate is None or (not t.coordinate.signal_type and not t.coordinate.target_entity):
                    raise ValueError(f"Kural 1 ihlali: {t.task_id} koordinatsız gönderilemez.")

            round_obs = dispatcher(round_type, tasks)
            all_observations.extend(round_obs)

            new_entries: List[EvidenceTimelineEntry] = []
            for obs in round_obs:
                ep_type = "absence" if obs.measurement_status == "absence" else "observation"
                ev_id = make_evidence_id(obs.signal_id, obs.timestamp, obs.value, obs.source_ref)
                is_counter = (obs.source_ref == "counter_evidence" or obs.signal_family == "counter_evidence")
                new_entries.append(
                    EvidenceTimelineEntry(
                        evidence_id=ev_id,
                        timeline_at=obs.timestamp,
                        temporal_basis="observed_at",
                        epistemic_type=ep_type,
                        epistemic_note=f"Inquest round {current_round} drill observation",
                        source_engine="investigation_loop",
                        content=f"Round {current_round} drill observation for {obs.signal_id}: {obs.value:.2f}",
                        source_metrics={
                            "signal_id": obs.signal_id,
                            "observed_value": obs.value,
                            "source_ref": obs.source_ref,
                            "is_counter_evidence": is_counter,
                        },
                    )
                )

            all_entries.extend(new_entries)

            # Kural 3: Emniyet Kilidi (Circuit Breaker)
            if self.inquirer.circuit_breaker_check(len(new_entries)):
                circuit_breaker_tripped = True

            self.inquirer.evaluate_round(
                round_num=current_round,
                hypotheses=hypotheses,
                new_entries=new_entries,
                is_falsification_round=(round_type == InvestigationRound.FALSIFICATION),
            )

            round_history.append(
                RoundSummary(
                    round_number=current_round,
                    round_type=round_type,
                    dispatched_tasks_count=len(tasks),
                    observations_count=len(round_obs),
                    new_evidence_count=len(new_entries),
                    hypotheses_open=len([h for h in hypotheses if h.status == HypothesisStatus.OPEN]),
                    hypotheses_resolved=len([h for h in hypotheses if h.status != HypothesisStatus.OPEN]),
                )
            )

        # Nihai Mühürleme
        full_timeline = EvidenceTimeline(entries=all_entries)
        rupture_rep: Optional[RuptureReport] = None
        if self.rupture_engine and all_observations:
            rupture_rep = self.rupture_engine.run(all_observations, t_start, t_end)

        return self.inquirer.seal_verdict(
            subject_id=subject_id,
            total_rounds=current_round,
            hypotheses=hypotheses,
            timeline=full_timeline,
            rupture_report=rupture_rep,
            circuit_breaker=circuit_breaker_tripped,
            round_history=round_history,
        )
