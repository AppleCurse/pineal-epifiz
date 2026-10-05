"""FAZ B · B5 — EŞİK KALİBRASYONU (ölçülmemiş 0.70 biter).

Röntgen bulgusu: sistemin en kritik eşiği ``0.70`` (alıntı doğrulama kapısı ve
güven skoru) KODUN İÇİNE SABİTLENMİŞTİ; hiç ölçülmemişti. "Kalibrasyon" da
yoktu: eşiği değiştiren bir veri, bir aralık, bir geri test hiç olmadı.

Bu modül o eşiği ÖLÇÜLEN bir değere çevirir:

1.  **Kayıt (ledger):** her eşik kararı, kararın verildiği SKOR ile birlikte
    eklemeli bir dosyaya yazılır (``memory/calibration/observations.jsonl``).
    Ham metin yazılmaz — yalnız ölçü ve kimlik.
2.  **Etiket (adjudication):** bir kararın doğru olup olmadığına OPERATÖR karar
    verir (karar mercii bellidir). Etiketsiz satır istatistiğe girmez.
3.  **Kalibrasyon:** etiketli örneklerden eşik SEÇİLİR (Youden J = TPR − FPR),
    veri azken varsayılana çekilir (shrinkage), Wilson güven aralığı ve geri
    test tablosu birlikte döner.
4.  **Kilit:** etiketli örnek sayısı ``PINEAL_CALIB_MIN_SAMPLES`` altındaysa
    eşik DEĞİŞMEZ; kaynak ``varsayılan`` olarak raporlanır. Yani kalibrasyon
    verisi olmadan eşik değiştirilemez.

LLM çağrısı yok, ağ yok, rastgelelik yok: aynı kayıt -> aynı eşik.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

#: Sistemin bugünkü sabiti. Kalibrasyon verisi yokken bu değer geçerlidir.
DEFAULT_THRESHOLD = 0.70

#: Kapsamlar: eşik her kapsam için AYRI ölçülür (alıntı kapısı ayrı, güven ayrı).
SCOPE_QUOTE = "quote"
SCOPE_CONFIDENCE = "confidence"

DEFAULT_MIN_SAMPLES = 30

#: Aday eşikler (ızgara). Skor 0..1 olduğu için 0.50-0.95 bandı taranır.
GRID: Tuple[float, ...] = tuple(round(0.50 + 0.01 * i, 2) for i in range(46))

_LOCK = threading.Lock()


# ------------------------------------------------------------------ yardımcılar
def _safe_float(value: Any, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(out) or math.isinf(out):
        return default
    return out


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def min_samples() -> int:
    """Kalibrasyonun eşiği DEĞİŞTİREBİLMESİ için gereken etiketli örnek sayısı."""
    raw = os.getenv("PINEAL_CALIB_MIN_SAMPLES", "")
    try:
        return max(2, int(str(raw).strip()))
    except (TypeError, ValueError):
        return DEFAULT_MIN_SAMPLES


def storage_dir() -> str:
    """Ledger dizini (``memory/`` altında tutulur, depoya girmez)."""
    return os.getenv("PINEAL_CALIB_DIR") or os.path.join("memory", "calibration")


def observe_enabled(scope: Optional[str] = None) -> bool:
    """Kararlar kaydedilsin mi? (varsayılan AÇIK: veri birikmesi gerekir)."""
    if scope:
        scoped = os.getenv(f"PINEAL_CALIB_OBSERVE_{str(scope).upper()}", "")
        if scoped.strip():
            return scoped.strip().lower() in {"1", "true", "yes", "on", "açık"}
    return os.getenv("PINEAL_CALIB_OBSERVE", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "açık",
    }


def env_override(scope: Optional[str] = None) -> Optional[float]:
    """Operatör eşiği ELLE sabitlediyse o değer (``PINEAL_THRESHOLD_QUOTE``)."""
    for key in ((f"PINEAL_THRESHOLD_{str(scope).upper()}",) if scope else ()) + ("PINEAL_THRESHOLD",):
        raw = os.getenv(key)
        if raw is None or not str(raw).strip():
            continue
        try:
            return _clamp(float(str(raw).strip()))
        except (TypeError, ValueError):
            continue
    return None


def _ledger_path(storage: Optional[str] = None, scope: Optional[str] = None) -> str:
    base = storage or storage_dir()
    if scope:
        return os.path.join(base, f"{scope}.jsonl")
    return os.path.join(base, "observations.jsonl")


# ---------------------------------------------------------------------- modeller
class Observation(BaseModel):
    """Tek bir eşik kararının kaydı (ham metin yok: yalnız ölçü + kimlik)."""

    observation_id: str
    recorded_at: float = 0.0
    scope: str = SCOPE_QUOTE
    task_id: str = ""
    claim_id: str = ""
    score: float = 0.0
    matched: bool = False
    #: Operatör kararı: True gerçek eşleşme, False uydurma, None etiketsiz.
    truth: Optional[bool] = None
    note: str = ""

    model_config = ConfigDict(extra="forbid")


class OperatingPoint(BaseModel):
    """Seçilen eşikte ölçülen başarım."""

    threshold: float = DEFAULT_THRESHOLD
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    model_config = ConfigDict(extra="forbid")


class ReliabilityBin(BaseModel):
    """Güvenilirlik diyagramı kovası: söylenen skor vs gözlenen isabet."""

    low: float = 0.0
    high: float = 1.0
    count: int = 0
    mean_score: float = 0.0
    accuracy: float = 0.0

    model_config = ConfigDict(extra="forbid")


class CalibrationReport(BaseModel):
    """Kalibrasyon sonucu: eşik + kanıt + dürüst ret sebebi."""

    scope: str = SCOPE_QUOTE
    samples: int = 0
    labeled: int = 0
    unlabeled: int = 0
    min_samples: int = DEFAULT_MIN_SAMPLES
    available: bool = False
    reason: str = ""
    default_threshold: float = DEFAULT_THRESHOLD
    measured_threshold: float = DEFAULT_THRESHOLD
    threshold: float = DEFAULT_THRESHOLD
    source: str = "varsayılan"
    shrinkage_weight: float = 0.0
    operating_point: OperatingPoint = Field(default_factory=OperatingPoint)
    confidence_interval: List[float] = Field(default_factory=list)
    reliability: List[ReliabilityBin] = Field(default_factory=list)
    expected_calibration_error: float = 0.0
    grid: List[OperatingPoint] = Field(default_factory=list)
    machine_note: str = ""

    model_config = ConfigDict(extra="forbid")


class ThresholdDecision(BaseModel):
    """Çalışma anında kullanılacak eşik + nereden geldiği."""

    value: float = DEFAULT_THRESHOLD
    source: str = "varsayılan"
    reason: str = ""
    report: Optional[CalibrationReport] = None

    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------------ ledger
def record(
    score: float,
    *,
    scope: str = SCOPE_QUOTE,
    matched: Optional[bool] = None,
    task_id: str = "",
    claim_id: str = "",
    truth: Optional[bool] = None,
    note: str = "",
    storage: Optional[str] = None,
    observation_id: Optional[str] = None,
) -> Optional[Observation]:
    """Bir eşik kararını ledger'a yazar. Pipeline'ı ASLA bozmaz (istisna yutar)."""
    if not observe_enabled(scope):
        return None
    value = _clamp(_safe_float(score, 0.0))
    obs = Observation(
        observation_id=observation_id or uuid.uuid4().hex[:16],
        recorded_at=time.time(),
        scope=str(scope or SCOPE_QUOTE),
        task_id=str(task_id or ""),
        claim_id=str(claim_id or ""),
        score=round(value, 6),
        matched=bool(value >= DEFAULT_THRESHOLD) if matched is None else bool(matched),
        truth=None if truth is None else bool(truth),
        note=str(note or "")[:200],
    )
    try:
        path = _ledger_path(storage, None)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, open(path, "a", encoding="utf-8") as handle:
            handle.write(obs.model_dump_json() + "\n")
    except OSError:
        return None
    return obs


def load(storage: Optional[str] = None, scope: Optional[str] = None) -> List[Observation]:
    """Ledger'ı okur; bozuksa o satırı atlar (sessiz veri kaybı olmaz: sayılır)."""
    path = _ledger_path(storage, None)
    if not os.path.exists(path):
        return []
    rows: List[Observation] = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(Observation.model_validate_json(line))
                except Exception:  # noqa: BLE001 - bozuk satır istatistiğe girmez
                    continue
    except OSError:
        return []
    if scope:
        rows = [r for r in rows if r.scope == scope]
    return rows


def adjudicate(observation_id: str, truth: bool, storage: Optional[str] = None) -> bool:
    """Operatör bir kayda ETİKET koyar (doğru/yanlış eşleşme). True = bulundu."""
    path = _ledger_path(storage, None)
    if not os.path.exists(path) or not observation_id:
        return False
    rows = load(storage)
    found = False
    for row in rows:
        if row.observation_id == observation_id:
            row.truth = bool(truth)
            found = True
    if not found:
        return False
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        tmp = f"{path}.tmp"
        with _LOCK, open(tmp, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(row.model_dump_json() + "\n")
        os.replace(tmp, path)
    except OSError:
        return False
    return True


# ------------------------------------------------------------------ istatistik
def _metrics(pairs: Sequence[Tuple[float, bool]], threshold: float) -> OperatingPoint:
    tp = fp = fn = tn = 0
    for score, truth in pairs:
        predicted = score >= threshold
        if predicted and truth:
            tp += 1
        elif predicted and not truth:
            fp += 1
        elif not predicted and truth:
            fn += 1
        else:
            tn += 1
    total = max(1, tp + fp + fn + tn)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return OperatingPoint(
        threshold=round(threshold, 4),
        accuracy=round((tp + tn) / total, 6),
        precision=round(precision, 6),
        recall=round(recall, 6),
        f1=round(f1, 6),
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
    )


def _wilson(successes: int, total: int, z: float = 1.96) -> List[float]:
    """İsabet oranı için Wilson güven aralığı (küçük örnekte dürüst aralık)."""
    if total <= 0:
        return []
    p = successes / total
    denom = 1 + (z * z) / total
    center = (p + (z * z) / (2 * total)) / denom
    margin = (z / denom) * math.sqrt((p * (1 - p) / total) + (z * z) / (4 * total * total))
    return [round(max(0.0, center - margin), 6), round(min(1.0, center + margin), 6)]


def _reliability(pairs: Sequence[Tuple[float, bool]], bins: int = 5) -> Tuple[List[ReliabilityBin], float]:
    """Güvenilirlik diyagramı: söylenen skor ile gözlenen isabet arasındaki fark (ECE)."""
    out: List[ReliabilityBin] = []
    ece = 0.0
    total = len(pairs)
    if total == 0:
        return out, 0.0
    for idx in range(bins):
        low, high = idx / bins, (idx + 1) / bins
        inside = [(s, t) for s, t in pairs if (low <= s < high) or (idx == bins - 1 and s >= high)]
        if not inside:
            continue
        mean_score = sum(s for s, _ in inside) / len(inside)
        accuracy = sum(1 for _, t in inside if t) / len(inside)
        out.append(
            ReliabilityBin(
                low=round(low, 4),
                high=round(high, 4),
                count=len(inside),
                mean_score=round(mean_score, 6),
                accuracy=round(accuracy, 6),
            )
        )
        ece += (len(inside) / total) * abs(mean_score - accuracy)
    return out, round(ece, 6)


def calibrate(
    observations: Iterable[Observation],
    *,
    scope: str = SCOPE_QUOTE,
    default: float = DEFAULT_THRESHOLD,
    required: Optional[int] = None,
) -> CalibrationReport:
    """Etiketli örneklerden eşiği ÖLÇER. Veri yetersizse eşiği DEĞİŞTİRMEZ."""
    rows = [r for r in (observations or []) if r.scope == scope] if scope else list(observations or [])
    required = min_samples() if required is None else max(2, int(required))
    pairs: List[Tuple[float, bool]] = [
        (_clamp(r.score), bool(r.truth)) for r in rows if r.truth is not None
    ]
    report = CalibrationReport(
        scope=str(scope or SCOPE_QUOTE),
        samples=len(rows),
        labeled=len(pairs),
        unlabeled=len(rows) - len(pairs),
        min_samples=required,
        default_threshold=round(_clamp(default), 4),
    )

    positives = sum(1 for _, t in pairs if t)
    negatives = len(pairs) - positives
    if len(pairs) < required:
        report.available = False
        report.reason = f"yetersiz_etiketli_örnek:{len(pairs)}<{required}"
        report.machine_note = (
            f"EŞİK: {report.threshold:.2f} (varsayılan, ÖLÇÜLMEDİ) · etiketli {len(pairs)}/{required} · "
            f"etiketsiz {report.unlabeled} kayıt bekliyor — veri olmadan eşik değişmez"
        )
        return report
    if positives == 0 or negatives == 0:
        report.available = False
        report.reason = f"tek_sınıf:pozitif={positives},negatif={negatives}"
        report.machine_note = (
            f"EŞİK: {report.threshold:.2f} (varsayılan) · örnekler tek sınıf "
            f"(+{positives}/-{negatives}); iki sınıf da gerekli"
        )
        return report

    grid = [_metrics(pairs, t) for t in GRID]
    best = max(grid, key=lambda row: (row.recall - (row.fp / max(1, row.fp + row.tn)), row.f1, row.threshold))
    report.measured_threshold = best.threshold
    # Veri azken ölçülen değer varsayılana ÇEKİLİR (n/(n+required) ağırlık).
    weight = round(len(pairs) / (len(pairs) + required), 6)
    report.shrinkage_weight = weight
    blended = _clamp(default + weight * (best.threshold - default))
    report.threshold = round(blended, 4)
    report.available = True
    report.source = "kalibre"
    report.reason = "yeterli_etiketli_örnek"
    report.grid = grid
    report.operating_point = _metrics(pairs, report.threshold)
    successes = report.operating_point.tp + report.operating_point.tn
    report.confidence_interval = _wilson(successes, max(1, len(pairs)))
    report.reliability, report.expected_calibration_error = _reliability(pairs)
    report.machine_note = (
        f"EŞİK: {report.threshold:.2f} (ölçüldü; ham {best.threshold:.2f}, ağırlık {weight:.2f}) · "
        f"{len(pairs)} etiketli örnek · isabet {report.operating_point.accuracy:.2f} "
        f"[{report.confidence_interval[0]:.2f}-{report.confidence_interval[1]:.2f}] · "
        f"F1 {report.operating_point.f1:.2f} · ECE {report.expected_calibration_error:.2f}"
    )
    return report


def resolved_threshold(
    scope: str = SCOPE_QUOTE,
    *,
    storage: Optional[str] = None,
    default: float = DEFAULT_THRESHOLD,
) -> ThresholdDecision:
    """Çalışma anındaki eşik: elle sabitleme > ölçülmüş > varsayılan."""
    override = env_override(scope)
    base = _clamp(default)
    if override is not None:
        return ThresholdDecision(
            value=override,
            source="elle_sabitleme",
            reason="PINEAL_THRESHOLD",
        )
    report = calibrate(load(storage), scope=scope, default=base)
    if not report.available:
        return ThresholdDecision(value=base, source="varsayılan", reason=report.reason, report=report)
    return ThresholdDecision(value=report.threshold, source="kalibre", reason=report.reason, report=report)


def summary(storage: Optional[str] = None, scope: str = SCOPE_QUOTE) -> Dict[str, Any]:
    """API/UI için tek çağrılık özet (rapor + bugün kullanılan eşik)."""
    decision = resolved_threshold(scope, storage=storage)
    payload: Dict[str, Any] = {
        "scope": scope,
        "threshold": decision.value,
        "source": decision.source,
        "reason": decision.reason,
    }
    if decision.report is not None:
        payload["report"] = decision.report.model_dump()
    return payload
