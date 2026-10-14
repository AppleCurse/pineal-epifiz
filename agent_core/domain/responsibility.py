"""Sorumluluk Zinciri (Responsibility Chain) — görev sözleşmesi ve iz şeması.

İlke (ürün kuralı, 2026-10-14):
    Bir bileşen görevini tamamlayamazsa görevi BIRAKMAZ; nedenini bildirir,
    elindeki yolları dener, destek ister/devreder — ama ASLA sahte başarı
    üretmez. Eksik kalırsa eksik olduğunu kanıtla söyler.

Bu modül üç şeyi tanımlar:

1. ``TaskContract`` — ajan/motor/servis çalışmaya BAŞLAMADAN önce hangi
   işi yapacağı, neyi yapmayacağı, kabul/başarısızlık koşulu ve kanıt
   çıktısı. Sözleşme eksikse görev başlamaz (``ensure_complete``).
2. ``ResponsibilityTrail`` — her çıktının taşıdığı sekiz alan:
   ``attempted_paths`` · ``blockers`` · ``support_requested`` · ``handoff``
   · ``partial_result`` · ``missing`` · ``next_action`` · ``integrity``.
3. ``seal_trail`` — sahte başarı kuralları: "tamamlandı" iddiası eksik
   kanıtla mühürlenemez; "yapamadım" iddiası da boş izle söylenemez
   (desteksiz pes = tespit edilir).

Bu şema ``backend/api.py`` kanıt kayıtlarına ``responsibility`` anahtarıyla,
görev başlangıcına da ``task_contract`` ile girer; ``tests/audit/test_responsibility_rules.py``
ve ``tests/unit/test_responsibility_chain.py`` ile kilitlenir.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "FAKE_SUCCESS",
    "QUIT_WITHOUT_SUPPORT",
    "Handoff",
    "ResponsibilityTrail",
    "TaskContract",
    "seal_trail",
]


#: Makine-okunur ihlal kodları (sahte başarı engeli).
FAKE_SUCCESS = "FAKE_SUCCESS"          # "tamam" dedi ama kanıt/iz eksik
QUIT_WITHOUT_SUPPORT = "QUIT_WITHOUT_SUPPORT"  # "yapamadım" dedi ama yol/destek/sonraki adım yok


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Handoff(BaseModel):
    """Görev devri — kime, neden, ne teslim edildi."""

    model_config = ConfigDict(extra="forbid")

    to: str
    reason: str
    handed_over: list[str] = Field(default_factory=list)


class TaskContract(BaseModel):
    """Görev sözleşmesi — çalışma BAŞLAMADAN önce tamamlanır.

    Eksik sözleşme = görev başlamaz (``ensure_complete`` ``ValueError``
    fırlatır); "yarım anladım, denedim" durumu kökten imkânsızdır.
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str
    agent_id: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)
    forbidden_behaviors: list[str] = Field(default_factory=list)
    success_condition: str = ""
    failure_condition: str = ""
    evidence_output: list[str] = Field(default_factory=list)

    def ensure_complete(self) -> "TaskContract":
        """Sözleşme kural denetimi — eksik varsa görev kapısı açılmaz."""
        missing: list[str] = []
        if not self.task_id.strip():
            missing.append("task_id")
        if not self.agent_id.strip():
            missing.append("agent_id")
        if not self.acceptance_criteria:
            missing.append("acceptance_criteria")
        if not self.required_inputs:
            missing.append("required_inputs")
        if not self.forbidden_behaviors:
            missing.append("forbidden_behaviors")
        if not self.success_condition.strip():
            missing.append("success_condition")
        if not self.failure_condition.strip():
            missing.append("failure_condition")
        if not self.evidence_output:
            missing.append("evidence_output")
        if missing:
            raise ValueError(
                "TASK_CONTRACT_INCOMPLETE: sözleşme eksik → görev başlamaz "
                f"(eksik: {', '.join(missing)}; agent={self.agent_id or '?'})"
            )
        return self

    @classmethod
    def for_agent(
        cls,
        task_id: str,
        agent_id: str,
        *,
        required_inputs: Sequence[str],
        acceptance_criteria: Sequence[str],
        evidence_output: Sequence[str],
        forbidden_behaviors: Sequence[str] = (
            "eksik veriyi tamamlamak/uydurmak",
            "kanıtsız 'tamam' raporu",
            "hatayı gizlemek",
        ),
        success_condition: str = "",
        failure_condition: str = "",
    ) -> "TaskContract":
        return cls(
            task_id=task_id,
            agent_id=agent_id,
            required_inputs=list(required_inputs),
            acceptance_criteria=list(acceptance_criteria),
            evidence_output=list(evidence_output),
            forbidden_behaviors=list(forbidden_behaviors),
            success_condition=success_condition
            or "tüm kabul kriterleri kanıt kaydıyla karşılandı",
            failure_condition=failure_condition
            or "girdi/kapı/kanıt eksik → dürüst blocked/halted raporu",
        ).ensure_complete()


class ResponsibilityTrail(BaseModel):
    """Bir bileşenin görev izi — sekiz zorunlu alan."""

    model_config = ConfigDict(extra="forbid")

    attempted_paths: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    support_requested: list[str] = Field(default_factory=list)
    handoff: Optional[Handoff] = None
    partial_result: Optional[str] = None
    missing: list[str] = Field(default_factory=list)
    next_action: Optional[str] = None
    integrity: dict[str, Any] = Field(default_factory=dict)
    sealed_at: str = Field(default_factory=_utcnow)

    # ── sahte başarı engeli ────────────────────────────────────────────
    def claimed_completed(self) -> bool:
        return str(self.integrity.get("claimed") or "") in {
            "completed",
            "completed_no_decision",
        }

    def seal(self) -> "ResponsibilityTrail":
        """Mühürle: ihlal varsa ``integrity.violation`` yazılır (gizlenmez)."""
        return seal_trail(self)


def seal_trail(trail: ResponsibilityTrail) -> ResponsibilityTrail:
    """Sahte başarı / desteksiz pes kurallarını uygular.

    Kurallar:
      * **Eksik kanıt başarı değildir.** "tamamlandı" iddiası; kanıt kaydı
        yokken (``integrity.evidence_recorded`` False) veya ``missing``
        doluyken mühürlenemez → ``FAKE_SUCCESS``.
      * **Desteksiz pes tespit edilir.** "yapamadım/bloke" iddiası; ne
        ``attempted_paths`` ne ``blockers`` ne ``next_action`` doluysa
        → ``QUIT_WITHOUT_SUPPORT`` (bu bir "ara rapor" bile değildir).
      * Dürüst ara rapor (attempted/blockers/next_action dolu) serbesttir —
        sistem kolay pes etmez, ama ettiğinde de ne yaptığını söyler.
    """
    claimed = str(trail.integrity.get("claimed") or "")
    evidence_recorded = bool(trail.integrity.get("evidence_recorded"))
    violation: Optional[str] = None

    if claimed in {"completed", "completed_no_decision"}:
        if not evidence_recorded or trail.missing:
            violation = FAKE_SUCCESS
    elif claimed in {"failed", "halted", "halted_evidence", "halted_critical", "timed_out"}:
        if not (trail.attempted_paths or trail.blockers or trail.next_action):
            violation = QUIT_WITHOUT_SUPPORT

    if violation:
        # İhlal GİZLENMEZ: mühür alana yazılır; çağıran katman
        # (executor) kaydı reddetmek veya durumu düşürmek zorundadır.
        trail.integrity = {
            **trail.integrity,
            "violation": violation,
            "sealed": False,
        }
    else:
        trail.integrity = {**trail.integrity, "violation": None, "sealed": True}
    return trail


def build_trail(
    *,
    claimed: str,
    evidence_recorded: bool,
    attempted_paths: Iterable[str] = (),
    blockers: Iterable[str] = (),
    support_requested: Iterable[str] = (),
    handoff: Optional[Mapping[str, Any] | Handoff] = None,
    partial_result: Optional[str] = None,
    missing: Iterable[str] = (),
    next_action: Optional[str] = None,
    extra_integrity: Optional[Mapping[str, Any]] = None,
) -> ResponsibilityTrail:
    """Pratik kurucu — ``seal`` ile birlikte kullanılır."""
    if isinstance(handoff, Mapping):
        handoff_obj: Optional[Handoff] = Handoff(**dict(handoff))
    else:
        handoff_obj = handoff

    def _sanitize(paths: Iterable[str]) -> list[str]:
        """Dürüst iz = tekrarsız, tek satır, uzunluk kapaklı."""
        out: list[str] = []
        for raw in paths:
            item = " ".join(str(raw).split())[:300]
            if item and item not in out:
                out.append(item)
        return out

    integrity: dict[str, Any] = {"claimed": claimed, "evidence_recorded": evidence_recorded}
    if extra_integrity:
        integrity.update(dict(extra_integrity))
    return seal_trail(
        ResponsibilityTrail(
            attempted_paths=_sanitize(attempted_paths),
            blockers=_sanitize(blockers),
            support_requested=_sanitize(support_requested),
            handoff=handoff_obj,
            partial_result=partial_result,
            missing=_sanitize(missing),
            next_action=next_action,
            integrity=integrity,
        )
    )
