import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { apiFetch, replace } = vi.hoisted(() => ({
  apiFetch: vi.fn(),
  replace: vi.fn(),
}));
vi.mock("../../lib/api", () => ({ apiFetch }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

import DashboardPage from "./page";

const user = {
  email: "ada@example.com",
  first_name: "Ada",
  id: 1,
  last_name: "Lovelace",
  memberships: [{ company: "Example", company_id: 1, role: "employee" }],
};

describe("DashboardPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("waits for session restoration before dashboard content", async () => {
    apiFetch.mockResolvedValue(
      new Response(JSON.stringify(user), { status: 200 }),
    );
    render(<DashboardPage />);
    expect(
      screen.queryByText("Today and fiscal progress"),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByText("Today and fiscal progress"),
    ).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
  });

  it("redirects an invalid session", async () => {
    apiFetch.mockResolvedValue(new Response(null, { status: 401 }));
    render(<DashboardPage />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  });
});
