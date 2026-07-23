# Subphase 3.2 Plan - WIO Records

Status: implemented; local validation evidence recorded 2026-07-24. RC acceptance remains blocked by migration rehearsal, privacy/authorization browser evidence, manual accessibility, and owner evidence. Required versions, correction-window separation, audited overrides, approval-owner snapshots, Pending assignment, company-date defaults, full filters, outcome feedback, and richer audit history reconcile through [Subphase 3.2R](subphase-3.2r-baseline-remediation-gate-plan.md).

## Outcome

Employees can create, save, submit, inspect, correct, and audit personal Work-in-office records under server-enforced date and state rules. Positive office claims become Pending; Not-in-office records close with zero credit and no approval task.

## Dependencies

- Subphase 3.1 fiscal periods, eligibility, assignment snapshots, and audit foundations.
- Authenticated employee identity and protected-route contract from Subphase 3.0.

## Workstreams

### 1. Record model and state machine

- Add `WorkInOfficeRecord` with employee, work date, location choice, review state, optional approver note, version, timestamps, and relevant policy/assignment snapshots.
- Enforce one current record per employee/date in the database.
- Model Draft, Pending assignment, Pending, Approved, Rejected, Not required, and Expired pending transitions explicitly.
- Keep material transition history in append-only audit events.

### 2. Date and eligibility rules

- Allow today and yesterday until 23:59 company time.
- Reject future dates and direct users to Planner.
- Reject ineligible dates with an exclusion reason.
- Reserve older-date creation for audited HR/admin override.
- Enforce all deadlines using server time in `Asia/Ho_Chi_Minh`.

### 3. Draft and submission behavior

- Create drafts only after explicit `Save draft`.
- Permit partial draft data while reserving employee/date.
- Allow draft edit/delete and block duplicate records.
- Send In-office submission to Pending and lock it.
- If no manager is effective on the work date, preserve submission as locked Pending assignment with zero credit.
- Save Not-in-office as zero credit with review state Not required; allow edits until deadline.

### 4. Rejection correction contract

- Keep work date immutable after rejection.
- Permit location and note changes until the rejection correction deadline.
- Resubmitting In office returns to Pending.
- Changing to Not in office closes rejection with zero credit.
- Preserve original values, reason, edits, and resubmission in audit history.
- Support audited HR/admin extension without exceeding final reconciliation rules.
- Evaluate rejected correction against its correction deadline rather than the original submission window.

### 5. Personal APIs and UI

- Build create, index, detail, edit, delete-draft, and audit-timeline endpoints.
- Build `/work-in-office`, `/work-in-office/new`, and `/work-in-office/[id]`.
- Default index to current month, newest first; support date, location, and review filters.
- Show drafts/rejections in an attention section.
- Return to index with focused status message and highlighted affected row after save/submit.
- Preserve input and return `409 Conflict` guidance on stale versions.
- Require version on every mutable update and delete.
- Use server/company date metadata for client defaults and deadline guidance.

## Testing strategy

- Unit-test every allowed and forbidden state transition.
- Test date boundaries around company midnight and reconciliation cutoff.
- Test database uniqueness, authorization ownership, snapshot immutability, stale writes, and audit completeness.
- Add browser journeys for In office, Not in office, draft lifecycle, rejection editing, and duplicate blocking.

## Deliverables

- WIO schema, constraints, state service, APIs, and personal pages.
- Employee-visible audit timeline.
- Stable contracts consumed later by approval, reports, heatmap, and dashboard work.

## Exit criteria

- Employee can finish all personal lifecycle paths without privileged intervention.
- Invalid dates, transitions, duplicates, and stale writes fail safely.
- Submitted office claims are ready for Subphase 3.3 manager review.

## Out of scope

- Approval queue and decisions, evidence, endorsers, seat choice, batch entry, and search.
