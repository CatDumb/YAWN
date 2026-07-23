import { execFileSync } from "node:child_process";
import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

const employeeEmail = "e2e.employee@example.com";
const mailDirectory = path.resolve(__dirname, "../../backend/.e2e/mail");
const repositoryRoot = path.resolve(__dirname, "../..");
const djangoPython = path.join(
  repositoryRoot,
  "backend",
  ".venv",
  "Scripts",
  "python.exe",
);

function rejectLatestPendingClaim() {
  execFileSync(
    djangoPython,
    [
      "backend/manage.py",
      "shell",
      "--settings=config.settings.e2e",
      "-c",
      [
        "from apps.accounts.models import User",
        "from apps.work_logs.models import WorkInOfficeRecord",
        "from apps.work_logs.services import reject_record",
        'manager, _ = User.objects.get_or_create(email="e2e.manager@example.com")',
        "record = WorkInOfficeRecord.objects.filter(review_state='pending').latest('pk')",
        "reject_record(record=record, actor=manager, reason='Please add context.')",
      ].join("; "),
    ],
    { cwd: repositoryRoot, stdio: "pipe" },
  );
}

function assignManagerForEmployee() {
  execFileSync(
    djangoPython,
    [
      "backend/manage.py",
      "shell",
      "--settings=config.settings.e2e",
      "-c",
      [
        "from django.utils import timezone",
        "from apps.accounts.models import CompanyMembership, ManagerAssignment, User",
        'employee = CompanyMembership.objects.get(user__email="e2e.employee@example.com")',
        'manager_user, _ = User.objects.get_or_create(email="e2e.manager@example.com")',
        "manager, _ = CompanyMembership.objects.get_or_create(user=manager_user, company=employee.company, defaults={'role': 'manager'})",
        "manager.role = 'manager'; manager.save()",
        "ManagerAssignment.objects.get_or_create(manager=manager, employee=employee, defaults={'effective_from': timezone.localdate()})",
      ].join("; "),
    ],
    { cwd: repositoryRoot, stdio: "pipe" },
  );
}

async function readOtp(): Promise<string | null> {
  try {
    const messages = await Promise.all(
      (await readdir(mailDirectory)).map(async (message) => ({
        message,
        modified: (await stat(path.join(mailDirectory, message))).mtimeMs,
      })),
    );
    messages.sort((left, right) => right.modified - left.modified);
    for (const { message } of messages) {
      const contents = await readFile(
        path.join(mailDirectory, message),
        "utf8",
      );
      const match = contents.match(/sign-in code is (\d{6})\./);
      if (match) return match[1];
    }
  } catch {
    // Polling waits for Django's file email backend.
  }
  return null;
}

async function signIn(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Already approved? Sign in" }).click();
  await page.getByLabel("Email").fill(employeeEmail);
  const oldMessages = new Set(await readdir(mailDirectory));
  await page.getByRole("button", { name: "Send code" }).click();
  const newestCode = async () => {
    const messages = await readdir(mailDirectory);
    if (messages.every((message) => oldMessages.has(message))) return null;
    return readOtp();
  };
  await expect.poll(newestCode).toMatch(/^\d{6}$/);
  const code = await newestCode();
  if (!code) throw new Error("OTP email disappeared before verification.");
  await page.getByLabel("Six-digit code").fill(code);
  await page.getByRole("button", { name: "Verify code" }).click();
  await expect(page).toHaveURL("/dashboard");
}

test("employee completes personal WIO lifecycle", async ({ page }) => {
  await signIn(page);
  assignManagerForEmployee();

  await page.getByRole("link", { name: "Work-in-office" }).click();
  await page.getByRole("link", { name: "Log work location" }).click();
  const browserToday = await page.getByLabel("Work date").inputValue();
  const serverToday = new Date(`${browserToday}T00:00:00Z`);
  serverToday.setUTCDate(serverToday.getUTCDate() - 1);
  const nextAllowedDate = serverToday.toISOString().slice(0, 10);
  await page.getByLabel("Work location").selectOption("in_office");
  await page.getByRole("button", { name: "Submit record" }).click();
  await expect(page).toHaveURL(/\/work-in-office\?saved=/);
  await expect(page.getByRole("cell", { name: "Pending" })).toBeVisible();

  rejectLatestPendingClaim();
  await page.reload();
  await page.getByRole("link", { name: /Correct rejection/ }).click();
  await expect(page.getByText(/Rejected: Please add context/)).toBeVisible();
  await page.getByLabel(/Note/).fill("Client workshop details added.");
  await page.getByRole("button", { name: "Submit record" }).click();
  await expect(page).toHaveURL(/\/work-in-office\?saved=/);
  await expect(page.getByRole("cell", { name: "Pending" })).toBeVisible();

  await page.getByRole("link", { name: "Log work location" }).click();
  await page.getByLabel("Work date").fill(nextAllowedDate);
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByRole("link", { name: /Finish draft/ })).toBeVisible();
  await page.getByRole("link", { name: /Finish draft/ }).click();
  await page.getByRole("button", { name: "Delete draft" }).click();
  await expect(page).toHaveURL("/work-in-office");

  await page.getByRole("link", { name: "Log work location" }).click();
  await page.getByLabel("Work date").fill(nextAllowedDate);
  await page.getByLabel("Work location").selectOption("not_in_office");
  await page.getByRole("button", { name: "Submit record" }).click();
  await expect(page.getByRole("cell", { name: "Not required" })).toBeVisible();

  await page.getByRole("link", { name: "Log work location" }).click();
  await page.getByLabel("Work date").fill(nextAllowedDate);
  await page.getByLabel("Work location").selectOption("not_in_office");
  await page.getByRole("button", { name: "Submit record" }).click();
  await expect(
    page.getByText("A record already exists for this date."),
  ).toBeVisible();
});
