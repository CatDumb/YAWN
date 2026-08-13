# YAWN Roadmap

## Product goal

Single-company web app for tracking daily work-in-office (WIO) activity, expected office ratio, manager approval, peer endorsement, optional evidence, and office seating.

## Initial ratio rules

Ratio formula:

`approved office days / expected office days`

YAWN also exposes a separate self-submitted audit stream: submitted in-office claims divided by the same expected-day denominator. It is for later comparison with an official system; no external import or reconciliation is part of this scope.

| Project status | Expected office ratio |
|---|---:|
| Benched | 100% |
| Same-base project | 50% |
| Different-base / off-shore project | 5% |

Rules are admin-configured and effective-dated. Applied rule is stored with each submitted log, while employee project-status history preserves expected-day calculation for dates without a log.

MVP calculation rules:

- Eligible workdays are Monday through Friday, excluding configured public holidays, approved leave, and approved remote-work exceptions.
- Each eligible date contributes its effective expected-office ratio. Sum daily fractions across the report range and round up once to a whole expected office day.
- An approved whole-day office log contributes one actual office day. MVP has no half-day credit.
- Pending, rejected, and expired in-office claims remain in the self-submitted audit stream but never add official Approved credit.
- If expected office days are zero, compliance ratio displays `N/A` rather than dividing by zero.
- Rule and project-status changes are effective-dated so mixed-status reporting ranges remain reproducible.

## MVP requirements

- Email OTP authentication.
- Roles: employee, line manager, HR/admin.
- Employee creates one daily log with office status, project status, note, optional evidence, optional seat, and tagged endorsers.
- Evidence supports file upload or direct laptop webcam capture.
- Evidence stored privately with role-based access.
- Manager approval queue with approve/reject and rejection reason.
- Peer endorsements provide audit signal only; they do not approve logs.
- Admin-managed floor plans for 1–2 office floors and selectable seats.
- Monthly dashboard and custom date-range reports.
- Optional employee-entered transition baseline for moving legacy target and achieved WIO totals into the current fiscal period; local WIO begins after its completed-month cutoff.
- Audit history for edits, approvals, rejections, endorsements, and evidence access.

## Delivery phases

### Phase 1: Foundation

- Create Next.js frontend and Django + Django REST Framework backend.
- Configure PostgreSQL, Django migrations, environments, CI, and deployment.
- Add Dockerfile for frontend and backend build consistency.
- Add Docker Compose for local Django, PostgreSQL, and optional Redis services.
- Add GitHub Actions CI checks for backend, frontend, Docker builds, and security scanning.
- Add staging and production deployment workflows with protected production approval.
- Add health endpoint, error monitoring, structured logs, and deployment alerts.


### Phase 2: Identity and access

- Add administrator-provisioned user registration and active company memberships.
- Add employee, line manager, and HR/admin role assignment.
- Add role and company permission checks.
- Add email OTP request, verification, session, logout, CSRF, and rate-limit behavior.
- Before Phase 3, complete identity hardening: require explicit inactive-membership reactivation,
  cover OTP abuse-control branches, bound synchronous SMTP delivery with a hard timeout, and enforce
  the 60-second resend policy consistently.
- Separate the public access/login entry at `/` from the protected `/dashboard` route, and add one
  real-browser authentication contract test across Next.js and Django.


### Phase 3: Daily logs and ratio

- Add project, employee base location, and ratio-rule administration.
- Add draft, submit, edit, and duplicate-date protection.
- Add the minimum assignment-scoped approve/reject path needed for a complete
  create-submit-approve-ratio slice, including state locks and audit events.
- Add personal monthly dashboard and custom-range ratio reports.
- Make ratio results explainable with a per-day ledger containing eligibility or exclusion reason,
  effective rule/version, expected fraction, approved credit, and rounding inputs/results.
- Add personal activity heatmap with calendar days shaded by activity; distinguish submitted logs from approved WIO days.

### Phase 4: Manager workflow

- Expand manager-to-employee assignment administration beyond the minimum Phase 3 path.
- Add dedicated pending queue, filters, and workflow-management UX.
- Expand approve/reject handling and rejection-reason UX without changing Phase 3 approval semantics.
- Preserve approved-log immutability and audit records established by the Phase 3 slice.

### Phase 5: Endorsements

- Allow employees to tag colleagues.
- Allow tagged colleagues to endorse or withdraw endorsement.
- Display endorsement history on logs.

### Phase 6: Evidence and seat map

- Add private image upload.
- Add explicit browser webcam capture permission flow.
- Store retention deadline with evidence and delete content 90 days after final approval or rejection,
  unless legal hold applies.
- Add legal-hold administration, idempotent deletion, deletion audit events, and retained audit
  metadata in the same release as upload; do not defer lifecycle enforcement to pilot hardening.
- Add admin floor-plan and seat editor.
- Add daily seat selection.
- Keep integration boundary for future room-booking or external map systems.

### Phase 7: Pilot and hardening

- Before pilot traffic, move OTP and approval email from request workers to a durable
  outbox/background worker with bounded retries, idempotency, operator recovery, queue monitoring,
  and an end-to-end delivery check.
- Pilot with one team/company.
- Validate ratio, approval, evidence privacy, and seat workflows.
- After pilot feedback, add line and company dashboards with role- and scope-based metrics.
- Add manager and admin report exports with line- and company-scoped access; define export formats, permissions, and report contents.
- Add reminders and external integrations only after pilot feedback.

### Phase 8: Future engagement

- Add personal achievement badges only after pilot feedback confirms activity metrics are useful, fair, and resistant to gaming.
- Add i18n and a user-selectable theme switch; keep light as default while respecting the operating system's dark
  preference until then.

## Deployment plan

- Local development uses Docker Compose.
- Frontend deploys to Vercel.
- Django API deploys as a Docker service on Render or equivalent managed container platform.
- PostgreSQL uses managed hosting with automated backups.
- Evidence images use private S3-compatible object storage, not container or server disk.
- CI builds and tests Docker images before deployment.
- Production deployment runs migrations before starting the new application version.
- Use separate development, staging, and production environments.
- Add health check endpoint, structured logs, error monitoring, HTTPS, and secret management.

## CI/CD plan

- Pull requests run formatting, linting, type checks, unit tests, integration tests, frontend build, and Docker image build.
- Merge to `main` deploys staging automatically.
- Release tag or manually approved workflow deploys production.
- Run Django deployment checks and database migrations during deployment.
- Use GitHub Environments for staging and production secrets and approval rules.
- Use dependency and container vulnerability scanning.
- Keep deployment artifacts tagged by commit SHA for rollback.
- Add smoke tests after deployment and stop rollout when health checks fail.

## Observability plan

- Add `/health/` and `/ready/` endpoints.
- Capture structured JSON logs with request ID, user ID where safe, route, status, latency, and deployment version.
- Send frontend and backend exceptions to Sentry or equivalent error-monitoring service.
- Track API latency, error rate, login failures, approval failures, upload failures, and database errors.
- Add uptime checks for frontend, API health endpoint, and critical login flow.
- Alert on elevated 5xx responses, failed deployments, unavailable database, and storage/email failures.
- Never log OTP values, session tokens, evidence URLs, webcam images, or sensitive personal data.
- Add OpenTelemetry traces and metrics after MVP baseline monitoring works.

## Acceptance tests

- Correct ratio for 100%, 50%, and 5% rules.
- Historical logs keep original applied rules after policy changes.
- Employee cannot approve logs or access another employee’s private evidence.
- Manager sees only assigned employees.
- Rejected log shows reason and can be resubmitted.
- Duplicate employee/date logs are blocked.
- Endorsement never changes approval state.
- Webcam denial falls back to upload or no evidence.
- Invalid seat selection is rejected.
- End-to-end flow passes: login, create log, evidence, seat, endorsement, manager approval, ratio update.

## MVP policy decisions

- Company membership is administrator-provisioned. Matching an email domain never grants access by itself.
- Company timezone is `Asia/Ho_Chi_Minh`. Calendar dates and submission deadlines use that timezone.
- Initial submission closes at 23:59 local time on the following calendar day. HR/admin override requires an audit event.
- Draft logs are editable. Submitted logs are locked. Rejected logs may be edited and resubmitted. Approved logs are immutable.
- Weekends, configured public holidays, approved leave, and approved remote-work exceptions do not count as eligible workdays.
- Evidence content is retained for 90 days after final approval or rejection, then deleted unless legal hold applies. Audit metadata remains.
- OTP expires after 10 minutes, allows five verification attempts, has a 60-second resend cooldown, and limits requests per email and request fingerprint.
- One employee may hold one seat per date, and one seat may belong to only one employee per date. Enforce both rules with database constraints.
- Manager assignments are modeled during Phase 2; the minimum assignment-scoped approval path
  arrives in Phase 3, and richer manager workflow arrives in Phase 4.
