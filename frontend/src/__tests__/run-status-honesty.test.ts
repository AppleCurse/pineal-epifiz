import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/svelte';
import TacticalWarRoom from '../components/TacticalWarRoom.svelte';
import Atlas from '../components/AtlasPinealCockpit.svelte';
import LiveControlPanel from '../components/LiveControlPanel.svelte';
import { agentStatuses, isProcessing, taskStatus } from '../store';

beforeEach(() => {
  taskStatus.set(null);
  agentStatuses.set({});
  isProcessing.set(false);
  vi.stubGlobal('fetch', vi.fn(async () => ({ok:true, json:async () => ({locked:true})})));
});

function firstWarStatus() {
  const view = render(TacticalWarRoom);
  return view.container.querySelector('.agent-card .status-pill')?.textContent?.trim();
}

describe('task-bound run status', () => {
  it('shows ready, not done, without a task run', () => {
    agentStatuses.set({osint_investigator:{status:'Ready', updatedAt:1}});
    taskStatus.set({task_id:'task1', runs:{}});
    expect(firstWarStatus()).toBe('READY');
  });

  it('does not use a completed run without task identity', () => {
    taskStatus.set({runs:{osint_investigator:{status:'completed'}}});
    expect(firstWarStatus()).not.toBe('DONE');
  });

  it('does not use a run explicitly associated with another task', () => {
    taskStatus.set({task_id:'task1', runs:{osint_investigator:{task_id:'other',status:'completed'}}});
    expect(firstWarStatus()).not.toBe('DONE');
  });

  it('shows done for the selected task terminal run', () => {
    taskStatus.set({task_id:'task1', runs:{osint_investigator:{status:'completed'}}});
    expect(firstWarStatus()).toBe('DONE');
  });

  it('does not allow ready to hide an unknown run state', () => {
    agentStatuses.set({osint_investigator:{status:'Ready', updatedAt:1}});
    taskStatus.set({task_id:'task1', runs:{osint_investigator:{status:'mystery'}}});
    expect(firstWarStatus()).toBe('UNKNOWN');
  });

  it('Atlas prefers task run over conflicting rack readiness', () => {
    agentStatuses.set({osint_investigator:{status:'Ready', updatedAt:1}});
    taskStatus.set({task_id:'task1', runs:{osint_investigator:{status:'completed'}}});
    const view = render(Atlas);
    expect(view.container.querySelector('.agent-matrix-chip .agent-status-tag')?.textContent?.trim()).toBe('DONE');
  });

  it('LiveControlPanel does not mark an unbound run done', () => {
    taskStatus.set({planned_agents:['osint_investigator'], runs:{osint_investigator:{status:'completed'}}});
    const view = render(LiveControlPanel);
    expect(view.container.querySelector('.cp-state')?.textContent?.trim()).not.toBe('TAMAM');
  });
});

it('does not carry runs across task changes or accept an unbound frame', async () => {
  const { mergeTaskSnapshot } = await import('../store');
  const first = {task_id:'old', runs:{osint_investigator:{status:'completed'}}};
  expect(mergeTaskSnapshot(first, {task_id:'new', status:'processing'})).toEqual({task_id:'new',status:'processing',runs:{},task_phase:'unknown',task_outcome:'unknown',decision_state:'unknown'});
  expect(mergeTaskSnapshot(first, {status:'completed'})).toEqual(first);
});

it.each([
  ['partially_completed', 'partial', 'KISMİ'],
  ['completed', 'unknown', 'BELİRSİZ'],
])('Atlas distinguishes %s with %s outcome', (status, task_outcome, label) => {
  taskStatus.set({task_id:'t', status, task_outcome, runs:{}});
  const view = render(Atlas);
  const banner = view.container.querySelector('.mission-status-banner') || view.container;
  expect(banner.textContent).toContain(label);
  expect(banner.textContent).not.toContain('SON İŞLEM TAMAMLANDI');
});

it('does not let a global processing flag hide the selected partial task', () => {
  taskStatus.set({task_id:'t', status:'partially_completed', task_outcome:'partial', runs:{}});
  isProcessing.set(true);
  const view = render(Atlas);
  expect(view.container.querySelector('.live-status-badge')?.textContent).toContain('KISMİ');
});

it('does not carry a prior outcome when a newer frame omits it', async () => {
  const { mergeTaskSnapshot } = await import('../store');
  const old = {task_id:'t', status:'completed', task_outcome:'completed', decision_state:'unknown'};
  const next = mergeTaskSnapshot(old, {task_id:'t', status:'timed_out'});
  expect(next.task_outcome).toBe('unknown');
});
