# Subphase 3.0 Checklist - Phase 2 Prerequisite Gate

Status: local implementation validation proven 2026-07-24; release acceptance BLOCKED. Do not mark this checklist complete until the linked [3.2R remediation](subphase-3.2r-baseline-remediation-gate-checklist.md) supplies release-candidate live-expiry and company-scope evidence.

## Membership and authentication

- [ ] Inactive-membership reactivation is explicit, authorized, and audited.
- [ ] Inactive users cannot authenticate or access protected APIs.
- [ ] Public `/` and protected `/dashboard` behavior matches product contract.
- [ ] Successful login lands on `/dashboard`.
- [ ] Invalid or expired sessions redirect to `/`.
- [ ] Logout clears server and client authentication state.
- [ ] Protected pages wait for session restoration before loading data.

## OTP and email safety

- [ ] OTP resend interval is consistently 60 seconds in backend and UI.
- [ ] Throttle, attempt-limit, expiry, replay, and lockout branches have tests.
- [ ] OTP responses do not enable account enumeration.
- [ ] Synchronous SMTP delivery has a hard timeout.
- [ ] SMTP timeout produces a controlled user-facing failure.
- [ ] Logs contain no OTP or sensitive email content.

## Contract verification

- [ ] Cookie, CSRF, origin, and auth error handling agree across Next.js and Django.
- [ ] Backend identity and authorization test suites pass.
- [ ] Real-browser login, refresh, protected navigation, expiry, and logout journey passes.
- [ ] No protected content flashes before auth resolution.
- [ ] Production rejects a second active company and ambiguous membership scope.
- [ ] Changed auth behavior is documented.

## Exit gate

- [ ] All Phase 2 hardening blockers are closed.
- [ ] CI or release-equivalent evidence is recorded.
- [ ] Subphase 3.0 acceptance is reconciled through 3.2R.

## 2026-07-24 evidence classification

Environment: local Windows release-like test stack; operator: Codex; artifacts: Playwright output and backend coverage XML in local temporary artifacts. `npm run test:e2e` passed 2/2 local browser journeys; `uv run pytest --cov-report=xml:...` passed 114/114 at 83.43% coverage.

- **PROVEN locally:** authentication/session implementation, OTP/authorization regression coverage, and login/refresh/logout browser path.
- **OPEN:** explicit checklist acceptance mapping through 3.2R.
- **BLOCKED:** release-candidate live-expiry journey, CI/RC artifact, and named release owner. Boxes remain unchecked because local evidence is not RC acceptance.
