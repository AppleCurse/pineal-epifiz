"""FREQUENCY temporal waveform engine."""

import asyncio
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from agent_core.domain.pillar_models import EvidenceStatus, FlowWindow, FrequencyReport, WaveSample

_EPOCH = re.compile(r"^\d{10,13}$")


def parse_timestamp(v: Any):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(float(v) / (1000 if float(v) > 1e12 else 1), timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    s = str(v).strip()
    if _EPOCH.match(s):
        return parse_timestamp(int(s))
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except ValueError:
        m = re.search(r"\d{4}-\d\d-\d\d[T ]\d\d:\d\d(?::\d\d)?(?:Z|[+-]\d\d:?\d\d)?", s)
        return parse_timestamp(m.group(0)) if m else None


def extract_post_series(data):
    p = data.get("target_profile") or {}
    posts = p.get("posts") or []
    times = p.get("post_times") or []
    meta = p.get("posts_meta") or []
    out = []
    for i in range(max(len(posts), len(times), len(meta))):
        x = posts[i] if i < len(posts) else ""
        text = x if isinstance(x, str) else str(x.get("text") or x.get("caption") or "")
        m = meta[i] if i < len(meta) and isinstance(meta[i], dict) else {}
        ts = (
            parse_timestamp(times[i] if i < len(times) else None)
            or (parse_timestamp(x.get("created_at") or x.get("timestamp")) if isinstance(x, dict) else None)
            or parse_timestamp(m.get("created_at") or m.get("timestamp"))
        )
        if ts:
            out.append(
                (
                    ts,
                    text,
                    float(m.get("like_count") or m.get("likes") or 0),
                    float(m.get("comment_count") or m.get("comments") or 0),
                )
            )
    return sorted(out)


class FrequencyEngine:
    def __init__(self, bucket_hours=24, smooth_window=3, min_samples=4, flow_z=0.75, collapse_z=-0.75):
        self.bucket_hours = max(1, bucket_hours)
        self.smooth_window = max(1, smooth_window)
        self.min_samples = min_samples
        self.flow_z = flow_z
        self.collapse_z = collapse_z

    async def analyze(self, data):
        return await asyncio.to_thread(self._sync, data)

    def _sync(self, data):
        ev = extract_post_series(data)
        if not ev:
            return FrequencyReport(machine_note="FREQUENCY: Zaman damgalı gönderi bulunamadı.")
        platform = str((data.get("target_profile") or {}).get("platform") or "primary")
        step = timedelta(hours=self.bucket_hours)
        start = ev[0][0].replace(minute=0, second=0, microsecond=0)
        grids = defaultdict(list)
        for ts, tx, lk, cm in ev:
            grids[start + step * int((ts - start).total_seconds() // step.total_seconds())].append((tx, lk, cm))
        samples = []
        t = start
        while t <= max(grids):
            a = grids.get(t, [])
            en = sum(
                1 + 0.65 * np.log1p(len(x)) + 0.35 * np.log1p(max(0, likes) + 2 * max(0, comments))
                for x, likes, comments in a
            )
            samples.append(
                WaveSample(
                    t=t,
                    energy=round(float(en), 4),
                    post_count=len(a),
                    mean_text_len=round(float(np.mean([len(x) for x, _, _ in a])) if a else 0, 2),
                    engagement=sum(likes + 2 * comments for _, likes, comments in a),
                    platform=platform,
                )
            )
            t += step
        refs = [f"post:{platform}:{x[0].isoformat()}" for x in ev]
        if len(samples) < self.min_samples:
            return FrequencyReport(
                samples=samples,
                evidence_refs=refs,
                machine_note=f"FREQUENCY: {len(samples)} kova < min {self.min_samples}.",
            )
        x = np.array([s.energy for s in samples])
        w = min(self.smooth_window, len(x))
        smooth = np.convolve(np.pad(x, (w // 2, w // 2), mode="edge"), np.ones(w) / w, "valid")[: len(x)]
        mu = float(smooth.mean())
        sd = float(smooth.std())
        z = (smooth - mu) / sd if sd > 1e-9 else np.zeros_like(smooth)
        peaks = [
            i
            for i in range(1, len(x) - 1)
            if smooth[i] >= smooth[i - 1] and smooth[i] >= smooth[i + 1] and smooth[i] > mu
        ]
        troughs = [
            i
            for i in range(1, len(x) - 1)
            if smooth[i] <= smooth[i - 1] and smooth[i] <= smooth[i + 1] and smooth[i] < mu
        ]

        def wins(mask, label):
            out = []
            i = 0
            while i < len(samples):
                if not mask[i]:
                    i += 1
                    continue
                j = i + 1
                while j < len(samples) and mask[j]:
                    j += 1
                q = samples[i:j]
                vals = [s.energy for s in q]
                out.append(
                    FlowWindow(
                        start=q[0].t,
                        end=q[-1].t,
                        peak_energy=max(vals),
                        mean_energy=float(np.mean(vals)),
                        sample_count=len(q),
                        label=label,
                    )
                )
                i = j
            return out

        night = sum(ts.hour >= 23 or ts.hour < 5 for ts, *_ in ev) / len(ev)

        # [FAZ B · B6] GERÇEK spektral analiz: sin/cos modeli değil, FFT
        # periodogramı. Yetersiz/sabit seride periyot UYDURULMAZ (alan None).
        from agent_core.engines.spectrum import analyze_spectrum

        spectrum = analyze_spectrum(
            [s.energy for s in samples], bucket_hours=self.bucket_hours
        )

        note = f"FREQUENCY: {len(samples)} kova · μ={mu:.2f} σ={sd:.2f}"
        if spectrum.available:
            note += (
                f" · baskın periyot {spectrum.dominant_period_days:g} gün"
                f" (güç payı {spectrum.periodic_strength:.2f})"
            )
        else:
            note += f" · periyot ölçülemedi ({spectrum.reason})"

        return FrequencyReport(
            status=EvidenceStatus.OBSERVED if len(samples) >= 8 else EvidenceStatus.WEAK,
            samples=samples,
            waveform=[round(float(v), 4) for v in smooth],
            timeline=[s.t.isoformat() for s in samples],
            peak_indices=peaks,
            trough_indices=troughs,
            flow_windows=wins(z >= self.flow_z, "flow"),
            friction_collapses=wins(z <= self.collapse_z, "collapse"),
            energy_mean=round(mu, 4),
            energy_std=round(sd, 4),
            night_energy_share=round(night, 4),
            dominant_period_days=spectrum.dominant_period_days,
            periodic_strength=spectrum.periodic_strength,
            dominant_harmonic=spectrum.dominant_harmonic,
            spectral_method=spectrum.method if spectrum.available else "",
            spectral_reason=spectrum.reason,
            spectrum=spectrum.spectrum,
            machine_note=note,
            evidence_refs=refs[:64],
        )
