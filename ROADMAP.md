# WIO Tracker Roadmap

## Product goal

Single-company web app for tracking daily work-in-office (WIO) activity, expected office ratio, manager approval, peer endorsement, optional evidence, and office seating.

## Initial ratio rules

Ratio formula:

`actual approved office days / expected office days`

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


### Phase 3: Daily logs and ratio

- Add project, employee base location, and ratio-rule administration.
- Add draft, submit, edit, and duplicate-date protection.
- Add monthly and custom-range ratio dashboards.

### Phase 4: Manager workflow

- Add manager-to-employee assignments.
- Add pending approval queue.
- Add approve/reject actions and rejection reasons.
- Freeze approved-log changes; preserve audit records.

### Phase 5: Endorsements

- Allow employees to tag colleagues.
- Allow tagged colleagues to endorse or withdraw endorsement.
- Display endorsement history on logs.

### Phase 6: Evidence and seat map

- Add private image upload.
- Add explicit browser webcam capture permission flow.
- Add admin floor-plan and seat editor.
- Add daily seat selection.
- Keep integration boundary for future room-booking or external map systems.

### Phase 7: Pilot and hardening

- Pilot with one team/company.
- Validate ratio, approval, evidence privacy, and seat workflows.
- Add reminders, exports, analytics, and external integrations only after pilot feedback.

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
- Manager assignments are modeled during Phase 2; assignment-scoped approval behavior arrives in Phase 4.
