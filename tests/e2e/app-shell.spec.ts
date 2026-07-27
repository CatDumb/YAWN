import { expect, test, type Locator, type Page } from "@playwright/test";

const manager = {
  email: "drawer.manager@example.com",
  first_name: "Drawer",
  id: 1,
  last_name: "Manager",
  memberships: [
    {
      company: "WIO",
      company_id: 1,
      role: "manager",
    },
  ],
};

async function stubAppShellApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    if (url.includes("/api/v1/users/me/")) {
      await route.fulfill({
        body: JSON.stringify(manager),
        contentType: "application/json",
        status: 200,
      });
      return;
    }
    if (url.includes("/api/v1/approvals/count/")) {
      await route.fulfill({
        body: '{"count":0}',
        contentType: "application/json",
        status: 200,
      });
      return;
    }
    await route.fulfill({
      body: '{"detail":"Fixture response."}',
      contentType: "application/json",
      status: 503,
    });
  });
}

async function navigationGeometry(navigation: Locator) {
  const dashboard = navigation.getByRole("link", {
    exact: true,
    name: "Dashboard",
  });

  await expect(dashboard).toBeVisible();
  await dashboard.hover();

  return dashboard.evaluate((element) => {
    const menuElement = element.closest("ul");
    const navigationElement = element.closest("nav");
    if (!menuElement || !navigationElement) throw new Error("Missing drawer navigation");

    const menuStyle = getComputedStyle(menuElement);
    return {
      linkWidth: element.getBoundingClientRect().width,
      menuInlinePadding:
        Number.parseFloat(menuStyle.paddingInlineStart) +
        Number.parseFloat(menuStyle.paddingInlineEnd),
      menuWidth: menuElement.getBoundingClientRect().width,
      navigationWidth: navigationElement.getBoundingClientRect().width,
    };
  });
}

function expectFullWidthNavigation(geometry: {
  linkWidth: number;
  menuInlinePadding: number;
  menuWidth: number;
  navigationWidth: number;
}) {
  expect(geometry.menuWidth).toBeCloseTo(geometry.navigationWidth, 1);
  expect(geometry.linkWidth).toBeCloseTo(
    geometry.menuWidth - geometry.menuInlinePadding,
    1,
  );
}

test("desktop drawer navigation hover fills its full inner lane", async ({ page }) => {
  await stubAppShellApi(page);

  await page.goto("/dashboard");

  const navigation = page.getByRole("navigation", {
    name: "Primary navigation",
  });
  await expect(navigation.getByRole("link", { name: "Approvals" })).toBeVisible();
  expectFullWidthNavigation(await navigationGeometry(navigation));
});

test("mobile drawer navigation fills its full inner lane", async ({ page }) => {
  await page.setViewportSize({ height: 844, width: 390 });
  await stubAppShellApi(page);

  await page.goto("/dashboard");
  await page.locator("label.drawer-button").click();

  const navigation = page.getByRole("navigation", {
    name: "Primary navigation",
  });
  expectFullWidthNavigation(await navigationGeometry(navigation));
});
