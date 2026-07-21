# Phase 2: access request, login, admin user control

> **Status — read before implementing:** Phase 2 access control, OTP login, Admin lifecycle,
> frontend auth flow, and flow documentation are already implemented in this working tree. Do not
> rebuild them. Backend audit on 2026-07-21: `41` tests pass. The development seed command below
> is now implemented. All Phase 2 identity and access items are present in this working tree.
>
> **Current work:** [Phase 2.1: Gmail OTP delivery and approval email](#phase-21-gmail-otp-delivery-and-approval-email)
> is implemented in this working tree. Its settings and limits override older OTP defaults elsewhere.

## Branch and documentation

- Create `feat/phase-2-identity-access` from clean `main`.
- Add root `recap.md`: current implementation, auth API inventory, gaps, and baseline checks: backend 41 passing / frontend 10 passing.
- Add Markdown flow docs:
  - `docs/auth-sign-up.md`: access-request flow.
  - `docs/auth-login.md`: OTP/session/logout flow, including disabled-user denial.
  - `docs/admin-user-lifecycle.md`: review, approve, reject, disable, and enable flow.
- Each doc includes actors, preconditions, happy/failure paths, API/admin actions, security rules, and PlantUML use-case diagram source. Link docs from `README.md`.

## Backend: public signup

- Add `AccessRequest` model and migration:
  - Target `company`, normalized email, first/last name, hashed requester fingerprint, status (`pending`, `approved`, `rejected`), timestamps, reviewer.
- Add public `POST /api/v1/auth/sign-up/`.
  - Payload: `email`, `first_name`, `last_name`.
  - Generic `202` response; never creates session, sends OTP, grants membership, or reveals account status.
  - Route requests only to active company from `WIO_SIGNUP_COMPANY_SLUG`.
  - Coalesce duplicate pending requests and apply separate email/fingerprint limits.
- Add signup company/rate-limit variables to `backend/.env.example`.
- Add a development-only, one-time admin seed command:
  - `python manage.py seed_dev_admin` creates `admin@wio.local` with password `admin`.
  - Seed user is active, staff, superuser, and has an active HR/admin membership in the seed company.
  - Command creates the seed company if absent, never resets an existing account, and becomes a no-op after successful seeding.
  - Command exits unless `DJANGO_DEBUG=true` and `WIO_ALLOW_INSECURE_DEV_SEED=true`; it must never run automatically in Docker, CI, staging, or production.
- Add `WIO_ALLOW_INSECURE_DEV_SEED=false` to `backend/.env.example` and document the explicit local-only seed command in `README.md`.

## Admin: access and user lifecycle

- Register access requests in Django Admin, visible only to superusers or active HR/admin members with staff access.
- Add review actions:
  - Approve: atomically create/reuse user, create/reactivate employee membership, mark approved, audit event.
  - Reject: mark rejected and audit event.
  - Approval never creates a session; user must complete normal OTP login.
- Add explicit user actions in Django Admin:
  - Disable selected users: set `User.is_active=False`, preserve memberships/history, write `accounts.user_disabled` audit event.
  - Enable selected users: set `User.is_active=True`, preserve membership state, write `accounts.user_enabled` audit event.
  - Remove direct `is_active` editing from admin forms so disable/enable cannot bypass audit.
- Disabled user behavior:
  - Existing session fails on next authenticated request.
  - OTP requests remain generic and send no email; OTP verification cannot create session.
  - Re-enabling user does not activate a disabled membership; HR/admin must activate membership separately.
  - Access-request approval never silently re-enables a disabled user.

## Frontend: signup first, then login

- Replace Phase 1 landing with client auth entry state.
- Default unauthenticated view is access-request form.
  - React Hook Form + Zod validation for names/email.
  - Generic pending-review confirmation after submit.
  - Explicit login action for already approved users.
- Login view:
  - Request OTP, retain normalized email + `challenge_id`, accept six digits, verify, create signed-in state.
  - Handle invalid/expired code, retry, API outage, and return-to-email states.
- App initialization calls `/api/v1/users/me/`.
  - Active session: protected Phase 2 placeholder with identity, memberships/roles, logout.
  - `401`/`403`: return to signup-first state.
- Reuse `apiFetch` credential/CSRF behavior and daisyUI. No Phase 3 dashboard or work-log work.

## Tests and acceptance

- Backend:
  - Signup creates only pending request; duplicate/rate-limited cases stay non-enumerating.
  - Approval enables OTP only when user and membership active; rejection does not.
  - Disable blocks protected requests and OTP delivery/login; enable restores eligibility only with active membership.
  - Lifecycle actions write audit events without email or OTP data.
  - Unauthorized Django Admin users cannot review requests or toggle users.
  - Development seed creates the expected admin, company, and HR/admin membership once; repeat execution never resets the password or privileges.
  - Development seed refuses to run when debug mode or explicit insecure-seed opt-in is absent.
- Frontend:
  - Signup initial state, validation, generic confirmation, transition to login.
  - OTP success/failure, session restore, logout, disabled response, retryable failures.
- Run `uv run pytest -p no:cacheprovider`, `npm run lint`, `npm run typecheck`, and `npm test`.

## Locked defaults

- Public signup is access request, not immediate activation.
- HR/admin reviews access and manages account lifecycle in Django Admin.
- Disable is global user suspension; memberships remain intact for safe re-enable.
- Docs use PlantUML use-case diagrams stored as readable Markdown source.
- Development seed login uses email `admin@wio.local` and password `admin`, because email is this app's username. It is explicitly opt-in and local-only.

## Phase 2.1: Gmail OTP delivery and approval email

### Scope and status

- **Implemented:** Gmail SMTP configuration, production deployment validation, Compose wiring,
  scheduled cleanup, and post-approval notification email.
- **Already implemented; preserve:** approved-user-only OTP eligibility, public access-request
  endpoint/page, Django Admin approval/rejection, OTP hashing/expiry/attempt limit, generic
  responses, CSRF/session login, audit events, and frontend six-digit-code flow.
- No Node/Express service, schema migration, OTP API change, queue/worker, retry system, HTML
  email, resend countdown, or delivery metrics in this phase.

### Gmail SMTP and deployment

- Use one dedicated Gmail account for YAWN. Enable Google 2-Step Verification and create an App
  Password; never commit it.
- Use Django SMTP with `smtp.gmail.com`, port `587`, TLS, Gmail address as
  `DJANGO_EMAIL_HOST_USER`, App Password as `DJANGO_EMAIL_HOST_PASSWORD`, and the same address in
  `DJANGO_DEFAULT_FROM_EMAIL`.
- Replace Resend-only production settings with provider-neutral SMTP settings. Production must
  fail startup when SMTP host, port, username, password, TLS, sender, or `WIO_APP_URL` is missing
  or invalid. `WIO_APP_URL` must be an HTTPS frontend homepage URL in deployment.
- Local direct Django keeps console email fallback when SMTP variables are absent; local Gmail
  testing reads ignored `backend/.env`. Docker Compose must stop overriding the email backend and
  pass ignored project `.env` SMTP values through to the backend.
- Deploy the existing Compose stack with production settings/host secrets and add a cleanup
  service. It waits for PostgreSQL, runs `purge_expired_otps --hours 24` and `clearsessions`, then
  repeats every 24 hours.

### OTP and session policy

- Keep OTP lifetime at 10 minutes and maximum verification attempts at five.
- Set `WIO_OTP_RESEND_SECONDS=30`, `WIO_OTP_REQUESTS_PER_HOUR=5`, and
  `WIO_OTP_IP_REQUESTS_PER_HOUR=100` explicitly in environment examples and deployment settings.
- Keep `WIO_TRUST_PROXY_HEADERS=false` until a trusted proxy overwrites forwarded headers.
- Keep fixed 14-day Django sessions; set the lifetime explicitly and do not refresh expiry on every
  request. New OTP is required after expiry, logout, cleared browser data, or a new device.
- Gmail send failure remains generic and is logged without recipient or secret. Do not retry in
  this phase; user may request another OTP after cooldown.

### Access approval notification

- Keep public access requests. Only authorized Django Admin approval of a `pending` request sends
  the notification; rejection, disable, enable, repeated approval, direct user creation, and
  membership reactivation do not.
- After approval transaction commits, send one plain-text Gmail email: access approved, homepage
  link from `WIO_APP_URL`, and instruction to choose **Already approved? Sign in**. Include no OTP,
  password, session link, or sensitive account data.
- Keep approval atomic. Notification failure cannot roll back approval; log
  `approval_email_delivery_failed` without recipient or message content. Add a TODO for branded
  HTML email later.

### Verification and documentation

- Add automated tests for production SMTP/app URL validation, 30-second cooldown, five-per-email
  and 100-per-IP limits, fixed 14-day session policy, scheduled cleanup commands, approval email
  after commit, rejection/no-op paths, and secret-safe delivery-failure logging.
- Preserve existing OTP/Admin lifecycle tests. No live Gmail credential runs in automated tests;
  use Django local-memory email backend there.
- Update backend setup, deployment docs, access-request flow, and Admin lifecycle flow with Gmail
  App Password setup, local/deployed secret locations, `WIO_APP_URL`, cleanup, and release test.
- Release test: submit public request, approve in Admin, receive approval email, open homepage,
  request OTP, receive Gmail code, verify in frontend, confirm session, wait 30 seconds, resend,
  and confirm logout/login behavior.
