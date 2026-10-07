"""FAZ D · D5 — RAPOR FABRİKASI adaptörleri: PDF · diyagram · video.

Üç yetenek, tek sözleşme (``renderer.report.*``):

    Rapor UYDURULMAZ. Girdi kanonik kanıt satırlarıdır; sıra ve epistemik
    notlar ``evidence_timeline``den gelir. Üretilen her eser kanıt
    kimliklerine geri bağlanır ve ``sha256`` ile mühürlenir; paketin
    ``manifest.json``u kanıt listesini + eser hash'lerini taşır.

Format üretilemezse (reportlab/Pillow/ffmpeg yok) yetenek ÇÖKMEZ: dürüst
``available=False`` + makine-okunur sebep döner ve diğer formatlar yine üretilir.
Markdown + manifest her koşulda yazılır (paketin çekirdeği).
"""

from __future__ import annotations

from typing import Any

from agent_core.capabilities.adapters_osint import _flag
from agent_core.capabilities.base import (
    Availability,
    BaseCapability,
    CapabilityContext,
    CapabilityKind,
    CapabilityResult,
    make_evidence,
)
from agent_core.services import report_factory

__all__ = [
    "ReportPdfCapability",
    "ReportDiagramCapability",
    "ReportVideoCapability",
]

GATE_REASON = f"gate_disabled:{report_factory.GATE}"


def _gate() -> Availability | None:
    if not _flag(report_factory.GATE):
        return Availability.unavailable(GATE_REASON)
    return None


def _params(ctx: CapabilityContext) -> tuple[str, str, list[dict[str, Any]]]:
    title = str(ctx.params.get("title") or ctx.subject or "").strip()
    subject = str(ctx.params.get("subject") or "").strip()
    raw = ctx.params.get("evidence") or []
    items = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    return title, subject, items


class _ReportCapability(BaseCapability):
    """Ortak gövde: paket üret, kanıta bağla, mühürle."""

    kind = CapabilityKind.RENDERER
    gates = frozenset({"vault", report_factory.GATE})
    timeout_seconds = 300.0
    license = "dahili (reportlab/Pillow/ffmpeg harici araçlar)"
    format_name = ""

    def availability(self) -> Availability:
        blocked = _gate()
        if blocked:
            return blocked
        ok, reason = report_factory.availability()[self.format_name]
        if not ok:
            return Availability.unavailable(reason)
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        title, subject, items = _params(ctx)
        if not title:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="empty_title"
            )
        package = report_factory.build_report(
            items, title=title, subject=subject, formats=(self.format_name,)
        )
        notes: dict[str, Any] = {
            "title": package.title,
            "subject": package.subject,
            "created_at": package.created_at,
            "evidence_ids": list(package.evidence_ids[:50]),
            "manifest_path": package.manifest_path,
            "manifest_sha256": package.manifest_sha256,
            "artifacts": [
                {
                    "name": a.name,
                    "available": a.available,
                    "reason": a.reason,
                    "path": a.path,
                    "sha256": a.sha256,
                    "bytes": a.bytes,
                }
                for a in package.artifacts
            ],
            "rejected_item_count": package.notes.get("rejected_item_count", 0),
            "excluded_strategy_count": package.notes.get("excluded_strategy_count", 0),
            "epistemic_counts": package.notes.get("epistemic_counts", {}),
            "fidelity": "yalnız kanonik kanıt çizelgesinden üretildi; içerik uydurulmadı",
        }
        if not package.available:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=package.reason or "report_failed",
                notes=notes,
            )

        items_out = []
        artifact = package.artifact(self.format_name)
        if artifact is not None and artifact.available:
            counts = package.notes.get("epistemic_counts", {})
            count_text = ", ".join(f"{k}:{v}" for k, v in sorted(counts.items())) or "yok"
            items_out.append(
                make_evidence(
                    content=(
                        f"Rapor ({artifact.name}) üretildi: {artifact.path} · "
                        f"sha256={artifact.sha256[:16]}… · {len(package.evidence_ids)} kanıt "
                        f"({count_text}) · {artifact.bytes} bayt"
                    ),
                    source_engine="report_factory",
                    provenance_refs=list(package.evidence_ids[:50]),
                    scope={
                        "format": artifact.name,
                        "sha256": artifact.sha256,
                        "manifest_sha256": package.manifest_sha256,
                        "claim": "artifact_from_evidence",
                    },
                )
            )
        elif artifact is not None:
            # Format yok ama paket teslim: md + manifest yine üretildi.
            notes["format_unavailable"] = artifact.reason
            markdown = package.artifact("markdown")
            if markdown is not None and markdown.available:
                items_out.append(
                    make_evidence(
                        content=(
                            f"Rapor markdown olarak üretildi ({markdown.path}); "
                            f"{self.format_name} ÜRETİLEMEDİ ({artifact.reason}) — yerine "
                            f"uydurma çıktı konmadı."
                        ),
                        source_engine="report_factory",
                        provenance_refs=list(package.evidence_ids[:50]),
                        scope={"format": "markdown", "fallback_for": self.format_name, "claim": "degraded"},
                    )
                )

        if package.manifest_path:
            items_out.append(
                make_evidence(
                    content=(
                        f"Rapor mührü: {package.manifest_path} · "
                        f"manifest_sha256={package.manifest_sha256[:16]}… · "
                        f"{len(package.evidence_ids)} kanıt bağlantısı (bütünlük mührü; "
                        "kriptografik imza değil)."
                    ),
                    source_engine="report_factory",
                    provenance_refs=list(package.evidence_ids[:50]),
                    scope={
                        "artifact": "manifest",
                        "manifest_sha256": package.manifest_sha256,
                        "claim": "integrity_seal",
                    },
                )
            )

        notes["evidence_count"] = len(items_out)
        return CapabilityResult(
            capability_id=self.id, available=True, items=tuple(items_out), notes=notes
        )


class ReportPdfCapability(_ReportCapability):
    """PDF rapor — reportlab yoksa dürüstçe kapalı."""

    id = "renderer.report.pdf"
    format_name = "pdf"
    description = "Kanıt çizelgesinden PDF rapor üretir (hash'li, kanıt bağlantılı)."


class ReportDiagramCapability(_ReportCapability):
    """Zaman çizelgesi diyagramı (PNG) — Pillow."""

    id = "renderer.report.diagram"
    format_name = "diagram"
    description = "Kanıt çizelgesini deterministik PNG diyagrama çevirir (tür = renk)."


class ReportVideoCapability(_ReportCapability):
    """Video özet (mp4) — ffmpeg yoksa dürüstçe kapalı."""

    id = "renderer.report.video"
    format_name = "video"
    description = "Kanıt çizelgesinden kısa video özet üretir (kareler Pillow, kodlama ffmpeg)."
