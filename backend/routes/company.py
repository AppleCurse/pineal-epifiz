"""Kurum hedefi uçları — ``/api/company/*`` (status · scan).

[API-BÖLME 7] Bu modül ``backend/api.py`` tek-modül TAVANI yüzünden ayrıldı
(``tests/unit/test_api_monolith_ratchet.py``; kural: yeni satır yerine MODÜL ÇIKAR).
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

__all__ = [
    "CompanyScanPayload",
    "register_company_routes",
]

_COMPANY_MODES = {
    "harvester": "sensor.company.harvester",
    "seo": "sensor.company.seo",
    "people": "sensor.company.people",
}


class CompanyScanPayload(BaseModel):
    """[FAZ D · D6] Kurum hedefi taraması: alan adı + mod seçimi."""

    domain: str = Field(min_length=1, max_length=253)
    client_id: str = Field(default="default", max_length=128)
    modes: list[str] = Field(default_factory=lambda: ["harvester", "seo", "people"])
    limit: int = Field(default=200, ge=1, le=1000)


def register_company_routes(
    app: FastAPI,
    *,
    rate_limit: Callable[[str, str], bool],
    check_vault_interlock: Callable[[str], bool],
    broadcast_log: Callable[[str, str, str], None],
    flag_env: Callable[[str], bool],
) -> None:
    @app.get("/api/company/status")
    async def api_company_status():
        """[FAZ D · D6] Kurum hedefi yeteneklerinin GERÇEK durumu (defterden)."""
        from agent_core.capabilities import bootstrap

        registry = bootstrap()
        rows = []
        for mode, cap_id in _COMPANY_MODES.items():
            cap = registry.get(cap_id)
            availability = cap.availability()
            rows.append(
                {
                    "mode": mode,
                    "capability_id": cap_id,
                    "available": availability.available,
                    "reason": availability.reason,
                    "gates": sorted(cap.gates),
                }
            )
        return {
            "gate": "ENABLE_COMPANY_TARGETING",
            "domain_hint": "yalnız alan adı (örn. ornek.com); özel/yerel adresler reddedilir",
            "modes": rows,
            "any_available": any(row["available"] for row in rows),
        }

    @app.post("/api/company/scan")
    async def api_company_scan(req: CompanyScanPayload):
        """[FAZ D · D6] Kurum hedefini omurgadan tarar (theHarvester · SEO · kişi)."""
        from agent_core.capabilities.base import CapabilityContext
        from agent_core.capabilities.policy import PolicyState
        from agent_core.capabilities.registry import bootstrap
        from agent_core.capabilities.runner import CapabilityRunner
        from agent_core.services import company_recon

        if not rate_limit(f"company:{req.client_id}", "company"):
            return JSONResponse(
                {"error": {"code": "RATE_LIMITED", "message": "Çok fazla kurum taraması"}},
                status_code=429,
            )

        domain = company_recon.normalize_domain(req.domain)
        if not domain:
            return JSONResponse(
                {
                    "error": {
                        "code": "INVALID_DOMAIN",
                        "message": "Geçerli bir alan adı verin (örn. ornek.com).",
                    }
                },
                status_code=400,
            )

        wanted = [str(m).strip().lower() for m in (req.modes or [])]
        unknown = [m for m in wanted if m not in _COMPANY_MODES]
        if unknown:
            return JSONResponse(
                {"error": {"code": "UNKNOWN_MODE", "message": f"Bilinmeyen mod: {', '.join(unknown)}"}},
                status_code=400,
            )
        if not wanted:
            wanted = list(_COMPANY_MODES)

        runner = CapabilityRunner(registry=bootstrap())
        state = PolicyState(
            enabled_flags={company_recon.GATE: flag_env(company_recon.GATE)},
            vault_locked=not check_vault_interlock(req.client_id),
            rate_ok=True,
        )

        results: dict[str, Any] = {}
        for mode in wanted:
            cap_id = _COMPANY_MODES[mode]
            params: dict[str, Any] = {"domain": domain}
            if mode == "harvester":
                params["limit"] = req.limit
            result = await runner.run(
                cap_id,
                CapabilityContext(subject=domain, params=params),
                state=state,
            )
            results[mode] = {
                "capability_id": cap_id,
                "available": bool(result.available),
                "denied_by": result.denied_by,
                "reason": result.unavailable_reason,
                "counts": {
                    "evidence": len(result.items),
                },
                "evidence": [
                    {
                        "evidence_id": item.evidence_id,
                        "epistemic_type": item.epistemic_type,
                        "source_engine": item.source_engine,
                        "content": item.content[:400],
                        "provenance_refs": list(item.provenance_refs)[:5],
                    }
                    for item in result.items[:25]
                ],
                "notes": dict(result.notes or {}),
            }
            if result.denied_by:
                broadcast_log(
                    req.client_id, "WARNING",
                    f"KURUM: {mode} engellendi — kapı:{result.denied_by}",
                )
            elif not result.available:
                broadcast_log(
                    req.client_id, "WARNING",
                    f"KURUM: {mode} hazır değil — {result.unavailable_reason}",
                )
            else:
                broadcast_log(
                    req.client_id, "INFO",
                    f"KURUM: {mode} tamam — {len(result.items)} kanıt ({domain})",
                )

        return {
            "domain": domain,
            "gate": company_recon.GATE,
            "modes": results,
            "evidence_total": sum(r["counts"]["evidence"] for r in results.values()),
        }
