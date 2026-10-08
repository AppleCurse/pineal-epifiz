"""FAZ D · D4 — DİL yetenekleri omurgada: tespit + yerel çeviri.

İki yetenek, tek sözleşme:
    ``extractor.text.language``        — deterministik dil tespiti (modelsiz,
                                         ağsız; ``services/language``).
    ``extractor.text.translate_local`` — yerel çeviri (ses/dinleme kuralı:
                                         yalnız localhost ucu veya yerel CLI;
                                         uzak uç REDDEDİLİR).

Kasa invariant'ı (Tüzük Md.4): her iki yetenek de ``vault`` kapısına bağlıdır;
kasa kilitliyken koşamazlar. Tespit saf hesap olsa bile istisna YOKTUR —
omurgadaki her yetenek aynı mandaldan geçer.

Dürüstlük: sinyal yoksa etiket UYDURULMAZ (``unknown`` + sebep); motor yoksa
çeviri ÜRETİLMEZ. Bilinmeyen durum kanıt olarak da YAZILMAZ — kanıt, ölçülmüş
bir tespittir; "ölçemedim" sonucu kanıt zincirine gürültü olarak eklenmez,
``notes`` içinde makine-okunur kalır.
"""

from __future__ import annotations

from agent_core.capabilities.adapters_osint import _flag
from agent_core.capabilities.base import (
    Availability,
    BaseCapability,
    CapabilityContext,
    CapabilityKind,
    CapabilityResult,
    make_evidence,
)
from agent_core.services.language import SUPPORTED_LANGUAGES, detect_language

__all__ = ["LanguageDetectCapability", "LocalTranslateCapability"]

#: Kanıt içeriğine giren tespit cümlesinin tavanı (kanıt zinciri şişmesin).
_MAX_EVIDENCE_CHARS = 500


class LanguageDetectCapability(BaseCapability):
    """Metnin dilini ölçer: Unicode yazı sistemi + durma sözcükleri (saf yerel)."""

    id = "extractor.text.language"
    kind = CapabilityKind.EXTRACTOR
    license = "yerel/deterministik (kod içi, harici bağımlılık yok)"
    # [D4] Tüzük Md.4: kasa mandalı istisnasızdır — tespit de kapıdan geçer.
    gates = frozenset({"vault"})
    timeout_seconds = 5.0
    description = (
        "Metnin dilini deterministik ölçer (tr/en/de/es/fr/ru/az); "
        "model ve ağ yok, sinyal yoksa etiket uydurmaz."
    )

    def availability(self) -> Availability:
        return Availability.ok()  # saf hesap: bağımlılık yoktur

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        text = (ctx.subject or ctx.params.get("text") or "").strip()
        if not text:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="empty_text"
            )

        finding = detect_language(text)
        notes = {
            "language": finding.language,
            "confidence": finding.confidence,
            "script": finding.script,
            "reason": finding.reason,
            "chars": finding.chars,
        }

        if finding.language == "unknown" or finding.language not in SUPPORTED_LANGUAGES:
            # Sinyal yok → etiket YOK: kanıt üretilmez, sebep gizlenmez.
            return CapabilityResult(
                capability_id=self.id, available=True, items=(), payload=finding, notes=notes
            )

        item = make_evidence(
            content=(
                f"text language detected as {finding.language} "
                f"(confidence {finding.confidence:.2f}, script {finding.script})"
            ),
            source_engine="language_detect",
            epistemic_type="observation",
            scope={
                "kind": "language",
                "language": finding.language,
                "confidence": finding.confidence,
                "script": finding.script,
            },
            source_metrics={"chars": finding.chars, "signals": finding.signals},
            confidence=finding.confidence,
        )
        return CapabilityResult(
            capability_id=self.id, available=True, items=(item,), payload=finding, notes=notes
        )


class LocalTranslateCapability(BaseCapability):
    """Yerel çeviri: localhost ucu veya yerel CLI — metin makineden çıkmaz."""

    id = "extractor.text.translate_local"
    kind = CapabilityKind.EXTRACTOR
    license = "harici süreç/yerel uç (kod gömülmez)"
    gates = frozenset({"vault", "ENABLE_LOCAL_TRANSLATE"})
    timeout_seconds = 35.0
    description = "Metni yerel motorda çevirir (uzak uç reddedilir, uydurma çeviri yok)."

    def availability(self) -> Availability:
        from agent_core.services.translation import GATE, resolve_engine

        if not _flag(GATE):
            return Availability.unavailable(f"gate_disabled:{GATE}")
        engine, reason = resolve_engine()
        if not engine:
            return Availability.unavailable(reason)
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        from agent_core.services import translation

        text = (ctx.subject or ctx.params.get("text") or "").strip()
        target = str(ctx.params.get("target") or "en").strip()
        if not text:
            return CapabilityResult(
                capability_id=self.id, available=False, unavailable_reason="empty_text"
            )

        result = await translation.translate_text(text, target)
        notes = {
            "engine": result.engine,
            "source_language": result.source_language,
            "source_confidence": result.source_confidence,
            "target_language": result.target_language,
            "chars": result.chars,
        }
        if not result.available:
            return CapabilityResult(
                capability_id=self.id,
                available=False,
                unavailable_reason=result.reason or "translation_unavailable",
                notes=notes,
            )

        item = make_evidence(
            content=result.text[:_MAX_EVIDENCE_CHARS * 4],
            source_engine=f"translate_{result.engine}",
            epistemic_type="observation",
            scope={
                "kind": "translation",
                "source_language": result.source_language,
                "target_language": result.target_language,
                "engine": result.engine,
                "source_chars": result.chars,
            },
            source_metrics={
                "translated_chars": len(result.text),
                "source_confidence": result.source_confidence,
            },
        )
        return CapabilityResult(
            capability_id=self.id,
            available=True,
            items=(item,),
            payload=result,
            notes=notes,
        )
