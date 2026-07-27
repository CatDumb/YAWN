# Subphase 3.8 Checklist - Hardening and Release Gate

Status: local hardening validation proven 2026-07-24; release not approved. Every unchecked box is either OPEN pending RC evidence or BLOCKED by unavailable RC/manual/owner/sign-off inputs.

## Security, privacy, and integrity

- [ ] Subphase 3.2R evidence is complete and reconciled with 3.0-3.2 checklists.
- [ ] Full role/company authorization matrix passes for every route/API.
- [ ] Production rejects a second active company and ambiguous membership scope fails closed.
- [ ] WIO, report/export, and Planner ownership tests pass.
- [ ] Logs, errors, email, CSV, and telemetry expose no prohibited content.
- [ ] Duplicate WIO/intention races are stopped by database constraints.
- [ ] Versioned write and `409 Conflict` recovery tests pass.
- [ ] Version omission is rejected on every mutable update/delete path.
- [ ] Approval races and undo timing preserve one coherent history.
- [ ] Bulk intentions are atomic under failure/concurrency.
- [ ] Company-time deadline and cutoff boundary tests pass.
- [ ] Pending assignment has no manager visibility and resolves only through audited HR/admin action.

## Calculation and export

- [ ] Summary, ledger, Dashboard, finalized revision, and CSV factual totals match using raw expected denominator and upward two-decimal percentage.
- [ ] Projection remains separate from verified ratio.
- [ ] Historical rule/assignment/base changes reproduce prior results.
- [ ] Final reports use frozen revision; correction creates linked successor without erasing history.
- [ ] Benched, exclusions, fractional rounding, zero denominator, pending, expired, and final states pass.
- [ ] CSV localization, encoding, formula-injection, range, and privacy tests pass.

## Accessibility and responsive quality

- [ ] Critical workflows are keyboard complete.
- [ ] Screen-reader journeys and status announcements pass.
- [ ] Heatmap and all states work without color alone.
- [ ] Focus, landmarks, headings, drawer/dialog, and undo behavior pass.
- [ ] 200% zoom has no page-level horizontal scrolling.
- [ ] Touch targets and reduced motion meet requirements.
- [ ] Mobile/desktop, English/Vietnamese, and Light/Dark/System combinations pass.

## Resilience and operations

- [ ] Dashboard partial failures and retries stay isolated; unexpected frontend failures show localized fallback copy and retain private-free Sentry diagnostics.
- [ ] Timeouts, email/export failures, stale conflicts, purge, and cutoff recover safely.
- [ ] Fault-injected finalization retries expiration, ledger freeze, and purge exactly once before writing Final.
- [ ] Target-size queue, heatmap, ledger, export, and projection performance is acceptable.
- [ ] Monitoring covers WIO, approval, ratio, export, projection, purge, and cutoff failures.
- [ ] Migrations, deployment order, rollback, jobs, and runbooks are verified.

## End-to-end acceptance

- [ ] In-office submission, manager approval, ratio, and heatmap journey passes.
- [ ] Rejection email/UI, correction, and resubmission journey passes.
- [ ] Rejected correction remains valid through its correction deadline after normal submission closes.
- [ ] Not-in-office zero-credit/no-approval journey passes.
- [ ] Draft save/continue/delete and duplicate-block journey passes.
- [ ] Historical calculation preservation journey passes.
- [ ] Benched calculation journey passes.
- [ ] Holiday/leave/remote-exception explanation journey passes.
- [ ] Single/bulk/recurring Planner projection-only journey passes.
- [ ] Planner skip/replace conflict and atomicity journey passes.
- [ ] Final cutoff intention purge and pending expiration journey passes.
- [ ] Missing-manager submission, Pending assignment, audited assignment, and approval journey passes.
- [ ] Raw fractional denominator and upward percentage rounding match every consumer.
- [ ] Frozen result and audited correction-revision journey passes.
- [ ] Live session-expiry and single-active-company journeys pass.
- [ ] CSV parity and private-field exclusion journey passes.
- [ ] Theme/language persistence before and after sign-in journey passes.
- [ ] Unauthorized employee/manager/admin route and API journey passes.
- [ ] Keyboard/screen-reader non-color heatmap journey passes.

## Release gate

- [ ] No open security/privacy, corruption, authorization, fiscal-result, cutoff/purge, or critical-accessibility blocker remains.
- [ ] Residual risks, owners, and rollback triggers are recorded.
- [ ] Product and engineering sign-off is recorded.
- [ ] Phase 3 is approved for release.

## 2026-07-24 evidence classification and release decision

Environment: local Windows release-like test stack; operator: Codex; artifacts: local backend coverage XML/HTML, frontend coverage output, generated schema parity file, and Playwright output. Automated checks passed: backend 114/114 at 83.43%; frontend 37/37 with all configured coverage thresholds; format/i18n/lint/typecheck/build; migrations/schema parity; local Playwright 2/2.

- **PROVEN locally:** automated integrity, ratio/export, failure/retry, performance, localization, page-contract, WIO browser, and schema/migration checks recorded in the [release evidence ledger](subphase-3.8-release-evidence.md).
- **OPEN:** full RC authorization/privacy matrix, complete E2E journey set, and RC deployment/rollback artifacts.
- **BLOCKED:** RC environment/build SHA; manual keyboard/screen-reader/200% zoom/touch/theme-language matrix; production-like migration rehearsal/repair report; named product, engineering, QA/release, operations, and rollback owners; product/engineering sign-off. No release approval is claimed.
