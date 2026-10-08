"""FAZ C · C4 — SESLİ RAPOR: görev sonucu **konuşulan** bir rapora çevrilir.

Röntgen bulgusu: sistem bulduğunu YAZIYORDU, SÖYLEMİYORDU. C2 ile Aspasia
konuşuyor, C3 ile göz dinliyor; C4 raporun kendisini seslendirir: operatör
ekrana bakmadan "ne buldun?" sorusunun cevabını DUYAR.

Bu yetenek **RENDERER** sınıfındadır: rapor da graf/değişim raporu gibi bir
çıktıdır ve aynı omurgadan geçer (registry → politika → availability → run).

DÜRÜSTLÜK KURALI (tartışmasız):
    * Metin **uydurulmaz**: yalnız görev payload'ında GERÇEKTEN olan alanlar
      söylenir. Alan yoksa o cümle KURULMAZ (boşluk tahminle doldurulmaz).
    * Sayılar payload'dan sayılır; güven ortalaması yalnız sayısal güveni
      olan koşulardan hesaplanır (hiçbiri yoksa cümle söylenmez).
    * Kırmızı çizgi (18 altı) raporda işaretliyse SESLİ olarak da söylenir —
      susturulmaz, görmezden gelinmez.

Çıktı: düz Türkçe konuşma metni (`script`) + kanıt kaydı (hangi bölümler,
kaç karakter). Sesi üretmek TTS yeteneğinin işidir; burada metin doğar.
"""

from __future__ import annotations

from typing import Any

from agent_core.capabilities.base import (
    Availability,
    BaseCapability,
    CapabilityContext,
    CapabilityKind,
    CapabilityResult,
    make_evidence,
)

#: Konuşma metni tavanı (TTS motorunu boğmamak için). Aşan metin KIRPILIR
#: ve durum `truncated` olarak işaretlenir — asla sessizce kesilmez.
MAX_SCRIPT_CHARS = 1200

#: Görev durumlarının Türkçe karşılıkları ( raporda İngilizce gelir).
_STATUS_WORDS = {
    "completed": "tamamlandı",
    "complete": "tamamlandı",
    "processing": "sürüyor",
    "running": "sürüyor",
    "pending": "bekliyor",
    "failed": "başarısız",
    "error": "hata verdi",
    "timed_out": "zaman aşımına uğradı",
    "cancelled": "iptal edildi",
    "halted": "durduruldu",
}

#: Kırmızı çizgi bayrağı taşıyabilecek alan adları (raporda geçiyorsa söylenir).
_MINOR_HINT_KEYS = ("minor_gate", "child_safety", "minor", "age_gate")


def _target_name(report: dict[str, Any]) -> str:
    profile = report.get("target_profile") or {}
    if isinstance(profile, dict):
        for key in ("name", "username", "handle", "target"):
            value = str(profile.get(key) or "").strip()
            if value:
                return value
    for key in ("target", "username"):
        value = str(report.get(key) or "").strip()
        if value:
            return value
    return ""


def _status_word(report: dict[str, Any]) -> str:
    status = str(report.get("status") or "").strip().lower()
    return _STATUS_WORDS.get(status, status)


def _run_numbers(report: dict[str, Any]) -> tuple[int, int, float | None]:
    """(koşan ajan, tamamlanan ajan, ortalama güven) — yalnız GERÇEK sayılar."""
    runs = report.get("runs") or {}
    if not isinstance(runs, dict) or not runs:
        return 0, 0, None
    total = len(runs)
    done = 0
    confidences: list[float] = []
    for entry in runs.values():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("status") or "").lower() in {"completed", "complete", "ok"}:
            done += 1
        value = entry.get("confidence")
        if isinstance(value, (int, float)):
            confidences.append(float(value))
    average = sum(confidences) / len(confidences) if confidences else None
    return total, done, average


def _change_numbers(report: dict[str, Any]) -> tuple[int, int, int] | None:
    """(yeni, kayıp, değişen) — B7 değişim raporu YOKSA None (uydurma yok)."""
    changes = report.get("changes")
    if not isinstance(changes, dict) or not changes.get("available"):
        return None
    added = changes.get("added") or []
    removed = changes.get("removed") or []
    changed = changes.get("changed") or []
    return len(added), len(removed), len(changed)


def build_report_script(report: dict[str, Any]) -> tuple[str, list[str]]:
    """Görev payload'ından konuşma metni kurar. Boş alan için cümle YOK.

    Dönen ikinci değer: kurulan bölümlerin adları (kanıt ve telemetri için).
    """
    lines: list[str] = []
    sections: list[str] = []

    target = _target_name(report)
    if target:
        lines.append(f"Hedef {target}.")
        sections.append("target")

    status = _status_word(report)
    if status:
        lines.append(f"Görev {status}.")
        sections.append("status")

    chain = report.get("evidence_chain") or []
    if isinstance(chain, list) and chain:
        lines.append(f"Kanıt zincirinde {len(chain)} kayıt var.")
        sections.append("evidence")

    total, done, average = _run_numbers(report)
    if total:
        lines.append(f"{total} ajan koştu, {done} tanesi tamamlandı.")
        sections.append("agents")
    if average is not None:
        lines.append(f"Ortalama güven {average:.2f}.")
        sections.append("confidence")

    change = _change_numbers(report)
    if change is not None:
        added, removed, changed = change
        lines.append(
            f"Geçmiş taramaya göre {added} yeni, {removed} kayıp, {changed} değişen kayıt."
        )
        sections.append("changes")

    if report.get("depth_report"):
        lines.append("Derinlik raporu hazır.")
        sections.append("depth")
    if report.get("follower_audit"):
        lines.append("Takipçi denetimi yapıldı.")
        sections.append("followers")
    if report.get("timing_forensics"):
        lines.append("Zaman adli incelemesi yapıldı.")
        sections.append("timing")

    # KIRMIZI ÇİZGİ: raporda işaretliyse SÖYLENİR (susturulmaz).
    for key in _MINOR_HINT_KEYS:
        flag = report.get(key)
        if isinstance(flag, dict) and flag:
            blocked = bool(flag.get("blocked") or flag.get("denied"))
            if blocked:
                lines.append("KIRMIZI ÇİZGİ: on sekiz altı tespit edildi, görev durduruldu.")
            else:
                lines.append("Kırmızı çizgi denetimi kayıt altında.")
            sections.append("red_line")
            break

    if not lines:
        return "", []

    lines.append("Rapor sonu.")
    return " ".join(lines), sections


class ReportScriptCapability(BaseCapability):
    """Görev sonucunu **konuşulan** rapora çevirir (metin; sesi TTS üretir).

    Uydurma cümle YOK: payload'da olmayan hiçbir alan söylenmez, kırpılan
    metin `truncated` olarak işaretlenir.
    """

    id = "voice.report.script"
    kind = CapabilityKind.RENDERER
    license = "dahili (deterministik metin kurucu)"
    gates = frozenset({"vault"})
    timeout_seconds = 30.0
    description = "Görev sonucunu sesli okunabilir Türkçe rapora çevirir."

    def availability(self) -> Availability:
        # Harici bağımlılık yok: metin kurucu her zaman hazırdır.
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        params = ctx.params or {}
        report = params.get("report")
        raw_text = str(params.get("text") or "").strip()

        if raw_text:
            script, sections = raw_text, ["free_text"]
        elif isinstance(report, dict) and report:
            script, sections = build_report_script(report)
        else:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="empty_report"
            )

        if not script:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="empty_report"
            )

        truncated = len(script) > MAX_SCRIPT_CHARS
        if truncated:
            script = script[:MAX_SCRIPT_CHARS].rstrip() + "…"

        return CapabilityResult(
            capability_id=self.id,
            available=True,
            payload={
                "script": script,
                "sections": sections,
                "chars": len(script),
                "truncated": truncated,
            },
            items=(
                make_evidence(
                    content=script,
                    source_engine=self.id,
                    scope={
                        "kind": "spoken_report",
                        "sections": ",".join(sections),
                        "chars": len(script),
                        "truncated": truncated,
                    },
                ),
            ),
        )
