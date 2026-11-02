# Sprint 1: minor approval hardening

## Migration
No persistent schema change. Deploy to all API and capability workers together.
Operator-provided names and verification flags are declarations, not authenticated
approvals; all declared minor investigations fail closed until a separate,
case-scoped independent approval system is implemented. Inform operators that
previously accepted exceptions will be denied. Historical ledger records remain
historical and must not be treated as proof of authorization.

## Rollback
Do not revert the fail-closed gate to the prior permissive implementation.
Rollback surrounding application changes only while retaining this gate (or an
equivalent independently reviewed fail-closed control) on every worker. If that
cannot be guaranteed, disable affected egress while rolling back. Verify the API
and direct runner both reject self-attested approvals after rollback.

## Known limitations
Declarations are process-local and can be removed with the existing clear API;
restart, other workers, replacing a declaration and ownership/clear governance
remain separate, unresolved safety risks. This change does not authenticate a
case, establish durable declarations or implement an exception workflow.
