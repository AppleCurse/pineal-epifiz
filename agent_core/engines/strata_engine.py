"""STRATA longitudinal layers and fossil records."""

import asyncio
import re

import numpy as np

from agent_core.domain.pillar_models import EvidenceStatus
from agent_core.domain.pillar_wave2_models import FossilRecord, IdentityDrift, StrataReport

from .frequency_engine import extract_post_series
from .void_engine import CATEGORY_LEXICON, _presence


class StrataEngine:
    def __init__(self, min_posts=6, full_sample_posts=12, extinction_threshold=0.05):
        self.min_posts = min_posts
        self.full_sample_posts = full_sample_posts
        self.extinction_threshold = extinction_threshold

    async def analyze(self, d):
        return await asyncio.to_thread(self._sync, d)

    def _sync(self, d):
        s = extract_post_series(d)
        if len(s) < self.min_posts:
            return StrataReport(machine_note=f"STRATA: {len(s)} gönderi < min {self.min_posts}.")
        n = max(2, len(s) // 3)
        e = s[:n]
        late = s[-n:]
        dr = []

        def add(name, a, b, hi, lo):
            r = b / max(a, 1e-6)
            dr.append(
                IdentityDrift(
                    metric=name,
                    early_value=float(a),
                    late_value=float(b),
                    drift_ratio=float(r),
                    is_significant=bool(r > hi or r < lo),
                    observable=f"{name}: {a:.3f}→{b:.3f}.",
                )
            )

        add("text_length", np.mean([len(x[1]) for x in e]), np.mean([len(x[1]) for x in late]), 1.6, 0.55)
        add(
            "emoji_density",
            np.mean([len(re.findall("[😀-🙏]", x[1])) / max(1, len(x[1])) for x in e]),
            np.mean([len(re.findall("[😀-🙏]", x[1])) / max(1, len(x[1])) for x in late]),
            2.5,
            0.3,
        )
        add(
            "punctuation_intensity",
            np.mean([(x[1].count("!") + x[1].count("?")) / max(1, len(x[1])) for x in e]),
            np.mean([(x[1].count("!") + x[1].count("?")) / max(1, len(x[1])) for x in late]),
            2,
            0.35,
        )
        add("engagement_level", np.mean([x[2] + x[3] for x in e]), np.mean([x[2] + x[3] for x in late]), 2.5, 0.3)
        ec = " ".join(x[1] for x in e).lower()
        lc = " ".join(x[1] for x in late).lower()
        f = []
        for cat, spec in CATEGORY_LEXICON.items():
            ep, _, _ = _presence(ec, spec["cues"])
            lp, _, _ = _presence(lc, spec["cues"])
            if ep > 0.35 and lp < self.extinction_threshold:
                last = max((x[0] for x in s if _presence(x[1].lower(), spec["cues"])[0] > 0.1), default=e[-1][0])
                f.append(
                    FossilRecord(
                        topic=cat,
                        last_seen_iso=last.isoformat(),
                        extinction_confidence=min(1, ep * (1 - lp)),
                        early_presence=ep,
                        late_presence=lp,
                        observables=[f"'{cat}' erken katmanda aktif, geç katmanda gözlenmedi."],
                        evidence_refs=[f"fossil:{cat}"],
                    )
                )
        depth = (s[-1][0] - s[0][0]).total_seconds() / 86400
        sig = sum(x.is_significant for x in dr)
        low_sample = len(s) < self.full_sample_posts
        status = (
            EvidenceStatus.WEAK
            if low_sample
            else (EvidenceStatus.OBSERVED if f or sig else EvidenceStatus.WEAK)
        )
        sample_note = f" · düşük örneklem ({len(s)}<{self.full_sample_posts})" if low_sample else ""
        return StrataReport(
            status=status,
            fossils=f,
            drifts=dr,
            archaeological_depth_days=depth,
            early_range=f"{e[0][0].date()}→{e[-1][0].date()}",
            late_range=f"{late[0][0].date()}→{late[-1][0].date()}",
            machine_note=f"STRATA: derinlik={depth:.0f}d · {len(f)} fosil · {sig}/{len(dr)} kritik drift{sample_note}",
            evidence_refs=[f"strata:depth_days={depth:.0f}"],
        )
