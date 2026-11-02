# Sprint 1: support resolution

## Migration
No automatic rewrite of checkpoint files. Back up the checkpoint directory while
writers are quiesced. Existing `resolved` entries lacking an approved response
are projected as `legacy_unverified`; blocking records without sufficient
resolution evidence fail resume and require operator review. Their original
bytes remain intact. Unknown requirements stay pending until a type-specific
validator exists. The support UI treats unknown states as unknown.

Support response and closure for operator-response requirements are recorded
in one checkpoint update. Vault and budget cases need an approved response and
a live check before closure; resume checks the current vault/budget again.
The vault policy-error path returns 503 and keeps the room manually locked.
These are checks of the observed local process state, not a distributed vault
or a cross-worker checkpoint/resume lock. InvestigationLoop is unchanged.

## Rollback
Quiesce writers and back up the latest checkpoint files, then retain the new
fail-closed support/resume checks and vault policy-error guard during any app
rollback. Reverting to the old support code can treat rejected or unknown
responses as closed and must not be used with resume enabled. If retention is
impossible, disable resume until equivalent guards are in place. Do not restore
an old backup over newer records without reconciling intervening responses.
Re-run rejection, unknown-state, vault policy error and resume tests before
reopening traffic.
