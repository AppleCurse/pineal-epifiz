"""FAZ D · D3 — MEDYA ADLİ HATTI adaptörleri: indir · kare · yazı · eşleştir.

Dört yetenek, tek sözleşme:

    sensor.media.fetch        → paylaşılan medyayı indirir (sha256 ile mühürler)
    analyzer.media.frames     → kare kare ÖLÇÜM (künye, parlaklık, sahne kesmesi,
                                 fotoğrafta keskinlik) — içerik yorumu DEĞİL
    extractor.media.transcript→ sesi yazıya döker; YALNIZ yerel motor
                                 (yerel uç/CLI); uzak uç reddedilir
    analyzer.media.similarity → pHash + Hamming ile yerel benzerlik araması

Dürüstlük: araç yok → `available=False` + sebep; ölçülmeyen iddia edilmez;
motor boş çıktı verirse transkript ÜRETİLMEZ; indirme özel adreslere yapılmaz.
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
from agent_core.services import media_forensics

__all__ = [
    "MediaFetchCapability",
    "MediaFramesCapability",
    "MediaTranscriptCapability",
    "MediaSimilarityCapability",
]

GATE_REASON = f"gate_disabled:{media_forensics.GATE}"
MAX_LINES = 25


def _gate() -> Availability | None:
    if not _flag(media_forensics.GATE):
        return Availability.unavailable(GATE_REASON)
    return None


def _source_from(ctx: CapabilityContext) -> str:
    return str(ctx.params.get("path") or ctx.params.get("source") or ctx.subject or "").strip()


async def _resolve_path(ctx: CapabilityContext) -> tuple[str, str, dict[str, Any]]:
    """Medya yolunu çözer: yerel dosya varsa o, yoksa indirilir.

    Döner: (yol, sebep, künye_notları)
    """
    raw = _source_from(ctx)
    if not raw:
        return "", "invalid_source", {}
    from pathlib import Path

    local = Path(raw).expanduser()
    if "://" not in raw and local.exists():
        return str(local), "", {"tool": "local_path", "source": raw}
    fetched = await media_forensics.fetch_media(raw)
    notes = {
        "tool": fetched.tool,
        "source": fetched.source,
        "kind": fetched.kind,
        "sha256": fetched.sha256,
        "bytes": fetched.bytes,
    }
    if not fetched.available:
        return "", fetched.reason or "fetch_failed", notes
    return fetched.path, "", notes


class MediaFetchCapability(BaseCapability):
    """Paylaşılan medyayı indirir ve mühürler (yt-dlp/httpx)."""

    id = "sensor.media.fetch"
    kind = CapabilityKind.SENSOR
    license = "yt-dlp (Unlicense) · httpx (BSD) — harici araç, kod gömülmez"
    gates = frozenset({"vault", "rate", media_forensics.GATE})
    timeout_seconds = 300.0
    description = "Video/foto indirir (platform linkleri yt-dlp, doğrudan bağlantılar httpx) ve sha256 ile mühürler."

    def availability(self) -> Availability:
        blocked = _gate()
        if blocked:
            return blocked
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        source = _source_from(ctx)
        if not source:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="invalid_source"
            )
        fetched = await media_forensics.fetch_media(source)
        notes = {
            "source": fetched.source,
            "path": fetched.path,
            "kind": fetched.kind,
            "tool": fetched.tool,
            "sha256": fetched.sha256,
            "bytes": fetched.bytes,
            "content_type": fetched.content_type,
        }
        if not fetched.available:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=fetched.reason,
                notes=notes,
            )
        item = make_evidence(
            content=(
                f"Medya indirildi: {fetched.kind} · {fetched.bytes} bayt · "
                f"sha256={fetched.sha256[:16]}… · araç={fetched.tool or 'bilinmiyor'} · "
                f"dosya={fetched.path}"
            ),
            source_engine="media_fetch",
            provenance_refs=[fetched.source],
            scope={"kind": fetched.kind, "sha256": fetched.sha256, "claim": "downloaded"},
        )
        notes["evidence_count"] = 1
        return CapabilityResult(capability_id=self.id, available=True, items=(item,), notes=notes)


class MediaFramesCapability(BaseCapability):
    """Kare kare ölçüm: künye, parlaklık, sahne kesmeleri, keskinlik."""

    id = "analyzer.media.frames"
    kind = CapabilityKind.ANALYZER
    license = "OpenCV (Apache-2.0) — harici bağımlılık"
    gates = frozenset({"vault", media_forensics.GATE})
    timeout_seconds = 300.0
    description = "Video/fotoğrafı kare kare ÖLÇER (fps, çözünürlük, parlaklık, sahne kesmesi); içerik yorumu yapmaz."

    def availability(self) -> Availability:
        blocked = _gate()
        if blocked:
            return blocked
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        path, reason, meta = await _resolve_path(ctx)
        if not path:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason=reason, notes=meta
            )
        analysis = media_forensics.analyze_frames(
            path, sample_every=int(ctx.params.get("sample_every") or 5)
        )
        notes: dict[str, Any] = {
            **meta,
            "width": analysis.width,
            "height": analysis.height,
            "fps": analysis.fps,
            "frames": analysis.frames,
            "duration_s": analysis.duration_s,
            "sampled": analysis.sampled,
            "brightness_mean": analysis.brightness_mean,
            "brightness_std": analysis.brightness_std,
            "scenes": list(analysis.scenes),
            "sharpness": analysis.sharpness,
            "measurement_notes": analysis.notes,
        }
        if not analysis.available:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=analysis.reason,
                notes=notes,
            )

        items = []
        if analysis.kind == "image":
            items.append(
                make_evidence(
                    content=(
                        f"Fotoğraf ölçümü: {analysis.width}x{analysis.height} · "
                        f"parlaklık={analysis.brightness_mean} (±{analysis.brightness_std}) · "
                        f"baskın renk=RGB{analysis.dominant_color} · keskinlik={analysis.sharpness}"
                    ),
                    source_engine="media_frames",
                    provenance_refs=[path],
                    scope={"kind": "image", "claim": "measured_frames"},
                )
            )
        else:
            items.append(
                make_evidence(
                    content=(
                        f"Video künyesi: {analysis.fps} fps · {analysis.frames} kare · "
                        f"{analysis.duration_s} sn · {analysis.width}x{analysis.height} · "
                        f"parlaklık={analysis.brightness_mean} (±{analysis.brightness_std}) · "
                        f"sahne kesmesi={len(analysis.scenes)}"
                    ),
                    source_engine="media_frames",
                    provenance_refs=[path],
                    scope={"kind": "video", "claim": "measured_frames"},
                )
            )
            for at_s in analysis.scenes[:MAX_LINES]:
                items.append(
                    make_evidence(
                        content=f"Sahne kesmesi (histogram farkı): {at_s}. saniye",
                        source_engine="media_frames",
                        provenance_refs=[path],
                        scope={"at_s": at_s, "claim": "scene_cut"},
                    )
                )
        notes["evidence_count"] = len(items)
        return CapabilityResult(capability_id=self.id, available=True, items=tuple(items), notes=notes)


class MediaTranscriptCapability(BaseCapability):
    """Sesi yazıya döker — yalnız yerel motor; uzak uç reddedilir."""

    id = "extractor.media.transcript"
    kind = CapabilityKind.EXTRACTOR
    license = "yerel motor (whisper CLI ya da yerel uç) — kod gömülmez"
    gates = frozenset({"vault", media_forensics.GATE})
    timeout_seconds = 900.0
    description = "Medyanın sesini metne çevirir (yerel whisper CLI/uç). Ses ve metin makineden çıkmaz."

    def availability(self) -> Availability:
        blocked = _gate()
        if blocked:
            return blocked
        engine, reason = media_forensics.resolve_engine()
        if not engine:
            return Availability.unavailable(reason or "no_engine")
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        path, reason, meta = await _resolve_path(ctx)
        if not path:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason=reason, notes=meta
            )
        transcript = await media_forensics.transcribe(path)
        notes: dict[str, Any] = {
            **meta,
            "engine": transcript.engine,
            "chars": transcript.chars,
            "language": transcript.language,
            "language_confidence": transcript.language_confidence,
            "media_sha256": transcript.media_sha256,
        }
        if not transcript.available:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=transcript.reason,
                notes=notes,
            )
        item = make_evidence(
            content=f"Transkript ({transcript.engine} yerel motor): {transcript.text[:4000]}",
            source_engine="media_transcript",
            provenance_refs=[path],
            scope={
                "engine": transcript.engine,
                "language": transcript.language,
                "language_confidence": transcript.language_confidence,
                "media_sha256": transcript.media_sha256,
                "claim": "engine_transcript_not_verified",
            },
        )
        notes["evidence_count"] = 1
        notes["fidelity"] = "motor çıktısı olduğu gibi taşındı; doğrulanmadı"
        return CapabilityResult(capability_id=self.id, available=True, items=(item,), notes=notes)


class MediaSimilarityCapability(BaseCapability):
    """Görsel benzerlik: pHash + Hamming (yerel indeks)."""

    id = "analyzer.media.similarity"
    kind = CapabilityKind.ANALYZER
    license = "OpenCV + kendi pHash uygulaması (dahili)"
    gates = frozenset({"vault", media_forensics.GATE})
    timeout_seconds = 120.0
    description = "Görselin algısal parmak izini (pHash) çıkarır ve yerel indekste en yakın görselleri bulur."

    def availability(self) -> Availability:
        blocked = _gate()
        if blocked:
            return blocked
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        path, reason, meta = await _resolve_path(ctx)
        if not path:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason=reason, notes=meta
            )
        result = media_forensics.visual_similarity(path, top_k=int(ctx.params.get("top_k") or 3))
        notes: dict[str, Any] = {
            **meta,
            "query_hash": result.query_hash,
            "index_size": result.index_size,
            "matches": list(result.matches),
        }
        if not result.available:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=result.reason,
                notes=notes,
            )
        items = [
            make_evidence(
                content=(
                    f"Görsel parmak izi: phash={result.query_hash} · "
                    f"yerel indeks={result.index_size} dosya"
                ),
                source_engine="media_similarity",
                provenance_refs=[path],
                scope={"phash": result.query_hash, "claim": "perceptual_hash"},
            )
        ]
        for match in result.matches[:MAX_LINES]:
            items.append(
                make_evidence(
                    content=(
                        f"Benzer görsel: {match['file']} · Hamming={match['distance']} "
                        f"({'benzer' if match['similar'] else 'uzak'})"
                    ),
                    source_engine="media_similarity",
                    provenance_refs=[match["file"]],
                    scope={"distance": match["distance"], "claim": "phash_match"},
                )
            )
        notes["evidence_count"] = len(items)
        return CapabilityResult(capability_id=self.id, available=True, items=tuple(items), notes=notes)
