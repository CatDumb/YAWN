# Phase 2: access request, login, admin user control

> **Status — read before implementing:** Phase 2 access control, OTP login, Admin lifecycle,
> frontend auth flow, and flow documentation are already implemented in this working tree. Do not
> rebuild them. Backend recheck on 2026-07-21: `44` tests pass. The development seed command below
> is now implemented. All Phase 2 identity and access items are present in this working tree.
>
> **Current work:** Phase 2.1 baseline is implemented; Phase 2.2 supersedes its cooldown and
> delivery-safety targets. Execute
> [Phase 2.2: security and architecture closeout](#phase-22-security-and-architecture-closeout)
> before starting Phase 3.

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
- Set `WIO_OTP_RESEND_SECONDS=60`, `WIO_OTP_REQUESTS_PER_HOUR=5`, and
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

- Add automated tests for production SMTP/app URL validation, 60-second cooldown, five-per-email
  and 100-per-IP limits, fixed 14-day session policy, scheduled cleanup commands, approval email
  after commit, rejection/no-op paths, and secret-safe delivery-failure logging.
- Preserve existing OTP/Admin lifecycle tests. No live Gmail credential runs in automated tests;
  use Django local-memory email backend there.
- Update backend setup, deployment docs, access-request flow, and Admin lifecycle flow with Gmail
  App Password setup, local/deployed secret locations, `WIO_APP_URL`, cleanup, and release test.
- Release test: submit public request, approve in Admin, receive approval email, open homepage,
  request OTP, receive Gmail code, verify in frontend, confirm session, wait 60 seconds, resend,
  and confirm logout/login behavior.

## Phase 2.2: security and architecture closeout

> **Executor instructions:** Execute work packages in order. Run each package's focused verification
> before continuing, then run the complete final gate. Do not implement Phase 3 product behavior in
> this closeout. If any STOP condition occurs, stop and report instead of widening scope.

### Status and drift check

- **Priority:** P1; blocks Phase 3.
- **Effort:** L across several small commits.
- **Risk:** MED because auth behavior and route ownership change.
- **Planned at:** commit `78ff489`, 2026-07-21.
- **Drift check:** before starting, run:

  ```powershell
  git diff --stat 78ff489..HEAD -- backend/apps/accounts backend/config/settings backend/tests frontend/src frontend/package.json frontend/package-lock.json tests scripts README.md TECHSTACK.md docs/infrastructure.md recap.md .env.example backend/.env.example
  ```

  Compare changed in-scope files with this plan. If behavior or paths no longer match, stop and
  refresh affected work package before editing.

### Locked decisions

- Access-request approval must skip existing inactive membership. It leaves request pending and
  grants no authority. Explicit membership reactivation remains only reactivation path.
- OTP resend cooldown is 60 seconds.
- SMTP stays synchronous in Phase 2 but gets 10-second hard connection timeout. No queue, retry
  system, Redis requirement, or worker belongs in this phase.
- `/` remains public access/login entry. Successful authentication routes to protected
  `/dashboard`.
- A `401` or `403` from session restoration or logout means local signed-in state is invalid and
  must be cleared. Network errors and `5xx` responses retain local state and show retry feedback.
- Cross-service coverage uses local test infrastructure only. Never add OTP-inspection endpoint or
  weaken production auth to make test easy.
- Render pre-deploy is sole production migration owner.

### Current state

- `backend/apps/accounts/admin.py:173-206` calls `get_or_create()` and currently sets
  `membership.is_active = True` for every existing inactive membership, preserving privileged role.
- `backend/apps/accounts/views.py:151-279` contains email/fingerprint limits, expiry, attempt
  exhaustion, challenge matching, and OTP verification. Existing tests cover email limit and resend
  reuse but not every security branch.
- `backend/apps/accounts/services.py:11-60` calls Django `send_mail()` from `transaction.on_commit()`;
  `backend/config/settings/base.py:131-140` has no `EMAIL_TIMEOUT`.
- `frontend/src/app/page.tsx` is one 606-line client component containing schemas, API orchestration,
  auth state, all forms, session restoration, signed-in placeholder, and logout.
- `frontend/src/lib/api.ts` owns credentialed fetch and CSRF acquisition. Preserve this boundary;
  feature code must call `apiFetch`, not raw `fetch`.
- `frontend/src/app/page.test.tsx:273-294` expects all logout failures to retain signed-in UI. That is
  correct for transient failures but wrong for `401`/`403`.
- `docs/testing.md` promises cross-service/E2E tests, but no real-browser auth test exists.
- `docs/infrastructure.md:56` correctly assigns migrations to Render pre-deploy;
  `TECHSTACK.md:117-118` incorrectly says GitHub workflows run them.
- Baseline already repaired after audit: commit `72e5171` restored static-file isolation and commit
  `78ff489` fixed company-ID authorization. Do not reimplement either change.

### Repository conventions

- Backend: Python 3.12, Django/DRF, pytest-django, Ruff, 100-column lines. Follow existing tests in
  `backend/tests/test_auth.py` and `backend/tests/test_admin_lifecycle.py`.
- Frontend: Next.js App Router, TypeScript, React, React Hook Form, Zod, Tailwind CSS 4, daisyUI 5,
  Vitest/Testing Library. Use semantic daisyUI classes and keep `apiFetch` as HTTP boundary.
- Commits use Conventional Commits. Make one logical commit per work package; examples:
  `test(auth): cover OTP abuse controls`, `fix(admin): require explicit membership reactivation`,
  `refactor(frontend): separate auth and dashboard routes`.
- Do not push or open PR unless operator explicitly requests it.

### Commands

Run from indicated directory.

| Purpose | Directory | Command | Expected result |
|---|---|---|---|
| Backend tests | `backend` | `uv run pytest -p no:cacheprovider` | 44 or more tests pass; coverage at least 70% |
| Backend lint | `backend` | `uv run ruff check .` | exit 0 |
| Backend format | `backend` | `uv run ruff format --check .` | exit 0 |
| Migration drift | `backend` | `uv run python manage.py makemigrations --check --dry-run --settings=config.settings.test` | `No changes detected` |
| Django checks | `backend` | `uv run python manage.py check --settings=config.settings.test` | no issues |
| Frontend format | `frontend` | `npm run format:check` | exit 0 |
| Frontend lint | `frontend` | `npm run lint` | exit 0, no warnings |
| Frontend types | `frontend` | `npm run typecheck` | exit 0 |
| Frontend tests | `frontend` | `npm run test:coverage` | all tests pass; thresholds pass |
| Frontend build | `frontend` | `npm run build` | production build succeeds |

### Work package 1: characterize OTP abuse-control branches

**Goal:** lock security behavior before changing email configuration or policy defaults.

**In scope:** `backend/tests/test_auth.py`.

**Steps:**

1. Add fingerprint-limit coverage using requests across enough distinct emails to hit
   `WIO_OTP_IP_REQUESTS_PER_HOUR`. Assert generic `202`, bounded challenge count, and no extra email.
2. Add expired-challenge verification coverage. Assert `400`, no session, no success audit event,
   and no mutation that makes expired challenge reusable.
3. Add attempt-exhaustion coverage. After configured number of wrong codes, assert challenge is
   consumed and later correct code still fails.
4. Add challenge/email mismatch coverage. Assert generic invalid response, no session, and no login
   audit event.
5. Keep response assertions non-enumerating. Tests must not require log messages or response bodies
   to expose account eligibility.

**Verify:**

```powershell
Set-Location backend
uv run pytest tests/test_auth.py -p no:cacheprovider
```

Expected: all auth tests pass and at least four new branch-focused tests exist.

### Work package 2: require explicit membership reactivation

**Goal:** ordinary access approval never silently restores employee, manager, or HR/admin authority.

**In scope:**

- `backend/apps/accounts/admin.py`
- `backend/tests/test_admin_lifecycle.py`
- `docs/admin-user-lifecycle.md`
- `docs/auth-sign-up.md` only if its approval failure path needs matching wording

**Steps:**

1. In `AccessRequestAdmin.approve_access_requests`, lock and inspect existing membership before
   changing request state. When membership exists and `is_active=False`, skip request, leave it
   `pending`, create no approval audit event, send no email, and grant no authority.
2. Report skipped requests through Django Admin messaging without including email addresses or
   sensitive account data. Batch approval must continue processing unrelated safe requests.
3. Preserve current behavior for new membership and already-active membership. Do not silently
   demote or promote roles.
4. Add regression tests for inactive employee, manager, and HR/admin memberships; each remains
   inactive with retained role and pending request. Verify explicit `reactivate_selected_memberships`
   still works and remains audited.
5. Update lifecycle docs so reviewers know reactivation is separate deliberate action.

**Verify:**

```powershell
Set-Location backend
uv run pytest tests/test_admin_lifecycle.py -p no:cacheprovider
uv run ruff check apps/accounts/admin.py tests/test_admin_lifecycle.py
uv run ruff format --check apps/accounts/admin.py tests/test_admin_lifecycle.py
```

Expected: all lifecycle tests pass; no inactive membership becomes active through access approval.

### Work package 3: bound SMTP and converge OTP policy

**Goal:** synchronous SMTP cannot wait indefinitely, and every Phase 2 surface uses locked
60-second resend cooldown.

**In scope:**

- `backend/config/settings/base.py`
- `backend/config/settings/production.py`
- `backend/tests/test_auth.py`
- `.env.example`
- `backend/.env.example`
- `backend/README.md`
- `docs/infrastructure.md`
- `recap.md`
- Phase 2.1 text in this `plan.md`

**Steps:**

1. Add `DJANGO_EMAIL_TIMEOUT_SECONDS`, parsed as positive integer, defaulting to `10`; expose it to
   Django as `EMAIL_TIMEOUT`. Production validation must reject values outside `1..30` seconds with
   clear `ImproperlyConfigured` message containing no credentials.
2. Add default and production-validation tests. Do not pass timeout through every `send_mail()` call;
   use Django backend setting as single configuration point.
3. Change `WIO_OTP_RESEND_SECONDS` default and both environment examples from `30` to `60`.
4. Update policy-default tests, backend/deployment docs, recap, and Phase 2.1 release instructions to
   say 60 seconds. Search repository for stale 30-second cooldown claims.
5. Preserve generic email failure logging, `transaction.on_commit()`, and no-retry behavior. Do not
   add queue or background worker.

**Verify:**

```powershell
Set-Location backend
uv run pytest tests/test_auth.py -p no:cacheprovider
uv run ruff check config/settings tests/test_auth.py
uv run ruff format --check config/settings tests/test_auth.py
Set-Location ..
rg -n "WIO_OTP_RESEND_SECONDS=30|cooldown is 30|wait 30 seconds|30-second cooldown" . -g "!frontend/node_modules/**" -g "!*.lock" -g "!plan.md" -g "!improvements.md"
```

Expected: tests pass; final `rg` returns no matches; timeout default is 10 and cooldown default is 60.

### Work package 4: clear invalid frontend sessions

**Goal:** local UI follows server auth truth without hiding transient outages.

**In scope:**

- `frontend/src/app/page.tsx`
- `frontend/src/app/page.test.tsx`
- `frontend/src/lib/api.ts` only if small shared status helper is needed

**Steps:**

1. Add tests first for logout `401`, logout `403`, logout `5xx`, and network failure.
2. For `401`/`403`, clear current user and OTP state, discard stale errors/notices, and return to
   public access view. Treat logout as locally complete because server no longer accepts session.
3. For `5xx` or network failure, retain signed-in UI and show retry feedback exactly as today.
4. Keep initial `/api/v1/users/me/` behavior: unauthenticated response shows public entry; offline
   response does not erase access to signup/login.

**Verify:**

```powershell
Set-Location frontend
npm test -- src/app/page.test.tsx
npm run typecheck
npm run lint
```

Expected: all page tests pass and assertions distinguish invalid-session from transient failure.

### Work package 5: separate public auth from protected dashboard

**Goal:** Phase 3 dashboard work starts behind stable route and feature boundary rather than
expanding monolithic auth page.

**Target shape:**

```text
frontend/src/app/page.tsx                    public access/login composition
frontend/src/app/dashboard/page.tsx          protected signed-in placeholder
frontend/src/features/auth/contracts.ts      user/membership types and guards
frontend/src/features/auth/schemas.ts        Zod schemas and inferred form types
frontend/src/features/auth/api.ts            auth calls built on apiFetch
frontend/src/features/auth/use-auth-flow.ts  public auth state transitions
frontend/src/features/auth/components/       AuthShell and focused form/view components
```

Tests may mirror this structure under `frontend/src/features/auth/` plus route tests under
`frontend/src/app/`. Keep filenames lowercase with hyphens, matching existing Next.js conventions.

**In scope:**

- `frontend/src/app/page.tsx`
- `frontend/src/app/page.test.tsx`
- `frontend/src/app/dashboard/page.tsx` (create)
- focused files under `frontend/src/features/auth/` (create)
- corresponding Vitest files
- `frontend/src/lib/api.ts` only for behavior required by both routes

**Steps:**

1. Move types, schemas, response parsing, and auth API functions without behavior changes. Keep all
   requests on `apiFetch` so credentials and CSRF remain centralized.
2. Extract focused daisyUI views/components. Preserve current accessible names, keyboard behavior,
   generic anti-enumeration copy, OTP paste behavior, and semantic color classes.
3. Make `/` public-only. Successful OTP verification calls `router.replace("/dashboard")`.
4. Create `/dashboard` as client-protected Phase 2 placeholder. It restores
   `/api/v1/users/me/`; redirects `401`/`403` to `/`; shows retryable service failure for network or
   `5xx`; and clears local state plus redirects after logout success or `401`/`403`.
5. Split tests by responsibility while preserving every existing assertion. Add route tests for
   successful login navigation, protected-session restoration, invalid-session redirect, transient
   failure, and logout behavior.
6. Do not add Phase 3 dashboard widgets, global state library, middleware-based authentication, or
   server-side session proxying.

**Verify:**

```powershell
Set-Location frontend
npm run format:check
npm run lint
npm run typecheck
npm run test:coverage
npm run build
```

Expected: all gates pass; `/` contains no signed-in dashboard placeholder; `/dashboard` exists in
build output; no auth feature calls raw `fetch`.

### Work package 6: add real-browser auth contract

**Goal:** prove Next.js and Django agree on CSRF, cookies, OTP verification, session restoration, and
logout without contacting Gmail or exposing test-only production endpoint.

**In scope:**

- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/playwright.config.ts` (create)
- `tests/e2e/auth.spec.ts` (create)
- small test bootstrap/support files under `tests/e2e/` (create)
- `backend/config/settings/e2e.py` (create, test-only settings)
- `.github/workflows/ci.yml`
- `docs/testing.md`

**Steps:**

1. Add `@playwright/test` as frontend dev dependency and `test:e2e` script. Pin version through npm
   lockfile; do not hand-edit lockfile.
2. Add test-only Django settings inheriting test settings, using isolated database configuration and
   Django file-based email backend in ignored temporary directory. Test settings must never be
   imported by development or production settings.
3. Add deterministic bootstrap support that migrates isolated database and creates one active
   company, employee user, and active employee membership. Store no credentials in repository.
4. Configure Playwright to start Django and Next.js on dedicated local ports, wait for readiness,
   and clean test mail/database artifacts. Reuse existing `apiFetch` origin/cookie behavior.
5. Browser test flow: open `/`, request OTP for seeded employee, read emitted test email from local
   file backend, extract six-digit code, verify through UI, arrive at `/dashboard`, reload and restore
   session, log out, and return to public `/`.
6. Add CI step after backend/frontend unit gates. Install only Chromium. Disable trace, video, and
   screenshots for this sensitive flow because they can capture OTP input; keep CI output scrubbed.
7. Document one local command and prerequisites in `docs/testing.md`.

**Verify:**

```powershell
Set-Location frontend
npx playwright install chromium
npm run test:e2e
```

Expected: one browser contract passes locally; no Gmail/network dependency; no sensitive browser or
mail artifacts are retained.

### Work package 7: align verification and deployment documentation

**Goal:** one documented local gate matches CI, and migration ownership has one source of truth.

**In scope:**

- `scripts/check.ps1` (create)
- `README.md`
- `TECHSTACK.md`
- `docs/infrastructure.md` only if clarification is needed; preserve Render ownership
- `.github/workflows/ci.yml` only for E2E step from work package 6

**Steps:**

1. Add fail-fast `scripts/check.ps1` that runs backend Ruff lint/format, coverage tests, migration
   drift, Django checks, and schema validation; then frontend format, lint, typecheck, coverage, and
   production build. Add optional container-build flag rather than making Docker mandatory for every
   fast local run.
2. Update root README to make script canonical local gate and list Docker omission.
3. Correct `TECHSTACK.md`: Render pre-deploy runs `python manage.py migrate --noinput`; GitHub staging
   and production workflows trigger provider deploys, wait for health, and smoke-test. They do not
   run second migration command.
4. Do not move database credentials into GitHub solely to make old documentation true.

**Verify:**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1
rg -n "staging.yml.*run migrations|production.yml.*run migrations" TECHSTACK.md README.md docs/infrastructure.md
```

Expected: script exits 0; final `rg` returns no stale workflow-owned migration claim.

### Final gate and done criteria

Run from repository root after every package lands:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1
Set-Location frontend
npm run test:e2e
Set-Location ..
git status --short
```

All must hold:

- [ ] Backend has more than 44 passing tests and at least 70% coverage.
- [ ] OTP fingerprint, expiry, exhaustion, and mismatch branches have explicit regression tests.
- [ ] Access approval cannot reactivate any inactive membership or emit approval side effects.
- [ ] SMTP timeout is 10 seconds; OTP resend cooldown is 60 seconds everywhere.
- [ ] Invalid-session logout clears UI; transient logout failure retains UI.
- [ ] Public auth lives at `/`; protected placeholder lives at `/dashboard`.
- [ ] Frontend formatting, lint, typecheck, coverage, and production build pass.
- [ ] One real-browser auth contract passes against real Next.js and Django processes.
- [ ] Local gate matches CI except explicitly optional Docker builds.
- [ ] Render pre-deploy is documented as sole migration owner.
- [ ] No production credentials, OTP values, email bodies, generated coverage, E2E mail, test DB, or
  Playwright artifacts are staged.
- [ ] No Phase 3 domain implementation or Phase 7 worker implementation appears in diff.

### STOP conditions

Stop and report; do not improvise if:

- In-scope auth code changed after commit `78ff489` enough that current-state statements are false.
- Membership safety fix appears to require schema migration or role reset.
- Test would require exposing OTP values through API/logs or weakening generic responses.
- SMTP timeout requires provider-specific code rather than Django standard backend setting.
- Route split requires changing backend API shapes, cookie policy, or CSRF contract.
- E2E setup needs real Gmail credentials, deployed secrets, or production-accessible test endpoint.
- Work expands into Redis/queue/background-worker implementation; that belongs to Phase 7.
- Any verification command fails twice after bounded correction attempt.

### Maintenance notes

- Phase 3 must build dashboard UI under `/dashboard` and preserve auth feature boundaries.
- Phase 3 ratio implementation must use approved credit only and expose explanation ledger from first
  public contract.
- Phase 4 expands manager UX without replacing Phase 3 approval semantics.
- Phase 6 evidence work must include lifecycle enforcement in its first release.
- Phase 7 cannot start pilot traffic until durable email delivery replaces request-worker SMTP.
