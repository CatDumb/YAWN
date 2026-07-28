# YAWN

Yet Another WIO Tracker.

Single-company web app for tracking work-in-office activity, approvals, endorsements, evidence, and office seating.

## Repository status

Phase 1 foundation covers frontend/backend scaffolding, operational baseline, local containers, tests, and CI/CD definitions. Phase 2 adds identity and access; daily work-log features begin in Phase 3.

See [ROADMAP.md](ROADMAP.md) for delivery phases and [TECHSTACK.md](TECHSTACK.md) for architecture and technology decisions.
See [CONTRIBUTING.md](CONTRIBUTING.md) for required commit-message format and [CHANGELOG.md](CHANGELOG.md) for release history.
See [testing](docs/testing.md) and [infrastructure](docs/infrastructure.md) for operating guides.

## Phase 2 identity and access

Phase 2 design and implementation baseline lives in [recap.md](recap.md). Flow documentation:

- [Access-request sign-up](docs/auth-sign-up.md)
- [OTP login, session, and logout](docs/auth-login.md)
- [Admin access and user lifecycle](docs/admin-user-lifecycle.md)
- [WIO transition baseline](docs/wio-transition-baseline.md)

For an explicitly opted-in local development administrator, set `DJANGO_DEBUG=true` and
`WIO_ALLOW_INSECURE_DEV_SEED=true`, then run `uv run python manage.py seed_dev_admin` from
`backend`. It creates `admin@wio.local` with password `admin` once; never use this outside local
development. See [backend setup](backend/README.md).

## Layout

```text
frontend/             Next.js application
backend/              Django and Django REST Framework API
  config/              Django project configuration
  apps/                Django domain applications
tests/                Cross-service and end-to-end tests
.github/workflows/    CI/CD workflow definitions
infra/                Deployment support files
```

## Development

Prerequisite for the default local stack: Docker Desktop with Docker Compose v2.

### One-command Docker Compose startup

Run this from repository root. It builds and starts PostgreSQL, Django, and Next.js as Docker
Compose services, waits for their health checks, applies migrations, and creates the `wio` signup
company:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-app.ps1
```

Services after startup:

- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:8000/health/`
- Swagger UI: `http://localhost:8000/api/schema/swagger-ui/`
- Django Admin: `http://localhost:8000/admin/`

View state or logs:

```powershell
docker compose ps
docker compose logs --follow
```

Create an administrator:

```powershell
docker compose exec backend python manage.py createsuperuser
```

### Gmail SMTP for Docker Compose

Compose reads mail settings from root ignored `.env`, not `backend/.env`. Copy `.env.example` to
`.env`, replace its active console-mail values with the Gmail SMTP values in the commented example,
and use a Google App Password without spaces. After changing mail settings, recreate the mail-sending
services:

```powershell
docker compose up --detach --force-recreate backend cleanup
```

The Gmail address must be identical for `DJANGO_EMAIL_HOST_USER` and
`DJANGO_DEFAULT_FROM_EMAIL`. Check Spam and All Mail during initial delivery tests.

Reset Compose databases only when their local data is disposable. This permanently removes YAWN
volumes plus legacy `wio-tracker` Compose and `wio-postgres` data, then starts a clean YAWN stack:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-app.ps1 -ResetDatabase
```

Include optional Redis:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-app.ps1 -WithRedis
```

### Manual local-process startup

Prerequisites: PostgreSQL 16+, Python 3.12 with `uv`, and Node.js 24.

Start PostgreSQL with Docker, if needed:

```powershell
docker run --name wio-postgres --env POSTGRES_DB=wio --env POSTGRES_USER=wio --env POSTGRES_PASSWORD=change-me-for-local-development --publish 5432:5432 --detach postgres:16
```

Start backend in one terminal:

```powershell
Set-Location backend
Copy-Item .env.example .env
$env:DJANGO_READ_DOT_ENV_FILE = 'true'
uv sync --all-groups --frozen
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py shell -c "from apps.accounts.models import Company; Company.objects.get_or_create(slug='wio', defaults={'name': 'WIO'})"
# Set WIO_SIGNUP_COMPANY_SLUG=wio in .env, then:
uv run python manage.py runserver
```

Start frontend in another terminal:

```powershell
Set-Location frontend
Copy-Item .env.example .env.local
npm ci
npm run dev
```

Local quality checks:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

This canonical local gate runs backend Ruff, tests, migration/schema checks, and frontend format,
lint, types, coverage, and production build. Docker builds are intentionally optional:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1 -ContainerBuild
```

## Architecture

Backend is a modular monolith: domain-focused Django apps, one API deployment, and one PostgreSQL database. Next.js frontend deploys separately but does not make product a microservice architecture.
