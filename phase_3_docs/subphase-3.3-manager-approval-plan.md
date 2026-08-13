# Subphase 3.3 Plan - Manager Approval

Status: implemented; local validation evidence recorded 2026-07-24. Acceptance remains blocked by the mandatory 3.2R release-candidate gate and required manual/owner evidence.

## Outcome

Shared protected app foundation exists, Pending assignment exceptions are safely resolved, and authorized managers can review only assigned employees' pending office claims, approve or reject them safely, undo accidental approval for 10 seconds, and handle reconciliation without silent decisions.

## Dependencies

- Subphase 3.2R fully accepted, including WIO state/version repairs, effective-dated manager ownership, Pending assignment, exact cutoff, and finalization coordinator contracts.
- Shared localization-key and locale-resolution conventions chosen before user-facing approval copy is added.

## Workstreams

### 1. Shared protected app foundation

- Establish one reusable protected-session boundary for all Phase 3 app routes.
- Build the responsive navigation frame, route metadata, role-aware visibility hooks, and shared page/loading/error primitives.
- Keep direct route and API authorization independent from navigation visibility.
- Defer Two Horizons Dashboard composition and final shell polish to Subphase 3.6.

### 2. Assignment-scoped authorization

- Snapshot manager ownership effective on WIO work date at submission.
- Require manager's current membership and authorization when acting.
- Scope list, detail, count, and decision APIs by company and snapped assignment.
- Let HR/admin reassign a pending claim only with an audit reason.
- Give HR/admin an actionable exception view for Pending assignment without exposing it to manager queues.
- Move Pending assignment to Pending only after an explicit audited assignment.
- Never migrate historical decisions when later assignments change.

### 3. Queue and decisions

- Build `/approvals` for eligible managers only.
- Sort oldest submission first; during reconciliation place prior-period unresolved claims first.
- Paginate at 50 claims per page and design for up to 100 assigned employees.
- Show employee, work date, base location, submitted time, and note indicator.
- Make approval one click; require non-empty rejection reason.
- Apply a decision only while state is Pending and version is current.

### 4. Undo and correction

- Expose `Undo approval` for 10 seconds after success.
- Enforce the undo deadline on the server using the approval timestamp; hiding the client action is not enforcement.
- Write undo as a separate reversal audit event; never delete approval history.
- After window closes, allow reversal only through audited HR/admin correction.
- Return conflict feedback when another actor already changed claim.

### 5. Reconciliation and cutoff

- Never auto-approve or auto-reject.
- Keep unresolved claims actionable through Reconciliation and ratio provisional.
- Register an idempotent finalization step that converts unresolved Pending and Pending assignment claims to Expired pending with zero contribution.
- Require audited HR/admin reopen/correction after finalization.

### 6. Awareness, localization contract, and rejection email

- Add exact pending-count endpoint and `99+` visual cap with exact accessible label.
- Refresh count on navigation/focus and after a decision.
- Display age of oldest pending claim.
- Send rejection-only action email with date, state, secure link, and no sensitive note content.
- Store user-facing approval copy as translation keys/parameters, resolve locale-aware dates centrally, and make email templates ready for English/Vietnamese catalogs.
- Reuse synchronous mail timeout protections until durable delivery arrives in Phase 7.

## Testing strategy

- Build authorization matrix tests for employee, assigned manager, unassigned manager, inactive manager, HR/admin, cross-company, and historical reassignment cases.
- Test concurrent decisions, undo timing, cutoff transitions, pagination/order, and audit append behavior.
- Test Pending assignment resolution, server-enforced undo boundary, finalization retry, protected shell behavior, and direct route denial.
- Test email content and absence of note leakage.
- Contract-test translation keys, parameters, and locale-aware date rendering without requiring the final Vietnamese catalog.

## Deliverables

- Scoped approval APIs and page.
- Shared protected app foundation consumed by Subphases 3.4-3.7.
- Pending badge/count contract.
- HR/admin Pending assignment resolution through Django Admin or an equally scoped internal surface.
- Approval, rejection, reversal, reassignment, expiration, and correction audit support.
- Localization-ready rejection email.

## Exit criteria

- No actor can list or act on a claim outside authorized scope.
- Decision races resolve once without lost or contradictory audit events.
- Ratio consumers receive reliable approved/zero/provisional states.

## Out of scope

- Batch approval, advanced filters, saved views, workflow metrics, approval emails, and manager digests.
