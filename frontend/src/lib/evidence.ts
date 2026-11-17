export type PillarId =
  | 'follower'
  | 'timing'
  | 'depth'
  | 'visual'
  | 'shadow'
  | 'osint'
  | 'resonance';

export interface PillarSummary {
  id: PillarId;
  hasData: boolean;
  evidenceCount: number;
  sources: string[];
  epistemicTypes: string[];
  confidence: number | null;
  sufficiency: string;
  chainEntries: any[];
}

const NON_EVIDENCE_STRINGS = new Set([
  '',
  'insufficient',
  'insufficient_data',
  'unavailable',
  'not_run',
  'skipped',
  'failed',
  'error',
  'empty',
  'no_evidence',
  'none',
  'unknown',
  'denied',
  'blocked',
  'yetersiz kanıt',
  'veri yok',
]);

const METADATA_ONLY_KEYS = new Set([
  '_provenance',
  'status',
  'verdict',
  'reason',
  'error',
  'available',
  'data_sufficiency',
  'confidence',
  'frames_problems',
  'frames_diagnostics',
  'claim_gate',
  'timestamp',
  'source_agent',
  'agent',
  'evidence_type',
  'epistemic_type',
  'call_ids',
  'llm_calls',
  'aux_llm_calls',
  'uncertainty',
  'responsibility',
]);

export function hasEvidence(val: any): boolean {
  if (val === null || val === undefined || typeof val === 'boolean') return false;
  if (typeof val === 'number') return Number.isFinite(val);
  if (typeof val === 'string') {
    return !NON_EVIDENCE_STRINGS.has(val.trim().toLowerCase());
  }
  if (Array.isArray(val)) {
    return val.some((item) => hasEvidence(item));
  }
  if (typeof val === 'object') {
    if (val.available === false) return false;
    for (const key of ['status', 'verdict', 'data_sufficiency']) {
      const flag = String(val[key] ?? '').trim().toLowerCase();
      if (flag && NON_EVIDENCE_STRINGS.has(flag)) {
        return false;
      }
    }
    const keys = Object.keys(val).filter((k) => !METADATA_ONLY_KEYS.has(k));
    if (keys.length === 0) return false;
    return keys.some((k) => hasEvidence(val[k]));
  }
  return false;
}

const PILLAR_AGENT_MAP: Record<PillarId, string[]> = {
  follower: ['follower_audit', 'authenticity_auditor', 'frequency_map'],
  timing: ['timing_forensics', 'behavioral_analyst', 'seismos_events', 'pulse_map'],
  depth: ['depth_analyst', 'psychodynamic_depth', 'strata_map', 'human_behavior', 'mirror_truth'],
  visual: ['vision_analyzer', 'visual_forensics', 'void_map'],
  shadow: ['shadow_executor', 'shadow_profile', 'gravity_map', 'pattern_interrupt'],
  osint: ['osint_deep_web', 'osint_footprint', 'key_matrix', 'deep_research'],
  resonance: ['resonance_calc'],
};

function _extractSource(item: any): string[] {
  const out: string[] = [];
  if (!item || typeof item !== 'object') return out;
  if (item.provenance?.engine) out.push(String(item.provenance.engine));
  if (item._provenance?.provider) out.push(String(item._provenance.provider));
  if (item.source_agent) out.push(String(item.source_agent));
  if (item.agent) out.push(String(item.agent));
  if (item.source_engine) out.push(String(item.source_engine));
  return out;
}

function _extractConfidence(item: any): number | null {
  if (!item || typeof item !== 'object') return null;
  const raw =
    item?.uncertainty?.confidence ??
    item?.result?.confidence ??
    item?.confidence;
  if (typeof raw === 'number' && Number.isFinite(raw)) {
    return raw <= 1 ? Math.round(raw * 100) : Math.round(raw);
  }
  return null;
}

function _extractSufficiency(item: any): string | null {
  if (!item || typeof item !== 'object') return null;
  const raw =
    item?.uncertainty?.data_sufficiency ??
    item?.data_sufficiency ??
    item?.result?.data_sufficiency ??
    item?.verdict;
  if (typeof raw === 'string' && raw.trim()) return raw.trim();
  return null;
}

export function buildPillarSummaries(taskStatus: any): Record<PillarId, PillarSummary> {
  const chain: any[] = Array.isArray(taskStatus?.evidence_chain)
    ? taskStatus.evidence_chain
    : [];

  const primaryByPillar: Record<PillarId, any[]> = {
    follower: [taskStatus?.follower_audit, taskStatus?.frequency_map],
    timing: [taskStatus?.timing_forensics, taskStatus?.seismos_events, taskStatus?.pulse_map],
    depth: [taskStatus?.depth_report, taskStatus?.psychodynamic_depth, taskStatus?.strata_map],
    visual: [taskStatus?.visual_evidence, taskStatus?.void_map],
    shadow: [taskStatus?.shadow_profile, taskStatus?.gravity_map],
    osint: [taskStatus?.osint_footprint, taskStatus?.key_matrix],
    resonance: [taskStatus?.resonance_calc ?? taskStatus?.reso],
  };

  const result = {} as Record<PillarId, PillarSummary>;
  (Object.keys(PILLAR_AGENT_MAP) as PillarId[]).forEach((pillarId) => {
    const agents = new Set(PILLAR_AGENT_MAP[pillarId]);
    const matchingChain = chain.filter((entry) => {
      if (!entry || typeof entry !== 'object') return false;
      const a = String(entry.agent || '').trim();
      const sa = String(entry.source_agent || '').trim();
      return agents.has(a) || (sa && agents.has(sa));
    });
    const substantiveChain = matchingChain.filter((entry) =>
      hasEvidence(entry?.result ?? entry?.content ?? entry)
    );
    const primaryItems = primaryByPillar[pillarId].filter((p) => hasEvidence(p));
    const hasData = primaryItems.length > 0 || substantiveChain.length > 0;
    const evidenceCount =
      substantiveChain.length > 0 ? substantiveChain.length : primaryItems.length;

    const sourcesSet = new Set<string>();
    const epistemicSet = new Set<string>();
    const confidences: number[] = [];
    const sufficiencies: string[] = [];

    for (const entry of substantiveChain) {
      for (const s of _extractSource(entry)) sourcesSet.add(s);
      const ep = entry?.epistemic_type || entry?.evidence_type;
      if (typeof ep === 'string' && ep.trim()) epistemicSet.add(ep.trim());
      const c = _extractConfidence(entry);
      if (c !== null) confidences.push(c);
      const suf = _extractSufficiency(entry);
      if (suf) sufficiencies.push(suf);
    }

    for (const p of primaryItems) {
      for (const s of _extractSource(p)) sourcesSet.add(s);
      const c = _extractConfidence(p);
      if (c !== null) confidences.push(c);
      const suf = _extractSufficiency(p);
      if (suf) sufficiencies.push(suf);
    }

    const avgConfidence =
      confidences.length > 0
        ? Math.round(confidences.reduce((a, b) => a + b, 0) / confidences.length)
        : null;

    result[pillarId] = {
      id: pillarId,
      hasData,
      evidenceCount,
      sources: sourcesSet.size > 0 ? Array.from(sourcesSet) : [],
      epistemicTypes: epistemicSet.size > 0 ? Array.from(epistemicSet) : [],
      confidence: avgConfidence,
      sufficiency: sufficiencies[0] || (hasData ? 'yeterli (ölçülen)' : 'yetersiz / veri yok'),
      chainEntries: substantiveChain,
    };
  });

  return result;
}

export function evidenceChainToReportItems(taskStatus: any): Array<Record<string, any>> {
  const chain: any[] = Array.isArray(taskStatus?.evidence_chain)
    ? taskStatus.evidence_chain
    : [];
  return chain
    .filter((entry) => entry && typeof entry === 'object' && hasEvidence(entry?.result ?? entry?.content ?? entry))
    .slice(0, 100)
    .map((entry, idx) => {
      const sourceEngine = String(entry.source_agent || entry.agent || entry.source_engine || 'pipeline');
      const ep = String(entry.epistemic_type || (entry.evidence_type === 'primary' ? 'inference' : 'observation'));
      const rawContent = entry.content ?? entry.result ?? entry;
      const content =
        typeof rawContent === 'string'
          ? rawContent.slice(0, 600)
          : JSON.stringify(rawContent).slice(0, 600);
      const rawId = typeof entry.evidence_id === 'string' ? entry.evidence_id : '';
      const validId = /^ev_[0-9a-f]{20}$/.test(rawId)
        ? rawId
        : `ev_${(idx + 1).toString(16).padStart(20, '0')}`;
      return {
        evidence_id: validId,
        source_engine: sourceEngine,
        epistemic_type: ['observation', 'absence', 'inference'].includes(ep) ? ep : 'inference',
        content,
        provenance_refs: [
          ...(entry.provenance?.engine ? [String(entry.provenance.engine)] : []),
          ...(Array.isArray(entry.call_ids) ? entry.call_ids.slice(0, 3).map(String) : []),
          sourceEngine,
        ],
      };
    });
}
