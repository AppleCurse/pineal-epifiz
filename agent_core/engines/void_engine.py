"""VOID negative-space engine."""

import asyncio
import re

import numpy as np

from agent_core.domain.pillar_models import AbsenceHypothesis, EvidenceStatus, VoidReport, VoidSignal

CATEGORY_LEXICON = {
    "politics": {"cues": {"siyaset", "seçim", "politics", "vote"}, "baseline": 0.18},
    "religion": {"cues": {"inanç", "dua", "faith", "din"}, "baseline": 0.12},
    "family": {"cues": {"aile", "family", "annem", "babam"}, "baseline": 0.22},
    "romance": {"cues": {"aşk", "sevgili", "dating"}, "baseline": 0.15},
    "career": {"cues": {"kariyer", "job", "ofis", "iş"}, "baseline": 0.28},
    "money": {"cues": {"para", "money", "yatırım"}, "baseline": 0.16},
    "health": {"cues": {"sağlık", "health", "spor", "uyku"}, "baseline": 0.2},
    "art_creation": {"cues": {"sanat", "müzik", "tasarım", "fotoğraf", "art"}, "baseline": 0.25},
    "travel": {"cues": {"seyahat", "travel", "tatil"}, "baseline": 0.18},
    "conflict": {"cues": {"kavga", "fight", "tartışma"}, "baseline": 0.1},
}


def _presence(corpus, cues):
    # `cues` bir küme: yineleme sırası hash tohumuna bağlıdır. Sıralı liste
    # deterministik çıktı garantisi verir (7 motor deterministik diye beyan
    # ediliyor; [RÖNTGEN 2026-09-23]).
    counts = {c: len(re.findall(rf"(?<!\w){re.escape(c)}(?!\w)", corpus, flags=re.IGNORECASE)) for c in cues}
    hits = sorted(c for c, count in counts.items() if count)
    n = sum(counts[c] for c in hits)
    return float(1 - np.exp(-0.45 * n)), n, hits[:8]


class VoidEngine:
    def __init__(self, min_tokens=40, void_threshold=0.22, strong_void=0.4, interest_boost=0.2):
        self.min_tokens = min_tokens
        self.void_threshold = void_threshold
        self.strong_void = strong_void
        self.interest_boost = interest_boost

    async def analyze(self, d):
        return await asyncio.to_thread(self._sync, d)

    def _sync(self, d):
        p = d.get("target_profile") or {}
        corpus = " ".join(
            [str(p.get("bio") or "")]
            + [x if isinstance(x, str) else str(x.get("text") or x.get("caption") or "") for x in p.get("posts") or []]
        ).lower()
        tokens = re.findall(r"[^\W\d_]+", corpus)
        if len(tokens) < self.min_tokens:
            return VoidReport(machine_note=f"VOID: {len(tokens)} token < min {self.min_tokens}.")
        interests = {str(x).lower() for x in p.get("interests") or p.get("following_topics") or []}
        out = []
        for cat, spec in CATEGORY_LEXICON.items():
            interest = cat in interests or any(any(c in it for c in spec["cues"]) for it in interests)
            expected = min(1, spec["baseline"] + (self.interest_boost if interest else 0))
            actual, n, hits = _presence(corpus, spec["cues"])
            delta = expected - actual
            score = float(np.clip(delta / max(expected, 1e-6), 0, 1)) if delta > 0 else 0
            if score < 0.12:
                continue
            status = (
                EvidenceStatus.OBSERVED
                if score >= self.strong_void and (interest or expected >= 0.2)
                else EvidenceStatus.WEAK
                if score >= self.void_threshold
                else EvidenceStatus.INCONCLUSIVE
            )
            hy = (
                [AbsenceHypothesis.AUDIENCE_FILTER, AbsenceHypothesis.ROLE_BOUNDARY]
                if interest
                else [AbsenceHypothesis.DISINTEREST, AbsenceHypothesis.UNKNOWN]
            )
            out.append(
                VoidSignal(
                    topic=cat,
                    category=cat,
                    expected_presence=expected,
                    actual_presence=actual,
                    absence_delta=delta,
                    absence_score=score,
                    status=status,
                    hypotheses=hy,
                    observables=[f"Kategori '{cat}': beklenen≈{expected:.2f}, gözlenen≈{actual:.2f}.", f"Cue hit={n}."],
                    evidence_refs=[f"void:{cat}:hits={n}"],
                )
            )
        out.sort(key=lambda x: -x.absence_score)
        top = [x.topic for x in out[:5] if x.absence_score >= self.void_threshold]
        idx = float(np.mean([x.absence_score for x in out])) if out else 0
        return VoidReport(
            status=EvidenceStatus.OBSERVED
            if any(x.status == EvidenceStatus.OBSERVED for x in out)
            else EvidenceStatus.WEAK
            if out
            else EvidenceStatus.INCONCLUSIVE,
            signals=out,
            top_voids=top,
            global_absence_index=idx,
            covered_categories=list(CATEGORY_LEXICON),
            machine_note=f"VOID: {len(out)} sinyal · idx={idx:.2f} · top={','.join(top) or '—'}",
            evidence_refs=[f"corpus_tokens:{len(tokens)}"],
        )
