import { defineConfig } from "@playwright/test";
import path from "node:path";

const frontendUrl = "http://127.0.0.1:3100";
const backendUrl = "http://127.0.0.1:8100";

export default defineConfig({
  testDir: path.resolve(__dirname, "../tests/e2e"),
  tsconfig: path.resolve(__dirname, "../tests/e2e/tsconfig.json"),
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  outputDir: path.resolve(__dirname, "test-results"),
  globalTeardown: path.resolve(__dirname, "../tests/e2e/global-teardown.ts"),
  use: {
    baseURL: frontendUrl,
    screenshot: "off",
    trace: "off",
    video: "off",
  },
  webServer: [
    {
      command:
        "uv run --project ../backend python ../tests/e2e/bootstrap.py && uv run --project ../backend python ../backend/manage.py runserver 127.0.0.1:8100 --settings=config.settings.e2e --noreload",
      env: {
        ...process.env,
        DJANGO_SETTINGS_MODULE: "config.settings.e2e",
      },
      reuseExistingServer: false,
      timeout: 120_000,
      url: `${backendUrl}/ready/`,
    },
    {
      command: "npm run dev -- --hostname 127.0.0.1 --port 3100",
      env: {
        ...process.env,
        NEXT_PUBLIC_API_URL: backendUrl,
        NEXT_PUBLIC_SENTRY_DSN: "",
      },
      reuseExistingServer: false,
      timeout: 120_000,
      url: frontendUrl,
    },
  ],
});
