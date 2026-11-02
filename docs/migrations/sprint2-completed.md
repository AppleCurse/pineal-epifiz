# Sprint 2 — task completion, timeout and resume

## Contract and migration
- Snapshot/result/error WS frames add `task_state_version=1`, `task_phase`,
  `task_outcome` and `decision_state`. Legacy `status` remains for existing
  consumers. Deploy clients that tolerate additive fields before the backend.
- `decision_state` is `unknown`: a returned call, output summary, legacy
  `completed`, or `decision_grade` does **not** prove a domain decision.
  Legacy completed checkpoints and resumed tasks have unknown full outcome.
- New non-resumed tasks can have `completion_policy=planned_runs_v1` and
  `task_outcome=completed` only if the existing decision engine returned
  completed, every planned agent has a matching completed run, and every
  recorded run is completed and task-bound. This is route-run completion,
  not proof of a domain decision or business acceptance. Missing plans/runs,
  no-decision, failures, unavailable and timed-out runs cannot become full
  route completion. The interpreter's provider response is not execution.
- `timed_out` and `partially_completed` are distinct terminal lifecycle states.
  `TaskCompleted` is emitted only for full route completion, not partial/halted;
  resumed legacy runs do not emit it when their outcome is unknown. Consumers
  should use the terminal snapshot/result for all other outcomes.
- `TaskSnapshot.completion_policy` is additive and nullable. Existing files
  need no backfill; do not infer it from historical status or run summaries.
- Before an authorized resume, the checkpoint stores an additive
  `attempt_history_version=1` and appends a copy of the prior snapshot, with
  an archive ID and the previous lifecycle run ID when known. A new lifecycle
  run ID is created. An archive error or unsupported/full history blocks
  resume; the cap is 100 entries. Existing child, vault, ownership, budget and
  support gates are retained. Archive includes the snapshot's existing data:
  keep checkpoint access controls and retention appropriate for that data.

## Boundaries
The archive captures the snapshot as it existed immediately before resume;
pre-migration terminal snapshots and earlier support mutations cannot be
reconstructed. The checkpoint lock and resume claim are process-local, so
cross-worker races and power-loss durability are not proved. Agent run records
still have no per-attempt ID; a late event cannot be reliably attributed across
resume, and a resumed full outcome remains unknown. No live provider/execution
or independent expert review was available.

## Rollback
Back up checkpoint files, including the versioned history, before rollback.
Keep the history fields and enforce the same archive-before-resume and safety
checks; otherwise disable resume until an equivalent adapter is deployed.
Do not backfill old completions, issue TaskCompleted for halted/partial tasks,
or restore Ready-to-DONE. Older clients can continue reading legacy `status`,
but will not understand the new distinction. Re-run timeout terminal,
partial/halt event, archive-failure, support/vault/child-gate, resume and UI
regression tests before re-enabling resumed execution.
