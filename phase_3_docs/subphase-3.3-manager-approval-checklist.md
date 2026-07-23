# Subphase 3.3 Checklist - Manager Approval

Status: local implementation validation proven 2026-07-24; release acceptance BLOCKED by mandatory 3.2R RC evidence and manual/owner evidence.

Dependency gate: every Subphase 3.2R item passes before work begins.

## Shared app foundation

- [ ] One protected-session boundary covers all Phase 3 app routes.
- [ ] Responsive navigation frame and shared page/loading/error primitives exist.
- [ ] Navigation visibility and direct route/API authorization are tested independently.
- [ ] Two Horizons Dashboard remains deferred to Subphase 3.6.

## Scope and authorization

- [ ] Submission snapshots manager assignment effective on work date.
- [ ] Manager assignment has at most one effective owner per employee/date.
- [ ] Missing coverage produces Pending assignment and no manager visibility.
- [ ] HR/admin assignment moves claim to Pending with required reason and audit event.
- [ ] List, detail, count, approve, reject, and undo enforce assignment scope.
- [ ] Acting manager must retain active authorized membership.
- [ ] Cross-company and unassigned-manager access is denied.
- [ ] HR/admin reassignment requires reason and audit event.
- [ ] Later assignment changes do not move historical decisions.

## Queue and decisions

- [ ] Queue is manager-only and oldest-first.
- [ ] Prior-period unresolved claims lead during reconciliation.
- [ ] Server pagination returns 50 claims per page.
- [ ] Rows show all required summary fields.
- [ ] Approve is one click without confirmation.
- [ ] Reject requires a reason.
- [ ] Decision succeeds only from current Pending state/version.
- [ ] Concurrent second decision returns conflict and preserves first result.

## Undo, cutoff, and awareness

- [ ] Approval exposes a 10-second undo action.
- [ ] Server rejects undo after the 10-second deadline regardless of client state.
- [ ] Undo appends reversal history instead of deleting approval.
- [ ] Post-window reversal requires audited HR/admin correction.
- [ ] Idempotent finalization step expires unresolved Pending and Pending assignment claims with zero contribution.
- [ ] System never auto-approves or auto-rejects.
- [ ] Badge refreshes on navigation, focus, and decisions.
- [ ] Visual badge caps at `99+`; accessible label gives exact count.
- [ ] Queue displays age of oldest pending claim.

## Email and exit gate

- [ ] Rejection email includes date, state, and secure link.
- [ ] Rejection email excludes approver note and other sensitive content.
- [ ] Approval UI/email copy uses translation keys, parameters, and locale-aware date contracts.
- [ ] No approval email is sent.
- [ ] Authorization matrix, race, undo, cutoff, pagination, audit, and email tests pass.
- [ ] Subphase 3.4 may begin.

## 2026-07-24 evidence classification

Environment: local Windows, Django test settings and jsdom component suite; operator: Codex; artifacts: local coverage XML/HTML and frontend coverage output. Backend full suite passed 114/114; frontend 37/37 passed. Focused page contracts cover manager approve/reject/undo and HR audited assignment.

- **PROVEN locally:** assignment-scoped queue/decision/undo/finalization/email contracts and manager/HR UI state transitions.
- **OPEN:** full checklist acceptance mapping and release-candidate email/authorization matrix evidence.
- **BLOCKED:** 3.2R RC gate, manual manager workflow/accessibility pass, named owner, and sign-off. Boxes remain unchecked because local tests do not accept the gate.
