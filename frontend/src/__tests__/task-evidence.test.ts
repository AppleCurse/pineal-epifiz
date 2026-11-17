import { describe, it, expect } from 'vitest';
import { render, waitFor } from '@testing-library/svelte';
import TaskEvidence from '../components/TaskEvidence.svelte';
import { mergeTaskSnapshot } from '../store';

describe('task-scoped evidence and channel status', () => {
  it('shows real channel outcomes and canonical items without inventing confidence', () => {
    const { container } = render(TaskEvidence, { task: {
      task_id: 'task-1',
      channel_status: [
        { channel: 'one', status: 'ok', detail: '0 eşleşme' },
        { channel: 'two', status: 'not_run', reason: 'disabled' },
        { channel: 'three', status: 'failed', reason: 'timeout' },
      ],
      evidence_chain: [{ agent: 'pillar_evidence_adapter', evidence_type: 'canonical_evidence', result: {
        schema_version: 'evidence-item-v1', items: [
          { evidence_id: 'ev_123', epistemic_type: 'inference', content: 'Bir çıkarım', source_engine: 'engine', provenance_refs: ['ref-1'], confidence: null },
          { evidence_id: 'ev_456', epistemic_type: 'observation', content: 'Bir gözlem', source_engine: 'engine', provenance_refs: [], confidence: 0 },
        ],
      } }],
    } });
    const text = container.textContent || '';
    for (const expected of ['one — Çalıştı', '0 eşleşme', 'two — Çalışmadı', 'three — Başarısız', 'Çıkarım', 'Gözlem', 'ref-1', 'Güven: Belirtilmemiş', 'Güven: 0%']) expect(text).toContain(expected);
    expect(text).toContain('ayrı ayrı bağlanmış değildir');
  });

  it('distinguishes absent and failed evidence from an empty result', async () => {
    const { container, rerender } = render(TaskEvidence, { task: { task_id: 'task-1' } });
    expect(container.textContent).toContain('henüz bildirilmedi');
    await rerender({ task: { task_id: 'task-1', evidence_chain: [{ agent: 'pillar_evidence_adapter', evidence_type: 'execution_failure', result: { build_status: 'failed' } }] } });
    await waitFor(() => expect(container.textContent).toContain('Kanıt kayıtları oluşturulamadı'));
  });

  it('does not carry previous task evidence into a new task snapshot', () => {
    const old = { task_id: 'old', evidence_chain: [{ secret: 'old' }], channel_status: [{ channel: 'old' }] };
    const fresh = mergeTaskSnapshot(old, { task_id: 'new', status: 'processing' });
    expect(fresh.evidence_chain).toBeUndefined();
    expect(fresh.channel_status).toBeUndefined();
  });
});
