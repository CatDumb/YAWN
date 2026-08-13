# Subphase 3.8 Plan - Hardening and Release Gate

Status: hardening implementation and local automated evidence complete as of 2026-07-24; release acceptance remains blocked by required release-candidate, manual, operational, owner, and sign-off evidence.

## Outcome

Complete Phase 3 slice is secure, consistent, observable, accessible, responsive, and proven through required end-to-end journeys. Release proceeds only with documented evidence and no unresolved critical gate failures.

## Dependencies

- Subphases 3.0-3.7 and mandatory 3.2R accepted in release candidate environment.
- Production-like fiscal, assignment, rule, exclusion, WIO, approval, and intention fixtures.
- Migration fixtures containing legacy ambiguous company scope, overlapping historical data, and unowned pending claims.

## Workstreams

### 1. Authorization and privacy matrix

- Exercise anonymous, employee, assigned/unassigned/inactive manager, HR/admin, and cross-company access across every route and API.
- Verify ownership for WIO, report, export, and Planner resources.
- Verify production rejects a second active company and APIs fail closed on ambiguous membership scope.
- Confirm navigation visibility never substitutes for backend enforcement.
- Inspect logs, errors, email, CSV, and telemetry for private Planner content, notes, OTPs, or unrelated account data.

### 2. Integrity and concurrency

- Race duplicate WIO/intention creation, WIO edits, approval decisions, undo, bulk intentions, and preference updates.
- Verify database constraints, versions, `409 Conflict` recovery, atomic bulk operations, and append-only audits.
- Require versions on all mutable update/delete paths and test omission as well as mismatch.
- Test server-time deadlines around company midnight, rejection windows, reconciliation, and final cutoff.
- Test Pending assignment creation/resolution and deterministic ownership across assignment changes.

### 3. Calculation and export verification

- Reconcile raw-denominator/upward-rounded summary, full ledger, Dashboard, projection, finalized revision, and CSV against controlled fixtures.
- Cover rule/assignment/base changes, Benched periods, exclusions, rounding, zero denominator, pending/rejected/expired claims, and finalized history.
- Prove Final reads frozen data and audited correction creates a linked successor revision.
- Validate localized headers, encoding, formula-injection defense, exact range, and private-field exclusion.

### 4. Accessibility and responsive review

- Run automated checks plus manual keyboard and screen-reader journeys.
- Verify focus, landmarks, headings, dialog/drawer behavior, status announcements, non-color state meaning, touch targets, reduced motion, and 200% zoom reflow.
- Test mobile/desktop, English/Vietnamese, Light/Dark/System, long names, and expanded copy.

### 5. Resilience, performance, and observability

- Test partial Dashboard/API failure, retries, timeouts, stale data labeling, email failure, export failure, and safe recovery.
- Fault-inject finalization between claim expiration, ledger freeze, and Planner purge; retry must converge exactly once before state becomes Final.
- Measure approval queue, month heatmap, ledger, export, and projection at target data sizes.
- Add actionable monitoring for WIO, approval, ratio, export, projection, purge, and cutoff failures without sensitive content.
- Verify migrations, deployment order, rollback approach, jobs, and operational runbooks.

### 6. Required acceptance journeys

Execute every journey from `overall.md`, including live session expiry; raw fractional denominator consistency; closed-date rejection correction; Pending assignment; exactly-once finalization; frozen revision history; and single-company enforcement.

### 7. Release decision

- Classify findings by severity and assign owners.
- Block release on security/privacy breach, data corruption, authorization bypass, incorrect fiscal result, failed irreversible cutoff/purge behavior, or inaccessible critical journey.
- Record accepted residual risks and rollback triggers.
- Obtain product/engineering release sign-off.

## Deliverables

- Automated hardening suites and manual test evidence.
- 3.0-3.2/3.2R acceptance reconciliation and legacy-data migration rehearsal evidence.
- Performance results, accessibility report, security/privacy matrix, and observability/runbook updates.
- Release decision with defects, residual risks, owners, and rollback criteria.

## Exit criteria

- All checklist gates and required acceptance journeys pass.
- No open release-blocking issue remains.
- Production migration, monitoring, support, and rollback readiness are documented and approved.

## Out of scope

- Deferred Phase 4-8 features listed in `overall.md`; hardening does not expand Phase 3 scope.
