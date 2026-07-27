import { expect, test } from "@playwright/test";

const manager = {
  email: "dashboard.retry@example.com",
  first_name: "Dashboard",
  id: 1,
  last_name: "Manager",
  memberships: [{ company: "WIO", company_id: 1, role: "manager" }],
};

test("dashboard retry recovers without exposing AbortSignal errors", async ({
  page,
}) => {
  let todayRequests = 0;
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    const fulfill = (body: unknown, status = 200) =>
      route.fulfill({
        body: JSON.stringify(body),
        contentType: "application/json",
        status,
      });

    if (url.includes("/api/v1/users/me/")) return fulfill(manager);
    if (url.includes("/api/v1/approvals/count/")) return fulfill({ count: 0 });
    if (url.includes("/api/v1/dashboard/today/")) {
      todayRequests += 1;
      if (todayRequests === 1)
        return fulfill(
          { detail: "Internal request implementation failed." },
          503,
        );
      return fulfill({
        attention: [],
        date: "2026-07-28",
        eligibility_reason: null,
        record_id: null,
        review_state: null,
      });
    }
    if (url.includes("/api/v1/dashboard/ratio/"))
      return fulfill({
        approved_days: "1",
        available: true,
        balance: "0",
        expected_display: "1",
        pending_assignment_count: 0,
        pending_count: 0,
        period_state: "active",
        ratio_display: "100%",
        reconciliation_cutoff: null,
        remaining_eligible_days: 2,
        revision: null,
      });
    if (url.includes("/api/v1/dashboard/activity/"))
      return fulfill({ intentions: [], records: [] });
    if (url.includes("/api/v1/dashboard/heatmap/")) return fulfill([]);

    return fulfill({ detail: "Fixture response." }, 503);
  });

  await page.goto("/dashboard");
  const alert = page
    .getByRole("alert")
    .filter({ hasText: "Module unavailable." });
  await expect(alert).toBeVisible();
  await alert.getByRole("button", { name: "Retry" }).click();

  await expect(alert).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Record WIO" })).toBeVisible();
  await expect(page.locator("body")).not.toContainText("AbortSignal");
  expect(pageErrors).toEqual([]);
});
