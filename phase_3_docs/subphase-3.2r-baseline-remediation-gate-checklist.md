# Subphase 3.2R Checklist - Baseline Remediation Gate

Status: local repair validation proven 2026-07-24; baseline release acceptance BLOCKED. This mandatory gate is not accepted until its required RC/browser/manual/migration evidence exists.

## Authentication and company scope

- [ ] Release-equivalent browser journey covers login, protected navigation, refresh, live expiry, and logout.
- [ ] Protected content never flashes before session resolution.
- [ ] Production enforces exactly one active company.
- [ ] Each user has at most one membership in that company.
- [ ] Ambiguous legacy scope fails closed and produces an actionable repair path.

## Fiscal and historical integrity

- [ ] Cutoff is an exact timezone-aware timestamp with the agreed default.
- [ ] Persisted lifecycle coordinator advances states idempotently and audits transitions.
- [ ] Final state waits for fixed expire/freeze/purge checkpoints; retry never duplicates effects.
- [ ] Base locations, project/manager assignments, and ratio rules preserve effective-dated history.
- [ ] Overlaps and incomplete required rule coverage are rejected.
- [ ] Historical corrections append versions instead of mutating used inputs.
- [ ] Finalized-ledger revision contract exists for Subphase 3.4.

## Ratio contract

- [ ] Query-independent domain calculation receives prepared inputs.
- [ ] Official denominator is raw expected-fraction sum.
- [ ] Percentage rounds upward to two percentage decimal places.
- [ ] Equation displays expected sum to two decimal places.
- [ ] Every calendar day and every overlapping exclusion reason is explained.
- [ ] Query count does not grow per ledger day.
- [ ] Zero denominator returns `N/A`.

## WIO correctness

- [ ] Every mutable update and delete requires version and returns `409` when missing or stale.
- [ ] Valid rejected correction bypasses the closed initial-submission window.
- [ ] Rejection correction still respects its own deadline and fiscal cutoff.
- [ ] HR/admin older-date override and deadline extension require audited reasons.
- [ ] Approved records are immutable across all fields and paths.
- [ ] Material transitions use distinct audit events with historical actor context.
- [ ] Manager assignment is effective-dated and non-overlapping.
- [ ] Submission snapshots exactly one manager or becomes Pending assignment.
- [ ] Ambiguous existing pending claims migrate to Pending assignment without guessed ownership.

## Personal WIO completion

- [ ] Form default/date guidance uses server company time.
- [ ] Month, custom range, location, and review filters work.
- [ ] Rows show required note indicator and last update.
- [ ] Outcome-specific focused messages and transient highlighting work.
- [ ] Conflict recovery preserves input.
- [ ] Audit timeline shows actor role, action, time, reason, and revision context.
- [ ] Mobile, keyboard, form-error, loading, empty, and status-announcement checks pass.

## Migration and exit gate

- [ ] Migration detects ambiguous data before enforcing constraints.
- [ ] Deterministic backfill, rollout order, repair report, and rollback notes are verified.
- [ ] Existing backend/frontend suites remain green.
- [ ] New boundary, history, concurrency, cutoff, ownership, and browser tests pass.
- [ ] Acceptance evidence is recorded.
- [ ] Subphase 3.3 may begin.

## 2026-07-24 reconciled baseline evidence

Environment: local Windows; backend `config.settings.test`; operator: Codex; artifacts: coverage XML/HTML under local temporary artifacts, Playwright output, generated schema parity file. Commands/results: backend full suite 114/114 at 83.43%; Ruff check/format passed; migration drift and application passed; Django check passed; OpenAPI validation passed with one existing serializer type-hint warning and checked-in schema parity; frontend 37/37 with all 70% coverage thresholds; local Playwright 2/2.

- **PROVEN locally:** repaired company scope, fiscal/cutoff/history, raw-denominator ratio, WIO version/correction/ownership, and local WIO browser behavior.
- **OPEN:** explicit original-3.0–3.2 item-to-evidence mapping in the release candidate.
- **BLOCKED:** RC live session-expiry test, production-like migration rehearsal/repair report/rollback validation, manual mobile/keyboard/screen-reader review, named owners, and acceptance sign-off. All acceptance boxes remain unchecked deliberately.
