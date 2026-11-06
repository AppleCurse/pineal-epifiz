# Sprint 3 — `data_confidence`, `input_data_present`, and `evidence_verification_status`

## Migration
`POST /api/hook/generate` and `UncertaintyReport` separate input presence from
corroborated evidence verification:

- `input_data_present: bool`: `True` only when at least one substantive,
  non-placeholder input field is present (`UncertaintyEngine._value_bears_evidence`).
  Whitespace-only or placeholder strings (`"bilinmiyor"`, `"yok"`, `"-"`, etc.)
  evaluate to `False`.
- `evidence_verification_status`: `"verified" | "unverified" | "not_applicable" | "unknown"`.
- In Hook Studio, `data_confidence` and `evidence_verification_status == "verified"`
  require verified task-level `VerifierReport` provenance without unverified raw
  payload overrides and with valid positive model confidence.
- Legacy records carrying `data_confidence=True` without explicit verification
  proof map to `evidence_verification_status="unknown"` (or `"unverified"`),
  never `"verified"`.
- SpiderFoot UI displays an explicit unverified warning whenever
  `evidence_verification_status !== "verified"` or `data_confidence === false`.

## Rollback
If rolling back downstream changes, keep the separation between
`input_data_present` and `evidence_verification_status`. Do not restore the
behavior where raw unverified bio/profile fields set `data_confidence=True` or
suppress the unverified warning in SpiderFoot. Re-run `tests/unit/test_hook_studio.py`,
`tests/unit/test_uncertainty_data_confidence_gate.py`, and frontend regression
tests after any rollback.
