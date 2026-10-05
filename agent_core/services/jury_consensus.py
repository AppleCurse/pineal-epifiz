"""FAZ B · B1 — BAĞIMSIZ JÜRİ KONSENSÜS DENETÇİSİ.

Bugüne dek panelin verdiği karar, panelin KENDİ aritmetiğine dayanıyordu:
`autonomous_verifier` oyları topluyor, çoğunluğu hesaplayıp hükmü yazıyordu.
Yani "sayımı yapan, sonucu da kendisi ilan eden" tek bir yer vardı.

Bu modül o sayımı TEKRAR ve BAĞIMSIZ yapar (duh fikri: aynı hipotezi ikinci
bir kafaya "anladın mı, doğru mu?" diye okutmak):

    1. Oylar yeniden sayılır (kapalı sözlük dışı oy sayılmaz).
    2. Çoğunluk/beraberlik/tek-koltuk kuralları BAĞIMSIZ uygulanır.
    3. Yeter sayı (quorum) denetlenir: tek koltukla alınan hüküm
       "konsensüs" DEĞİLDİR — işaretlenir.
    4. Panelin ilan ettiği hükümle denetçinin bulduğu hüküm KARŞILAŞTIRILIR;
       uyuşmazlık UYDURULARAK kapatılmaz, rapora yazılır.

Bağlayıcılık (bilinçli ve ölçülebilir):
- `PINEAL_JURY_QUORUM` (varsayılan 1 = bugünkü davranış): yeter sayı.
- `PINEAL_JURY_BINDING` (varsayılan **false**): true ise uyuşmazlıkta
  denetçinin bulduğu (daha temkinli) hüküm GEÇERLİ olur. Kapalıyken
  uyuşmazlık yalnızca GÖRÜNÜR olur; hiçbir şey gizlenmez.

Dürüstlük: bu modül LLM çağırmaz, ağa çıkmaz, tahmin üretmez — yalnızca
verilmiş oyların üzerinde deterministik aritmetik yapar.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ClaimConsensus",
    "ConsensusSummary",
    "quorum",
    "binding_enabled",
    "audit_claim",
    "summarize",
]

#: Kapalı oy sözlüğü (autonomous_verifier ile BİREBİR aynı; kopya değil, tek
#: doğruluk kaynağı orasıdır — burada yalnızca sayım için yeniden yazılır).
VOTE_VERIFIED = "DOĞRULANDI"
VOTE_CONTRADICTED = "ÇELİŞKİLİ"
VOTE_FALSE = "YALAN"
VOTE_UNKNOWN = "BİLİNMİYOR"
CONCLUSIVE_VOTES = frozenset({VOTE_VERIFIED, VOTE_CONTRADICTED, VOTE_FALSE})


def quorum() -> int:
    """Karar için gereken ENAZ bağımsız koltuk sayısı."""
    raw = os.getenv("PINEAL_JURY_QUORUM", "1").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def binding_enabled() -> bool:
    return os.getenv("PINEAL_JURY_BINDING", "false").strip().lower() == "true"


class ClaimConsensus(BaseModel):
    """Tek bir iddia için bağımsız yeniden sayım sonucu."""

    claim_id: Optional[str] = None
    claim_text: str = ""
    seats: int = 0              # oy veren bağımsız koltuk
    counted: int = 0            # kesin (sözlük içi) oy
    tally: Dict[str, int] = Field(default_factory=dict)
    reported_verdict: str = ""
    recomputed_verdict: str = ""
    agreement: bool = True      # ilan edilen hüküm == denetçinin bulduğu
    quorum_required: int = 1
    quorum_met: bool = False
    consensus_strength: float = 0.0   # en kalabalık oy / toplam oy (0..1)
    dissent: List[str] = Field(default_factory=list)   # hükme katılmayan koltuklar
    notes: List[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class ConsensusSummary(BaseModel):
    claims_audited: int = 0
    mismatches: int = 0
    mismatch_claims: List[str] = Field(default_factory=list)
    quorum_required: int = 1
    quorum_met_claims: int = 0
    single_seat_claims: int = 0
    mean_strength: float = 0.0
    binding: bool = False
    downgraded_claims: int = 0
    machine_note: str = ""
    model_config = ConfigDict(extra="forbid")


def _recompute(votes: Dict[str, str], required: int) -> tuple[str, List[str], float, bool]:
    """Oyları BAĞIMSIZ sayar: (hüküm, notlar, uzlaşma gücü, yeter sayı)."""
    notes: List[str] = []
    clean = {seat: vote for seat, vote in (votes or {}).items() if vote in CONCLUSIVE_VOTES or vote == VOTE_UNKNOWN}
    if not clean:
        return VOTE_UNKNOWN, ["hiç_oy_yok"], 0.0, False

    tally: Dict[str, int] = {}
    for vote in clean.values():
        tally[vote] = tally.get(vote, 0) + 1
    top_status, top_count = max(sorted(tally.items()), key=lambda item: item[1])
    strength = round(top_count / len(clean), 4)
    met = len(clean) >= required

    if not met:
        notes.append(f"yeter_sayı_yok:{len(clean)}<{required}")
        return VOTE_UNKNOWN, notes, strength, False
    if len(clean) == 1:
        notes.append("tek_koltuk_konsensüs_değil")
        return top_status, notes, strength, True
    if top_count * 2 > len(clean):
        return top_status, notes, strength, True
    notes.append(f"berabere:{top_count}/{len(clean)}")
    return VOTE_UNKNOWN, notes, strength, True


def audit_claim(result: Any, *, required: Optional[int] = None) -> ClaimConsensus:
    """Panelin bir iddia için verdiği kararı BAĞIMSIZ denetler."""
    required = quorum() if required is None else max(1, int(required))
    votes: Dict[str, str] = dict(getattr(result, "juror_votes", None) or {})
    reported = str(getattr(result, "truth_status", "") or "")
    verdict, notes, strength, met = _recompute(votes, required)
    counted = sum(1 for v in votes.values() if v in CONCLUSIVE_VOTES)

    tally: Dict[str, int] = {}
    for vote in votes.values():
        tally[vote] = tally.get(vote, 0) + 1

    dissent = sorted(seat for seat, vote in votes.items() if vote != verdict)
    return ClaimConsensus(
        claim_id=getattr(result, "claim_id", None),
        claim_text=str(getattr(result, "claim_text", "") or "")[:200],
        seats=len(votes),
        counted=counted,
        tally=tally,
        reported_verdict=reported,
        recomputed_verdict=verdict,
        agreement=(reported == verdict),
        quorum_required=required,
        quorum_met=met,
        consensus_strength=strength,
        dissent=dissent,
        notes=notes,
    )


def summarize(reports: Sequence[ClaimConsensus], *, required: Optional[int] = None) -> ConsensusSummary:
    required = quorum() if required is None else max(1, int(required))
    total = len(reports or [])
    if total == 0:
        return ConsensusSummary(
            quorum_required=required,
            binding=binding_enabled(),
            machine_note="KONSENSÜS: denetlenecek iddia yok.",
        )
    mismatched = [r for r in reports if not r.agreement]
    strength = sum(r.consensus_strength for r in reports) / total
    summary = ConsensusSummary(
        claims_audited=total,
        mismatches=len(mismatched),
        mismatch_claims=[str(r.claim_id or r.claim_text[:40]) for r in mismatched],
        quorum_required=required,
        quorum_met_claims=sum(1 for r in reports if r.quorum_met),
        single_seat_claims=sum(1 for r in reports if r.seats == 1),
        mean_strength=round(strength, 4),
        binding=binding_enabled(),
    )
    summary.machine_note = (
        f"KONSENSÜS: {total} iddia denetlendi · {len(mismatched)} uyuşmazlık · "
        f"yeter sayı {summary.quorum_met_claims}/{total} · ortalama uzlaşma {strength:.2f}"
        + (" · BAĞLAYICI" if summary.binding else " · salt denetim")
    )
    return summary


def consensus_downgrades(reports: Iterable[ClaimConsensus]) -> Dict[str, str]:
    """Bağlayıcı kipte hangi iddianın hangi hükme DÜŞÜRÜLDÜĞÜ (id -> hüküm)."""
    if not binding_enabled():
        return {}
    return {
        str(r.claim_id or r.claim_text[:40]): r.recomputed_verdict
        for r in reports
        if not r.agreement
    }
