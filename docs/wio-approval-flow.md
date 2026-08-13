# WIO approval and audit streams

YAWN reports two WIO streams over the same expected-day denominator. They are deliberately separate: **Approved** is official credit, while **Self-submitted** is an employee audit trail for comparing YAWN with a later official system. This change does not import or reconcile any external system.

## Roles and states

Employees submit an in-office claim to their effective line manager. It is `pending`, or `pending_assignment` when no effective manager exists, until a manager approves or rejects it. Manager approval records `approval_method: manager_approved`.

Line managers and HR/admin have no upstream manager assignment. Their own in-office submissions become `approved` immediately with `approval_method: self_approved`. The approver snapshot is their own membership. Dashboard and Reports explain why their two totals normally match.

`draft` and `not_required` claims receive no credit. In-office claims in `pending`, `pending_assignment`, `approved`, `rejected`, and `expired_pending` count in the self-submitted stream; only `approved` counts in the Approved stream.

## Formulas and legacy treatment

For each report range:

```text
Approved ratio       = approved in-office credit / expected-day denominator
Self-submitted ratio = submitted in-office credit / same expected-day denominator
```

Both displayed percentages are uncapped and round upward independently. Their balances are calculated independently against the same expected total. A legacy carry-forward row contributes its achieved credit to both streams because legacy daily review detail is unavailable.

## Self-approval correction window

For ten server-timed seconds after a self-approval, the record owner can use `POST /api/v1/work-in-office/{id}/undo-self-approval/` with its current `version`. It returns the record to `draft`, keeps the date, location, and note for correction, clears approval metadata, increments the version, and records an audit event. Invalid or expired requests return `400`; stale versions return `409`; other users cannot discover the record through this endpoint.

Manager approval undo remains limited to manager-approved records. Migrated self-approved records are outside this short undo window.

## API and CSV

Report and dashboard responses retain the Approved fields and add `self_submitted_days`, `self_submitted_ratio_display`, `self_submitted_percentage`, `self_submitted_balance`, and `self_approval_applies`. Ledger rows add `self_submitted_credit` and `approval_method`.

CSV exports include self-submitted credit, review state, approval method, and source after the existing Approved credit column. New finalized revisions persist both credits. Older frozen revisions derive a missing self-submitted value from their frozen review state; existing frozen JSON is never rewritten.
