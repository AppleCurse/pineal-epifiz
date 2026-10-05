"""Capability Spine — tek sözleşme katmanı (Faz 0).

Bu modül, Pineal'e giren HER yeteneğin (kendi kodumuz veya harici bir
depodan gelen adaptör) uymak zorunda olduğu sözleşmeyi tanımlar.

Neden var?
    Yıldız depo karar ağacı (``docs/reports/YILDIZ_DEPO_KARAR_AGACI_2026-10-05.md``)
    hükmü: bir yetenek ancak tek sözleşmeye, tek kanıt zincirine, tek
    telemetriye ve tek güvenlik çekirdeğine bağlanıyorsa ürüne girer.
    Aksi halde ortaya çıkan şey entegrasyon değil yamalı bohçadır.

Sözleşmenin değişmezleri:
    1. Kanıtsız çıktı yok — bir yetenek ``EvidenceItem`` üretemiyorsa sonucu
       rapora yazılamaz (kanıt mührü, fail-closed).
    2. Sessiz başarısızlık yok — bağımlılık/anahtar/kapı yoksa
       ``available=False`` + makine-okunur sebep; asla uydurma içerik.
    3. İkinci kaynak yok — "yetenek var mı?" sorusunun tek cevabı
       ``CapabilityRegistry``'dir (kural [009] duplication dersi).

Bu dosya bilinçli olarak HARİCİ BAĞIMLILIK İÇERMEZ (Faz 0 = yeni paket yok).
"""

from __future__ import annotations

import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from agent_core.domain.evidence_models import EvidenceItem
from agent_core.domain.pillar_models import EvidenceStatus

__all__ = [
    "CapabilityKind",
    "Availability",
    "CapabilityContext",
    "CapabilityResult",
    "Capability",
    "BaseCapability",
    "new_evidence_id",
    "make_evidence",
]


class CapabilityKind(str, Enum):
    """Yetenek sınıfları — registry ve telemetri bu ayrımı kullanır."""

    SENSOR = "sensor"        # dış dünyadan veri getirir (IG/X/web/telefon…)
    EXTRACTOR = "extractor"  # ham veriden yapılandırılmış kanıt çıkarır (OCR/ASR/dil…)
    ANALYZER = "analyzer"    # kanıt üzerinde deterministik veya LLM analizi
    VERIFIER = "verifier"    # iddiayı çapraz doğrular (tersine görsel, jüri…)
    MEMORY = "memory"        # kalıcı/geçmiş veri (zaman serisi, graf, kalibrasyon)
    RENDERER = "renderer"    # rapor/görsel ihracatı
    TOOL = "tool"            # MCP / skill köprüsü (kum havuzu)


def new_evidence_id() -> str:
    """Kanıt kimliği üretir: ``ev_`` + 20 hex (``evidence_models`` şeması)."""
    return f"ev_{secrets.token_hex(10)}"


def make_evidence(
    *,
    content: str,
    source_engine: str,
    epistemic_type: str = "observation",
    provenance_refs: list[str] | None = None,
    observed_at: datetime | None = None,
    source_status: EvidenceStatus | None = EvidenceStatus.OBSERVED,
    scope: dict[str, Any] | None = None,
    source_metrics: dict[str, Any] | None = None,
    confidence: float | None = None,
) -> EvidenceItem:
    """Doğrulanmış tek bir kanıt kaydı üretir (fail-closed).

    Boş içerik veya boş kaynak adı kabul edilmez: kanıt mührü gereği
    "içeriği olmayan kanıt" diye bir şey yoktur; çağıran dürüst hata alır.
    """
    text = (content or "").strip()
    engine = (source_engine or "").strip()
    if not text:
        raise ValueError("make_evidence: content boş olamaz (kanıt mührü)")
    if not engine:
        raise ValueError("make_evidence: source_engine boş olamaz (kanıt mührü)")
    if epistemic_type not in {"observation", "absence", "inference", "strategy"}:
        raise ValueError(f"make_evidence: geçersiz epistemic_type={epistemic_type!r}")
    return EvidenceItem(
        evidence_id=new_evidence_id(),
        epistemic_type=epistemic_type,  # type: ignore[arg-type]
        source_engine=engine,
        source_status=source_status,
        content=text,
        provenance_refs=list(provenance_refs or []),
        scope=scope,
        observed_at=observed_at or datetime.now(timezone.utc),
        confidence=confidence,
        source_metrics=source_metrics,
    )


@dataclass(frozen=True)
class Availability:
    """Bir yeteneğin şu anda çalışıp çalışamayacağının dürüst cevabı."""

    available: bool
    reason: str | None = None

    @classmethod
    def ok(cls) -> "Availability":
        return cls(available=True, reason=None)

    @classmethod
    def unavailable(cls, reason: str) -> "Availability":
        return cls(available=False, reason=reason)


@dataclass
class CapabilityContext:
    """Yetenek koşusu için bağlam (tek giriş noktası)."""

    subject: str = ""                       # hedef: kullanıcı adı / e-posta / URL
    task_id: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float | None = None    # None ise yeteneğin kendi varsayılanı
    budget_usd: float | None = None
    emit: Callable[[dict[str, Any]], None] | None = None  # telemetri köprüsü (opsiyonel)


@dataclass
class CapabilityResult:
    """Yetenek çıktısı — rapora giden TEK yol budur."""

    capability_id: str
    available: bool
    unavailable_reason: str | None = None
    items: tuple[EvidenceItem, ...] = ()
    payload: Any | None = None      # geçiş dönemi: eski tarayıcı sonuç modeli
    notes: dict[str, Any] = field(default_factory=dict)
    error: str | None = None        # koşu hatası (kanıt ÜRETİLMEZ)
    denied_by: str | None = None    # PolicyKernel'in reddettiği kapı
    duration_ms: int = 0
    cost_usd: float = 0.0

    @property
    def ok(self) -> bool:
        """Kanıt üretildi mi? (uygunluk + hata yokluğu + en az bir kanıt)"""
        return self.available and self.error is None and bool(self.items)

    def to_dict(self) -> dict[str, Any]:
        """Telemetri/UI için sade sözlük (kanıtlar ayrı taşınır)."""
        return {
            "capability_id": self.capability_id,
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "denied_by": self.denied_by,
            "error": self.error,
            "evidence_count": len(self.items),
            "evidence_ids": [i.evidence_id for i in self.items],
            "notes": dict(self.notes),
            "duration_ms": self.duration_ms,
            "cost_usd": self.cost_usd,
        }


@runtime_checkable
class Capability(Protocol):
    """Yetenek sözleşmesi (protocol — duck-typing yeterli)."""

    id: str
    kind: CapabilityKind
    license: str
    gates: frozenset[str]

    def availability(self) -> Availability: ...

    def run(self, ctx: CapabilityContext) -> Awaitable[CapabilityResult]: ...


class BaseCapability(ABC):
    """Adaptörler için taban sınıf.

    Alt sınıflar ``id``, ``kind``, ``license``, ``gates`` alanlarını ve
    ``availability`` / ``run`` metodlarını sağlar. ``id`` noktalı küçük harf
    sözdiziminde olmalıdır (``sensor.x.twscrape`` gibi); registry bunu doğrular.
    """

    id: str = ""
    kind: CapabilityKind = CapabilityKind.SENSOR
    license: str = "unknown"
    gates: frozenset[str] = frozenset()
    timeout_seconds: float = 30.0
    description: str = ""

    @abstractmethod
    def availability(self) -> Availability:
        """Yetenek şu an kullanılabilir mi? (asla istisna fırlatmaz)"""

    @abstractmethod
    async def run(self, ctx: CapabilityContext) -> CapabilityResult:
        """Yeteneği koşar ve kanıt üretir (yoksa dürüst unavailable döner)."""

    def __repr__(self) -> str:  # pragma: no cover - hata ayıklama
        return f"<{type(self).__name__} id={self.id!r} kind={self.kind.value}>"
