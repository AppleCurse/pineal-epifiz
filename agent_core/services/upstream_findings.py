"""Type-gated upstream findings for agent prompts.

Only explicitly tagged, unverified inferences from known analysis agents may
enter the shared prompt block. Strategy, verifier results, untyped legacy
findings, and unknown agent outputs are excluded; canonical pillar evidence is
consumed through the separate typed timeline service.
"""
from __future__ import annotations

from typing import Any

# These are agent-output classifications, not truth labels. The generated core
# remains an unverified claim; strategy and verifier outputs stay separate.
_UPSTREAM_TYPES_BY_AGENT = {
    "vision_analyzer": "inference",
    "osint_investigator": "inference",
    "depth_analyst": "inference",
    "human_behavior": "inference",
    "mirror_truth": "inference",
    "cognitive_profiler": "inference",
    "passion_mapper": "inference",
    "friction_detector": "inference",
    "authenticity_auditor": "inference",
    "target_psyche_profiler": "inference",
    # The compatibility report contains a recommended_approach field; keep it
    # out of general evidence/inference prompts with other action suggestions.
    "resonance_calc": "strategy",
    "pattern_interrupt": "strategy",
    "resonance_synthesizer": "strategy",
    "shadow_executor": "strategy",
    # Verifier A's verdict semantics are intentionally not folded into general
    # cross-agent findings; REFUTED/CONTRADICTED/UNVERIFIED remain separate.
    "autonomous_verifier": "verification",
}
_MAX_PROMPT_CHARS = 2000
_MAX_CORE_CHARS = 280


def classify_upstream_finding(agent: str) -> str:
    """Return an explicit type for known sources; unknown sources fail closed."""
    return _UPSTREAM_TYPES_BY_AGENT.get(agent, "untyped")


def upstream_findings_block(payload: Any) -> str:
    """Render only executor-authored, explicitly unverified inference cores."""
    findings = payload.get("_upstream_findings") if isinstance(payload, dict) else None
    if not isinstance(findings, list) or not findings:
        return ""

    lines: list[str] = []
    total_chars = 0
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        if finding.get("origin") != "task_executor":
            continue
        raw_agent = finding.get("agent")
        if not isinstance(raw_agent, str):
            continue
        if classify_upstream_finding(raw_agent) != "inference":
            continue
        if finding.get("epistemic_type") != "inference":
            continue
        if finding.get("verification_status") != "unverified":
            continue

        agent = raw_agent[:40]
        raw_core = finding.get("core")
        if not isinstance(raw_core, str):
            continue
        core = raw_core.strip()[:_MAX_CORE_CHARS]
        if not core:
            continue
        line = f"- [{agent}] [inference, doğrulanmamış] {core}"
        if total_chars + len(line) > _MAX_PROMPT_CHARS:
            break
        lines.append(line)
        total_chars += len(line)

    if not lines:
        return ""
    return (
        "DİĞER AJANLARIN BULGULARI (yalnız açıkça türü inference olan, "
        "doğrulanmamış iddialar — kendi kanıtınla çelişirse KENDİ KANITIN "
        "geçerlidir; bunu kopya olarak değil çapraz kontrol referansı olarak "
        "kullan):\n" + "\n".join(lines)
    )
