# Sprint 2 — interpreter response status

## Migration
`POST /api/experimental/interpreter/execute` changes its status contract.
Clients must handle `empty_response`, `response_received`, `code_proposed`,
`execution_unknown`, and `error`; the first four are not proof of execution.
Deploy client support before the backend and monitor unknown status handling.
There is no persistent schema migration. Old `success` records or log lines
cannot be reclassified as executed without separate evidence. Open Interpreter
remains disabled by default and `auto_run` remains forced off.

## Rollback
Retain this status mapping (or an equivalent fail-closed adapter) when rolling
back other changes. Do not restore the old success assertion for empty or
unproven responses. If a consumer cannot be updated, disable the interpreter
endpoint until it supports the new statuses. Re-run gate, empty-response, code
proposal and provider-error tests before enabling it.
