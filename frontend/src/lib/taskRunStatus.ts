/** Task-scoped view of agent runs; rack readiness is not a run result. */
export function taskRuns(task: any): Record<string, any> {
  if (typeof task?.task_id !== 'string' || !task.task_id.trim() || !task.runs || typeof task.runs !== 'object' || Array.isArray(task.runs)) return {};
  return Object.fromEntries(Object.entries(task.runs).filter(([name, value]) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
    const run = value as Record<string, any>;
    return (!run.task_id || run.task_id === task.task_id) && (!run.agent_name || run.agent_name === name);
  }));
}

/** Rack labels describe availability and cannot certify a task run. */
export function rackAvailability(status: unknown): string {
  const value = String(status || '').toLowerCase();
  if (value === 'ready') return 'READY';
  if (value === 'active' || value === 'running') return 'ACTIVE';
  if (value === 'wait' || value === 'idle') return 'WAIT';
  return 'UNKNOWN';
}

export function taskRunLabel(run: any): string {
  switch (run?.status) {
    case 'completed': return 'DONE';
    case 'completed_no_decision': return 'NO-DECISION';
    case 'running': return 'ACTIVE';
    case 'pending': return 'WAIT';
    case 'halted': return 'HALTED';
    case 'failed': return 'FAILED';
    case 'timed_out': return 'TIMED_OUT';
    case 'unavailable': return 'UNAVAILABLE';
    default: return 'UNKNOWN';
  }
}
