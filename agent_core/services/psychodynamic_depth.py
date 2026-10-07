"""GÖREV 2.3 + 2.4 — 4 kanalli capraz-gerilim motoru + epistemik kapi.

DORT KANAL (beyan/sahneleme/ritim/sosyal), kanal-ici olcumler:
  Ch1 beyan (declaration): metin kumelenmesi (tema sayisi, tekrar, anomali).
  Ch2 sahneleme (staging): gorsel yapi (nesne/form dagilimi, kapsam).
  Ch3 ritim (rhythm): zaman forensigi (orneklem, kirilmalar, rejimler).
  Ch4 sosyal (social): takipci denetimi (erisim, olcum butunlugu).

CAPRAZ GERILIM: T[i][j] = |I_i - I_j| * min(C_i, C_j); kosegen 0, simetrik.
  compensation_index = sahnelemenin diger kanallarla ortalama gerilimi.
  reaction_formation_index = beyan-sahneleme gerilimi (T[0][1]).
Bu iki skor YAPISALDIR; klinik yorum icermez, yorumu analist yapar.

EPISTEMIK KAPI (2.4): agirlik = kanal kullanilabilirligi (completeness),
w_i = C_i / ΣC. Metin yoksa C_decl = 0 -> w_decl = 0 ve butce otomatik
gorsel+zamansala (+sosyal) kayar. Hic kanal yoksa verdict "no_evidence"
doner; FONKSIYON ASLA halt etmez/yukselmez (tum govde korumalidir).

Formul katsayilari v1 sezgiselidir; her biri belgeli + test-kilitlidir.
Cikti JSON-serializable'dir.
"""

from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import math
from typing import Any, Dict, List

from agent_core.services.theme_cluster import cluster_texts

try:  # GÖREV 2 artığı: piksel ölçümü yalnız PIL varsa (yoksa None+not).
    from PIL import Image as _PILImage

    HAS_PIL = True
except ImportError:  # pragma: no cover - ortama bağlı dal
    _PILImage = None  # type: ignore[assignment]

    HAS_PIL = False

CHANNELS = ("declaration", "staging", "rhythm", "social")

# Ch2 piksel notu: renk doygunlugu HAM JPEG cozumu gerektirir; stdlib'da
# guvenilir JPEG cozucu YOKTUR (PIL kurulu degil). Olcmeden sayi yazmak
# uydurma olacagi icin alan None + acik not doner (test-kilitli).
SATURATION_NOTE = (
    "PIL kurulu degil; piksel-düzeyi doygunluk olculmedi (None). "
    "pillow kurulumu sonrasi ~20 satirla etkinlestirilebilir."
)


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, str)]


def _clamp01(value: Any) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0.0
    if num != num:  # NaN
        return 0.0
    return min(1.0, max(0.0, num))


def _norm_entropy(dist: Dict[str, int]) -> float:
    total = sum(dist.values())
    if total <= 0 or len(dist) <= 1:
        return 0.0
    probs = [c / total for c in dist.values()]
    ent = -sum(p * math.log(p) for p in probs if p > 0.0)
    return round(ent / math.log(len(dist)), 3)


def _no_evidence(reason: str) -> Dict[str, Any]:
    channels = {
        name: {"intensity": 0.0, "coherence": 0.0, "completeness": 0.0,
               "signals": {}}
        for name in CHANNELS
    }
    return {
        "channels": channels,
        "tension_matrix": [[0.0] * 4 for _ in range(4)],
        "compensation_index": 0.0,
        "reaction_formation_index": 0.0,
        "epistemic_weights": {f"w_{name}": 0.0 for name in CHANNELS},
        "confidence": 0.0,
        "verdict": "no_evidence",
        "reason": reason,
        "inputs_seen": {"n_texts": 0, "n_images": 0, "timing_samples": 0,
                        "audit_present": False, "post_type_n": 0},
    }


def analyze_depth(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Derinlik raporu uretir. TOTAL FONKSIYON: girdi ne olursa olsun
    sozlesmeye uygun dict doner, asla yukseltmez (halt yok)."""
    try:
        return _analyze_depth_inner(_as_dict(input_data))
    except Exception as exc:  # savunma hatti: motorsal halt yasak
        return _no_evidence(f"hesap hatasi, kanit uretilemedi: {type(exc).__name__}")


def _analyze_depth_inner(data: Dict[str, Any]) -> Dict[str, Any]:
    target = _as_dict(data.get("target_profile"))
    visual = _as_dict(data.get("visual_evidence"))
    timing = _as_dict(data.get("timing_forensics"))
    audit = _as_dict(data.get("follower_audit"))

    # ---- Ch1 beyan ----
    bio = target.get("bio") or ""
    texts = ([bio] if isinstance(bio, str) and bio.strip() else []) + [
        p for p in _as_str_list(target.get("posts")) if p.strip()
    ]
    themes = cluster_texts(texts)
    n_texts = themes["n_texts"]
    c1 = 1.0 if n_texts > 0 else 0.0
    if n_texts > 0:
        i1 = round(0.5 * min(1.0, n_texts / 6.0)
                   + 0.5 * themes["repetition_score"], 3)
        coh1 = round(1.0 - themes["isolated_anomaly_count"] / n_texts, 3)
    else:
        i1, coh1 = 0.0, 0.0
    sig1 = {"n_texts": n_texts, "n_themes": themes["n_themes"],
            "repetition_score": themes["repetition_score"],
            "isolated_anomaly_count": themes["isolated_anomaly_count"],
            "total_chars": sum(len(t) for t in texts)}

    # ---- Ch2 sahneleme ----
    images = target.get("images")
    n_images = len(images) if isinstance(images, list) else 0
    objects = _as_str_list(visual.get("detected_objects"))
    aesthetic = visual.get("aesthetic_style")
    aesthetic_present = isinstance(aesthetic, str) and bool(aesthetic.strip())
    type_list = [t for t in _as_str_list(target.get("post_types")) if t]
    format_mix: Dict[str, int] = {}
    for t in type_list:
        format_mix[t] = format_mix.get(t, 0) + 1
    fmt_entropy = _norm_entropy(format_mix)
    if objects:
        c2 = 1.0
    elif aesthetic_present or n_images > 0:
        c2 = 0.5
    else:
        c2 = 0.0
    if c2 > 0:
        i2 = round(min(1.0, 0.5 * min(1.0, len(objects) / 8.0)
                       + 0.3 * min(1.0, n_images / 6.0)
                       + 0.2 * fmt_entropy), 3)
        coh2 = round(1.0 - fmt_entropy, 3)
    else:
        i2, coh2 = 0.0, 0.0
    sig2 = {"n_images": n_images, "n_objects": len(objects),
            "object_diversity": round(len(set(objects)) / len(objects), 3)
            if objects else 0.0,
            "aesthetic_present": aesthetic_present,
            "format_mix": format_mix, "format_entropy": fmt_entropy,
            "color_saturation": None, "saturation_note": SATURATION_NOTE}

    # ---- Ch3 ritim ----
    samples = timing.get("samples")
    n_samples = samples if isinstance(samples, int) and samples > 0 else 0
    night_share = timing.get("night_share")
    night_share = float(night_share) if isinstance(night_share, (int, float)) else None
    traj = _as_dict(timing.get("trajectory"))
    # [BUGFIX] `ruptures` yoksa (trajectory çıkarılamadı) bu blok TypeError
    # fırlatıyordu ve analyze_depth'in savunma hattı onu yutup TÜM raporu
    # "no_evidence" yapıyordu — yani 4 kanallı derinlik motoru sahici
    # girdilerin çoğunda hiç sonuç üretmiyordu. Listeye indirgenir, sonra
    # güvenle dolaşılır.
    raw_ruptures = traj.get("ruptures")
    ruptures = raw_ruptures if isinstance(raw_ruptures, list) else []
    n_ruptures = len(ruptures)
    regimes = traj.get("regimes")
    n_regimes = len(regimes) if isinstance(regimes, list) else 0
    rupture_kinds = sorted({r.get("kind") for r in ruptures
                            if isinstance(r, dict) and isinstance(r.get("kind"), str)})
    c3 = 1.0 if n_samples >= 3 else (0.5 if n_samples > 0 else 0.0)
    if c3 > 0:
        i3 = round(min(1.0, 0.6 * min(1.0, n_ruptures / 2.0)
                       + 0.4 * min(1.0, n_samples / 8.0)), 3)
        coh3 = round(1.0 - min(1.0, n_ruptures / max(1, n_samples - 1)), 3)
    else:
        i3, coh3 = 0.0, 0.0
    sig3 = {"samples": n_samples, "night_share": night_share,
            "peak_hour": timing.get("peak_hour"),
            "median_drift_hours": timing.get("median_drift_hours"),
            "n_ruptures": n_ruptures, "n_regimes": n_regimes,
            "rupture_kinds": rupture_kinds,
            "span_hours": traj.get("span_hours")}

    # ---- Ch4 sosyal ----
    er = audit.get("engagement_rate")
    er_val = float(er) if isinstance(er, (int, float)) else None
    c4 = _clamp01(audit.get("data_completeness")) if audit else 0.0
    if c4 > 0 and er_val is not None:
        i4 = round(min(1.0, er_val / 0.1), 3)  # v1: %10 ER = tam siddet
    else:
        i4 = 0.0
    coh4 = c4  # olcum butunlugu = tutarlilik olcusu
    sig4 = {"followers": audit.get("followers"),
            "following": audit.get("following"),
            "engagement_rate": er_val, "verdict": audit.get("verdict"),
            "data_completeness": c4 if audit else None}

    intensities = [i1, i2, i3, i4]
    coherences = [coh1, coh2, coh3, coh4]
    completeness = [c1, c2, c3, c4]

    # ---- Capraz gerilim ----
    tension = [
        [round(abs(intensities[i] - intensities[j])
               * min(completeness[i], completeness[j]), 3)
         for j in range(4)]
        for i in range(4)
    ]
    compensation = round(sum(tension[1][j] for j in (0, 2, 3)) / 3.0, 3)
    reaction_formation = tension[0][1]

    # ---- Epistemik kapi ----
    total = sum(completeness)
    if total <= 0:
        out = _no_evidence("kullanilabilir kanal yok (metin/gorsel/zaman/sosyal bos)")
        out["inputs_seen"] = {"n_texts": n_texts, "n_images": n_images,
                              "timing_samples": n_samples,
                              "audit_present": bool(audit),
                              "post_type_n": len(type_list)}
        return out
    weights = [round(c / total, 3) for c in completeness]
    confidence = round(sum(w * c for w, c in zip(weights, completeness)), 3)
    carriers = [name for name, w in zip(CHANNELS, weights) if w > 0]
    reason = f"tasiyici kanallar: {', '.join(carriers)}"
    if c1 == 0:
        reason += "; metin kanali kapali (w_declaration=0)"

    return {
        "channels": {
            name: {"intensity": inten, "coherence": coh,
                   "completeness": comp, "signals": sig}
            for name, inten, coh, comp, sig in zip(
                CHANNELS, intensities, coherences, completeness,
                (sig1, sig2, sig3, sig4))
        },
        "tension_matrix": tension,
        "compensation_index": compensation,
        "reaction_formation_index": reaction_formation,
        "epistemic_weights": {f"w_{name}": w
                              for name, w in zip(CHANNELS, weights)},
        "confidence": confidence,
        "verdict": "ok",
        "reason": reason,
        "inputs_seen": {"n_texts": n_texts, "n_images": n_images,
                        "timing_samples": n_samples,
                        "audit_present": bool(audit),
                        "post_type_n": len(type_list)},
    }


def measure_saturation(image_paths: Any, max_side: int = 64) -> Dict[str, Any]:
    """GÖREV 2 artığı: yerel dosyaların ortalama HSV doygunluğu (0.0-1.0).

    PIL yoksa/ölçülebilir piksel yoksa mean None + dürüst not (uydurma yok).
    Bozuk/eksik dosya atlanır ve SAYILIR (n_measured/n_total). Saf-stdlib
    JPEG çözücü olmadığı için bu fonksiyon PIL'e mahkûmdur; HAS_PIL bayrağı
    ortamı bildirir. Deterministiktir (aynı bayt -> aynı sayı).
    """
    paths = [p for p in (image_paths or []) if isinstance(p, str)]
    total = len(paths)
    if not HAS_PIL or _PILImage is None:
        return {"mean_saturation": None, "n_measured": 0, "n_total": total,
                "note": SATURATION_NOTE, "has_pil": False}
    values = []
    for path in paths:
        try:
            with _PILImage.open(path) as img:
                small = img.convert("RGB")
                small.thumbnail((max_side, max_side))
                pixels = list(small.convert("HSV").getdata())
        except Exception:
            logger.warning('Suppressed exception observed at agent_core/services/psychodynamic_depth.py:286 (continue)')
            continue
        if not pixels:
            continue
        values.append(sum(px[1] for px in pixels) / len(pixels) / 255.0)
    if not values:
        return {"mean_saturation": None, "n_measured": 0, "n_total": total,
                "note": "ölçülebilir piksel bulunamadı (dosyalar açılamadı/boş)",
                "has_pil": True}
    return {"mean_saturation": round(sum(values) / len(values), 3),
            "n_measured": len(values), "n_total": total,
            "note": f"{len(values)}/{total} dosya ölçüldü (HSV-S ortalaması)",
            "has_pil": True}
