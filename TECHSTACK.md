# WIO Tracker Tech Stack

## Frontend

- Next.js App Router
- TypeScript
- React
- Tailwind CSS 4
- daisyUI 5
- React Hook Form
- Zod

Frontend UI rules:

- Use daisyUI components with Tailwind responsive utilities.
- Use semantic daisyUI colors such as `primary`, `success`, `warning`, `error`, and `base-*`.
- Prefer default daisyUI component variants.
- Avoid custom CSS unless daisyUI and Tailwind utilities cannot provide the required behavior.

## Backend

- Python 3.12+
- Django
- Django REST Framework
- Django ORM
- Django migrations
- Django authentication and permissions
- drf-spectacular OpenAPI 3 schema, Swagger UI, and ReDoc
- uv dependency management with committed lockfile

Django REST Framework exposes REST APIs for users, projects, work logs, approvals, endorsements, evidence, reports, floor plans, and seats.

## Data and infrastructure

- PostgreSQL
- Django email OTP authentication flow
- S3-compatible private object storage for evidence images
- Redis optional later for background jobs and rate limiting
- Vercel for frontend deployment
- Render or equivalent managed container hosting for Django backend
- Docker and Docker Compose

## Deployment architecture

```text
Browser
  |
  v
Vercel: Next.js frontend
  |
  v
Managed container platform: Django + Django REST Framework API
  |                 |                 |
  v                 v                 v
PostgreSQL       Object storage      Email provider
managed DB      private evidence    OTP delivery
```

## Docker usage

- Use `Dockerfile` for reproducible frontend and backend builds.
- Use `compose.yaml` for local development.
- Local Compose services: frontend, backend, PostgreSQL, and optional Redis.
- Keep production database and evidence storage outside containers.
- Do not use container filesystem for persistent user uploads.
- Use multi-stage builds where useful to reduce production image size.
- Run containers as non-root users where platform supports it.
- Pin major dependency versions and scan images in CI.

## Production process

- Build and test on every pull request.
- Build tagged Docker images on release.
- Run `python manage.py check --deploy` against production settings.
- Run database migrations as a deployment step before application startup.
- Serve Django with Gunicorn, not `manage.py runserver`.
- Configure `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, secure cookies, HTTPS, and production secret values.
- Add `/health/` endpoint for platform health checks.
- Enable structured logs, error monitoring, database backups, and restore testing.
- Keep staging environment close to production configuration.

Docker Compose supports development, testing, CI, and production workflows; production should use a separate production override and managed persistent services. [Docker Compose production guidance](https://docs.docker.com/compose/how-tos/production/)

Render supports Django web services, Dockerfile-based deployment, managed PostgreSQL, background workers, and pre-deploy migration commands. [Render web services](https://render.com/docs/web-services) [Render Docker deployment](https://render.com/docs/docker)

Django production deployment must use a production WSGI/ASGI server and pass the deployment checklist. [Django deployment checklist](https://docs.djangoproject.com/en/dev/howto/deployment/checklist/)

## Security

- Server-side authorization on every protected operation.
- Default all DRF endpoints to authenticated users with active company membership; opt out only explicit public endpoints.
- Hash OTP codes at rest; enforce expiry, single use, resend cooldown, attempt limits, and per-email/IP request limits.
- Use credentialed session cookies, CSRF protection, explicit CORS origins, and same-site custom frontend/API domains.
- Private evidence bucket; use short-lived signed URLs.
- Validate file type, file size, and image dimensions.
- Never expose service-role credentials to browser.
- Audit role changes, approvals, rejections, endorsements, edits, and evidence access.
- Rate-limit OTP requests, login attempts, uploads, and webcam evidence actions.

## Testing and quality

- pytest-django for backend unit and integration tests.
- Vitest for frontend utility tests.
- Ruff for Python linting and formatting.
- mypy optional for Python type checking.
- ESLint and Prettier for frontend quality.
- GitHub Actions for test, lint, type-check, and build checks.
- GitHub Actions environments for staging and production deployment approvals.
- Dependency scanning and container image scanning in CI.

## CI/CD

GitHub Actions workflows live under `.github/workflows/`:

- `ci.yml`: backend tests, frontend tests, linting, type checks, and build validation.
- `security.yml`: dependency audit, secret scanning, and Docker image scanning.
- `staging.yml`: build tagged images, deploy staging, run migrations, and execute smoke tests.
- `production.yml`: deploy only from release tag or manual approval, run migrations, smoke test, and report status.

Pipeline rules:

- Pull requests must pass CI before merge.
- Production secrets stay in protected GitHub Environment or hosting-provider secret storage.
- Docker images use commit SHA tags, never only `latest`.
- Failed health checks stop deployment.
- Keep previous image available for rollback.

GitHub Actions supports repository workflows for CI/CD, protected environments, deployment approvals, and secret controls. [GitHub Actions docs](https://docs.github.com/en/actions)

## Observability

- Sentry for frontend and Django exception monitoring and performance visibility.
- Python `logging` with JSON formatter for backend logs.
- Request correlation ID passed through frontend, API, logs, and traces.
- OpenTelemetry for future vendor-neutral traces and metrics.
- Hosting-platform logs and metrics for container, CPU, memory, and restart events.
- Uptime monitoring for frontend URL, `/health/`, and login flow.

Required dashboard signals:

- Request count and p50/p95/p99 latency.
- 4xx and 5xx rate.
- Login and OTP failure rate.
- Work-log submission and approval failure rate.
- Evidence upload failure rate.
- Database connection and query errors.
- Email delivery failures.
- Container restarts and deployment status.

Privacy rules:

- Never log OTP codes, access tokens, cookies, private evidence URLs, webcam images, or unnecessary personal data.
- Scrub email addresses and user identifiers from high-volume logs where possible.
- Restrict observability dashboard access to authorized engineering/admin users.

OpenTelemetry supports Python traces and metrics; logs remain a developing signal, so use normal structured application logging for MVP. [OpenTelemetry Python docs](https://opentelemetry.io/docs/languages/python/)

## Suggested repository layout

```text
/
  frontend/        Next.js application
  backend/         Django project
  backend/config/  Django settings and URL configuration
  backend/apps/    Django applications
    accounts/      Users, roles, and manager assignments
    work_logs/     Logs, ratios, approvals, and endorsements
    office/        Floor plans and seats
    evidence/      Private evidence upload and access
    audit/         Audit events
  backend/manage.py Django management entry point
  tests/             Cross-service and end-to-end tests
```

## Backend API groups

- `/api/v1/auth`
- `/api/v1/users`
- `/api/v1/projects`
- `/api/v1/ratio-rules`
- `/api/v1/work-logs`
- `/api/v1/approvals`
- `/api/v1/endorsements`
- `/api/v1/evidence`
- `/api/v1/reports`
- `/api/v1/floor-plans`
- `/api/v1/seats`

## Core backend entities

`User`, `Role`, `ManagerAssignment`, `Project`, `ProjectStatusRule`, `WorkLog`, `WorkLogEvidence`, `FloorPlan`, `Seat`, `SeatAssignment`, `Endorsement`, `AuditEvent`.

## Initial backend decisions

- REST API, JSON payloads.
- Modular monolith backend with one Django deployment and one PostgreSQL database.
- Django Admin used for HR/admin management workflows.
- One company and one timezone for MVP.
- Invite/admin-provisioned company membership; email-domain match alone never grants access.
- Email OTP creates a Django session; Basic authentication is disabled.
- One active project-status category per employee at a time.
- Work-log state: `draft`, `submitted`, `approved`, `rejected`.
- Endorsements are audit signals, never approval substitutes.
- Store applied ratio rule snapshot on submitted work logs.
