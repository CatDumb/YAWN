# Subphase 3.2R Plan - Baseline Remediation Gate

Status: repair implementation locally validated 2026-07-24. The gate remains RC-acceptance blocked pending migration rehearsal, authorization/privacy browser proof, manual accessibility, and named-owner evidence before release.

## Outcome

The implemented authentication, fiscal-policy, ratio-foundation, and personal WIO slices satisfy their documented contracts and provide safe, versioned foundations for approval, reports, Planner, Dashboard, and finalization.

## Dependencies

- Existing Subphase 3.0-3.2 implementation and migrations.
- Product decisions recorded in `overall.md`.
- A migration strategy for existing companies, memberships, assignments, periods, rules, and WIO records.

## Workstreams

### 1. Authentication and company-scope acceptance

- Add a release-equivalent browser journey for live session expiry, protected navigation, refresh, and logout without protected-data flash.
- Enforce exactly one active company in production and at most one membership per user in that company.
- Fail closed on ambiguous legacy scope and provide an HR/admin repair path.
- Keep cross-company denial tests using inactive or isolated fixtures.

### 2. Fiscal lifecycle and cutoff

- Migrate reconciliation cutoff from date to timezone-aware timestamp.
- Default cutoff to the final microsecond of the fourteenth local calendar day after period end.
- Replace advisory derived state with one persisted, audited, idempotent transition coordinator.
- Define fixed expire/freeze/purge checkpoints and retry state so `Final` is written only after all checkpoints succeed.
- Preserve explicit audited reopen and correction-revision lineage.

### 3. Versioned policy and ratio foundation

- Effective-date employee base location, project base location, project assignment, manager assignment, and ratio rules where they affect historical meaning.
- Reject overlapping versions and incomplete Benched/Same-base/Different-base rule coverage at safe configuration boundaries.
- Make historical inputs immutable; corrections append audited versions.
- Refactor ratio calculation into a query-independent domain function receiving prepared policy, exclusion, approval, and as-of inputs.
- Calculate `approved days / raw expected-fraction sum`; display the denominator to two decimals and round percentage upward to two percentage decimals.
- Return every calendar day and all overlapping exclusion reasons without per-day query growth.
- Add the schema/contract needed for Subphase 3.4 to freeze finalized ledger revisions.

### 4. WIO state and concurrency repairs

- Require version on every mutable update and delete; return `409 Conflict` when missing or stale.
- Separate initial-submission eligibility from rejection-correction eligibility so a valid correction window is not blocked by an older work date.
- Implement audited HR/admin older-date creation/correction override with required reason and cutoff enforcement.
- Make rejection-deadline extension require an audit reason.
- Use distinct append-only audit events for draft save/delete, submission, Not-in-office correction, rejection, resubmission, and override; snapshot actor role/company context.
- Ensure approved records are immutable across every mutable field and service path.

### 5. Approval-owner foundation

- Make manager assignments effective-dated with at most one effective manager per employee/date.
- Add `Pending assignment` and `Expired pending` to the WIO state model.
- Snapshot approval owner on In-office submission.
- When no manager covers the work date, preserve submission as locked Pending assignment with zero credit.
- Backfill existing pending claims only when exactly one historical owner is provable; otherwise migrate them to Pending assignment for audited HR/admin resolution.

### 6. Personal WIO API and UI completion

- Use server/company date metadata for form defaults and deadline guidance; browser UTC never determines the default alone.
- Add month and custom-date-range filters while preserving location and review filters.
- Show note indicator and last update in index rows.
- Return exact outcome messages for draft, Not-in-office, Pending assignment, and Pending submissions; move focus to the message and clear transient highlight state.
- Require versions for draft deletion and all edits while preserving unsaved input on conflict.
- Show authorized audit actor role, action, timestamp, reason, and revision context.
- Add focused field errors, empty/loading states, keyboard behavior, and mobile coverage required by the original checklists.

## Migration and rollout

- Back up and inspect active company, membership, period, location, assignment, rule, and pending-claim data before migration.
- Abort migration on ambiguous active-company or overlapping effective-date data; emit a repair report rather than guessing.
- Backfill deterministic values transactionally.
- Deploy additive schema first where required, backfill, switch reads/writes, then enforce constraints.
- Keep rollback instructions for every data-shape transition.

## Testing strategy

- Preserve all existing suites.
- Add boundary, overlap, gap, historical-reproduction, percentage-rounding, cutoff retry, ambiguous-scope, missing-manager, rejected-correction, override, required-version, query-count, and audit tests.
- Execute the real-browser authentication and WIO journeys against a release-equivalent stack.
- Record commands, environment, timestamp, and results as acceptance evidence.

## Deliverables

- Corrected schema, services, APIs, UI behavior, migrations, and tests.
- Migration repair report and rollback notes.
- Acceptance evidence linked from the 3.0-3.2 and 3.2R checklists.
- Stable approval-owner, ratio-input, finalization, and localization-ready contracts for Subphase 3.3 onward.

## Exit criteria

- Every 3.2R checklist item passes.
- Original 3.0-3.2 acceptance checklists are reconciled with evidence.
- No unresolved authorization, historical-result, cutoff, state-machine, concurrency, or migration blocker remains.
- Subphase 3.3 may begin.

## Out of scope

- Manager queue and decisions, Reports UI/CSV, Planner, Dashboard composition, full Vietnamese catalogs, and production release.
