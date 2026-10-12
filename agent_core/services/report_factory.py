"""FAZ D · D5 — RAPOR FABRİKASI: kanıt bağlantılı, hash'li rapor paketi.

Rapor UYDURULMAZ: paket yalnız kanonik kanıt zaman çizelgesinden
(``evidence_timeline.build_evidence_timeline``) beslenir. Sıra, epistemik tür ve
kaynak notu oradan gelir; üretilen her şey geri kanıta bağlanabilir.

Dört çıktı, tek sözleşme:

    markdown  → her zaman üretilir (bağımlılık yok)
    pdf       → reportlab (yoksa dürüst `dependency_missing:reportlab`)
    diagram   → Pillow ile deterministik PNG zaman çizelgesi
    video     → kare kare PNG → ffmpeg (yoksa `dependency_missing:ffmpeg`)

Bütünlük (hash'li mühür):
    * Her eser için ``sha256``.
    * ``manifest.json``: eser listesi + kanıt kimlikleri + epistemik sayımlar.
    * Manifestin kendi gövdesi de hash'lenir (``manifest_sha256``) — böylece
      paket sonradan değiştirilirse mühür tutmaz.

Bu bir KRİPTOGRAFİK İMZA DEĞİLDİR: anahtar yoktur, yalnız bütünlük mührüdür.
Yalan söylenmez; manifest de bunu açıkça yazar.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from agent_core.domain.evidence_models import EvidenceItem
from agent_core.services.evidence_timeline import build_evidence_timeline

__all__ = [
    "GATE",
    "ReportArtifact",
    "ReportPackage",
    "report_dir",
    "availability",
    "slugify",
    "build_report",
]

GATE = "ENABLE_REPORT_FACTORY"
MANIFEST_SCHEMA = "pineal.report.v1"

_FORMATS = ("markdown", "pdf", "diagram", "video")

#: Epistemik tür → diyagram rengi (görsel ayrım; anlam değişmez).
_TYPE_COLORS = {
    "observation": (56, 189, 248),
    "absence": (251, 191, 36),
    "inference": (167, 139, 250),
}


def report_dir() -> Path:
    """Rapor dizini: ``PINEAL_REPORT_DIR`` ya da ``memory/reports``."""
    raw = os.getenv("PINEAL_REPORT_DIR", "").strip()
    base = Path(raw).expanduser() if raw else Path("memory") / "reports"
    return base


def slugify(value: str, *, limit: int = 48) -> str:
    """Dosya adı için güvenli kısa ad (Türkçe karakterler sadeleşir)."""
    table = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    text = (value or "").translate(table).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text or "rapor")[:limit]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def availability() -> dict[str, tuple[bool, str]]:
    """Her format için dürüst durum: (var mı, sebep)."""
    pdf_ok = _module_available("reportlab")
    pillow_ok = _module_available("PIL")
    ffmpeg = shutil.which("ffmpeg")
    return {
        "markdown": (True, ""),
        "pdf": (pdf_ok, "" if pdf_ok else "dependency_missing:reportlab"),
        "diagram": (pillow_ok, "" if pillow_ok else "dependency_missing:Pillow"),
        "video": (
            bool(ffmpeg) and pillow_ok,
            "" if (ffmpeg and pillow_ok) else ("dependency_missing:ffmpeg" if not ffmpeg else "dependency_missing:Pillow"),
        ),
    }


def _module_available(name: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


@dataclass
class ReportArtifact:
    name: str
    available: bool
    reason: str = ""
    path: str = ""
    sha256: str = ""
    bytes: int = 0


@dataclass
class ReportPackage:
    available: bool
    reason: str = ""
    title: str = ""
    subject: str = ""
    created_at: str = ""
    evidence_ids: tuple[str, ...] = ()
    artifacts: tuple[ReportArtifact, ...] = ()
    manifest_path: str = ""
    manifest_sha256: str = ""
    notes: dict[str, Any] = field(default_factory=dict)

    def artifact(self, name: str) -> ReportArtifact | None:
        for item in self.artifacts:
            if item.name == name:
                return item
        return None


# --------------------------------------------------------------- metin üretimi
def _line_text(entry: Any) -> str:
    when = entry.timeline_at.strftime("%Y-%m-%d %H:%M") if entry.timeline_at else "tarihsiz"
    sources = ", ".join(entry.provenance_refs[:4]) if entry.provenance_refs else "kaynak yok"
    return (
        f"- **{when}** · `{entry.epistemic_type}` · {entry.source_engine}\n"
        f"  {entry.content}\n"
        f"  ↳ Kaynak: {sources}\n"
        f"  ↳ Not: {entry.epistemic_note}"
    )


def render_markdown(title: str, subject: str, created_at: str, entries: list[Any], stats: dict[str, Any]) -> str:
    head = [
        f"# {title}",
        "",
        f"- Hedef: {subject or '—'}",
        f"- Üretim: {created_at}",
        f"- Kanıt: {len(entries)} satır · reddedilen: {stats.get('rejected_item_count', 0)}"
        f" · strateji (çizelge dışı): {stats.get('excluded_strategy_count', 0)}",
        "",
        "> Bu rapor yalnız kanonik kanıt zaman çizelgesinden üretildi; içerik "
        "uydurulmadı. Epistemik notlar kanıt kaydından aynen taşınır.",
        "",
        "## Kanıt çizelgesi",
        "",
    ]
    body = [_line_text(entry) for entry in entries] or ["- (kanıt satırı yok)"]
    return "\n".join(head + body) + "\n"


# ------------------------------------------------------------------- PDF
def _write_pdf(path: Path, title: str, subject: str, created_at: str, entries: list[Any]) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    width, height = A4
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.setTitle(title)
    y = height - 25 * mm
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(20 * mm, y, title[:90])
    y -= 8 * mm
    pdf.setFont("Helvetica", 9)
    pdf.drawString(20 * mm, y, f"Hedef: {(subject or '-')[:80]} · Üretim: {created_at}")
    y -= 4 * mm
    pdf.drawString(20 * mm, y, f"Kanıt satırı: {len(entries)} · içerik kanıt kaydından aynen taşınır")
    y -= 8 * mm

    pdf.setFont("Helvetica", 9)
    for entry in entries:
        when = entry.timeline_at.strftime("%Y-%m-%d %H:%M") if entry.timeline_at else "tarihsiz"
        header = f"[{when}] ({entry.epistemic_type}) {entry.source_engine}"
        for chunk in _wrap(header, 110):
            pdf.drawString(20 * mm, y, chunk)
            y -= 4 * mm
        for chunk in _wrap(entry.content, 110):
            pdf.drawString(24 * mm, y, chunk)
            y -= 4 * mm
        sources = ", ".join(entry.provenance_refs[:3]) if entry.provenance_refs else "kaynak yok"
        for chunk in _wrap(f"Kaynak: {sources}", 100):
            pdf.setFillGray(0.35)
            pdf.drawString(24 * mm, y, chunk)
            pdf.setFillGray(0)
            y -= 4 * mm
        for chunk in _wrap(f"Not: {entry.epistemic_note}", 100):
            pdf.setFillGray(0.45)
            pdf.drawString(24 * mm, y, chunk)
            pdf.setFillGray(0)
            y -= 4 * mm
        y -= 3 * mm
        if y < 25 * mm:
            pdf.showPage()
            pdf.setFont("Helvetica", 9)
            y = height - 20 * mm
    pdf.showPage()
    pdf.save()


def _wrap(text: str, width: int) -> list[str]:
    words = str(text).replace("\n", " ").split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            if current:
                lines.append(current)
            current = word[:width]
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines or [""]


# ---------------------------------------------------------------- diyagram
def _write_diagram(path: Path, title: str, entries: list[Any]) -> None:
    from PIL import Image, ImageDraw

    row_h = 46
    header_h = 90
    width = 1000
    height = header_h + max(1, len(entries)) * row_h + 30
    image = Image.new("RGB", (width, height), (12, 16, 28))
    draw = ImageDraw.Draw(image)
    draw.text((24, 24), title[:80], fill=(226, 232, 240))
    draw.text(
        (24, 48),
        f"{len(entries)} kanıt satırı · renk = epistemik tür (gözlem/mavi, yokluk/sarı, çıkarım/mor)",
        fill=(148, 163, 184),
    )
    for index, entry in enumerate(entries):
        top = header_h + index * row_h
        color = _TYPE_COLORS.get(entry.epistemic_type, (148, 163, 184))
        draw.rectangle([20, top + 6, 28, top + row_h - 8], fill=color)
        when = entry.timeline_at.strftime("%Y-%m-%d") if entry.timeline_at else "tarihsiz"
        draw.text((40, top + 8), f"{when} · {entry.epistemic_type} · {entry.source_engine}"[:120], fill=(203, 213, 225))
        draw.text((40, top + 24), entry.content[:130], fill=(148, 163, 184))
    image.save(path, format="PNG")


# ------------------------------------------------------------------- video
def _write_video(path: Path, title: str, entries: list[Any], *, tmp: Path) -> tuple[bool, str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False, "dependency_missing:ffmpeg"
    if not _module_available("PIL"):
        return False, "dependency_missing:Pillow"

    from PIL import Image, ImageDraw

    frames: list[Path] = []
    cards = [("BAŞLIK", title)] + [
        (entry.epistemic_type, f"{entry.content[:90]} · {entry.source_engine}") for entry in entries[:20]
    ]
    for index, (kind, text) in enumerate(cards):
        frame = Image.new("RGB", (1280, 720), (12, 16, 28))
        draw = ImageDraw.Draw(frame)
        draw.text((80, 300), kind, fill=(56, 189, 248))
        draw.text((80, 360), text[:80], fill=(226, 232, 240))
        target = tmp / f"frame_{index:03d}.png"
        frame.save(target, format="PNG")
        frames.append(target)

    listing = tmp / "frames.txt"
    listing.write_text(
        "".join(f"file '{frame.name}'\nduration 1.0\n" for frame in frames) + f"file '{frames[-1].name}'\n",
        encoding="utf-8",
    )
    try:
        proc = subprocess.run(
            [
                ffmpeg, "-y", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(listing),
                "-vsync", "vfr", "-pix_fmt", "yuv420p", str(path),
            ],
            capture_output=True,
            timeout=180,
        )
    except Exception as exc:
        return False, f"ffmpeg_failed:{type(exc).__name__}"
    if proc.returncode != 0 or not path.exists():
        return False, f"ffmpeg_failed:rc{proc.returncode}"
    return True, ""


# ------------------------------------------------------------------- paket
def _manifest_payload(
    *,
    title: str,
    subject: str,
    created_at: str,
    entries: list[Any],
    stats: dict[str, Any],
    artifacts: list[ReportArtifact],
) -> dict[str, Any]:
    return {
        "schema": MANIFEST_SCHEMA,
        "title": title,
        "subject": subject,
        "created_at": created_at,
        "evidence_ids": [entry.evidence_id for entry in entries],
        "epistemic_counts": stats.get("epistemic_counts", {}),
        "rejected_item_count": stats.get("rejected_item_count", 0),
        "excluded_strategy_count": stats.get("excluded_strategy_count", 0),
        "artifacts": [
            {"name": a.name, "file": Path(a.path).name, "sha256": a.sha256, "bytes": a.bytes}
            for a in artifacts
            if a.available
        ],
        "fidelity": (
            "Yalnız kanonik kanıt zaman çizelgesinden üretildi; içerik uydurulmadı. "
            "manifest_sha256 bir bütünlük mührüdür, kriptografik imza DEĞİLDİR."
        ),
    }


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_report(
    items: Iterable[EvidenceItem | dict[str, Any]] | None,
    *,
    title: str,
    subject: str = "",
    formats: Iterable[str] = ("markdown", "pdf"),
    out_dir: Path | None = None,
    created_at: datetime | None = None,
) -> ReportPackage:
    """Kanıt satırlarından rapor paketi üretir (markdown + istenen formatlar).

    Hiçbir format zorunlu değildir: üretilemeyen her format kendi
    ``ReportArtifact``ında dürüst sebeple ``available=False`` olur — paket
    yine de teslim edilir (markdown + manifest her zaman yazılır).
    """
    clean_title = (title or "").strip()[:200]
    if not clean_title:
        return ReportPackage(available=False, reason="empty_title")

    timeline = build_evidence_timeline(items)
    entries = list(timeline.entries)
    stats: dict[str, Any] = {
        "rejected_item_count": timeline.rejected_item_count,
        "excluded_strategy_count": timeline.excluded_strategy_count,
        "epistemic_counts": {},
    }
    for entry in entries:
        stats["epistemic_counts"][entry.epistemic_type] = stats["epistemic_counts"].get(entry.epistemic_type, 0) + 1

    moment = (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    created = moment.strftime("%Y-%m-%d %H:%M UTC")
    stamp = moment.strftime("%Y%m%d-%H%M%S")

    target_dir = Path(out_dir) if out_dir is not None else report_dir()
    stem = f"{stamp}-{slugify(clean_title)}"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return ReportPackage(
            available=False,
            reason="report_dir_unwritable",
            title=clean_title,
            notes={"error": type(exc).__name__},
        )

    wanted = [str(name).strip().lower() for name in formats]
    unknown = [name for name in wanted if name not in _FORMATS]
    if unknown:
        return ReportPackage(available=False, reason=f"unknown_format:{unknown[0]}", title=clean_title)

    artifacts: list[ReportArtifact] = []
    caps = availability()

    def _record(name: str, path: Path) -> None:
        artifacts.append(
            ReportArtifact(
                name=name,
                available=True,
                path=str(path),
                sha256=_sha256_file(path),
                bytes=path.stat().st_size,
            )
        )

    # markdown: her zaman
    markdown_path = target_dir / f"{stem}.md"
    markdown_path.write_text(
        render_markdown(clean_title, subject, created, entries, stats), encoding="utf-8"
    )
    _record("markdown", markdown_path)

    if "pdf" in wanted:
        ok, reason = caps["pdf"]
        if not ok:
            artifacts.append(ReportArtifact("pdf", False, reason))
        else:
            pdf_path = target_dir / f"{stem}.pdf"
            try:
                _write_pdf(pdf_path, clean_title, subject, created, entries)
                _record("pdf", pdf_path)
            except Exception as exc:
                artifacts.append(ReportArtifact("pdf", False, f"pdf_failed:{type(exc).__name__}"))

    if "diagram" in wanted:
        ok, reason = caps["diagram"]
        if not ok:
            artifacts.append(ReportArtifact("diagram", False, reason))
        else:
            png_path = target_dir / f"{stem}.png"
            try:
                _write_diagram(png_path, clean_title, entries)
                _record("diagram", png_path)
            except Exception as exc:
                artifacts.append(ReportArtifact("diagram", False, f"diagram_failed:{type(exc).__name__}"))

    if "video" in wanted:
        ok, reason = caps["video"]
        if not ok:
            artifacts.append(ReportArtifact("video", False, reason))
        else:
            mp4_path = target_dir / f"{stem}.mp4"
            tmp_dir = target_dir / f"{stem}-frames"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            try:
                written, video_reason = _write_video(mp4_path, clean_title, entries, tmp=tmp_dir)
                if written:
                    _record("video", mp4_path)
                else:
                    artifacts.append(ReportArtifact("video", False, video_reason))
            except Exception as exc:
                artifacts.append(ReportArtifact("video", False, f"video_failed:{type(exc).__name__}"))
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    payload = _manifest_payload(
        title=clean_title,
        subject=subject,
        created_at=created,
        entries=entries,
        stats=stats,
        artifacts=artifacts,
    )
    manifest_sha = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    sealed = {**payload, "manifest_sha256": manifest_sha}
    manifest_path = target_dir / f"{stem}.manifest.json"
    manifest_path.write_text(
        json.dumps(sealed, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )

    return ReportPackage(
        available=True,
        title=clean_title,
        subject=subject,
        created_at=created,
        evidence_ids=tuple(entry.evidence_id for entry in entries),
        artifacts=tuple(artifacts),
        manifest_path=str(manifest_path),
        manifest_sha256=manifest_sha,
        notes={
            "rejected_item_count": timeline.rejected_item_count,
            "excluded_strategy_count": timeline.excluded_strategy_count,
            "epistemic_counts": stats["epistemic_counts"],
            "unavailable": {a.name: a.reason for a in artifacts if not a.available},
        },
    )
