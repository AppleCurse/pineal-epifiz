# Sprint 2 — task-scoped run display

## Migration
No persisted data or API shape change. Deploy the UI after confirming WS
snapshot/result frames include `task_id` and `runs`. Missing task identifiers
are ignored; task changes discard the previous task's runs rather than merging
them. Rack availability remains separate: `READY` never implies a finished
run. War Room, Atlas and LiveControlPanel derive completion only from a matching
task frame and its agent run. A run's explicit foreign task/agent identity is
rejected. The server currently serializes task identity on the containing frame,
not each run; this check does not prove durability or disambiguate concurrent
attempts of the same task. Task selection still follows incoming WS frames.

## Rollback
No data rollback is required. Do not restore the Ready-to-DONE mapping; if the
new UI must be rolled back, preserve the task-bound status adapter or hide
completion badges. Re-test no-run Ready, mismatched task, unknown status and
valid completed-run cases. This does not modify agent decision semantics.
