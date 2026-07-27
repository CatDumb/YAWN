# Phase 3 Overall Plan

Status: implementation-aware planning baseline as of 2026-07-23. Subphases 3.0-3.2 have working code and automated coverage, but the implementation audit found acceptance gaps. They are therefore **implemented, acceptance incomplete**, not complete. Subphase 3.2R is a mandatory remediation gate before Subphase 3.3. Subphases 3.3-3.8 remain unimplemented and may be shaped by this document.

## 0. Implementation baseline and status rules

### Verified baseline

- Full backend suite: 65 tests passed with 80.66% measured coverage.
- Full frontend suite: 33 tests passed.
- Backend Ruff and frontend ESLint passed.
- TypeScript type checking passed.
- Django reported no migration drift under test settings.
- Only the real-browser authentication journey remains. WIO lifecycle browser coverage was deliberately removed on 2026-07-26; the audit did not execute the remaining journey against a live release-equivalent stack.

Green tests prove the implemented paths they cover; they do not override missing acceptance behavior.

### Mandatory remediation gate

[Subphase 3.2R](subphase-3.2r-baseline-remediation-gate-plan.md) repairs the audited 3.0-3.2 gaps before manager approval work begins. Its checklist is the acceptance authority for the repaired baseline.

The principal gaps are:

- Authentication browser coverage omits live session expiry.
- Fiscal cutoff is stored as a date instead of an exact timestamp, and lifecycle state is not advanced through one persisted, audited coordinator.
- Effective-dated policy coverage, base-location history, and finalized calculation history are not yet strong enough for reproducible reports.
- The ratio implementation and this plan previously disagreed about denominator rounding.
- WIO stale-write protection is optional, rejected corrections can be blocked by the original submission window, and the audited older-date override is absent.
- Existing manager assignments are not effective-dated, and submitted claims have no deterministic approval-owner snapshot.
- Current WIO index, status feedback, audit detail, and company-date behavior do not yet meet the full UI contract.

### Status rules

- **Implemented** means code exists.
- **Accepted** means every applicable checklist item and required browser journey has evidence.
- Checkboxes remain unchecked until acceptance evidence exists.
- Later subphases may not treat an implemented-but-unaccepted dependency as complete.

## 1. Phase objective

Phase 3 delivers the first complete work-in-office (WIO) product slice:

1. An employee records whether they worked in an office.
2. Office claims receive assignment-scoped manager review.
3. Approved office days update an explainable fiscal-year ratio.
4. Employees inspect monthly activity and detailed ratio evidence.
5. Employees privately plan future office/home intentions and see how the plan may affect projected compliance.
6. Employees can export their own factual WIO and ratio data.

The product remains a single-company web application. Production permits exactly one active company, and each user has at most one membership in it. Extra inactive companies may exist only for historical or test data; activating a second company fails validation. The company timezone is `Asia/Ho_Chi_Minh`.

## 2. Required Phase 2 gate

Do not begin the Phase 3 feature rollout until the roadmap's Phase 2 hardening is complete:

- Explicit inactive-membership reactivation.
- OTP abuse-control branch coverage.
- Hard timeout around synchronous SMTP delivery.
- Consistent 60-second resend behavior.
- Public `/` and protected `/dashboard` separation.
- One real-browser authentication contract across Next.js and Django.

Unauthenticated access to protected routes redirects to `/`. Successful login lands on `/dashboard`.

## 3. Product language

Use **Work-in-office** or **WIO** in user-facing UI. Do not call the feature “Work Logs” or use generic “attendance” language when describing an employee's daily choice.

Daily wording:

- Prompt: **Did you work in the office?**
- Choice: **Yes, in office**
- Choice: **No, elsewhere**

Display location choice and review state separately:

- Location: `In office` or `Not in office`.
- Review: `Draft`, `Pending assignment`, `Pending`, `Approved`, `Rejected`, `Not required`, or `Expired pending`.

Internal `WorkLog` names may remain temporarily where renaming would create migration risk, but new UI, documentation, and API descriptions should follow WIO terminology consistently.

## 4. Information architecture and access

### Public route

- `/`: access request and OTP sign-in.
- Theme and language controls are available before authentication.

### Protected app routes

- `/dashboard`: default signed-in information hub.
- `/work-in-office`: personal WIO records and actions.
- `/work-in-office/new`: new WIO entry.
- `/work-in-office/[id]`: record detail, allowed edits, audit history.
- `/planner`: private future intentions.
- `/reports`: fiscal ratio, custom-range ledger, personal CSV export.
- `/approvals`: assigned managers only.
- `/settings`: preferences.
- `/profile`: profile and effective assignment information.
- Django Admin: projects, base locations, policies, fiscal periods, exceptions, and other HR/admin operations.

### Sidebar

Recommended order:

1. Dashboard
2. Work-in-office
3. Planner
4. Reports
5. Approvals — visible only to eligible managers
6. Administration — visible only to HR/admin and opens Django Admin
7. Settings

Desktop uses a persistent sidebar with an optional icon-only collapsed state. It starts expanded, persists the user's local choice, and keeps accessible labels, active state, and tooltips when collapsed. Mobile uses a top bar and an always-expanded modal navigation drawer.

All protected routes sit under one authenticated application layout. Client-side route changes retain the drawer, session identity, approval badge, and desktop collapse state; only the content slot changes. A shared content-only loading skeleton may appear while a protected route resolves. Selecting an internal route closes transient mobile-drawer and account-menu state.

The bottom user bar shows initials, full name, active role, and company. Clicking it opens a menu containing **Profile** and **Log out**. Long names truncate visually but retain a complete accessible label.

Visibility is convenience only; frontend routes and backend APIs must independently enforce role, active membership, company, and manager-assignment scope.

## 5. Selected UI direction: Two Horizons

Surface mode: **Operate**.

The dashboard uses the existing YAWN visual world: calm paper-like surfaces, lo-fi indigo for primary actions, restrained semantic colors, clear system typography, soft elevation, and daisyUI semantic tokens. It must avoid a generic grid of equal “bento” cards.

### Structural thesis

The employee needs two time horizons at once:

- **Now:** today's WIO state and the next valid action.
- **Fiscal outlook:** verified progress, planned coverage, recoverable deficit, and cutoff state.

The first viewport places these horizons prominently. The adjustable-month heatmap forms the next dominant band. Recent WIO activity and upcoming intentions follow.

Signature visual: verified green fiscal progress meets a yellow planned range, leaving any uncovered gap visible without presenting intentions as earned credit.

The Impeccable structural roll ran in degraded mode because its external challenger catalog was unavailable. A network retry was blocked to avoid disclosing project/design context. The grounded structural direction was explicitly accepted.

## 6. Dashboard

Dashboard is an information hub. It contains no editable forms and no manager approval module.

### Core modules

- Today's WIO state with contextual navigation action.
- Fiscal-year-to-date ratio summary.
- Planned-coverage range and warning.
- Adjustable-month activity heatmap with visible legend.
- Five most recent WIO records from the selected month.
- Five upcoming private intentions from today, independent of selected month.
- Attention notice for drafts and rejected claims.

Contextual actions navigate to the owning page:

- `Record WIO`
- `Continue draft`
- `Fix rejected WIO`
- `View ratio details`

### Time behavior

- Ratio context is the active fiscal period, not a calendar month.
- Heatmap and recent activity use an independently selected month.
- Month navigation may move across fiscal years without artificial limits.
- Future cells never allow WIO submissions.
- Intention creation is limited to the current active fiscal period.
- Historical fiscal periods are available through Reports.

### Mobile order

1. Top bar and navigation trigger.
2. Today's WIO state and action.
3. Fiscal ratio and plan-coverage warning.
4. Monthly heatmap.
5. Upcoming intentions.
6. Recent WIO activity.

### Loading, errors, and empty states

- Restore the session before loading protected data; invalid sessions redirect to `/`.
- Use stable shape-matching skeletons only while loading.
- Load Today, ratio, heatmap, intentions, and activity independently.
- A failed module receives a local error and Retry action; other modules remain usable.
- Never guess ratio data after a calculation failure.
- Preserve old month data in a clearly dimmed loading state during month changes.
- After a successful empty response, show a small semantic icon, short heading, one sentence, and at most one CTA.
- Preserve the empty month grid because it teaches the heatmap model.

## 7. Monthly heatmap

The heatmap is a compact, adjustable-month grid inspired by GitHub contribution calendars, not a 365-cell yearly grid. It has localized weekday headings ordered Monday through Sunday (English: `Mon`, `Tue`, `Wed`, `Thu`, `Fri`, `Sat`, `Sun`), and day 1 is placed under its real weekday. Leading cells before day 1 are blank, non-interactive, and hidden from assistive technology.

### Legend and states

- Green + check: approved WIO.
- Aqua + `M`: WIO waiting for manager assignment.
- Blue + clock: WIO pending approval.
- Orange + cross: rejected WIO.
- Gray + hourglass: expired pending WIO.
- Base/neutral + cross: recorded Not in office.
- Neutral outline + dot: draft.
- Gray disabled: ineligible date, with exclusion reason.
- Yellow + check: future Office intention.
- Yellow + cross: future Not-in-office intention.
- Stronger/lighter yellow: Firm/Flexible intention.
- Empty + open circle: eligible date with no record or intention.

A persistent visible legend is mandatory. It is one vertical column: `swatch + symbol: label`. Every row aligns the small square swatch, non-color symbol, colon, and text label; each swatch uses the same semantic fill, border, and state treatment as its heatmap cells. The swatch, symbol, and colon are decorative and hidden from assistive technology, while the text label remains visible and accessible. Office and Home intention cells include their Firm/Flexible commitment so the yellow treatment can be stronger or lighter. Every cell also needs a complete accessible label. Tooltip content may supplement but never replace visible or assistive meaning.

### Cell actions

- Approved, Pending assignment, pending, rejected, or Expired pending WIO: open WIO detail.
- Draft: continue draft.
- Not in office: edit within deadline, otherwise open read-only detail.
- Future intention: open intention editor.
- Empty future date in active fiscal period: create intention.
- Empty today/yesterday: create WIO when deadline permits.
- Ineligible date: show exclusion reason without navigating.
- Older empty eligible date: explain the closed deadline rather than acting as a dead control.

## 8. WIO record lifecycle

### Entry fields

- Required work date.
- Required `Yes, in office` / `No, elsewhere` choice.
- Optional plain-text note to approver, shown only for an office claim.
- Note maximum: 500 characters.
- No daily project-status selector.

Future evidence, endorser, and seat sections must have clear extension seams but do not ship in Phase 3.

### Allowed dates

- Today.
- Yesterday until 23:59 company time.
- No future WIO dates; use Planner instead.
- Ineligible dates cannot be submitted and display the exclusion reason.
- Older dates require HR/admin audited override.

### Draft behavior

- Draft creation is explicit through `Save draft`; merely visiting the form creates nothing.
- Drafts may contain partial data.
- A draft reserves employee/date and blocks a second record.
- Drafts remain editable and deletable.
- Dashboard exposes `Continue draft`.

### Submission and review states

- `Yes, in office` enters manager approval and can earn ratio credit only after approval.
- If no manager is effective on the work date, an office claim enters `Pending assignment`. It preserves the employee's submission time, remains locked, earns zero credit, and is invisible to manager queues until HR/admin assigns an owner with an audited reason.
- `No, elsewhere` records zero credit immediately and does not create an approval task.
- A Not-in-office record remains editable until the normal submission deadline.
- Changing Not in office to In office creates a pending claim and locks it.
- Submitted office claims remain locked while pending.
- Rejected office claims become editable and may be resubmitted.
- Approved WIO remains immutable.
- Every material transition creates an audit event.

This is a deliberate amendment to the roadmap's broader “approve/reject work logs” wording: only a positive office claim requires manager verification.

### Rejected claims

- Work date remains fixed.
- WIO choice and approver note become editable.
- Resubmitting In office returns to Pending.
- Changing to Not in office records zero credit and closes the rejection.
- Original values, rejection reason, edits, and resubmission remain auditable.
- Correction deadline is 23:59 on the calendar day after rejection, never later than fiscal reconciliation cutoff.
- HR/admin may grant an audited extension before final lock.

### Post-submit navigation

Return to `/work-in-office` with a focused status message and briefly highlighted affected row:

- `Draft saved.`
- `WIO record saved.`
- `Submitted for approval.`

Do not use a success modal or celebration page.

### Work-in-office index

- Defaults to current month, newest first.
- Filters: month/custom date, WIO choice, review state.
- Primary action: `Record WIO`.
- Rows show date, location choice, review state, note indicator, and last update.
- Drafts and rejected claims appear in an attention section.
- No search in Phase 3.

## 9. Manager approval

`/approvals` is separate from Dashboard and visible only to eligible managers. Backend authorization remains mandatory.

### Phase 3 scope

- Pending office claims for assigned employees only.
- Oldest submission first.
- Maximum design target: 100 assigned employees per manager.
- Server pagination: 50 claims per page.
- List row shows employee, work date, base location, submitted time, and note indicator.
- Detail is optional; approve and reject are available from the list.
- Approve is one click with no confirmation.
- Reject requires a reason.
- No batch approval, advanced filters, saved views, or workflow metrics until Phase 4.

### Accidental approval

After approval, show a 10-second `Undo approval` action. Undo writes a separate audit reversal event; it never removes history. After the undo window, only HR/admin may reverse with an audited correction.

### Assignment ownership

- At most one approval manager may be effective for an employee on any date; overlaps are rejected.
- Submission snapshots the manager assignment effective on the WIO date.
- Missing manager coverage produces `Pending assignment`; HR/admin is never a silent fallback manager.
- That manager owns the claim even if a later assignment changes.
- The manager must still hold an active authorized membership when acting.
- HR/admin may explicitly reassign a pending claim with an audit reason.
- Historical decisions never migrate when assignments change.

### Cutoff behavior

- Never auto-approve or auto-reject.
- During reconciliation, prior-period unresolved claims sort first and remain actionable.
- Ratio remains provisional.
- At final cutoff, unresolved claims contribute zero and become `Expired pending`.
- HR/admin may reopen/correct only with an audit reason.

### Manager awareness

- Approvals sidebar item carries a pending-count badge.
- Refresh on navigation/focus and after a decision.
- Visual count caps at `99+`; accessible label exposes exact count.
- Approval page shows age of oldest pending claim.
- No per-submission manager email in Phase 3.

## 10. Fiscal-period ratio model

### Fiscal periods

Ratio policy uses company fiscal years, not calendar years.

Django Admin manages explicit Fiscal Period records:

- Name, start date, end date.
- Reconciliation cutoff timestamp.
- Status: Upcoming, Active, Reconciliation, Final.
- Periods cannot overlap.
- Only one period may be Active.
- Status normally derives from dates; audited admin reopen is exceptional.
- Admin may clone the previous period as a reviewed starting point.

Default reconciliation window is 14 days after fiscal year-end. Normal WIO submission deadlines do not extend; pending reviews and audited corrections may resolve during reconciliation. The result locks and becomes final at cutoff.

### Formula

- Eligible workdays are Monday–Friday minus public holidays, approved leave, and approved remote-work exceptions.
- Each eligible day contributes its effective expected-office fraction.
- Sum fractions across the requested calculation range and round up once.
- An approved whole-day office claim contributes one actual day.
- No half-day credit in MVP.
- Zero expected days displays `N/A`.
- Submitted records snapshot relevant assignment/rule versions for reproducibility.

### Status derivation

- Each employee has at most one effective-dated WIO policy assignment per date.
- An assignment is linked to one project.
- Employee and project each have a base location.
- Project assignment derives Same base or Different base.
- No project assignment means Benched.
- No daily category selection exists.
- Multi-project weighting is outside MVP.

### Ratio rules

- Benched, Same base, and Different base always have complete effective-dated rule coverage.
- Gaps and overlaps are rejected.
- Historical used versions cannot be edited or deleted.
- Future unused versions may change.

### Dashboard ratio

- Primary calculation: fiscal-year-to-date through today.
- Show uncapped percentage and equation, for example `6 approved / 5 expected`.
- Visual goal progress caps at 100%; excess appears as text such as `+1 day above expectation`.
- Do not label an employee generally compliant/non-compliant.
- While active, compare approved days with expected days accrued through today.
- Show exact recoverable deficit, pending claims, and eligible days remaining.
- Use amber warning while Active/Reconciliation; use error treatment only for a locked final miss.
- Do not predict unknown outcomes or count intentions as approved credit.

Monthly views do not present standalone compliance verdicts. They show activity and raw expected fractions. Custom ranges may show a clearly labeled range calculation, with a warning that separately rounded ranges are not additive.

## 11. Explainable reports

### Report boundaries

- Every calculation belongs to one fiscal period.
- A custom calculation cannot cross fiscal-period boundaries.
- Users may switch fiscal period.
- Cross-year UI may compare finalized summaries but never merge denominators, rules, or cutoffs.

### Per-day ledger

The complete ledger contains every calendar day. UI filters default to eligible days plus exceptions, but excluded rows remain available.

Each row exposes:

- Date.
- Eligibility or exclusion reason.
- Effective project status and rule version.
- Expected fraction.
- WIO location choice.
- Approval state and approved credit.
- Rounding input and final range result.

Desktop uses a table. Mobile uses stacked disclosure rows.

### Personal CSV export

Personal CSV export ships in Phase 3 on `/reports`, beside report filters.

- Exports the complete unfiltered ledger for the selected fiscal/month/custom range.
- Includes fiscal-period identifier and status.
- Uses the selected interface language for headers and ISO-safe data values where needed.
- Reports generation status and exact range.
- Excludes approver-note text by default.
- Excludes all Planner intentions and private Planner notes.
- Dashboard has no export button; it links to Reports.
- PDF is deferred.
- Manager/admin scoped exports remain Phase 7.

## 12. Private Planner intentions

Planner is a personal tool. Intentions never alter verified ratio, eligible-day calculation, WIO state, manager approval, or audit credit.

### Intention fields

- Date.
- Location: Office or Home.
- Commitment: Firm or Flexible.
- Optional private plain-text note, maximum 300 characters.
- No rich text or attachments.

Absence of an intention means undecided; do not add a third Undecided value.

Only the owning employee may access intention fields through product UI and APIs. Managers and HR/admin receive no product access to location, commitment, or note content.

### Creation modes

- Single date.
- Bulk continuous start/end range.
- Recurring selected weekdays within required start/end dates.

Rules:

- New intentions may start today or later; no backdating.
- All intentions must fall within the current active fiscal period.
- Bulk and recurring operations skip ineligible dates and show reasons.
- Weekends and admin-managed holidays are skipped; approved leave and remote exceptions also make a date ineligible.
- No monthly patterns, arbitrary recurrence intervals, open-ended series, or cross-fiscal-year recurrence.
- Recurring edits support one occurrence, this-and-future, or whole series.
- Series edits/removal affect today and future only; elapsed dates are never bulk-rewritten.
- Past single intentions may be manually removed.

### Conflict behavior

- One effective intention per employee/date.
- Before bulk/series save, preview conflicts.
- Offer `Skip existing` or `Replace existing`; default to Skip.
- Never silently overwrite notes.
- Replacement affects selected dates only.
- Existing WIO records do not block intentions; fact and plan remain separate.

### Storage model

Materialize one private occurrence row per eligible date, optionally linked to a series record.

- Series stores pattern and shared defaults.
- Per-date rows support unique employee/date constraints and fast monthly queries.
- One-occurrence edits become overrides.
- This-and-future splits a series.
- Fiscal purge removes occurrences and series together.
- Bulk operations are transactional after conflict preview.

### Projection

Projection is presented as **plan coverage**, never predicted approval:

- Verified ratio remains approved days divided by accrued expected days.
- Fiscal projection uses currently configured full-period rules, assignments, holidays, leave, and exceptions.
- Firm Office intentions form minimum planned office count.
- Flexible Office intentions extend optimistic planned count.
- Home intentions add no office credit.
- Example: `Current plan covers 42–48 of 50 expected office days.`
- Warning includes remaining uncovered amount and unplanned eligible days.
- No project assignment projects as Benched.

### Later eligibility changes

If admin later makes an intended date ineligible:

- Retain intention temporarily but mark it Excluded.
- Remove it from projection immediately.
- Gray the date and show exclusion reason plus previous intention details.
- Disable location/commitment edits; user may delete it.
- Recurring pattern remains unchanged and skips the occurrence.

### Deletion and retention

- Single deletion offers brief undo.
- Series deletion requires confirmation.
- Deleted intention content has no product audit/history trail.
- Security logs may record actor, timestamp, and success/failure, never note/location/commitment content.
- At fiscal final cutoff, automatically purge intention notes, occurrences, and series.
- Notify users before scheduled purge.

### Planner UI

- Desktop: month calendar left, editor/details panel right.
- Mobile: month calendar above selected-date editor.
- Toolbar: Single, Bulk, Recurring.
- Projection summary appears above calendar.
- Upcoming list follows calendar for scanning and keyboard access.
- Initial defaults require explicit location and commitment, use Monday week start, open current month, and do not remember last creation mode.
- Settings may store personal default location, commitment, and week start.

## 13. Administration

Phase 3 HR/admin workflows stay in Django Admin rather than a custom frontend.

Admin scope:

- Projects and project base locations.
- Employee base locations.
- Effective-dated employee project assignments.
- Effective-dated ratio rules.
- Manager assignments and pending-claim reassignment.
- Fiscal periods and reconciliation cutoffs.
- Public holidays.
- Approved leave ranges.
- Approved remote-work exception ranges.
- Audited overrides and period reopen/correction.

Holiday records are company-wide date/name. Leave and remote exception records are employee ranges with optional internal reference/reason. Overlaps deduplicate eligibility exclusions. Non-final periods recalculate immediately; finalized periods require explicit audited reopen/correction.

## 14. Settings, profile, theme, and language

### Settings

- Theme: System, Light, Dark.
- Language: English, Vietnamese.
- Planner defaults: location, commitment, week start.
- Reduced-motion override.
- Read-only company timezone and current fiscal-period information.
- Log out action.

Do not expose daisyUI's novelty theme catalog. System theme follows OS changes live. Persist authenticated preference server-side and use local fallback before login to prevent theme flash.

### Language

- English is default until chosen; browser locale is a first-visit hint.
- Translate UI, validation, dates, ratio explanations, Planner, and CSV headers.
- User-entered notes remain untouched.
- No locale-prefixed URLs.
- Update the document language correctly.
- Missing translations fail CI; avoid mixed-language screens.

### Profile

Profile shows full name, email, company, role, base location, manager, and active project/policy assignment with relevant effective dates.

The user may edit preferred display name only. Legal/full name, email, role, base, manager, and assignment remain admin-managed.

## 15. Notifications

- Dashboard and Work-in-office surfaces show current review states.
- Send email only when an office claim is rejected because action is required.
- Rejection email includes date, state, and secure link; no sensitive note content.
- Do not send approval emails by default.
- Do not build a notification center in Phase 3.
- Manager awareness comes from the Approvals navigation badge and queue age.
- Phase 7 moves OTP and approval-related email to the durable outbox/background worker described by the roadmap.

## 16. Accessibility and responsive quality

Target WCAG 2.2 AA.

- Keyboard-complete navigation and workflows.
- Visible focus.
- Semantic landmarks and heading hierarchy.
- Accessible modal drawer, dialogs, confirmations, and undo notices.
- Non-color state indicators.
- Persistent heatmap legend and complete cell labels.
- Screen-reader status announcements without repeated noise.
- 44px touch targets where practical.
- Reflow at 200% zoom without page-level horizontal scrolling.
- Reduced-motion support.
- Contrast verified independently in Light and Dark themes.
- English and Vietnamese layouts tolerate text expansion.

## 17. Data integrity and concurrency

- Database constraint enforces one current WIO record per employee/date.
- Database constraint enforces one intention per employee/date.
- Effective-date ranges reject invalid overlaps.
- Mutable WIO and intention resources carry a version.
- Stale updates return `409 Conflict`.
- UI preserves unsaved input, reloads latest state, and explains the conflict.
- Manager action succeeds only while claim remains Pending.
- Bulk intention writes are atomic; never partially save a requested operation.
- Server time and company timezone, not browser time alone, enforce deadlines.

## 18. Audit visibility

- Employee sees full event timeline for their own WIO record.
- Assigned manager sees timeline for claims inside assignment scope.
- HR/admin sees all authorized audit information through Django Admin.
- Events show actor role, timestamp, action, and reason where applicable.
- Never expose security metadata, private Planner content, or unrelated account data.

WIO audit includes creation, draft save/delete, submission, Not-in-office correction, rejection, resubmission, approval, approval reversal, reassignment, HR override, and final-period correction.

## 19. Suggested backend modules and records

Keep backend as existing Django modular monolith. Suggested records:

- `FiscalPeriod`
- `BaseLocation`
- `Project`
- `EmployeeProjectAssignment`
- `ProjectStatusRule`
- `PublicHoliday`
- `ApprovedLeave`
- `RemoteWorkException`
- `WorkInOfficeRecord`
- `ApprovalDecision` or explicit approval audit events
- `WorkIntentionSeries`
- `WorkIntentionOccurrence`
- `UserPreference`
- Existing effective-dated `ManagerAssignment`
- Existing `AuditEvent`

Keep ratio calculation in a pure, testable domain service. The service should accept period/range, employee policy history, exclusions, WIO approvals, and an as-of date, then return totals plus the per-day explanation ledger. Projection should be a separate service layered over verified calculation plus future intentions.

## 20. Suggested API groups

Exact payloads belong in implementation design, but route responsibilities should remain separate:

- `/api/v1/work-in-office/`
- `/api/v1/approvals/`
- `/api/v1/reports/ratio/`
- `/api/v1/reports/ratio/export/`
- `/api/v1/intentions/`
- `/api/v1/intentions/preview/`
- `/api/v1/preferences/`
- Existing admin/model endpoints as needed for Django Admin.

Dashboard may use a composed read endpoint if measurement proves multiple requests too costly, but independent module error boundaries must remain possible.

## 21. Delivery sequence

Implementation plans and completion gates for every slice are listed in the [Phase 3 subphase index](README.md).

### Slice 0 — prerequisite gate

Finish Phase 2 identity hardening and protected-route browser contract.

### Slice 1 — fiscal and policy foundation

- Fiscal periods and cutoff states.
- Base locations, projects, assignments, complete ratio rules.
- Holidays, leave, and remote exceptions.
- Django Admin configuration and validation.
- Pure ratio calculator with per-day ledger tests.

### Slice 2 — WIO records

- WIO model, unique date rule, versions, deadlines, drafts.
- In-office and Not-in-office semantics.
- Conditional approver note.
- Personal index/detail/create APIs and pages.
- Audit timeline.

### Slice 3 — approval slice

- Assignment-scoped pending queue.
- Inline approve, reject reason, 10-second undo.
- Rejection correction/resubmission.
- Expired-pending and reconciliation behavior.
- Rejection email.

### Slice 4 — ratio and reports

- Fiscal-year-to-date summary.
- Complete explainable ledger.
- Custom in-period ranges.
- Personal CSV export.
- Final/provisional states.

### Slice 5 — private Planner

- Single, bulk, and recurring intentions.
- Conflict preview and transactional writes.
- Series edits and future-only constraints.
- Plan-coverage projection.
- Fiscal purge and privacy controls.

### Slice 6 — app shell and dashboard

- Sidebar, mobile drawer, profile bar, role-aware navigation.
- Two Horizons dashboard.
- Monthly heatmap and accessible legend.
- Recent WIO and upcoming intentions.
- Partial loading/error/empty states.

### Slice 7 — preferences and localization

- Settings and Profile.
- System/Light/Dark theme.
- English/Vietnamese localization.
- Pre-auth theme/language controls.
- Reduced-motion and Planner defaults.

### Slice 8 — hardening and release gate

- Authorization matrix tests.
- Concurrency and duplicate tests.
- Accessibility/manual keyboard checks.
- Responsive and dark-theme checks.
- CSV integrity and injection-safety checks.
- Full end-to-end journeys.
- Observability for WIO, approval, ratio, export, and projection failures without sensitive content.

Frontend shell and localization infrastructure may start earlier in parallel once contracts stabilize, but feature release should follow dependency order above.

## 22. Required end-to-end acceptance journeys

1. Employee records In office; assigned manager approves; ratio and heatmap update.
2. Manager rejects; employee sees required-action email/UI, edits, and resubmits.
3. Employee records Not in office; zero credit is recorded and no approval task exists.
4. Employee saves, continues, and deletes a draft; duplicate date is blocked.
5. Rule, project assignment, and base-location changes preserve historical calculations.
6. No project assignment calculates as Benched.
7. Holidays, leave, and remote exceptions explain eligibility correctly.
8. Planner single, bulk, and recurring actions alter projection only.
9. Planner conflict preview handles skip and replace atomically.
10. Fiscal cutoff purges private intentions and finalizes unresolved pending claims correctly.
11. CSV totals match complete ledger and exclude private/approver notes.
12. English/Vietnamese and System/Light/Dark choices persist before and after sign-in.
13. Unauthorized employee, manager, and admin access remains blocked at route and API layers.
14. Heatmap remains understandable by keyboard and screen reader without color.

## 23. Roadmap amendments

Update `ROADMAP.md` in a later explicit implementation/documentation change with these accepted amendments:

### Add to Phase 3

- Protected sidebar app shell and Two Horizons dashboard.
- Fiscal-period administration with a configurable reconciliation cutoff.
- Fiscal-year-to-date ratio presentation; selected-month activity heatmap.
- Personal private intentions: single, bulk, and selected-weekday recurrence.
- Plan-coverage projection warnings that never affect verified ratio.
- Personal CSV export from Reports.
- System/Light/Dark theme selection.
- English/Vietnamese localization.
- Settings and Profile surfaces.
- Only positive office claims require manager approval; Not-in-office records receive zero credit without approval.

### Reorder later phases

- Phase 5 becomes office seating: floor plans, seat administration, and daily seat selection.
- Phase 6 combines evidence and endorsements: private evidence lifecycle plus tag/endorse/withdraw workflows.
- Phase 7 pilot/hardening remains the next phase and keeps manager/admin scoped exports plus durable notification delivery.
- Remove theme selection and initial i18n from Phase 8 because they move to Phase 3.

### Preserve later extension seams

Phase 3 WIO forms and record details must leave room for:

- Phase 5 office/floor/seat selection.
- Phase 6 private evidence upload/webcam lifecycle.
- Phase 6 endorser tagging and endorsement history.

Do not expose disabled placeholder controls to users; preserve architectural/component seams only.

## 24. Explicit non-goals for Phase 3

- Custom HR/admin frontend.
- Batch approval or advanced manager workflow.
- Line/company dashboards.
- Manager/admin exports.
- PDF export.
- Evidence upload or webcam capture.
- Seat selection or floor-plan editor.
- Endorser tagging or endorsement actions.
- Notification center or manager email digest.
- Multi-project weighted assignments.
- Half-day office credit.
- Monthly recurrence patterns or cross-fiscal intention series.
- Gamification, badges, or compliance ranking.
- Public marketing landing-page redesign; `/` remains authentication/access entry.

## 25. Builder-owned implementation details

The following may be resolved during technical design without changing product intent:

- Exact serializers and endpoint payload shapes.
- Query/cache library choice.
- Whether Dashboard uses composed or parallel read endpoints after measurement.
- Exact semantic color token values, provided accepted meanings and WCAG contrast remain intact.
- CSV filename format and low-level encoding compatibility.
- Internal class/model names during any staged migration away from `WorkLog` terminology.

Any change to user-visible workflow, fiscal calculation, privacy, approval scope, intention retention, or phase ordering requires product confirmation and an update to this document.
