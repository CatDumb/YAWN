import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

import { expect, test } from "@playwright/test";

const employeeEmail = "e2e.employee@example.com";
const mailDirectory = path.resolve(__dirname, "../../backend/.e2e/mail");

async function readOtp(): Promise<string | null> {
  try {
    const messages = await readdir(mailDirectory);
    for (const message of messages) {
      const contents = await readFile(
        path.join(mailDirectory, message),
        "utf8",
      );
      const match = contents.match(/sign-in code is (\d{6})\./);
      if (match) return match[1];
    }
  } catch {
    // Delivery is asynchronous; polling below waits for file backend output.
  }
  return null;
}

test("OTP login restores session and logout clears it", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Already approved? Sign in" }).click();
  await page.getByLabel("Email").fill(employeeEmail);
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(
    page.getByText("If your account is eligible, a sign-in code has been sent."),
  ).toBeVisible();
  await expect(page.getByText(employeeEmail)).toBeVisible();

  await expect
    .poll(readOtp, { message: "OTP email was not delivered." })
    .toMatch(/^\d{6}$/);
  const code = await readOtp();
  if (!code) throw new Error("OTP email disappeared before verification.");

  await page.getByLabel("Six-digit code").fill(code);
  await page.getByRole("button", { name: "Verify code" }).click();

  await expect(page).toHaveURL("/dashboard");
  await expect(page.getByText(employeeEmail)).toBeVisible();
  await page.reload();
  await expect(page.getByText(employeeEmail)).toBeVisible();

  await page.getByRole("button", { name: /^Account menu for / }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL("/");
  await expect(
    page.getByRole("button", { name: "Request access", exact: true }),
  ).toBeVisible();
});
