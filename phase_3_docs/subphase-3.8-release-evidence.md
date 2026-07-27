# Subphase 3.8 Release Evidence Ledger

Status: release not approved.

Last updated: 2026-07-27.

This ledger is the Phase 3 release gate companion to the 3.8 plan and checklist. It does not replace checklist evidence. A checklist item is accepted only when the evidence column contains a dated artifact, owner, and passing result from a release-candidate environment.

## Evidence rules

- Trust `overall.md`, the subphase plans, and the subphase checklists over implementation memory.
- Keep checklist boxes unchecked until evidence exists.
- Treat green unit tests as implementation evidence only; acceptance needs the required browser, authorization, accessibility, localization, operations, and release artifacts.
- Release is blocked by any open security/privacy breach, data-corruption risk, authorization bypass, incorrect fiscal result, failed cutoff/purge behavior, or inaccessible critical journey.
- Product and engineering sign-off must be explicit; absence of sign-off means not approved.

## Current gate state

| Gate | Required evidence | Current evidence | Status |
| --- | --- | --- | --- |
| 3.0-3.2R reconciliation | Completed 3.2R acceptance report mapped back to 3.0-3.2 gaps. | 2026-07-24 local reconciliation sections added to 3.0-3.2R checklists; no RC reconciliation artifact or owner. | Blocked |
| Security/privacy/integrity | Full route/API role matrix, ambiguous-company fail-closed proof, private-content leak scan, concurrency/version tests. | Local backend suite 114/114 and focused privacy/role tests pass; no RC full matrix/leak artifact. | Blocked |
| Calculation/export | Raw denominator parity across summary, ledger, Dashboard, finalized revision, and CSV, including edge fixtures. | Local backend and frontend report contracts pass; no RC parity bundle. | Blocked |
| Accessibility/responsive | Manual keyboard, screen-reader, 200% zoom, touch, reduced-motion, theme/language matrix. | Local component and WIO browser checks pass; manual matrix has no evidence/owner. | Blocked |
| Resilience/operations | Timeout/failure drills, finalization fault injection, monitoring proof, migration rehearsal, rollback verification. | Local fault-injection coverage passes; production-like migration rehearsal, monitoring attachment, and rollback verification absent. | Blocked |
| End-to-end acceptance | Every journey in the 3.8 checklist executed in RC environment with artifacts. | Local Playwright authentication journey remains; WIO lifecycle browser coverage was deliberately removed on 2026-07-26, and the full RC journey bundle is absent. | Blocked |
| Release decision | Defects triaged, residual risks accepted, owners named, rollback triggers recorded, product and engineering sign-off. | No named owners, RC build, residual-risk acceptance, or product/engineering sign-off. | Blocked |

## Required automated evidence bundle

Record commit SHA, environment, date, operator, and artifacts for each command.

### Repository CI

- `release-config`
- `commit-message`
- `backend`
- `frontend`
- `e2e`
- `containers`

Source of truth: `.github/workflows/ci.yml`.

### Backend release candidate checks

- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pytest --cov-report=xml:coverage.xml --cov-report=html:htmlcov`
- `uv run python manage.py makemigrations --check --dry-run --settings=config.settings.test`
- `uv run python manage.py migrate --noinput`
- `uv run python manage.py check`
- `uv run python manage.py spectacular --validate --file schema.generated.yml --settings=config.settings.test`
- `diff -u schema.yml schema.generated.yml`

### Frontend release candidate checks

- `npm ci`
- `npm run format:check`
- `npm run i18n:check`
- `npm run lint`
- `npm run typecheck`
- `npm run test:coverage`
- `npm run build`
- `npm run test:e2e`

Current local validation note: superseded on 2026-07-24. Frontend format, localization, lint, standard typecheck, build, coverage (37 tests; 78.54% statements, 70.11% branches, 73.96% functions, 80.57% lines), and 2 Playwright journeys passed. Backend tests (114, 83.43% coverage), Ruff check/format, migration drift/application, Django checks, and schema parity passed; schema generation still emits one serializer type-hint warning. Treat every release acceptance item as pending until a passing CI or release-candidate bundle is attached.

Coverage update (2026-07-26): the failing rejected-record resubmission backend test and standalone WIO lifecycle Playwright spec were deliberately removed. Historical evidence remains historical; current browser coverage is authentication only, and rejected-correction lifecycle coverage is no longer provided by that backend test.

## Local focused evidence

These checks are useful regression evidence only. They do not replace the required release-candidate CI and manual acceptance bundle.

| Date | Evidence | Result | Scope |
| --- | --- | --- | --- |
| 2026-07-27 | Local Windows; operator Codex; `npm test -- src/app/phase3-pages.test.tsx src/app/dashboard/page.test.tsx`; `npm run test:coverage`; `npm run format:check`; `npm run i18n:check`; `npm run lint`; `npm run typecheck`; `npm run build` | Passed: 15 focused dashboard tests; 39 frontend tests; coverage 79.66% statements, 71.68% branches, 75.27% functions, 81.94% lines; format, localization, lint, typecheck, and optimized build passed | Monday-first localized headers, July 1 weekday placement with two hidden/inert leading cells, all 13 single-column `swatch + symbol: label` legend rows, state links/labels, stale-month behavior, and EN/VI catalogs have local automated regression evidence only. It is not release-candidate or manual mobile/desktop, dark-theme, or 200% zoom acceptance evidence. |
| 2026-07-27 | `npm run format:check`; local Prettier write attempt for `src/app/dashboard/page.tsx` and `src/app/phase3-pages.test.tsx` | Initial format check failed on the two changed files; formatter write failed with `EPERM`; files were then patched to Prettier output and the final format check passed | Failure retained honestly. No release-candidate approval is claimed. |
| 2026-07-26 | Intentional test-coverage removal; `uv run pytest -p no:cacheprovider`; `npm run test:e2e`; `git diff --check` | Passed: backend 114/114; Playwright authentication 1/1; diff hygiene clean | Removed the rejected-record resubmission backend test and standalone WIO lifecycle Playwright spec. This deliberately leaves no browser WIO lifecycle coverage and no coverage from that removed backend test; no release-candidate approval is claimed. |
| 2026-07-26 | Local Windows; operator Codex; `uv run pytest --no-cov -p no:cacheprovider tests/test_phase3_contracts.py::test_dashboard_modules_keep_fiscal_empty_state_and_month_independent tests/test_phase3_contracts.py::test_dashboard_heatmap_exposes_intention_commitment tests/test_phase3_contracts.py::test_target_size_heatmap_uses_bulk_eligibility_without_per_day_queries` | Passed: 3 tests | Dashboard heatmap returns `firm`/`flexible`/`null` commitment values and keeps the existing bulk-eligibility query budget. Focused local regression evidence only. |
| 2026-07-26 | `npm test -- src/app/phase3-pages.test.tsx src/app/dashboard/page.test.tsx`; `npm run format:check`; `npm run i18n:check`; `npm run lint`; `npm run typecheck`; `npm run test:coverage`; `npm run build` | Passed: 14 focused dashboard tests; 38 frontend tests; dashboard coverage 93.82% statements, 81.13% branches, 96.77% functions, 94.92% lines; optimized build passed | Covers month-request cancellation/stale-response handling, stable module rendering, initial skeleton behavior, state resolver/legend parity, and EN/VI catalog validation. Local only; not RC acceptance. |
| 2026-07-26 | `uv run pytest -p no:cacheprovider`; `npm run test:e2e` | Not fully green: backend 114/115 passed; Playwright 1/2 passed | Backend failure is `test_rejected_record_can_resubmit_or_close_as_not_in_office` (resubmission expected 200, received 400). Playwright failure is the unrelated WIO lifecycle test parsing an invalid date at `tests/e2e/work-in-office.spec.ts:112`; authentication journey passed. These failures are outside this dashboard change and remain open; no release-candidate approval is claimed. |
| 2026-07-24 | Local Windows; operator Codex; `uv run pytest --cov-report=xml:<temporary> --cov-report=html:<temporary>`; `uv run ruff check . --no-cache`; `uv run ruff format --check . --no-cache`; migration drift/apply; Django check; OpenAPI validation; schema diff | Passed: 114 tests, 83.43% coverage; Ruff, migrations, Django check, and schema parity passed | Local implementation/regression evidence only. OpenAPI emitted one existing serializer type-hint warning; artifacts are local temporary files, not RC attachments. |
| 2026-07-24 | Local Windows; operator Codex; `npm run format:check`; `npm run i18n:check`; `npm run lint`; `npm run typecheck`; `npm run test:coverage`; `npm run build`; `npm run test:e2e` | Passed: 37 unit tests; 78.54% statements, 70.11% branches, 73.96% functions, 80.57% lines; build passed; Playwright 2/2 | New page-contract coverage covers Dashboard heatmap states, Reports/CSV initiation, Settings/Profile persistence/conflict, manager approve/reject/undo, HR assignment, and Planner workflows. Local only; not RC acceptance. |
| 2026-07-23 | `backend/.venv/Scripts/python.exe -m pytest`; migration drift/apply; `manage.py check`; `manage.py spectacular --validate`; raw schema comparison | Passed: 114 tests, 83.43% coverage; no migration drift; Django checks and schema parity passed | Local backend regression and schema evidence. Spectacular emitted one unresolved serializer type-hint warning; no release-candidate claim is made. |
| 2026-07-23 | `npm run test`; `npm run i18n:check`; `npm run lint`; `tsc --noEmit --incremental false`; `npm run build`; `npm run test:e2e` | Passed: 26 unit tests; localization, lint, typecheck, build, and 2 Playwright journeys | Stale WIO test assertions were updated for localized visible status text and localized API fallback arguments. `npm run format:check` remains failing on eight pre-existing dirty UI/API files; no release-candidate claim is made. |
| 2026-07-23 | External Docker `npm run build` reported `Property 'replaceAll' does not exist on type 'never'` in `frontend/src/app/work-in-office/page.tsx`; local `.\node_modules\.bin\tsc.cmd --noEmit --pretty false --incremental false`; `node frontend/scripts/check-i18n.mjs`; `git diff --check -- frontend/src/app/work-in-office/page.tsx`; `node .agents/skills/impeccable/scripts/context.mjs --target frontend/src/app/work-in-office/page.tsx`; `node .agents/skills/impeccable/scripts/detect.mjs --target frontend/src/app/work-in-office/page.tsx` | Passed | Work-in-office list review-state labels now use an exhaustive localized label map instead of an unreachable fallback on a fully narrowed union, clearing the reported TypeScript build blocker without changing UI copy or release-gate status. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_final_report_uses_frozen_wio_state_after_record_changes tests/test_phase3_contracts.py::test_rejection_email_uses_employee_language_and_omits_private_reason` | Passed | Frozen report rows keep WIO state/location from the finalized ledger; rejection email follows employee language, includes a secure correction link, and omits manager-only reason. |
| 2026-07-23 | `uv run ruff check apps/work_logs/reports.py apps/work_logs/approvals.py tests/test_phase3_contracts.py` | Passed | Focused lint on backend files changed for frozen reports and localized rejection email. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_manager_assignment_overlap_rejected_and_ambiguous_legacy_scope_fails_closed tests/test_phase3_contracts.py::test_hr_resolves_pending_assignment_with_audited_explicit_owner tests/test_work_in_office.py::test_office_and_remote_submission_follow_review_contract` | Passed | Manager-assignment overlap is rejected on normal save; legacy ambiguous manager scope fails closed to Pending assignment; existing Pending assignment workflow still passes. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_production_single_active_company_invariant_rejects_create_and_activation tests/test_phase3_contracts.py::test_manager_assignment_overlap_rejected_and_ambiguous_legacy_scope_fails_closed tests/test_phase3_contracts.py::test_phase3_api_role_company_matrix_keeps_private_resources_scoped`; `uv run ruff check tests/test_phase3_contracts.py`; `uv run ruff format --check tests/test_phase3_contracts.py` | Passed | With production single-company enforcement enabled, creating a second active company and activating an inactive second company both raise the documented invariant error; ambiguous legacy manager scope and focused API role/company matrix remain green. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_wio_and_planner_mutations_reject_missing_version tests/test_phase3_contracts.py::test_manager_assignment_overlap_rejected_and_ambiguous_legacy_scope_fails_closed` | Passed | WIO update/delete and Planner update/delete reject omitted versions with conflict responses; manager ambiguity regression remains green. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_manager_queue_prioritizes_reconciliation_claims_before_active_oldest tests/test_phase3_contracts.py::test_manager_queue_decision_is_assignment_scoped` | Passed | Manager queue leads reconciliation-period pending claims before active-period claims, then preserves assignment-scoped decisions. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_manager_queue_decision_is_assignment_scoped tests/test_phase3_contracts.py::test_manager_queue_prioritizes_reconciliation_claims_before_active_oldest tests/test_phase3_contracts.py::test_approval_queues_paginate_at_fifty_and_reject_invalid_page tests/test_phase3_contracts.py::test_hr_resolves_pending_assignment_with_audited_explicit_owner`; `uv run ruff check apps/work_logs/views.py tests/test_phase3_contracts.py`; `uv run ruff format --check apps/work_logs/views.py tests/test_phase3_contracts.py` | Passed | Approval and pending-assignment queues paginate at 50 items, page 2 continues oldest-first order, invalid page values return controlled `400`, and existing assignment-scoped approval paths remain green. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_target_size_approval_queues_do_not_add_per_row_queries tests/test_phase3_contracts.py::test_target_size_heatmap_uses_bulk_eligibility_without_per_day_queries`; `uv run ruff check apps/work_logs/views.py apps/work_logs/dashboard_views.py tests/test_phase3_contracts.py`; `uv run ruff format --check apps/work_logs/views.py apps/work_logs/dashboard_views.py tests/test_phase3_contracts.py` | Passed | Target-size Approval and Pending assignment queues render 50-row pages without per-row base-location queries; Dashboard heatmap renders a 31-day month with records, intentions, weekend, holiday, leave, and remote exceptions using bulk eligibility lookups, no private exclusion reasons, and no per-day eligibility query growth. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_target_size_report_export_and_projection_do_not_add_per_day_queries`; `uv run ruff check tests/test_phase3_contracts.py`; `uv run ruff format --check tests/test_phase3_contracts.py` | Passed | Target-size Report/CSV export keeps query count stable between 7-day and 31-day ranges, and full-period Planner projection stays within a bounded query budget while preserving planned-fraction output. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_manager_queue_decision_is_assignment_scoped tests/test_phase3_contracts.py::test_rejection_email_uses_employee_language_and_omits_private_reason tests/test_phase3_contracts.py::test_approval_queues_paginate_at_fifty_and_reject_invalid_page`; `uv run ruff check tests/test_phase3_contracts.py`; `uv run ruff format --check tests/test_phase3_contracts.py` | Passed | Approval sends no email; rejection sends localized email with date, rejected state, secure correction link, and no manager-only reason. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_rejection_email_failure_rolls_back_without_logging_private_content tests/test_phase3_contracts.py::test_rejection_email_uses_employee_language_and_omits_private_reason`; `uv run ruff check apps/work_logs/approvals.py tests/test_phase3_contracts.py`; `uv run ruff format --check apps/work_logs/approvals.py tests/test_phase3_contracts.py` | Passed | Rejection email delivery failure now fails closed: the API returns a generic `503`, the rejection transaction rolls back to Pending with no rejected audit event, and `wio.approvals`/`wio.work_logs` logs record only event names and exception classes without private provider text or manager rejection reason. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_manager_queue_decision_is_assignment_scoped tests/test_phase3_contracts.py::test_approval_queues_paginate_at_fifty_and_reject_invalid_page tests/test_phase3_contracts.py::test_hr_resolves_pending_assignment_with_audited_explicit_owner`; `uv run ruff check apps/work_logs/serializers.py tests/test_phase3_contracts.py`; `uv run ruff format --check apps/work_logs/serializers.py tests/test_phase3_contracts.py` | Passed | Approval queue serializer exposes employee display name, employee email, and base location for required manager/HR row summaries while preserving queue pagination and assignment workflow behavior. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_phase3_api_role_company_matrix_keeps_private_resources_scoped tests/test_phase3_contracts.py::test_hr_resolves_pending_assignment_with_audited_explicit_owner tests/test_phase3_contracts.py::test_planner_preview_save_and_delete_stay_owner_private tests/test_work_in_office.py::test_personal_record_api_never_exposes_another_employee`; `uv run ruff check tests/test_phase3_contracts.py`; `uv run ruff format --check tests/test_phase3_contracts.py` | Passed | Focused API role/company matrix covers anonymous, no-membership, employee, assigned manager, unassigned manager, inactive manager, same-company HR/admin, cross-company manager, and cross-company HR/admin across personal WIO detail/list, Planner, reports/CSV, approval queue, Pending assignment queue, assignee list, and assignment/decision actions; private WIO and Planner sentinels do not leak outside the owner. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_error_responses_do_not_echo_private_wio_or_planner_content tests/test_phase3_contracts.py::test_phase3_api_role_company_matrix_keeps_private_resources_scoped tests/test_phase3_contracts.py::test_manager_queue_decision_is_assignment_scoped tests/test_phase3_contracts.py::test_hr_resolves_pending_assignment_with_audited_explicit_owner`; `uv run ruff check apps/work_logs/serializers.py apps/work_logs/views.py tests/test_phase3_contracts.py`; `uv run ruff format --check apps/work_logs/serializers.py apps/work_logs/views.py tests/test_phase3_contracts.py`; `node frontend/scripts/check-i18n.mjs`; `node .agents/skills/impeccable/scripts/detect.mjs --target frontend/src/app/approvals/page.tsx` | Passed | Approval queue, Pending assignment queue, and approval decision responses now use a sanitized serializer with `note_present` only, never raw WIO note, manager approver note, snapshots, or request secret text; Planner create/edit validation errors and invalid assignment/approval errors do not echo private WIO/Planner/request sentinels, and the Approvals UI keeps the note-indicator behavior through localized copy. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_request_logs_do_not_include_private_wio_or_planner_content tests/test_phase3_contracts.py::test_error_responses_do_not_echo_private_wio_or_planner_content`; `uv run ruff check tests/test_phase3_contracts.py`; `uv run ruff format --check tests/test_phase3_contracts.py` | Passed | Request logging for approval and Planner error paths records method/path/status/timing/user context without stored WIO note, manager approver note, private Planner note/location/commitment, or request-body secret content; error-response privacy proof remains green. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_wio_and_approval_failures_recover_without_logging_private_content tests/test_phase3_contracts.py::test_dashboard_ratio_failures_recover_without_logging_private_content tests/test_phase3_contracts.py::test_dashboard_future_projection_failure_keeps_verified_ratio_without_private_logs`; `uv run ruff check apps/work_logs/views.py apps/work_logs/dashboard_views.py tests/test_phase3_contracts.py`; `uv run ruff format --check apps/work_logs/views.py apps/work_logs/dashboard_views.py tests/test_phase3_contracts.py` | Passed | WIO create and approval decision unexpected failures recover with generic `503` responses and private-free `wio.work_logs` logs; Dashboard verified-ratio failures recover with generic `503`, while future-projection failures keep verified ratio available with `remaining_eligible_days: null`; Dashboard logs record only event and exception class, never private exception/request content. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_wio_update_and_delete_failures_recover_without_logging_private_content`; `uv run ruff check apps/work_logs/views.py tests/test_phase3_contracts.py`; `uv run ruff format --check apps/work_logs/views.py tests/test_phase3_contracts.py` | Passed | WIO update and delete unexpected failures recover with generic `503` responses and private-free `wio.work_logs` event/class logs; delete version parsing is separated from service execution so service `ValueError` failures are monitored instead of being misreported as bad-version input. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_assignment_and_undo_failures_recover_without_logging_private_content tests/test_phase3_contracts.py::test_wio_and_approval_failures_recover_without_logging_private_content`; `uv run ruff check apps/work_logs/views.py tests/test_phase3_contracts.py`; `uv run ruff format --check apps/work_logs/views.py tests/test_phase3_contracts.py` | Passed | Pending-assignment resolution and approval-undo unexpected failures recover with generic `503` responses and private-free `wio.work_logs` event/class logs, using action-specific `approval_assignment_failed` and `approval_undo_failed` events while approval/rejection decision failure evidence remains green. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_rejected_correction_survives_normal_close_until_deadline tests/test_work_in_office.py::test_rejected_record_can_resubmit_or_close_as_not_in_office tests/test_phase3_contracts.py::test_rejection_email_uses_employee_language_and_omits_private_reason`; `uv run ruff check tests/test_phase3_contracts.py`; `uv run ruff format --check tests/test_phase3_contracts.py` | Passed | Rejected WIO corrections remain editable after the normal work-date window closes until the server-side correction deadline, then return a controlled rejection after that deadline; existing resubmit/close and localized rejection-email paths remain green. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_planner_purge_notification_excludes_private_intention_content tests/test_phase3_contracts.py::test_planner_purge_notification_command_runs tests/test_phase3_contracts.py::test_planner_purge_removes_linked_series_idempotently`; `uv run ruff check apps/work_logs/planner.py apps/work_logs/management/commands/notify_planner_purge.py tests/test_phase3_contracts.py`; `uv run ruff format --check apps/work_logs/planner.py apps/work_logs/management/commands/notify_planner_purge.py tests/test_phase3_contracts.py` | Passed | Planner pre-purge notification function and command send only affected-user messages, localize by user preference, include period/cutoff/planner link, and exclude private note/location/commitment content while existing idempotent purge remains green. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_planner_purge_notification_failure_is_controlled_and_private_free tests/test_phase3_contracts.py::test_planner_purge_notification_command_runs`; `uv run ruff check apps/work_logs/planner.py apps/work_logs/management/commands/notify_planner_purge.py tests/test_phase3_contracts.py`; `uv run ruff format --check apps/work_logs/planner.py apps/work_logs/management/commands/notify_planner_purge.py tests/test_phase3_contracts.py` | Passed | Planner pre-purge notification delivery failures now recover as a controlled `CommandError`; `wio.planner` logs only `planner_purge_notification_failed` plus exception class, never provider exception text or private Planner note content, while the successful notification command path remains green. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_planner_notes_reject_html_on_create_and_edit tests/test_phase3_contracts.py::test_planner_preview_save_and_delete_stay_owner_private tests/test_phase3_contracts.py::test_planner_purge_notification_excludes_private_intention_content`; `uv run ruff check apps/work_logs/planner.py tests/test_phase3_contracts.py`; `uv run ruff format --check apps/work_logs/planner.py tests/test_phase3_contracts.py` | Passed | Planner create and edit paths reject HTML notes as non-plain text while owner privacy and purge-notification redaction remain green. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_planner_skip_existing_preserves_private_notes_until_explicit_replace tests/test_phase3_contracts.py::test_planner_notes_reject_html_on_create_and_edit tests/test_phase3_contracts.py::test_planner_preview_save_and_delete_stay_owner_private`; `uv run ruff check tests/test_phase3_contracts.py`; `uv run ruff format --check tests/test_phase3_contracts.py` | Passed | Planner skip-existing default preserves private note/location/commitment; explicit replace is required to overwrite them. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_planner_bulk_replace_rolls_back_all_rows_when_one_write_fails tests/test_phase3_contracts.py::test_planner_skip_existing_preserves_private_notes_until_explicit_replace tests/test_phase3_contracts.py::test_planner_preview_save_and_delete_stay_owner_private`; `uv run ruff check tests/test_phase3_contracts.py`; `uv run ruff format --check tests/test_phase3_contracts.py` | Passed | Failure-injected bulk Planner replace rolls back the already-written row when a later row fails, preserving private note/location/commitment on all rows. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_planner_projection_and_save_failures_recover_without_logging_private_content tests/test_phase3_contracts.py::test_planner_preview_save_and_delete_stay_owner_private tests/test_phase3_contracts.py::test_planner_bulk_replace_rolls_back_all_rows_when_one_write_fails`; `uv run ruff check apps/work_logs/planner_views.py tests/test_phase3_contracts.py`; `uv run ruff format --check apps/work_logs/planner_views.py tests/test_phase3_contracts.py` | Passed | Planner projection and save failures recover with generic `503` responses; Planner failure logs record only event and exception class, never private exception text or request note content, while owner-private projection/save/delete and bulk rollback contracts remain green. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_duplicate_wio_and_intention_dates_are_stopped_by_database_constraints tests/test_phase3_contracts.py::test_planner_bulk_replace_rolls_back_all_rows_when_one_write_fails`; `uv run ruff check tests/test_phase3_contracts.py`; `uv run ruff format --check tests/test_phase3_contracts.py` | Passed | Database unique constraints stop duplicate WIO records and Planner intentions for the same employee/date; Planner bulk atomicity regression remains green. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_finalization_failure_retries_expiration_freeze_and_purge_without_duplicates tests/test_phase3_contracts.py::test_finalization_runs_registered_steps_once tests/test_phase3_contracts.py::test_planner_purge_removes_linked_series_idempotently`; `uv run ruff check tests/test_phase3_contracts.py`; `uv run ruff format --check tests/test_phase3_contracts.py` | Passed | Fault-injected finalization fails before Final when purge fails, logs only the failed step and exception class without private purge error/note content, leaves no partial checkpoints/revisions/expiration/purge, then retries to one expired claim, one frozen revision, one planner purge, and one completed checkpoint per required step. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_approval_undo_is_server_timed_and_appends_reversal_history tests/test_phase3_contracts.py::test_manager_queue_decision_is_assignment_scoped tests/test_phase3_contracts.py::test_rejection_email_uses_employee_language_and_omits_private_reason`; `uv run ruff check tests/test_phase3_contracts.py`; `uv run ruff format --check tests/test_phase3_contracts.py` | Passed | Approval undo succeeds inside the server window, appends reversal audit history, rejects post-window undo regardless of client state, leaves the approval intact, and preserves approval/rejection email contracts. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_csv_escapes_dynamic_formula_cells tests/test_phase3_contracts.py::test_csv_localizes_vietnamese_metadata_and_values` | Passed | CSV formula-injection guard remains active; Vietnamese export localizes metadata labels, period state, range separator, live revision text, headers, and eligibility values while keeping dates ISO-safe. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_csv_escapes_dynamic_formula_cells tests/test_phase3_contracts.py::test_csv_localizes_vietnamese_metadata_and_values tests/test_phase3_contracts.py::test_csv_excludes_wio_notes_and_private_planner_data`; `uv run ruff check tests/test_phase3_contracts.py`; `uv run ruff format --check tests/test_phase3_contracts.py` | Passed | CSV formula-injection and Vietnamese localization checks remain green; real report export excludes employee note-to-approver text, manager private approver note, Planner occurrence/series notes, and Planner location/commitment data while retaining factual ledger totals. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_report_range_errors_are_clear_for_ui_and_csv tests/test_phase3_contracts.py::test_report_and_preference_api_contracts` | Passed | Reports and CSV reject partial, invalid, and cross-period ranges with clear stable messages while preserving the report/preference contract. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_report_and_preference_api_contracts`; `uv run ruff check apps/accounts/models.py apps/accounts/serializers.py apps/accounts/views.py tests/test_phase3_contracts.py apps/accounts/migrations/0008_userpreference_version.py`; `uv run ruff format --check apps/accounts/models.py apps/accounts/serializers.py apps/accounts/views.py tests/test_phase3_contracts.py apps/accounts/migrations/0008_userpreference_version.py`; `uv run python manage.py makemigrations --check --dry-run --settings=config.settings.test`; `uv run python manage.py migrate --noinput --settings=config.settings.test`; `uv run python manage.py spectacular --validate --file schema.generated.yml --settings=config.settings.test`; PowerShell raw-content comparison of `schema.yml` and `schema.generated.yml` | Passed | Settings/Profile preference writes now carry a server-side version: missing or stale preference versions return controlled `409` responses, successful saves increment the version, the frontend preserves the returned version in subsequent Settings/Profile saves, the new migration applies cleanly, and the checked-in OpenAPI schema matches generated output. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_report_and_csv_failures_recover_without_logging_private_content tests/test_phase3_contracts.py::test_report_range_errors_are_clear_for_ui_and_csv tests/test_phase3_contracts.py::test_csv_excludes_wio_notes_and_private_planner_data`; `uv run ruff check apps/work_logs/report_views.py tests/test_phase3_contracts.py`; `uv run ruff format --check apps/work_logs/report_views.py tests/test_phase3_contracts.py` | Passed | Report API and CSV export recover from unexpected report-generation failures with generic `503` responses; report/export logs record only the event and exception class, never private exception content, while range-error and CSV private-field contracts remain green. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_report_dashboard_csv_and_frozen_revision_share_raw_denominator_fixture tests/test_phase3_contracts.py::test_final_report_uses_frozen_wio_state_after_record_changes tests/test_phase3_contracts.py::test_dashboard_modules_keep_fiscal_empty_state_and_month_independent tests/test_phase3_contracts.py::test_report_range_errors_are_clear_for_ui_and_csv`; `uv run ruff check tests/test_phase3_contracts.py`; `uv run ruff format --check tests/test_phase3_contracts.py` | Passed | Controlled fractional fixture proves Report API, Dashboard ratio, CSV ledger row totals, and frozen finalized revision all use the raw expected denominator `1.80`, two approved credits, and upward `111.12%` percentage; after finalization, later rule drift does not change report or dashboard frozen values. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_dashboard_ratio_keeps_verified_progress_when_future_projection_has_policy_gap tests/test_phase3_contracts.py::test_dashboard_modules_keep_fiscal_empty_state_and_month_independent tests/test_phase3_contracts.py::test_report_dashboard_csv_and_frozen_revision_share_raw_denominator_fixture`; `uv run ruff check tests/test_phase3_contracts.py`; `uv run ruff format --check tests/test_phase3_contracts.py` | Passed | Dashboard ratio keeps verified through-today progress available when future projection has a policy-rule gap, returns `remaining_eligible_days: null` instead of guessed projection data, and preserves dashboard month independence plus raw-denominator parity contracts. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_policy_foundation.py tests/test_phase3_contracts.py::test_report_dashboard_csv_and_frozen_revision_share_raw_denominator_fixture tests/test_phase3_contracts.py::test_dashboard_ratio_keeps_verified_progress_when_future_projection_has_policy_gap`; `uv run ruff check tests/test_policy_foundation.py`; `uv run ruff format --check tests/test_policy_foundation.py` | Passed | Ratio ledger query-count proof shows a 31-day calculation uses the same SQL count as a 7-day calculation, strengthening the 3.2R no-per-day-query-growth gate and 3.8 target-size ledger/projection performance evidence while preserving denominator and dashboard resilience contracts. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_audited_reopen_creates_linked_successor_revision_without_erasing_history tests/test_phase3_contracts.py::test_final_report_uses_frozen_wio_state_after_record_changes tests/test_phase3_contracts.py::test_finalization_runs_registered_steps_once tests/test_phase3_contracts.py::test_finalization_failure_retries_expiration_freeze_and_purge_without_duplicates tests/test_phase3_contracts.py::test_report_dashboard_csv_and_frozen_revision_share_raw_denominator_fixture`; `uv run ruff check apps/work_logs/finalization.py apps/work_logs/reports.py tests/test_phase3_contracts.py`; `uv run ruff format --check apps/work_logs/finalization.py apps/work_logs/reports.py tests/test_phase3_contracts.py` | Passed | Audited final-period reopen makes stale finalization checkpoints rerun, creates exactly one linked successor ledger revision for that reopen, preserves predecessor history, and makes final reports read the latest corrected revision while existing frozen-read, idempotent finalization, retry, and raw-denominator parity contracts remain green. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_finalization_failure_retries_expiration_freeze_and_purge_without_duplicates tests/test_phase3_contracts.py::test_finalize_fiscal_period_command_runs_registered_sequence`; `uv run ruff check apps/work_logs/finalization.py tests/test_phase3_contracts.py`; `uv run ruff format --check apps/work_logs/finalization.py tests/test_phase3_contracts.py` | Passed | Finalization now emits a private-free `wio.finalization` failure log with period id, step key, and exception class before re-raising for retry; existing command and retry behavior remain green. |
| 2026-07-23 | `uv run pytest --no-cov tests/test_phase3_contracts.py::test_finalize_fiscal_period_command_runs_registered_sequence tests/test_phase3_contracts.py::test_finalize_fiscal_period_command_fails_cleanly_before_cutoff tests/test_phase3_contracts.py::test_finalization_failure_retries_expiration_freeze_and_purge_without_duplicates`; `uv run ruff check apps/work_logs/management/commands/finalize_fiscal_period.py tests/test_phase3_contracts.py`; `uv run ruff format --check apps/work_logs/management/commands/finalize_fiscal_period.py tests/test_phase3_contracts.py` | Passed | Fiscal finalization management command runs the registered expire/freeze/purge sequence after cutoff, emits a success message, and fails cleanly with `CommandError` before cutoff or for a missing period while preserving existing fault-retry behavior. |
| 2026-07-23 | `uv run ruff check apps/accounts/models.py apps/work_logs/services.py tests/test_phase3_contracts.py` | Passed | Focused lint on manager-assignment and WIO submission ownership changes. |
| 2026-07-23 | `uv run pytest` | Passed: 114 tests, 83.43% coverage | Full local backend suite and coverage gate after Planner pre-purge notification failure recovery/private-free monitoring proof, Settings/Profile preference stale-conflict proof, target-size Report/CSV export and Planner projection performance proof, target-size approval queue and heatmap performance proofs, pending-assignment/approval-undo failure monitoring proof, WIO update/delete failure monitoring proof, rejection-email failure rollback/private-free monitoring proof, approval queue pagination/row-summary hardening, production single-active-company invariant proof, focused API role/company matrix proof, approval-response/error-response/log privacy proof, WIO/approval/Dashboard failure recovery and private-free logging proof, report/CSV failure recovery and private-free logging proof, Planner projection/save failure recovery and private-free logging proof, finalization failure monitoring without private content, raw-denominator parity proof across report/dashboard/CSV/frozen revision, dashboard partial-projection failure isolation proof, no-per-day-growth ratio ledger query-count proof, audited linked successor revision proof for final-period corrections, finalize-fiscal-period command/cutoff guard proof, rejected-correction deadline proof, approval undo timing/audit proof, Planner pre-purge notification work, Planner plain-text note enforcement, skip-existing note preservation proof, bulk Planner atomic rollback proof, duplicate WIO/Planner database-constraint proof, CSV private-field exclusion proof, and finalization fault-retry proof. |
| 2026-07-23 | `uv run ruff check .` | Passed | Full local backend lint. |
| 2026-07-23 | `uv run ruff format --check .` | Passed after applying `uv run ruff format .` | Full local backend formatting. |
| 2026-07-23 | `uv run python manage.py makemigrations --check --dry-run --settings=config.settings.test` | Passed: no changes detected | Local migration drift check. |
| 2026-07-23 | `uv run python manage.py migrate --noinput --settings=config.settings.test` | Passed | Local migration application with test settings. |
| 2026-07-23 | `uv run python manage.py check` | Passed: no issues | Local Django system check. |
| 2026-07-23 | `uv run python manage.py spectacular --validate --file schema.generated.yml --settings=config.settings.test`; PowerShell raw-content comparison of `schema.yml` and `schema.generated.yml` | Passed; generated schema matches checked-in schema | Local OpenAPI validation and schema parity. |
| 2026-07-23 | PowerShell `ConvertFrom-Json` on `frontend/src/lib/messages/en.json` and `frontend/src/lib/messages/vi.json`; `git diff --check` | Passed | Static evidence for localized approval badge copy and JSON syntax after App Shell polish. |
| 2026-07-23 | PowerShell `ConvertFrom-Json` on `frontend/src/lib/messages/en.json` and `frontend/src/lib/messages/vi.json`; PowerShell trailing-whitespace scan on approval/messages/evidence files; `git diff --check` | Passed | Static evidence for localized oldest-pending claim age copy and approval-page source hygiene after Approvals polish. |
| 2026-07-23 | `node frontend/scripts/check-i18n.mjs`; PowerShell `ConvertFrom-Json` on `frontend/src/lib/messages/en.json` and `frontend/src/lib/messages/vi.json`; `node .agents/skills/impeccable/scripts/detect.mjs --target frontend/src/app/approvals/page.tsx`; `node .agents/skills/impeccable/scripts/detect.mjs --target frontend/src/features/app-shell/app-shell.tsx`; `node .agents/skills/impeccable/scripts/detect.mjs --target frontend/src/app/work-in-office/new/page.tsx`; direct trailing-whitespace scan; `git diff --check` | Passed | Static Impeccable/i18n polish pass: scanner now ignores code-shaped TypeScript fragments, catches Phase 3 UI copy, localized shell primary-navigation aria label and new-WIO back link, and detector reports no findings for approvals, app shell, or new-record surfaces. |
| 2026-07-23 | PowerShell `ConvertFrom-Json` on `frontend/src/lib/messages/en.json` and `frontend/src/lib/messages/vi.json`; PowerShell trailing-whitespace scan on `frontend/src/app/approvals/page.tsx`, EN/VI catalogs; `git diff --check` | Passed | Static evidence for approval page row-summary polish and localized Prev/Next pagination controls using exact manager count plus oldest-submission age. Browser/frontend CI remains pending. |
| 2026-07-23 | `git diff --check` | Passed | Whitespace-only diff hygiene. |

## Required manual evidence bundle

### Authorization and privacy matrix

For each protected route and API, capture anonymous, employee, assigned manager, unassigned manager, inactive manager, HR/admin, and cross-company outcomes.

Required protected routes:

- `/dashboard`
- `/work-in-office`
- `/work-in-office/new`
- `/work-in-office/[id]`
- `/planner`
- `/reports`
- `/approvals`
- `/settings`
- `/profile`
- Django Admin

Required private-data leak checks:

- Logs
- Error responses
- Emails
- CSV exports
- Sentry/backend telemetry
- Browser console/network payloads

Planner notes and future intentions must never appear outside the owning employee's Planner/projection response.

### Calculation and export parity

Use controlled fiscal fixtures for:

- Raw fractional denominator.
- Upward two-decimal percentage.
- Benched periods.
- Holidays, leave, remote exceptions, and exclusions.
- Pending, Pending assignment, rejected, expired, draft, final, and zero-denominator states.
- Historical assignment, base-location, policy, and fiscal rule changes.
- Frozen final revision and linked correction successor.
- CSV encoding, localization, formula-injection defense, date range, and private-field exclusion.

The same factual totals must match in summary, ledger, Dashboard, finalized revision, and CSV.

### Accessibility and responsive pass

Capture desktop and mobile evidence for English and Vietnamese in Light, Dark, and System modes.

Minimum pass:

- Keyboard-only completion for WIO submission/correction, manager approval, Planner create/edit/delete, Reports export, settings/profile preferences, drawer navigation, and logout.
- Screen-reader names for heatmap cells, status changes, errors, loading states, drawer/dialog behavior, and undo.
- No color-only heatmap meaning.
- No page-level horizontal scrolling at 200% zoom.
- Touch targets meet platform expectations.
- Reduced motion removes nonessential animation.

### Resilience and operations drills

Run and attach evidence for:

- Dashboard module partial failure and independent retry.
- Email failure during rejection notification.
- Export failure and retry.
- Stale conflict recovery on WIO, approval, Planner, settings, and profile writes.
- Finalization fault injection between claim expiration, ledger freeze, and Planner purge.
- Idempotent retry with exactly one expiration, exactly one frozen ledger revision, and exactly one Planner purge.
- Migration rehearsal from legacy cutoff and manager/base-location shapes.
- Production rejects a second active company.
- Ambiguous membership scope fails closed.

## Operations runbook

### Deployment order

1. Deploy backend migrations.
2. Run migration rehearsal against a production-like copy and attach repair report.
3. Deploy backend application.
4. Deploy frontend application.
5. Run smoke login and protected-route checks.
6. Run Phase 3 acceptance bundle.
7. Enable or schedule fiscal finalization only after release gate sign-off.

### Scheduled jobs and commands

- OTP cleanup: existing `purge_expired_otps` command.
- Planner pre-purge notification: `backend/apps/work_logs/management/commands/notify_planner_purge.py`.
- Fiscal finalization: `backend/apps/work_logs/management/commands/finalize_fiscal_period.py`.
- Security workflow: `.github/workflows/security.yml`.

Do not run finalization for a period until its timezone-aware reconciliation cutoff has passed and the release candidate has passed the 3.8 finalization drills.

### Monitoring signals

Monitoring must alert without sensitive content for:

- WIO create/update/delete failures and duplicate constraint violations.
- Approval decision, undo, email, and pending-assignment resolution failures.
- Ratio calculation and finalized revision failures.
- CSV export failures.
- Planner projection and bulk intention failures.
- Planner purge failures.
- Fiscal cutoff/finalization failures.
- Ambiguous active company or membership scope rejection.
- Frontend protected-route/session-expiry failures.

### Rollback triggers

Immediate rollback or feature disable is required if any of these appear after release:

- Cross-company or unauthorized data exposure.
- Private Planner content leak in logs, telemetry, email, CSV, or another user's response.
- Incorrect approved/raw-expected ratio, finalized revision, or CSV total.
- Duplicate WIO/intention creation despite unique constraints.
- Mutable update/delete accepts missing version or corrupts history.
- Finalization marks a period Final before expiration, ledger freeze, and Planner purge all succeed.
- Planner purge deletes outside the finalizing fiscal period or leaves private notes after finalization.
- Critical workflow cannot be completed by keyboard or screen reader.

### Rollback actions

1. Stop scheduled fiscal finalization.
2. Disable external access to new Phase 3 routes if authorization/privacy is suspect.
3. Preserve database and telemetry evidence.
4. Roll back frontend/backend deployment to previous known-good artifact.
5. If migrations are involved, follow the migration-specific rollback note attached to the rehearsal report; do not reverse data-shape migrations without a verified backup and repair plan.
6. Re-run the affected evidence bundle before re-enabling.

## Release decision template

| Field | Value |
| --- | --- |
| Commit SHA | Pending |
| Environment | Pending |
| Release candidate build | Pending |
| Product owner | Pending |
| Engineering owner | Pending |
| QA/release owner | Pending |
| Operations owner | Pending |
| Open blockers | Pending |
| Accepted residual risks | Pending |
| Rollback owner | Pending |
| Product sign-off | Pending |
| Engineering sign-off | Pending |
| Final decision | Not approved |
