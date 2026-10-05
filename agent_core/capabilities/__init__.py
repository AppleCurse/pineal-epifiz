"""Capability Spine — Pineal'in tek yetenek sözleşmesi (Faz 0).

Kullanım:

    from agent_core.capabilities import bootstrap, run_capability
    from agent_core.capabilities.base import CapabilityContext
    from agent_core.capabilities.policy import PolicyState

    bootstrap()  # yerleşik adaptörleri kaydeder (idempotent)

    result = await run_capability(
        "sensor.identity.maigret",
        CapabilityContext(subject="ornek_kullanici"),
        state=PolicyState(vault_locked=False, enabled_flags={"ENABLE_MAIGRET": True}),
    )
    if result.ok:
        for item in result.items:      # EvidenceItem — kanıt zincirine girer
            ...

Tasarım kuralı: yetenek eklemek = ``BaseCapability`` alt sınıfı yazıp
``registry.register(...)`` ile kaydetmek. Bunun dışındaki her yol (doğrudan
import denemesi, env okuyan ikinci bir katman) yasaktır — bkz. kural [009]
ve C8 ölü-anahtar denetimi.
"""

from __future__ import annotations

from agent_core.capabilities.base import (  # noqa: F401  (yeniden ihracat)
    Availability,
    BaseCapability,
    Capability,
    CapabilityContext,
    CapabilityKind,
    CapabilityResult,
    make_evidence,
    new_evidence_id,
)
from agent_core.capabilities.policy import (  # noqa: F401
    PolicyDecision,
    PolicyKernel,
    PolicyState,
)
from agent_core.capabilities.registry import (  # noqa: F401
    CapabilityRegistry,
    bootstrap,
    default_registry,
)
from agent_core.capabilities.runner import CapabilityRunner, run_capability  # noqa: F401

__all__ = [
    "Availability",
    "BaseCapability",
    "Capability",
    "CapabilityContext",
    "CapabilityKind",
    "CapabilityResult",
    "CapabilityRegistry",
    "CapabilityRunner",
    "PolicyDecision",
    "PolicyKernel",
    "PolicyState",
    "bootstrap",
    "default_registry",
    "make_evidence",
    "new_evidence_id",
    "run_capability",
]
