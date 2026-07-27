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
  let currentUserRequests = 0;
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    if (url.includes("/api/v1/users/me/")) {
      currentUserRequests += 1;
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
  return { currentUserRequests: () => currentUserRequests };
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
    if (!menuElement || !navigationElement)
      throw new Error("Missing drawer navigation");

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

async function pageContentGeometry(
  page: Page,
  contentWidth: "narrow" | "medium" | "wide",
) {
  const canvas = page.locator(".app-page-canvas");
  const content = page.locator(".app-page-content");

  await expect(content).toBeVisible();
  await expect(content).toHaveAttribute("data-content-width", contentWidth);

  return content.evaluate((element) => {
    const canvasElement = element.parentElement;
    if (!canvasElement) throw new Error("Missing authenticated page canvas");

    const contentRect = element.getBoundingClientRect();
    const canvasRect = canvasElement.getBoundingClientRect();

    return {
      canvasLeft: canvasRect.left,
      contentLeft: contentRect.left,
      contentWidth: contentRect.width,
      maxWidth: getComputedStyle(element).maxWidth,
    };
  });
}

test("desktop drawer navigation hover fills its full inner lane", async ({
  page,
}) => {
  await stubAppShellApi(page);

  await page.goto("/dashboard");

  const navigation = page.getByRole("navigation", {
    name: "Primary navigation",
  });
  await expect(
    navigation.getByRole("link", { name: "Approvals" }),
  ).toBeVisible();
  expectFullWidthNavigation(await navigationGeometry(navigation));
});

test("protected navigation preserves drawer DOM and session state", async ({
  page,
}) => {
  const api = await stubAppShellApi(page);

  await page.goto("/dashboard");
  const navigation = page.getByRole("navigation", {
    name: "Primary navigation",
  });
  const rail = page.locator("aside.app-navigation-rail");
  await expect(rail).toBeVisible();
  await rail.evaluate((element) =>
    element.setAttribute("data-persistence-probe", "stable"),
  );
  expect(api.currentUserRequests()).toBe(1);

  await Promise.all([
    page.waitForURL("**/reports"),
    navigation.getByRole("link", { name: "Reports" }).click(),
  ]);

  await expect(
    navigation.getByRole("link", { name: "Reports" }),
  ).toHaveAttribute("aria-current", "page");
  await expect(rail).toHaveAttribute("data-persistence-probe", "stable");
  await expect(page.getByLabel("Restoring session")).toHaveCount(0);
  expect(api.currentUserRequests()).toBe(1);
});

test("authenticated pages retain one left edge across content-width tiers", async ({
  page,
}) => {
  await page.setViewportSize({ height: 900, width: 1440 });
  await stubAppShellApi(page);

  await page.goto("/dashboard");
  const navigation = page.getByRole("navigation", {
    name: "Primary navigation",
  });
  const dashboard = await pageContentGeometry(page, "wide");

  await Promise.all([
    page.waitForURL("**/planner"),
    navigation.getByRole("link", { name: "Planner" }).click(),
  ]);
  const planner = await pageContentGeometry(page, "medium");

  await Promise.all([
    page.waitForURL("**/settings"),
    navigation.getByRole("link", { name: "Settings" }).click(),
  ]);
  const settings = await pageContentGeometry(page, "narrow");

  expect(dashboard.canvasLeft).toBeCloseTo(dashboard.contentLeft, 1);
  expect(planner.canvasLeft).toBeCloseTo(planner.contentLeft, 1);
  expect(settings.canvasLeft).toBeCloseTo(settings.contentLeft, 1);
  expect(planner.contentLeft).toBeCloseTo(dashboard.contentLeft, 1);
  expect(settings.contentLeft).toBeCloseTo(dashboard.contentLeft, 1);
  expect(dashboard.maxWidth).toBe("none");
  expect(planner.maxWidth).toBe("768px");
  expect(settings.maxWidth).toBe("672px");
  expect(dashboard.contentWidth).toBeGreaterThan(planner.contentWidth);
  expect(planner.contentWidth).toBeGreaterThan(settings.contentWidth);

  await Promise.all([
    page.waitForURL("**/dashboard"),
    navigation.getByRole("link", { name: "Dashboard" }).click(),
  ]);
  await page.getByRole("button", { name: "Collapse navigation" }).click();
  await expect(page.locator("aside.app-navigation-rail")).toHaveJSProperty(
    "clientWidth",
    80,
  );
  const collapsedDashboard = await pageContentGeometry(page, "wide");

  await Promise.all([
    page.waitForURL("**/settings"),
    navigation.getByRole("link", { name: "Settings" }).click(),
  ]);
  const collapsedSettings = await pageContentGeometry(page, "narrow");

  expect(collapsedDashboard.canvasLeft).toBeCloseTo(
    collapsedDashboard.contentLeft,
    1,
  );
  expect(collapsedSettings.canvasLeft).toBeCloseTo(
    collapsedSettings.contentLeft,
    1,
  );
  expect(collapsedSettings.contentLeft).toBeCloseTo(
    collapsedDashboard.contentLeft,
    1,
  );
});

test("authenticated page canvas fills narrow viewports without overflow", async ({
  page,
}) => {
  await page.setViewportSize({ height: 844, width: 390 });
  await stubAppShellApi(page);

  await page.goto("/settings");
  const geometry = await pageContentGeometry(page, "narrow");
  const viewport = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    width: window.innerWidth,
  }));

  expect(geometry.contentWidth).toBeLessThanOrEqual(viewport.width - 32);
  expect(viewport.scrollWidth).toBeLessThanOrEqual(viewport.width);
});

test("profile navigation closes the persistent account menu", async ({
  page,
}) => {
  await stubAppShellApi(page);
  await page.goto("/dashboard");

  await page
    .getByRole("button", { name: /Account menu for Drawer Manager/ })
    .click();
  await expect(page.locator("details[open]")).toHaveCount(1);

  await Promise.all([
    page.waitForURL("**/profile"),
    page.getByRole("link", { name: "Profile" }).click(),
  ]);

  await expect(page.locator("details[open]")).toHaveCount(0);
});

test("desktop drawer collapses to icon navigation and restores after reload", async ({
  page,
}) => {
  await stubAppShellApi(page);

  await page.goto("/dashboard");
  const navigation = page.getByRole("navigation", {
    name: "Primary navigation",
  });
  const rail = page.locator("aside.app-navigation-rail");
  const toggle = page.getByRole("button", { name: "Collapse navigation" });

  await expect(page.getByRole("link", { name: "YAWN" })).toHaveAttribute(
    "href",
    "/dashboard",
  );
  await expect(
    navigation.getByRole("link", { name: "Dashboard" }),
  ).toHaveAttribute("aria-current", "page");
  await expect(rail).toHaveJSProperty("clientWidth", 288);

  await toggle.focus();
  await page.keyboard.press("Enter");

  await expect(
    page.getByRole("button", { name: "Expand navigation" }),
  ).toHaveAttribute("aria-expanded", "false");
  await expect(rail).toHaveJSProperty("clientWidth", 80);
  const expandIcon = page
    .getByRole("button", { name: "Expand navigation" })
    .locator("svg");
  const dashboardIcon = navigation
    .getByRole("link", { name: "Dashboard" })
    .locator("svg");
  const [expandBox, dashboardBox] = await Promise.all([
    expandIcon.boundingBox(),
    dashboardIcon.boundingBox(),
  ]);
  if (!expandBox || !dashboardBox)
    throw new Error("Missing drawer icon geometry");
  expect(expandBox.x + expandBox.width / 2).toBeCloseTo(
    dashboardBox.x + dashboardBox.width / 2,
    1,
  );
  await expect(
    navigation.getByRole("link", { name: "Work-in-office" }),
  ).toBeVisible();
  await expect(
    navigation.locator("li").filter({ hasText: "" }).nth(0),
  ).toHaveAttribute("data-tip", "Dashboard");
  await expect(page.locator("html")).toHaveAttribute(
    "data-navigation",
    "collapsed",
  );

  await page.reload();

  await expect(
    page.getByRole("button", { name: "Expand navigation" }),
  ).toBeVisible();
  await expect(page.locator("aside.app-navigation-rail")).toHaveJSProperty(
    "clientWidth",
    80,
  );

  await page
    .getByRole("button", { name: /Account menu for Drawer Manager/ })
    .focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("link", { name: "Profile" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Log out" })).toBeVisible();
});

test("mobile drawer navigation fills its full inner lane", async ({ page }) => {
  await page.setViewportSize({ height: 844, width: 390 });
  await page.addInitScript(() =>
    localStorage.setItem("yawn.navigation-collapsed", "true"),
  );
  await stubAppShellApi(page);

  await page.goto("/dashboard");
  await page.locator("label.drawer-button").click();

  const navigation = page.getByRole("navigation", {
    name: "Primary navigation",
  });
  expectFullWidthNavigation(await navigationGeometry(navigation));
  await expect(page.locator("aside.app-navigation-rail")).toHaveJSProperty(
    "clientWidth",
    288,
  );
  await expect(
    navigation.getByText("Work-in-office", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Expand navigation" }),
  ).toBeHidden();

  await Promise.all([
    page.waitForURL("**/work-in-office"),
    navigation.getByRole("link", { name: "Work-in-office" }).click(),
  ]);
  await expect(page.locator("#app-navigation")).not.toBeChecked();
});
