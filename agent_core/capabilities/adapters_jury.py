"""FAZ D · D2 — YEREL JÜRİ yeteneği: karar makineden çıkmaz, maliyeti sıfırdır.

``verifier.jury.local`` omurgadadır: her çağrı kasa + ``ENABLE_LOCAL_JURY``
kapılarından geçer ve kanıt zincirine **inference** olarak yazılır (jüri hükmü
gözlem değil, model yargısıdır).

Dürüstlük kuralı — konsensüs yoksa İDDİA da yoktur:
    * Oybirliği ya da yeter sayılı çoğunluk  → kanıt üretilir (``inference``).
    * Berabere / tek koltuk / geçerli oy yok → KANIT ÜRETİLMEZ; koltuk koltuk
      döküm ``notes`` içinde makine-okunur kalır (gizlenmez, ama "karar" diye
      de yazılmaz).
"""

from __future__ import annotations

from agent_core.capabilities.base import (
    Availability,
    BaseCapability,
    CapabilityContext,
    CapabilityKind,
    CapabilityResult,
    make_evidence,
)
from agent_core.services import local_jury

__all__ = ["LocalJuryCapability"]


class LocalJuryCapability(BaseCapability):
    """Aynı kanıtı birden çok YEREL modelde bağımsız oylar; kural açık yazılır."""

    id = "verifier.jury.local"
    kind = CapabilityKind.VERIFIER
    license = "yerel uç (ollama/llama.cpp/vLLM); kod gömülmez"
    # Kasa mandalı istisnasızdır (Tüzük Md.4); üstüne operatör kapısı gelir.
    gates = frozenset({"vault", local_jury.GATE})
    timeout_seconds = 180.0
    description = (
        "Aynı iddia ve kanıtı birden çok YEREL modelde bağımsız oylar; oybirliği "
        "ya da yeter sayılı çoğunluk karar olur. Uzak uç reddedilir; motor yoksa "
        "karar UYDURULMAZ."
    )

    def availability(self) -> Availability:
        available, reason = local_jury.availability()
        return Availability(available=available, reason=None if available else reason)

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        params = ctx.params or {}
        claim = (ctx.subject or str(params.get("claim") or "")).strip()
        evidence = str(params.get("evidence") or params.get("evidence_text") or "").strip()
        try:
            timeout = float(params.get("timeout") or 60.0)
        except (TypeError, ValueError):
            timeout = 60.0

        verdict = await local_jury.evaluate(claim, evidence, timeout=timeout)
        notes = {
            "rule": verdict.rule,
            "verdict": verdict.verdict,
            "consensus": verdict.consensus,
            "seats_run": verdict.seats_run,
            "counted": verdict.counted,
            "quorum_required": verdict.quorum_required,
            "tally": dict(verdict.tally),
            "dissent": list(verdict.dissent),
            "duplicates_removed": list(verdict.duplicates_removed),
            "endpoint": verdict.endpoint,
            "seat_errors": {
                vote.model: vote.error for vote in verdict.votes if vote.error
            },
            "machine_note": verdict.machine_note,
        }
        all_votes = [
            {
                "model": vote.model,
                "vote": vote.vote,
                "raw_vote": vote.raw_vote,
                "confidence": vote.confidence,
                "latency_ms": vote.latency_ms,
                "error": vote.error,
            }
            for vote in verdict.votes
        ]

        if not verdict.available:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=verdict.reason,
                payload=verdict,
                notes=notes,
            )
        if not verdict.consensus:
            return CapabilityResult(
                capability_id=self.id,
                available=True,
                items=(),  # konsensüs yok → İDDİA yok
                payload=verdict,
                notes={**notes, "seats": all_votes},
            )

        # Güven yalnız SAYILAN oyların kendi beyanından ortalanır; yoksa None.
        confidences = [
            vote.confidence for vote in verdict.votes if vote.confidence is not None and not vote.error
        ]
        confidence = round(sum(confidences) / len(confidences), 3) if confidences else None
        models = ", ".join(vote.model for vote in verdict.votes if not vote.error)
        item = make_evidence(
            content=(
                f"yerel jüri kararı: {verdict.verdict} "
                f"(kural {verdict.rule}, {verdict.counted}/{verdict.seats_run} koltuk oy verdi)"
            ),
            source_engine="local_jury",
            epistemic_type="inference",
            scope={
                "kind": "jury_verdict",
                "rule": verdict.rule,
                "seats": verdict.seats_run,
                "counted": verdict.counted,
                "tally": dict(verdict.tally),
                "models": [vote.model for vote in verdict.votes if not vote.error],
            },
            source_metrics={
                "rule": verdict.rule,
                "tally": dict(verdict.tally),
                "dissent": list(verdict.dissent),
                "quorum_required": verdict.quorum_required,
                "models": models,
            },
            confidence=confidence,
        )
        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=(item,),
            payload=verdict,
            notes={**notes, "seats": all_votes},
        )
