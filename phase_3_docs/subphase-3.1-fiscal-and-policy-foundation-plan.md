# Subphase 3.1 Plan - Fiscal and Policy Foundation

Status: implemented; local validation evidence recorded 2026-07-24. RC acceptance remains blocked by migration rehearsal, calculator parity, manual accessibility, and owner evidence. Cutoff precision, persisted lifecycle coordination, versioned base-location history, complete coverage enforcement, query-independent calculation, agreed ratio semantics, and finalized-revision foundations reconcile through [Subphase 3.2R](subphase-3.2r-baseline-remediation-gate-plan.md).

## Outcome

System can reproduce an employee's expected-office obligation for any range within one fiscal period and explain every calendar day. HR/admin can safely configure fiscal periods, assignments, rules, and exclusions through Django Admin.

## Dependencies

- Subphase 3.0 gate complete.
- Existing company, employee, membership, manager-assignment, and audit models understood.
- Company timezone fixed to `Asia/Ho_Chi_Minh`.

## Workstreams

### 1. Fiscal periods

- Add `FiscalPeriod` with name, start/end dates, exact timezone-aware reconciliation cutoff, and persisted Upcoming/Active/Reconciliation/Final state.
- Prevent overlap and enforce at most one Active period.
- Advance normal status through an idempotent audited coordinator when dates make transitions due.
- Write Final only after registered finalization steps succeed.
- Support exceptional audited reopen/correction as linked revisions.
- Provide reviewed clone-from-previous-period admin action.

### 2. Policy and assignment data

- Add base locations and projects.
- Version employee and project base-location assignments where changes affect historical status.
- Add effective-dated employee project assignments.
- Derive Benched, Same base, or Different base from assignment and employee/project locations.
- Add effective-dated `ProjectStatusRule` coverage for all three statuses.
- Reject gaps and overlaps; protect historically used versions from edits or deletion and append corrected versions.

### 3. Eligibility exclusions

- Add company-wide public holidays.
- Add employee approved-leave and remote-work-exception ranges.
- Deduplicate overlapping exclusion sources while retaining explanation reasons.
- Recalculate non-final periods immediately; require audited reopen/correction for final periods.

### 4. Pure ratio domain service

- Accept prepared employee policy history, one fiscal period/range, exclusions, approvals, and as-of date without querying persistence.
- Produce a row for every calendar day with eligibility, reason, status/rule version, expected fraction, approval credit, and rounding inputs.
- Sum expected fractions without integer ceiling; divide approved days by the raw sum and round displayed percentage upward to two decimal places.
- Return `N/A` when expected days are zero.
- Keep projection logic outside this service.
- Define the finalized per-day ledger revision contract used by Reports after cutoff.

### 5. Administration and audit

- Configure Django Admin forms, list views, validation, and permissions.
- Audit changes that affect historical or finalized calculations.
- Display effective dates and conflict errors clearly enough for safe HR operation.

## Testing strategy

- Unit-test weekday, holiday, leave, exception, assignment, rule, fractional sum, and rounding behavior.
- Test fiscal boundaries, leap days, timezone cutoffs, zero denominator, gaps, overlaps, and historical immutability.
- Add integration tests proving admin validation and reproducible results after future configuration changes.

## Deliverables

- Schema and migrations for fiscal/policy records.
- Django Admin configuration.
- Pure ratio calculator and per-day ledger contract.
- Fixture/factory coverage for later WIO and report subphases.

## Exit criteria

- Calculator results are deterministic and fully explained per day.
- Invalid period, assignment, and rule configurations cannot be saved.
- Historical calculations remain reproducible after future-dated configuration changes.

## Out of scope

- Employee report UI, CSV export, WIO entry, approvals, or Planner projection.
- Multi-project weighting and half-day office credit.
