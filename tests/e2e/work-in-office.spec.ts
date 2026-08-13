import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

const employeeEmail = "e2e.employee@example.com";
const managerEmail = "e2e.manager@example.com";
const mailDirectory = path.resolve(__dirname, "../../backend/.e2e/mail");

async function messageNames(): Promise<Set<string>> {
  try {
    return new Set(await readdir(mailDirectory));
  } catch {
    return new Set();
  }
}

async function latestOtp(
  email: string,
  existingMessages: Set<string>,
): Promise<string | null> {
  try {
    const messages = (await readdir(mailDirectory)).filter(
      (message) => !existingMessages.has(message),
    );
    for (const message of messages) {
      const contents = await readFile(
        path.join(mailDirectory, message),
        "utf8",
      );
      if (!contents.includes(email)) continue;
      const match = contents.match(/sign-in code is (\d{6})\./);
      if (match) return match[1];
    }
  } catch {
    // Delivery is asynchronous; Playwright polling waits for the file backend.
  }
  return null;
}

async function signIn(page: Page, email: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Already approved? Sign in" }).click();
  await page.getByLabel("Email").fill(email);
  const existingMessages = await messageNames();
  await page.getByRole("button", { name: "Send code" }).click();
  await expect
    .poll(() => latestOtp(email, existingMessages))
    .toMatch(/^\d{6}$/);
  const code = await latestOtp(email, existingMessages);
  if (!code) throw new Error(`OTP disappeared for ${email}.`);
  await page.getByLabel("Six-digit code").fill(code);
  await page.getByRole("button", { name: "Verify code" }).click();
  await expect(page).toHaveURL("/dashboard");
}

async function signOut(page: Page) {
  await page.getByRole("button", { name: /^Account menu for / }).click();
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL("/");
}

test("draft, submit, reject, correct, and duplicate WIO lifecycle", async ({
  page,
}) => {
  await signIn(page, employeeEmail);
  await page.goto("/work-in-office/new");

  await page.getByLabel("Work date").fill("2026-07-28");
  await page
    .getByLabel("Did you work in the office?")
    .selectOption("in_office");
  await page.getByLabel(/^Note/).fill("Temporary draft");
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page).toHaveURL(/\/work-in-office\?saved=\d+/);
  await page.getByRole("link", { name: /2026-07-28/ }).click();
  await page.getByRole("button", { name: "Delete draft" }).click();
  await expect(page).toHaveURL("/work-in-office");
  await expect(page.getByText("2026-07-28")).toHaveCount(0);

  await page.goto("/work-in-office/new");
  const workDateInput = page.getByLabel("Work date");
  await expect(workDateInput).toHaveValue(/^\d{4}-\d{2}-\d{2}$/);
  const workDate = await workDateInput.inputValue();
  await page
    .getByLabel("Did you work in the office?")
    .selectOption("in_office");
  await page.getByLabel(/^Note/).fill("Draft badge evidence");
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page).toHaveURL(/\/work-in-office\?saved=\d+/);
  await expect(page.getByRole("status")).toContainText("Draft saved");

  await page.getByRole("link", { name: new RegExp(workDate) }).click();
  await page.getByLabel(/^Note/).fill("Submitted badge evidence");
  await page.getByRole("button", { name: "Submit record" }).click();
  await expect(page).toHaveURL(/\/work-in-office\?saved=\d+/);
  await expect(page.getByRole("status")).toContainText(
    "Submitted for approval",
  );

  await signOut(page);
  await signIn(page, managerEmail);
  await page.goto("/approvals");
  await expect(page.getByText(employeeEmail)).toBeVisible();
  await page.getByRole("button", { name: "Reject" }).click();
  await page
    .getByLabel("Rejection reason")
    .fill("Badge evidence needs correction");
  await page.getByRole("button", { name: "Confirm rejection" }).click();
  await expect(page.getByText(employeeEmail)).toHaveCount(0);

  await signOut(page);
  await signIn(page, employeeEmail);
  await page.goto("/work-in-office");
  await page.getByRole("link", { name: new RegExp(workDate) }).click();
  await expect(
    page.getByText("Badge evidence needs correction", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Did you work in the office?")
    .selectOption("not_in_office");
  await page.getByRole("button", { name: "Submit record" }).click();
  await expect(page).toHaveURL(/\/work-in-office\?saved=\d+/);
  await expect(page.getByRole("status")).toContainText("WIO record saved");

  await page.goto("/work-in-office/new");
  await page.getByLabel("Work date").fill(workDate);
  await page
    .getByLabel("Did you work in the office?")
    .selectOption("not_in_office");
  await page.getByRole("button", { name: "Submit record" }).click();
  await expect(
    page.getByText(/A record already exists for this date/),
  ).toBeVisible();
});
