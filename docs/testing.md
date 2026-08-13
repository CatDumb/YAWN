# Tests

Backend and frontend test guidance for YAWN.

Tools include pytest-django for backend tests, Vitest for frontend utilities, and Playwright for the
cross-service browser contract.

```powershell
Set-Location backend
uv run pytest -p no:cacheprovider

Set-Location ..\frontend
npm test
```

Run the focused Django Admin lifecycle suite from `backend`:

```powershell
uv run pytest tests/test_admin_lifecycle.py -p no:cacheprovider
```

CI also runs PostgreSQL migrations, schema validation, linting, type checks, frontend build, the
real-browser auth contract, and Docker image builds.

Run full local gate from repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

## Browser auth contract

Install backend and frontend dependencies, then install only Playwright Chromium once:

```powershell
Set-Location backend
uv sync --all-groups --frozen
Set-Location ..\frontend
npm ci
npx playwright install chromium
```

Run the contract from `frontend` with one command:

```powershell
npm run test:e2e
```

Ports `3100` and `8100` must be free. The command starts isolated Next.js and Django processes,
uses SQLite plus Django's file email backend, and needs no Gmail credentials. OTP mail, test DB,
screenshots, video, and traces are not retained.
