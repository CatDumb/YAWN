# WIO Tracker

Single-company web app for tracking work-in-office activity, approvals, endorsements, evidence, and office seating.

## Repository status

Phase 1 foundation is active. Backend authentication and operational baseline, frontend scaffold, local containers, tests, and CI/CD definitions are present. Daily work-log features begin in Phase 2.

See [ROADMAP.md](ROADMAP.md) for delivery phases and [TECHSTACK.md](TECHSTACK.md) for architecture and technology decisions.
See [CONTRIBUTING.md](CONTRIBUTING.md) for required commit-message format.

## Layout

```text
frontend/             Next.js application
backend/              Django and Django REST Framework API
  config/              Django project configuration
  apps/                Django domain applications
tests/                Cross-service and end-to-end tests
.github/workflows/    CI/CD workflow definitions
infra/                Deployment and infrastructure support files
```

## Development

Prerequisites: Docker Desktop, or Python 3.12 with `uv` plus Node.js 24.

Docker setup:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Services:

- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:8000/health/`
- Swagger UI: `http://localhost:8000/api/schema/swagger-ui/`
- Django Admin: `http://localhost:8000/admin/`

Local quality checks:

```powershell
Set-Location backend
uv sync --all-groups --frozen
uv run pytest -p no:cacheprovider
uv run ruff check .

Set-Location ..\frontend
npm ci
npm run lint
npm run typecheck
npm test

# Enforces 70% unit-test coverage for each service and writes local reports.
Set-Location ..\backend
uv run pytest --cov-report=xml:coverage.xml --cov-report=html:htmlcov

Set-Location ..\frontend
npm run test:coverage
```

## Architecture

Backend is a modular monolith: domain-focused Django apps, one API deployment, and one PostgreSQL database. Next.js frontend deploys separately but does not make product a microservice architecture.
