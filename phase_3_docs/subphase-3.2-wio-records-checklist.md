# Subphase 3.2 Checklist - WIO Records

Status: local implementation validation proven 2026-07-24; release acceptance BLOCKED. Reconcile this checklist only after [3.2R](subphase-3.2r-baseline-remediation-gate-checklist.md) proves repaired concurrency, correction, ownership, audit, migration, and UI behavior in a release candidate.

## Model and rules

- [ ] Database enforces one current WIO record per employee/date.
- [ ] Record has explicit state, version, timestamps, and required snapshots.
- [ ] Note accepts plain text only, is limited to 500 characters, and appears only for In office.
- [ ] Today and eligible yesterday are accepted.
- [ ] Future, ineligible, and closed older dates are rejected with useful reasons.
- [ ] Server/company time enforces deadlines.

## Lifecycle

- [ ] Visiting new-entry page creates no record.
- [ ] Explicit Save draft creates a partial reserving record.
- [ ] Draft can be continued and deleted.
- [ ] In-office submission becomes Pending and locked.
- [ ] Missing effective manager preserves submission as locked Pending assignment.
- [ ] Not-in-office submission gets zero credit and no approval task.
- [ ] Not-in-office record remains editable only through normal deadline.
- [ ] Rejected record keeps date fixed and allows valid correction.
- [ ] Rejected correction uses its own deadline even when normal submission window is closed.
- [ ] Rejected In-office resubmission returns to Pending.
- [ ] Rejected record changed to Not in office closes with zero credit.
- [ ] Approved records are immutable.
- [ ] Every material transition writes an audit event.
- [ ] Older-date HR/admin override and deadline extension require audited reasons.

## APIs and UI

- [ ] Personal create/index/detail/edit/delete APIs enforce ownership.
- [ ] Index defaults to current month and newest first.
- [ ] Date, location, and review filters work.
- [ ] Month and custom-range filtering match the overall contract.
- [ ] Draft and rejected attention section works.
- [ ] Post-save status message and row highlight identify affected record.
- [ ] Status copy distinguishes draft, Not-in-office, Pending assignment, and Pending outcomes and receives focus.
- [ ] `409 Conflict` preserves input and offers latest-state reload.
- [ ] Every mutable update and delete requires version.
- [ ] Detail shows complete authorized audit timeline.
- [ ] Form defaults use server company date rather than browser UTC alone.

## Quality and exit gate

- [ ] Transition, deadline, uniqueness, auth, snapshot, and concurrency tests pass.
- [ ] Browser journeys cover In office, Not in office, draft, correction, and duplicate paths.
- [ ] Accessibility checks pass for form errors, focus, and status announcements.
- [ ] Subphase 3.2 acceptance and the full 3.2R gate pass before Subphase 3.3 begins.

## 2026-07-24 evidence classification

Environment: local Windows browser/test stack; operator: Codex; artifacts: Playwright output and backend coverage XML. `uv run pytest --cov-report=xml:...` passed 114/114 at 83.43%; `npm run test:e2e` passed employee WIO lifecycle.

- **PROVEN locally:** WIO lifecycle, version/conflict, correction, ownership, audit, and duplicate-path automation.
- **OPEN:** reconciliation of original 3.2 items against 3.2R evidence.
- **BLOCKED:** RC browser accessibility/manual form-error and announcement evidence, migration rehearsal/rollback evidence, and named acceptance owner. Boxes remain unchecked because local results are not release acceptance.
