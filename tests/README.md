# Tests

Cross-service and end-to-end test coverage for WIO Tracker.

Tools include pytest-django for backend tests and Vitest for frontend utilities.

```powershell
Set-Location backend
uv run pytest -p no:cacheprovider

Set-Location ..\frontend
npm test
```

CI also runs PostgreSQL migrations, schema validation, linting, type checks, frontend build, and Docker image builds.
