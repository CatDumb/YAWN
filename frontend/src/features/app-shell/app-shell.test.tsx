import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  apiFetch: vi.fn(),
  currentUser: vi.fn(),
  logout: vi.fn(),
  pathname: "/dashboard",
  replace: vi.fn(),
  router: null as unknown as { replace: ReturnType<typeof vi.fn> },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => state.pathname,
  useRouter: () => state.router,
}));
vi.mock("../../lib/api", () => ({ apiFetch: state.apiFetch }));
vi.mock("../auth/api", () => ({
  currentUser: state.currentUser,
  logout: state.logout,
  responseDetail: vi.fn(
    async (_response: Response, fallback: string) => fallback,
  ),
}));

import { AppShell } from "./app-shell";

const manager = {
  email: "drawer.manager@example.com",
  first_name: "Drawer",
  id: 1,
  last_name: "Manager",
  memberships: [{ company: "WIO", company_id: 1, role: "manager" }],
};

function renderShell() {
  return render(
    <AppShell>
      <main>Page content</main>
    </AppShell>,
  );
}

describe("AppShell navigation", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    document.documentElement.dataset.navigation = "expanded";
    state.pathname = "/dashboard";
    state.replace.mockReset();
    state.router = { replace: state.replace };
    state.currentUser.mockResolvedValue({
      response: new Response(null, { status: 200 }),
      user: manager,
    });
    state.apiFetch.mockResolvedValue(
      new Response(JSON.stringify({ count: 3 }), { status: 200 }),
    );
    state.logout.mockResolvedValue(new Response(null, { status: 204 }));
  });

  it("links YAWN to the signed-in homepage and marks the active route", async () => {
    renderShell();

    const dashboard = await screen.findByRole("link", { name: "Dashboard" });
    expect(dashboard).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "YAWN" })).toHaveAttribute(
      "href",
      "/dashboard",
    );
  });

  it("collapses, retains accessible navigation names, and persists the choice", async () => {
    renderShell();

    const toggle = await screen.findByRole("button", {
      name: "Collapse navigation",
    });
    toggle.focus();
    fireEvent.click(toggle);

    expect(toggle).toHaveFocus();
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(localStorage.getItem("yawn.navigation-collapsed")).toBe("true");
    expect(document.documentElement.dataset.navigation).toBe("collapsed");
    expect(
      screen.getAllByRole("link", { name: "Work-in-office" }),
    ).toHaveLength(1);
    expect(
      screen.getByRole("button", { name: "Expand navigation" }),
    ).toBeVisible();
  });

  it("restores persisted collapse state and keeps nested WIO routes active", async () => {
    localStorage.setItem("yawn.navigation-collapsed", "true");
    state.pathname = "/work-in-office/42";
    renderShell();

    const workInOffice = await screen.findByRole("link", {
      name: "Work-in-office",
    });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Expand navigation" }),
      ).toBeVisible(),
    );
    expect(workInOffice).toHaveAttribute("aria-current", "page");
  });

  it("keeps shell DOM and session state across protected route updates", async () => {
    const view = renderShell();
    const dashboard = await screen.findByRole("link", { name: "Dashboard" });
    const rail = document.querySelector("aside.app-navigation-rail");

    expect(rail).toBeInTheDocument();
    expect(dashboard).toHaveAttribute("aria-current", "page");
    expect(state.currentUser).toHaveBeenCalledTimes(1);

    state.pathname = "/reports";
    view.rerender(
      <AppShell>
        <main>Reports content</main>
      </AppShell>,
    );

    expect(
      await screen.findByRole("link", { name: "Reports" }),
    ).toHaveAttribute("aria-current", "page");
    expect(rail).toBeInTheDocument();
    expect(state.currentUser).toHaveBeenCalledTimes(1);
  });

  it("shows the manager approval badge and account actions", async () => {
    renderShell();

    expect(
      await screen.findByRole("link", {
        name: "Approvals: 3 pending claim(s)",
      }),
    ).toBeVisible();
    expect(screen.queryByRole("link", { name: "Administration" })).toBeNull();

    fireEvent.click(
      screen.getByRole("button", { name: /Account menu for Drawer Manager/ }),
    );
    expect(screen.getByRole("link", { name: "Profile" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Log out" })).toBeVisible();
  });

  it("redirects after logout and reports logout failure", async () => {
    renderShell();

    fireEvent.click(
      await screen.findByRole("button", {
        name: /Account menu for Drawer Manager/,
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));
    await waitFor(() => expect(state.replace).toHaveBeenCalledWith("/"));

    state.logout.mockResolvedValueOnce(new Response(null, { status: 500 }));
    fireEvent.click(
      screen.getByRole("button", { name: /Account menu for Drawer Manager/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to log out. Try again.",
    );
  });
});
