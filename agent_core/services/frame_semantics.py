"""İkinci kademe: KARE SEMANTİĞİ — çıkarım üretir, ÖLÇÜM üretmez.

Neden ayrı bir modül? Birinci kademe (``frame_evidence``) yalnız ölçülebilir
sayılar üretir: parlaklık, kontrast, kenar yoğunluğu. "Bu karede ne var?"
sorusunun cevabı ise bir modelin **iddiasıdır**. İkisini aynı kaba koymak,
modelin cümlesini ölçüm gibi raporlamak olurdu.

Bu modülün tek işi o iddiaları *çıkarım* olarak, kaynağı ve sınırı yazılı
biçimde kaydetmek:

    ölçülmüş kare (tier-1)  →  DEĞİŞİM NOKTASI seçimi  →  model (LLM)
                                                          ↓
                                        SemanticInference[epistemic_type="inference"]

Sert kurallar (hepsi testlidir):

    1. **Yalnız değişim noktaları analiz edilir.** Her kareyi modele göndermek
       maliyet duvarıdır; üstelik zaman çizgisinin düz kısmı hakkında üretilen
       etiket yeni bilgi taşımaz.
    2. **Etiket ölçüm alanına YAZILMAZ.** ``detected_objects`` /
       ``environment_and_places`` ölçüm alanlarıdır; buradan ``ritual.*``
       sinyali doğar. Model etiketi oraya yazılsaydı, halüsinasyon "ritüel
       kayboldu" iddiasına dönüşürdü. Bu yüzden çıkarımlar ayrı bir defterde
       yaşar ve ``counts_toward_cluster`` DAİMA ``False``dur.
    3. **Yorum etiketi reddedilir.** "depresif", "yalnız", "kaygılı" gibi
       kökler taşıyan etiketler kayda geçmez (``rejected_interpretation``).
       Sistem teşhis koymaz; etiketleri de koydurtmaz.
    4. **Model yoksa etiket yok.** Çağrı hatası/bozuk JSON → kayıt ÜRETİLMEZ,
       sebep ``problems`` altında. Boş sonuç "temiz kare" sayılmaz.
    5. **Deterministik kimlik**: ``si_<20 hex>`` yalnız (sürüm, kare, tür,
       etiket)ten türetilir; aynı girdi aynı kimliği verir.

Tüketici: ``agent_core.task_executor`` (``_analyze_frame_semantics``) ve rapor
(``LifeRuptureReport.semantic_inferences``).
Test: ``tests/unit/test_frame_semantics.py``.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Optional, Sequence

__all__ = [
    "DEFAULT_MAX_INFERENCE_FRAMES",
    "DEFAULT_SEMANTIC_BUDGET_SECONDS",
    "EPISTEMIC_TYPE",
    "FRAME_SEMANTIC_PROMPT",
    "FRAME_SEMANTIC_PROMPT_VERSION",
    "LABEL_KINDS",
    "SemanticCollection",
    "SemanticInference",
    "collect_semantic_inferences",
    "select_inference_frames",
    "slug_label",
]

#: Bu modülün ürettiği tek epistemik tür. "observation" YAZMAZ.
EPISTEMIC_TYPE = "inference"

#: Kabul edilen etiket türleri. Aktivite/duygu türü YOK: bunlar ölçüm değil.
LABEL_KINDS = ("object", "place")

FRAME_SEMANTIC_PROMPT_VERSION = "frame-semantics-v1"

DEFAULT_MAX_INFERENCE_FRAMES = 4
DEFAULT_SEMANTIC_BUDGET_SECONDS = 60.0
DEFAULT_SEMANTIC_CONCURRENCY = 2
MAX_LABELS_PER_FRAME = 12
MAX_LABEL_CHARS = 64

#: Model'den istenen sözleşme. Örnek nesne listesi VERİLMEZ: örnek liste,
#: kişiye/olaya bağlı bir "aranan şeyler" listesine dönüşür.
FRAME_SEMANTIC_PROMPT = """Tek bir sosyal medya görseli veriliyor.
Görevin: YALNIZ fotoğrafta fiilen görünen somut nesneleri ve mekânları yazmak.

Yasak:
- Duygu, ruh hali, kişilik veya psikolojik çıkarım YAZMA.
- Görünmeyen şeyi tahmin etme. Emin değilsen yazma.
- Genel sıfat/tarz anlatımı yazma ("güzel", "karanlık atmosfer").

Yanıtı TAM olarak şu JSON ile ver:
{"labels": [{"label": "<kısa somut ad>", "kind": "object"}]}
`kind` yalnız `object` ya da `place` olabilir. Görünen bir şey yoksa:
{"labels": []}
"""

AskFn = Callable[[Mapping[str, Any], str], Awaitable[Any]]

_NUMERIC_RE = re.compile(r"^[\d\s.,;:%]+$")
_SLUG_RE = re.compile(r"[^\w]+", re.UNICODE)


def slug_label(raw: Any) -> str:
    """Etiketi karşılaştırılabilir anahtara çevirir (kişiye özel liste YOK)."""
    if not isinstance(raw, str):
        return ""
    lowered = raw.strip().lower()
    if not lowered:
        return ""
    return _SLUG_RE.sub("_", lowered).strip("_")


def _forbidden_roots() -> tuple[str, ...]:
    """Yorum kökleri tek kaynaktan gelir (rapordaki yasak listesi)."""
    from agent_core.lifecycle.pipeline import FORBIDDEN_INTERPRETATION_ROOTS

    return FORBIDDEN_INTERPRETATION_ROOTS


@dataclass(frozen=True)
class SemanticInference:
    """Tek bir model iddiası — ÖLÇÜM DEĞİL, çıkarım."""

    inference_id: str
    frame_id: str
    observed_at: str
    label: str
    label_slug: str
    kind: str
    method: str = "vision_llm"
    prompt_version: str = FRAME_SEMANTIC_PROMPT_VERSION
    epistemic_type: str = EPISTEMIC_TYPE
    counts_toward_cluster: bool = False
    source_sha256: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "inference_id": self.inference_id,
            "frame_id": self.frame_id,
            "observed_at": self.observed_at,
            "label": self.label,
            "label_slug": self.label_slug,
            "kind": self.kind,
            "method": self.method,
            "prompt_version": self.prompt_version,
            # Bu iki alan sözleşmedir: çıkarım asla ölçüm/küme kanıtı sayılmaz.
            "epistemic_type": self.epistemic_type,
            "counts_toward_cluster": self.counts_toward_cluster,
            "source_sha256": self.source_sha256,
        }


@dataclass
class SemanticCollection:
    """Çıkarım defteri + ne yapılamadığının kaydı."""

    inferences: list[dict[str, Any]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_inferences": self.inferences,
            "problems": self.problems,
            "diagnostics": self.diagnostics,
        }


def _inference_id(frame_id: str, kind: str, slug: str) -> str:
    key = f"{FRAME_SEMANTIC_PROMPT_VERSION}|{frame_id}|{kind}|{slug}"
    return "si_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def select_inference_frames(
    frames: Sequence[Mapping[str, Any]],
    *,
    change_point_ids: Optional[Sequence[str]] = None,
    max_frames: int = DEFAULT_MAX_INFERENCE_FRAMES,
) -> tuple[list[Mapping[str, Any]], list[str]]:
    """Modele gidecek kareleri seçer: YALNIZ değişim noktaları.

    Değişim noktası listesi verilmezse hiçbir kare seçilmez (``change_points_missing``):
    "hangi kareye bakılacağını" ucuza karar vermek bu kademenin varlık sebebidir.
    Tavan aşılırsa ilk/son korunur, aradan eşit aralıkla seçilir (deterministik).
    """
    problems: list[str] = []
    if not isinstance(frames, (list, tuple)):
        return [], ["frames_not_list"]
    by_id = {
        str(frame.get("frame_id")): frame
        for frame in frames
        if isinstance(frame, Mapping) and frame.get("frame_id")
    }
    if not by_id:
        return [], ["no_frames"]

    if not change_point_ids:
        return [], ["change_points_missing"]

    ordered: list[Mapping[str, Any]] = []
    for frame_id in change_point_ids:
        frame = by_id.get(str(frame_id))
        if frame is not None and frame not in ordered:
            ordered.append(frame)
    if not ordered:
        return [], ["change_points_unmatched"]

    ordered.sort(key=lambda frame: (str(frame.get("observed_at")), str(frame.get("frame_id"))))
    if max_frames <= 0:
        return [], ["inference_budget_zero"]
    if len(ordered) > max_frames:
        if max_frames == 1:
            chosen = [ordered[0]]
        else:
            step = (len(ordered) - 1) / (max_frames - 1)
            indices = sorted({int(round(index * step)) for index in range(max_frames)})
            chosen = [ordered[index] for index in indices]
        problems.append(f"inference_budget_applied: {max_frames}")
        ordered = chosen
    return ordered, problems


def _parse_labels(payload: Any) -> tuple[list[tuple[str, str]], list[str]]:
    """Modelin cevabını katı biçimde ayrıştırır. Uydurma YOK.

    Dönen: (kabul edilen (etiket, tür) çiftleri, ret sebepleri).
    """
    if not isinstance(payload, Mapping):
        return [], ["payload_not_mapping"]
    raw_labels = payload.get("labels")
    if raw_labels is None:
        return [], ["labels_missing"]
    if not isinstance(raw_labels, (list, tuple)):
        return [], ["labels_not_list"]

    accepted: list[tuple[str, str]] = []
    rejected: list[str] = []
    roots = _forbidden_roots()

    for index, item in enumerate(raw_labels):
        if not isinstance(item, Mapping):
            rejected.append(f"label_not_mapping[{index}]")
            continue
        label = item.get("label")
        if not isinstance(label, str) or not label.strip():
            rejected.append(f"label_empty[{index}]")
            continue
        label = label.strip()
        if len(label) > MAX_LABEL_CHARS:
            rejected.append(f"label_too_long[{index}]")
            continue
        if _NUMERIC_RE.match(label):
            rejected.append(f"label_numeric[{index}]")
            continue
        lowered = label.lower()
        hit = next((root for root in roots if root in lowered), None)
        if hit is not None:
            # Teşhis sızmaz: etiket de cümle gibi denetlenir.
            rejected.append(f"rejected_interpretation[{index}]:{hit}")
            continue
        kind = str(item.get("kind") or "").strip().lower()
        if kind not in LABEL_KINDS:
            rejected.append(f"kind_not_allowed[{index}]:{kind or 'empty'}")
            continue
        slug = slug_label(label)
        if not slug:
            rejected.append(f"label_unusable[{index}]")
            continue
        accepted.append((label, kind))

    if len(accepted) > MAX_LABELS_PER_FRAME:
        rejected.append(f"label_budget_applied: {MAX_LABELS_PER_FRAME}")
        accepted = accepted[:MAX_LABELS_PER_FRAME]
    return accepted, rejected


async def _one_frame(
    frame: Mapping[str, Any],
    ask: AskFn,
    collection: SemanticCollection,
) -> list[dict[str, Any]]:
    frame_id = str(frame.get("frame_id"))
    prompt = FRAME_SEMANTIC_PROMPT
    try:
        payload = await ask(frame, prompt)
    except Exception as error:  # noqa: BLE001 — fail-closed, kare atlanır
        collection.problems.append(f"semantic_call_failed:{frame_id}:{type(error).__name__}")
        return []
    if isinstance(payload, Mapping) and payload.get("status") == "failed":
        reason = payload.get("reason") or "unknown"
        collection.problems.append(f"semantic_call_failed:{frame_id}:{reason}")
        return []

    accepted, rejected = _parse_labels(payload)
    for reason in rejected:
        collection.problems.append(f"semantic_label_rejected:{frame_id}:{reason}")
    collection.diagnostics["rejected_label_count"] += len(rejected)
    if not accepted:
        # Boş cevap "temiz kare" DEĞİLDİR: ne ölçüldü ne de yokluk kaydedildi.
        collection.problems.append(f"semantic_empty:{frame_id}")
        return []

    observed_at = str(frame.get("observed_at") or "")
    sha = frame.get("source_sha256") if isinstance(frame.get("source_sha256"), str) else None
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for label, kind in accepted:
        slug = slug_label(label)
        key = f"{kind}|{slug}"
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            SemanticInference(
                inference_id=_inference_id(frame_id, kind, slug),
                frame_id=frame_id,
                observed_at=observed_at,
                label=label,
                label_slug=slug,
                kind=kind,
                source_sha256=sha,
            ).to_dict()
        )
    collection.diagnostics["analyzed_frame_count"] += 1
    return rows


async def collect_semantic_inferences(
    frames: Sequence[Mapping[str, Any]],
    *,
    ask: AskFn,
    change_point_ids: Optional[Sequence[str]] = None,
    max_frames: int = DEFAULT_MAX_INFERENCE_FRAMES,
    budget_seconds: float = DEFAULT_SEMANTIC_BUDGET_SECONDS,
    concurrency: int = DEFAULT_SEMANTIC_CONCURRENCY,
) -> SemanticCollection:
    """Değişim noktalarındaki kareler için model iddialarını toplar.

    Hata fırlatmaz. Model yoksa ``inferences`` boş kalır ve sebep yazılır —
    "etiket yok" ile "bakılmadı" ayrımı ``problems``/``diagnostics``ten okunur.
    """
    collection = SemanticCollection(
        diagnostics={
            "prompt_version": FRAME_SEMANTIC_PROMPT_VERSION,
            "candidate_frame_count": 0,
            "analyzed_frame_count": 0,
            "inference_count": 0,
            "rejected_label_count": 0,
            "budget_exceeded": False,
            "epistemic_type": EPISTEMIC_TYPE,
            "counts_toward_cluster": False,
        }
    )

    selected, problems = select_inference_frames(
        frames, change_point_ids=change_point_ids, max_frames=max_frames
    )
    collection.problems.extend(problems)
    collection.diagnostics["candidate_frame_count"] = len(selected)
    if not selected:
        return collection

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _guarded(frame: Mapping[str, Any]) -> list[dict[str, Any]]:
        async with semaphore:
            return await _one_frame(frame, ask, collection)

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(_guarded(frame) for frame in selected), return_exceptions=True),
            timeout=max(1.0, budget_seconds),
        )
    except asyncio.TimeoutError:
        collection.diagnostics["budget_exceeded"] = True
        collection.problems.append("semantic_budget_exceeded")
        results = []

    merged: dict[str, dict[str, Any]] = {}
    for frame, item in zip(selected, results, strict=False):
        if isinstance(item, BaseException):
            collection.problems.append(
                f"semantic_task_error:{frame.get('frame_id')}:{type(item).__name__}"
            )
            continue
        for row in item:
            merged.setdefault(row["inference_id"], row)

    collection.inferences = sorted(
        merged.values(), key=lambda row: (row["observed_at"], row["frame_id"], row["kind"], row["label_slug"])
    )
    collection.diagnostics["inference_count"] = len(collection.inferences)
    if not collection.inferences:
        collection.problems.append("no_semantic_inference")
    return collection
