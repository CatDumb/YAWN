# Subphase 3.0 Plan - Phase 2 Prerequisite Gate

Status: implemented; local validation evidence recorded 2026-07-24. RC acceptance remains blocked by live expiry, authorization-matrix, manual-accessibility, and owner evidence. The single-active-company invariant is reconciled through [Subphase 3.2R](subphase-3.2r-baseline-remediation-gate-plan.md).

## Outcome

Phase 2 identity and route hardening is complete, tested, and stable enough for every protected Phase 3 surface to rely on one authentication contract. No Phase 3 feature rollout starts before this gate passes.

## Dependencies

- Existing access-request, OTP, session, and membership flows.
- Existing Next.js and Django authentication integration.
- Agreed public `/` and protected `/dashboard` route split.

## Workstreams

### 1. Membership lifecycle

- Make inactive-membership reactivation an explicit state transition.
- Define authorized actors, validation, audit behavior, and duplicate/reactivation outcomes.
- Ensure inactive memberships cannot authenticate or retain protected access before reactivation.

### 2. OTP abuse controls

- Cover resend throttling, failed-attempt limits, expiration, replay, and lockout branches.
- Enforce a consistent 60-second resend interval in API behavior and UI feedback.
- Keep responses resistant to account enumeration.

### 3. SMTP timeout

- Put synchronous SMTP delivery behind a hard timeout.
- Return a controlled failure without hanging the request worker.
- Record operational diagnostics without logging OTPs or sensitive message content.

### 4. Browser authentication contract

- Keep `/` public and redirect authenticated completion to `/dashboard`.
- Require authentication for `/dashboard` and every future protected route.
- Restore session before protected data requests begin.
- Redirect invalid or expired sessions to `/` and clear stale client auth state.
- Align cookie, CSRF, origin, and error behavior between Next.js and Django.

### 5. Verification

- Add backend tests for membership, OTP, timeout, session, and authorization branches.
- Add one real-browser journey covering login, protected navigation, refresh, expiry, and logout.
- Confirm no protected-data flash occurs during session restoration.

## Deliverables

- Hardened authentication and membership behavior.
- Automated backend and browser contract tests.
- Updated auth documentation where behavior changed.
- Recorded proof that all gate checks pass in CI or the release-equivalent environment.

## Exit criteria

- Every item in the matching checklist is complete.
- Real-browser auth contract passes without manual cookie manipulation.
- Live session expiry is proven against a release-equivalent stack.
- Production company scope is deterministic and cannot become ambiguous.
- Known Phase 2 identity blockers are resolved or explicitly removed from Phase 3 scope by product approval.

## Out of scope

- Phase 3 WIO, ratio, approval, Planner, or dashboard feature implementation.
- Durable background email delivery, which remains Phase 7 work.
