"""Etiket mutabakatı — tek model iddiası ölçüm DEĞİLDİR; iki BAĞIMSIZ model aynı
şeyi söylerse kanıt derecesi yükselir.

Neden bu modül var? ``frame_semantics`` tek geçişte etiket üretir ve onları
bilinçli olarak ``inference`` sayar; bu yüzden ``ritual.*`` sözlüğü hiç dolmaz.
Sözlüğün dolması için etiketin *güvenilir* hale gelmesi gerekir. Bu modül o
güveni ÖLÇEREK verir, ilan ederek değil:

    görünüm A (model M1) ─┐
                          ├─ aynı kare + aynı tür + aynı slug → CORROBORATED
    görünüm B (model M2) ─┘

Sert kurallar (hepsi testlidir):

    1. **Bağımsızlık model kimliğindedir.** İki geçiş aynı modele gittiyse bu
       bir TEKRARDIR, mutabakat değildir → ``independence_unverified``,
       terfi YOK. Aynı modelin iki kez aynı şeyi söylemesi yeni bilgi taşımaz.
    2. **Kimliği bilinmeyen model bağımsız sayılmaz.** ``model_id`` boş ya da
       ``unknown`` ise o görünüm sayılmaz; "bilmiyorum"u "bağımsız" okumak
       sessiz bir yalandır.
    3. **Farklı prompt sürümü karşılaştırılamaz** (``prompt_mismatch``): aynı
       soruyu sormadan aynı cevabı beklemek ölçüm değildir.
    4. **Tek görünüm terfi ettirmez.** ``min_views`` varsayılan 2.
    5. Sonuç ``observation``dır ama ``observation_grade="corroborated"``dur:
       araç ölçümü (``measured``) ile aynı kefeye konmaz, raporda ayrı sayılır.
    6. Deterministik kimlik: ``cl_<20 hex>``.

Tüketici: ``agent_core.task_executor`` (iki geçişli ``_analyze_frame_semantics``),
``agent_core.lifecycle.observation_adapter`` (sözlük kaynağı).
Test: ``tests/unit/test_frame_consensus.py``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

__all__ = [
    "CORROBORATED_GRADE",
    "MEASURED_GRADE",
    "MIN_CONSENSUS_VIEWS",
    "LabelView",
    "ConsensusResult",
    "build_consensus",
    "UNKNOWN_MODEL",
]

#: Araç ölçümü (tier-1 sayısal özellikler).
MEASURED_GRADE = "measured"
#: İki bağımsız modelin mutabakatı — ölçüm değil, GÜÇLENDİRİLMİŞ çıkarım.
CORROBORATED_GRADE = "corroborated"

MIN_CONSENSUS_VIEWS = 2
#: Model kimliği çözülemediğinde yazılan yer tutucu; bağımsızlık SAYILMAZ.
UNKNOWN_MODEL = "unknown"

_UNKNOWN_MODEL_VALUES = frozenset({"", "unknown", "none", "null", "n/a"})


@dataclass(frozen=True)
class LabelView:
    """Tek bir model geçişinin etiketleri (bağımsızlık birimi)."""

    view_id: str
    model_id: str
    prompt_version: str
    labels: tuple[Mapping[str, Any], ...] = ()

    def normalised_model(self) -> str:
        model = str(self.model_id or "").strip()
        return UNKNOWN_MODEL if model.lower() in _UNKNOWN_MODEL_VALUES else model

    def is_independent_source(self) -> bool:
        return self.normalised_model() != UNKNOWN_MODEL


@dataclass
class ConsensusResult:
    """Mutabakat defteri: ne terfi etti, ne reddedildi, neden."""

    corroborated: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "corroborated_labels": self.corroborated,
            "problems": list(self.rejected),
            "diagnostics": dict(self.diagnostics),
        }


def _corroboration_id(frame_id: str, kind: str, slug: str) -> str:
    key = f"consensus-v1|{frame_id}|{kind}|{slug}"
    return "cl_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def build_consensus(
    views: Sequence[LabelView],
    *,
    min_views: int = MIN_CONSENSUS_VIEWS,
) -> ConsensusResult:
    """Görünümleri karşılaştırır; yalnız BAĞIMSIZ mutabakatı terfi ettirir.

    Hata fırlatmaz: eksik/bozuk görünüm reddedilir ve gerekçesi yazılır.
    """
    result = ConsensusResult(
        diagnostics={
            "view_count": 0,
            "independent_view_count": 0,
            "distinct_model_count": 0,
            "corroborated_count": 0,
            "inference_only_count": 0,
            "min_views": int(min_views),
            "grade": CORROBORATED_GRADE,
        }
    )
    if not isinstance(views, (list, tuple)) or not views:
        result.rejected.append("no_views")
        return result

    usable: list[LabelView] = []
    for index, view in enumerate(views):
        if not isinstance(view, LabelView):
            result.rejected.append(f"view_not_label_view[{index}]")
            continue
        usable.append(view)

    result.diagnostics["view_count"] = len(usable)
    independent = [view for view in usable if view.is_independent_source()]
    result.diagnostics["independent_view_count"] = len(independent)
    models = sorted({view.normalised_model() for view in independent})
    result.diagnostics["distinct_model_count"] = len(models)

    for view in usable:
        if not view.is_independent_source():
            result.rejected.append(f"independence_unverified:{view.view_id}:{UNKNOWN_MODEL}")

    if len(independent) < max(2, min_views):
        result.rejected.append(
            f"insufficient_independent_views: {len(independent)} < {max(2, min_views)}"
        )
    if len(models) < max(2, min_views):
        # Aynı model iki kez: tekrar var, bağımsızlık yok.
        result.rejected.append(f"same_model_repeat: {','.join(models) or UNKNOWN_MODEL}")

    # (frame, kind, slug) → görünümler
    by_label: dict[tuple[str, str, str], list[tuple[LabelView, Mapping[str, Any]]]] = {}
    for view in independent:
        for row in view.labels:
            if not isinstance(row, Mapping):
                result.rejected.append(f"label_not_mapping:{view.view_id}")
                continue
            frame_id = str(row.get("frame_id") or "").strip()
            kind = str(row.get("kind") or "").strip().lower()
            slug = str(row.get("label_slug") or "").strip()
            if not frame_id or not kind or not slug:
                result.rejected.append(f"label_incomplete:{view.view_id}")
                continue
            by_label.setdefault((frame_id, kind, slug), []).append((view, row))

    seen_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    for (frame_id, kind, slug), entries in sorted(by_label.items()):
        agreeing: list[tuple[LabelView, Mapping[str, Any]]] = []
        seen_models: set[str] = set()
        for view, row in entries:
            model = view.normalised_model()
            if model in seen_models:
                continue  # aynı model iki kez sayılmaz
            seen_models.add(model)
            agreeing.append((view, row))

        if len(agreeing) < max(2, min_views):
            result.diagnostics["inference_only_count"] += 1
            continue

        versions = {view.prompt_version for view, _ in agreeing}
        if len(versions) > 1:
            # Farklı soruya verilmiş cevaplar karşılaştırılamaz.
            result.rejected.append(f"prompt_mismatch:{frame_id}:{slug}:{','.join(sorted(versions))}")
            result.diagnostics["inference_only_count"] += 1
            continue

        label = str(agreeing[0][1].get("label") or slug)
        observed_at = str(agreeing[0][1].get("observed_at") or "")
        corroboration_id = _corroboration_id(frame_id, kind, slug)
        if corroboration_id in seen_ids:  # pragma: no cover - savunma
            continue
        seen_ids.add(corroboration_id)
        rows.append(
            {
                "corroboration_id": corroboration_id,
                "frame_id": frame_id,
                "observed_at": observed_at,
                "label": label,
                "label_slug": slug,
                "kind": kind,
                "epistemic_type": "observation",
                "observation_grade": CORROBORATED_GRADE,
                "agreement_count": len(agreeing),
                "models": sorted(view.normalised_model() for view, _ in agreeing),
                "views": sorted(view.view_id for view, _ in agreeing),
                "prompt_version": sorted(versions)[0],
                "counts_toward_cluster": True,
            }
        )

    rows.sort(key=lambda row: (row["observed_at"], row["frame_id"], row["kind"], row["label_slug"]))
    result.corroborated = rows
    result.diagnostics["corroborated_count"] = len(rows)
    if not rows:
        result.rejected.append("no_corroborated_label")
    return result


def labels_by_frame(
    corroborated: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, list[str]]]:
    """``corroborated`` satırlarını kare başına ``{objects, places}``e indirger.

    Adaptörün sözlük kaynağı budur: ölçüm (``detected_objects``) ile
    güçlendirilmiş etiket ayrı tutulur, karıştırılmaz.
    """
    grouped: dict[str, dict[str, list[str]]] = {}
    for row in corroborated or ():
        if not isinstance(row, Mapping):
            continue
        frame_id = str(row.get("frame_id") or "")
        kind = str(row.get("kind") or "")
        label = str(row.get("label") or "")
        if not frame_id or not label or kind not in ("object", "place"):
            continue
        bucket = grouped.setdefault(frame_id, {"objects": [], "places": []})
        key = "objects" if kind == "object" else "places"
        if label not in bucket[key]:
            bucket[key].append(label)
    for bucket in grouped.values():
        bucket["objects"].sort()
        bucket["places"].sort()
    return grouped


def model_id_or_unknown(model: Optional[str]) -> str:
    """Model kimliğini normalize eder; bilinmiyorsa ``unknown`` (bağımsız DEĞİL)."""
    text = str(model or "").strip()
    return UNKNOWN_MODEL if text.lower() in _UNKNOWN_MODEL_VALUES else text
