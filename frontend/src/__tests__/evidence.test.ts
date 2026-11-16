import { describe, it, expect } from 'vitest';
import {
  hasEvidence,
  buildPillarSummaries,
  evidenceChainToReportItems,
} from '../lib/evidence';

describe('hasEvidence strictness', () => {
  it('rejects null, undefined, empty objects/arrays, and status-only or insufficient objects', () => {
    expect(hasEvidence(null)).toBe(false);
    expect(hasEvidence(undefined)).toBe(false);
    expect(hasEvidence('')).toBe(false);
    expect(hasEvidence('   ')).toBe(false);
    expect(hasEvidence('insufficient_data')).toBe(false);
    expect(hasEvidence({})).toBe(false);
    expect(hasEvidence([])).toBe(false);
    expect(hasEvidence([{ status: 'insufficient_data' }])).toBe(false);
    expect(hasEvidence({ available: false, score: 99 })).toBe(false);
    expect(hasEvidence({ status: 'insufficient_data', reason: 'no posts' })).toBe(false);
    expect(hasEvidence({ verdict: 'insufficient', confidence: 0.2 })).toBe(false);
    expect(hasEvidence({ data_sufficiency: 'insufficient', _provenance: { provider: 'groq' } })).toBe(false);
    expect(hasEvidence({ _provenance: { provider: 'groq' }, frames_problems: ['none'] })).toBe(false);
  });

  it('accepts objects with real substantive forensic measurements', () => {
    expect(hasEvidence({ authenticity_score: 82, avg_followers: 12400 })).toBe(true);
    expect(hasEvidence({ status: 'ok', verdict: 'ok', compensation_index: 0.42 })).toBe(true);
    expect(hasEvidence([{ url: 'https://example.com' }])).toBe(true);
  });
});

describe('buildPillarSummaries and evidenceChainToReportItems', () => {
  it('wires backend evidence_chain metadata into the 7 pillar summaries', () => {
    const status = {
      follower_audit: { authenticity_score: 88, avg_followers: 5000 },
      visual_evidence: { status: 'insufficient_data', frames_problems: ['no_images'] },
      reso: { alignment_score: 74, resonance_angle: 18 },
      evidence_chain: [
        {
          agent: 'authenticity_auditor',
          evidence_type: 'primary',
          epistemic_type: 'observation',
          provenance: { engine: 'follower_audit' },
          uncertainty: { confidence: 0.88, data_sufficiency: 'sufficient' },
          result: { authenticity_score: 88 },
        },
        {
          agent: 'resonance_calc',
          evidence_type: 'primary',
          epistemic_type: 'inference',
          uncertainty: { confidence: 0.74, data_sufficiency: 'partial' },
          result: { alignment_score: 74 },
        },
      ],
    };

    const summaries = buildPillarSummaries(status);
    expect(summaries.follower.hasData).toBe(true);
    expect(summaries.follower.evidenceCount).toBe(1);
    expect(summaries.follower.confidence).toBe(88);
    expect(summaries.follower.epistemicTypes).toContain('observation');
    expect(summaries.follower.sources).toContain('follower_audit');
    expect(summaries.follower.sufficiency).toBe('sufficient');

    expect(summaries.visual.hasData).toBe(false);
    expect(summaries.visual.evidenceCount).toBe(0);

    expect(summaries.resonance.hasData).toBe(true);
    expect(summaries.resonance.confidence).toBe(74);
    expect(summaries.resonance.epistemicTypes).toContain('inference');

    const reportItems = evidenceChainToReportItems(status);
    expect(reportItems).toHaveLength(2);
    expect(reportItems[0].evidence_id).toMatch(/^ev_[0-9a-f]{20}$/);
  });
});
