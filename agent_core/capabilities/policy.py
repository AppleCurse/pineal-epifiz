"""PolicyKernel — her yeteneğin geçmek zorunda olduğu güvenlik/politika kapısı.

Tek kural: **bilinmeyen kapı = ret.** Bir yetenek, çekirdeğin tanımadığı bir
kapı (gate) bildiriyorsa çalıştırılmaz; bu, "yeni bir depo eklendi, kimse
hangi kapılardan geçtiğini okumadı" senaryosunu yapısal olarak imkânsız kılar.

Kapı sözlüğü:
    ``vault``    — kasa mandalı açık olmalı (kilitliyken dış ağa çıkış yok)
    ``consent``  — hedef için rıza kaydı olmalı (Faz 5 rıza defteri)
    ``budget``   — görev bütçesi aşılmamış olmalı
    ``rate``     — hız durumu biliniyor ve izin veriyor olmalı (bilinmiyorsa RET)
    ``ENABLE_*`` — env anahtarı açık olmalı (örn. ``ENABLE_MAIGRET``)

Bu modül harici bağımlılık içermez ve hiçbir ortam değişkenini kendisi
okumaz: durum dışarıdan ``PolicyState`` ile verilir (test edilebilirlik +
"örtük kaynak" yasağı).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

__all__ = ["PolicyDecision", "PolicyState", "PolicyKernel", "BUILTIN_GATES"]


#: Çekirdeğin bildiği kapılar. Bunun dışındaki her şey fail-closed reddedilir.
BUILTIN_GATES = frozenset({"vault", "consent", "budget", "rate"})


@dataclass(frozen=True)
class PolicyDecision:
    """Kapı değerlendirmesinin sonucu."""

    allowed: bool
    gate: str | None = None
    reason: str | None = None

    @classmethod
    def allow(cls) -> "PolicyDecision":
        return cls(allowed=True, gate=None, reason=None)

    @classmethod
    def deny(cls, gate: str, reason: str) -> "PolicyDecision":
        return cls(allowed=False, gate=gate, reason=reason)


@dataclass(frozen=True)
class PolicyState:
    """Kapıların değerlendirileceği durum (çağıran sağlar)."""

    vault_locked: bool = False
    consent_recorded: bool = False
    spent_usd: float = 0.0
    budget_usd: float | None = None
    rate_ok: bool | None = None          # None = bilinmiyor → "rate" kapısı RET
    enabled_flags: Mapping[str, bool] = field(default_factory=dict)


class PolicyKernel:
    """Yetenek kapılarını değerlendirir (durumsuz, deterministik)."""

    KNOWN_GATES = BUILTIN_GATES

    def evaluate(self, gates: frozenset[str] | set[str], state: PolicyState) -> PolicyDecision:
        """Kapıları deterministik sırada değerlendirir; ilk ret kararı kesindir."""
        for gate in sorted(gates or ()):
            if gate.startswith("ENABLE_"):
                if not bool(state.enabled_flags.get(gate, False)):
                    return PolicyDecision.deny(gate, "gate_disabled")
                continue

            if gate not in self.KNOWN_GATES:
                # Fail-closed: tanınmayan kapı asla "yok sayılmaz".
                return PolicyDecision.deny(gate, "unknown_gate")

            if gate == "vault" and state.vault_locked:
                return PolicyDecision.deny(gate, "vault_locked")

            if gate == "consent" and not state.consent_recorded:
                return PolicyDecision.deny(gate, "consent_missing")

            if gate == "budget":
                if state.budget_usd is not None and state.spent_usd >= state.budget_usd:
                    return PolicyDecision.deny(gate, "budget_exhausted")

            if gate == "rate":
                if state.rate_ok is None:
                    return PolicyDecision.deny(gate, "rate_state_missing")
                if not state.rate_ok:
                    return PolicyDecision.deny(gate, "rate_limited")

        return PolicyDecision.allow()
