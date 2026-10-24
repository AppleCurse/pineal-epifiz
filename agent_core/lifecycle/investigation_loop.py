"""Investigation Loop - Multi-Turn Socratic Investigative Orchestrator.

Kangren Çözümü: Asla tek tur gidilmez.
Montaj hattı (single-pass pipeline) yerine çok turlu hipotez-doğrulama-çürütme döngüsü.

Kurallar:
1. Asgari 2 tur, azami 4 tur. İlk tur asla nihai hüküm olamaz.
2. Ajanlar koordinatla çalışır (soru, hedef tarih aralığı, hedef kaynak, aranacak kanıt).
3. Beyin kendi hipotezini çürütmeye çalışır (falsification).
4. Döngü sonsuza gitmez (azami 4 tur veya bilgi doyumunda durur).
5. Tüm turların kanıt defteri (InvestigationLedger) kalıcıdır; önceki turun kanıtı silinmez.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from agent_core.domain.evidence_models import EvidenceTimeline, EvidenceTimelineEntry
from agent_core.lifecycle.baseline_builder import BaselineProfile, SignalObservation
from agent_core.lifecycle.rupture_engine import RuptureEngine
from agent_core.lifecycle.rupture_reporter import RuptureReport


class QuestionStatus(str, Enum):
    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    FALSIFIED = "FALSIFIED"


class TurnStage(str, Enum):
    TURN_1_WIDE_RECON = "WIDE_RECON"
    TURN_2_TARGETED_DRILL = "TARGETED_DRILL"
    TURN_3_FALSIFICATION = "FALSIFICATION"
    TURN_4_RESOLUTION = "RESOLUTION"


@dataclass(frozen=True)
class TargetedTask:
    """Ajanlara verilen koordinatlı nokta atışı görev."""
    task_id: str
    target_agent: str
    question_id: str
    hypothesis: str
    target_time_window: Optional[Tuple[datetime, datetime]]
    target_scope: Dict[str, Any]
    evidence_type_sought: str


@dataclass
class InvestigativeQuestion:
    """Soruşturan Beyin (LeadInquirer) tarafından üretilen dinamik soru."""
    question_id: str
    turn_created: int
    hypothesis: str
    target_agent: str
    target_time_window: Optional[Tuple[datetime, datetime]]
    target_scope: Dict[str, Any]
    evidence_type_sought: str
    status: QuestionStatus = QuestionStatus.PENDING
    supporting_evidence_ids: List[str] = field(default_factory=list)
    counter_evidence_ids: List[str] = field(default_factory=list)
    resolution_note: str = ""


@dataclass
class TurnRecord:
    """Tek bir turun eksiksiz denetim kaydı."""
    turn_index: int
    stage: TurnStage
    tasks_dispatched: List[TargetedTask]
    observations_gathered: List[SignalObservation]
    new_questions_spawned: List[str]
    resolved_questions: List[str]
    notes: str = ""


class InvestigationLedger:
    """Tüm turların silinmez, kümülatif hafıza defteri."""

    def __init__(self, subject_id: str) -> None:
        self.subject_id = subject_id
        self.turns: List[TurnRecord] = []
        self.all_observations: List[SignalObservation] = []
        self.questions: Dict[str, InvestigativeQuestion] = {}
        self.evidence_history: List[EvidenceTimelineEntry] = []

    def record_observation(self, obs: SignalObservation) -> None:
        self.all_observations.append(obs)

    def add_question(self, q: InvestigativeQuestion) -> None:
        self.questions[q.question_id] = q

    def resolve_question(
        self, q_id: str, status: QuestionStatus, note: str, ev_ids: List[str], counter: bool = False
    ) -> None:
        if q_id in self.questions:
            q = self.questions[q_id]
            q.status = status
            q.resolution_note = note
            if counter:
                q.counter_evidence_ids.extend(ev_ids)
            else:
                q.supporting_evidence_ids.extend(ev_ids)


class LeadInquirer:
    """Soruşturan Beyin: Bulguları okur, çelişkileri yakalar, hedefli sorular üretir ve hipotezleri çürütür."""

    def __init__(self, min_turns: int = 2, max_turns: int = 4) -> None:
        self.min_turns = min_turns
        self.max_turns = max_turns

    def evaluate_and_spawn_questions(
        self,
        turn_index: int,
        ledger: InvestigationLedger,
        baseline: Optional[BaselineProfile],
    ) -> List[TargetedTask]:
        """Gelen bulguları analiz edip sonraki tur için koordinatlı görevler üretir."""
        tasks: List[TargetedTask] = []
        obs = ledger.all_observations

        if turn_index == 1:
            # 1. Tur: Geniş Keşif Değerlendirmesi
            distinct_signals = {o.signal_id for o in obs}
            timestamps = [o.timestamp for o in obs]
            min_ts = min(timestamps) if timestamps else None
            max_ts = max(timestamps) if timestamps else None

            # Sinyal bazlı yaşam aralıklarını incele
            for sid in distinct_signals:
                sig_obs = [o for o in obs if o.signal_id == sid]
                sig_times = [o.timestamp for o in sig_obs]
                sig_max = max(sig_times)
                if max_ts and (max_ts - sig_max).days >= 90:
                    q_id = f"q_disappearance_{sid.replace('.', '_')}"
                    hypothesis = f"Sinyal '{sid}' {sig_max.date()} tarihinden sonra kalıcı olarak kesildi."
                    q = InvestigativeQuestion(
                        question_id=q_id,
                        turn_created=turn_index,
                        hypothesis=hypothesis,
                        target_agent="vision_analyzer" if "visual" in sid else "timing_forensics",
                        target_time_window=(sig_max, max_ts),
                        target_scope={"signal_id": sid, "check_reappearance": True},
                        evidence_type_sought="counter_or_confirmation",
                    )
                    ledger.add_question(q)
                    tasks.append(TargetedTask(
                        task_id=f"task_{q_id}",
                        target_agent=q.target_agent,
                        question_id=q_id,
                        hypothesis=hypothesis,
                        target_time_window=q.target_time_window,
                        target_scope=q.target_scope,
                        evidence_type_sought=q.evidence_type_sought,
                    ))

            # Anomali 2: Gece paylaşımı kontrolü
            night_obs = [o for o in obs if o.signal_id == "timing.is_night_post" and o.value == 1.0]
            if night_obs and min_ts and max_ts:
                earliest_night = min(o.timestamp for o in night_obs)
                q_id = "q_night_emergence"
                hypothesis = f"Gece paylaşımları {earliest_night.date()} civarında ortaya çıktı."
                q = InvestigativeQuestion(
                    question_id=q_id,
                    turn_created=turn_index,
                    hypothesis=hypothesis,
                    target_agent="timing_forensics",
                    target_time_window=(min_ts, earliest_night),
                    target_scope={"check_earlier_night_shifts": True},
                    evidence_type_sought="baseline_verification",
                )
                ledger.add_question(q)
                tasks.append(TargetedTask(
                    task_id=f"task_{q_id}",
                    target_agent=q.target_agent,
                    question_id=q_id,
                    hypothesis=hypothesis,
                    target_time_window=q.target_time_window,
                    target_scope=q.target_scope,
                    evidence_type_sought=q.evidence_type_sought,
                ))

            # Eğer özel bir anomali henüz yakalanmadıysa temel keşif görevi aç
            if not tasks:
                q_id = "q_wide_recon_baseline"
                hypothesis = "Başlangıç keşfi: zaman aralığında genel sinyal haritasını genişlet."
                q = InvestigativeQuestion(
                    question_id=q_id,
                    turn_created=turn_index,
                    hypothesis=hypothesis,
                    target_agent="general_recon",
                    target_time_window=None,
                    target_scope={"expand_coverage": True},
                    evidence_type_sought="baseline_coverage",
                )
                ledger.add_question(q)
                tasks.append(TargetedTask(
                    task_id=f"task_{q_id}",
                    target_agent=q.target_agent,
                    question_id=q_id,
                    hypothesis=hypothesis,
                    target_time_window=None,
                    target_scope=q.target_scope,
                    evidence_type_sought=q.evidence_type_sought,
                ))

        elif turn_index >= 2:
            # 2. ve sonraki turlar: Çürütme (Falsification) ve Karşı Hipotezler
            for q_id, q in list(ledger.questions.items()):
                if q.status == QuestionStatus.PENDING:
                    counter_q_id = f"q_counter_{q_id}"
                    if counter_q_id not in ledger.questions:
                        counter_hypo = f"Karşı Hipotez: {q.hypothesis} iddiası üretim biçimi (medium) değişikliğinden kaynaklanıyor olabilir."
                        cq = InvestigativeQuestion(
                            question_id=counter_q_id,
                            turn_created=turn_index,
                            hypothesis=counter_hypo,
                            target_agent="media_provenance",
                            target_time_window=q.target_time_window,
                            target_scope={"check_staged_or_authored": True, "parent_question": q_id},
                            evidence_type_sought="confounding_verification",
                        )
                        ledger.add_question(cq)
                        tasks.append(TargetedTask(
                            task_id=f"task_{counter_q_id}",
                            target_agent=cq.target_agent,
                            question_id=counter_q_id,
                            hypothesis=counter_hypo,
                            target_time_window=cq.target_time_window,
                            target_scope=cq.target_scope,
                            evidence_type_sought=cq.evidence_type_sought,
                        ))

        return tasks

    def should_continue(self, turn_index: int, ledger: InvestigationLedger, new_observations_count: int) -> bool:
        """Döngünün devam edip etmeyeceğini belirleyen durdurma koşulları."""
        # Kural 1: Asgari 2 tur tamamlanmadan durulamaz
        if turn_index <= self.min_turns:
            return True

        # Kural 2: Azami 4 tur tamamlandıysa kesin dur
        if turn_index > self.max_turns:
            return False

        # Kural 3: Yeni turda hiç yeni gözlem/kanıt üretilemediyse (doyum) dur
        if new_observations_count == 0:
            return False

        # Kural 4: Tüm açık sorular yanıtlandıysa dur
        pending = [q for q in ledger.questions.values() if q.status == QuestionStatus.PENDING]
        return len(pending) > 0


class InvestigationLoop:
    """Asla tek tur gitmeyen, çok turlu dinamik soruşturma denetleyicisi."""

    def __init__(
        self,
        inquirer: Optional[LeadInquirer] = None,
        rupture_engine: Optional[RuptureEngine] = None,
    ) -> None:
        self.inquirer = inquirer or LeadInquirer(min_turns=2, max_turns=4)
        self.rupture_engine = rupture_engine

    def execute_inquest(
        self,
        subject_id: str,
        initial_observations: List[SignalObservation],
        baseline: BaselineProfile,
        agent_dispatcher_callable,
        target_start: datetime,
        target_end: datetime,
    ) -> Tuple[RuptureReport, InvestigationLedger]:
        """Çok turlu soruşturmayı yürütür."""
        ledger = InvestigationLedger(subject_id=subject_id)
        for obs in initial_observations:
            ledger.record_observation(obs)

        turn = 1
        new_obs_count = len(initial_observations)

        stages = [
            TurnStage.TURN_1_WIDE_RECON,
            TurnStage.TURN_2_TARGETED_DRILL,
            TurnStage.TURN_3_FALSIFICATION,
            TurnStage.TURN_4_RESOLUTION,
        ]

        while self.inquirer.should_continue(turn, ledger, new_obs_count):
            stage = stages[min(turn - 1, len(stages) - 1)]
            tasks = self.inquirer.evaluate_and_spawn_questions(turn, ledger, baseline)

            turn_new_obs: List[SignalObservation] = []
            if tasks:
                agent_results = agent_dispatcher_callable(turn, tasks)
                for res_obs in agent_results:
                    ledger.record_observation(res_obs)
                    turn_new_obs.append(res_obs)

                for task in tasks:
                    matched = [o for o in turn_new_obs if task.question_id in o.source_ref]
                    if matched:
                        ledger.resolve_question(
                            task.question_id,
                            QuestionStatus.RESOLVED,
                            note=f"Tur {turn} içinde {len(matched)} kanıt bulundu.",
                            ev_ids=[o.source_ref for o in matched],
                        )

            ledger.turns.append(TurnRecord(
                turn_index=turn,
                stage=stage,
                tasks_dispatched=tasks,
                observations_gathered=turn_new_obs,
                new_questions_spawned=[t.question_id for t in tasks],
                resolved_questions=[
                    t.question_id for t in tasks
                    if ledger.questions.get(t.question_id) and ledger.questions[t.question_id].status == QuestionStatus.RESOLVED
                ],
            ))

            new_obs_count = len(turn_new_obs)
            turn += 1

        engine = self.rupture_engine or RuptureEngine(baseline)
        final_report = engine.run(
            observations=ledger.all_observations,
            target_start=target_start,
            target_end=target_end,
        )

        return final_report, ledger
