import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { apiFetch, replace, router } = vi.hoisted(() => {
  const replace = vi.fn();
  return { apiFetch: vi.fn(), replace, router: { replace } };
});

vi.mock("../../lib/api", () => ({ apiFetch }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

import DashboardPage from "./page";

const user = {
  email: "ada@example.com",
  first_name: "Ada",
  id: 1,
  last_name: "Lovelace",
  memberships: [{ company: "Example", company_id: 1, role: "employee" }],
};
const jsonResponse = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    headers: { "Content-Type": "application/json" },
    status,
  });

describe("DashboardPage", () => {
  beforeEach(() => apiFetch.mockReset());
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("restores active session and logs out", async () => {
    apiFetch.mockResolvedValueOnce(jsonResponse(user));
    render(<DashboardPage />);
    expect(await screen.findByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("Example")).toBeInTheDocument();
    apiFetch.mockResolvedValueOnce(new Response(null, { status: 204 }));
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(apiFetch).toHaveBeenLastCalledWith("/api/v1/auth/logout/", {
      method: "POST",
    });
  });

  it.each([401, 403])(
    "redirects an invalid restored session (%s)",
    async (status) => {
      apiFetch.mockResolvedValueOnce(new Response(null, { status }));
      render(<DashboardPage />);

      await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    },
  );

  it("retains dashboard route and reports restored-session 503", async () => {
    apiFetch.mockResolvedValueOnce(
      jsonResponse({ detail: "Session unavailable." }, 503),
    );
    render(<DashboardPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Session unavailable.",
    );
    expect(replace).not.toHaveBeenCalled();
  });

  it.each([401, 403])("clears invalid logout session (%s)", async (status) => {
    apiFetch.mockResolvedValueOnce(jsonResponse(user));
    render(<DashboardPage />);
    await screen.findByText("ada@example.com");
    apiFetch.mockResolvedValueOnce(new Response(null, { status }));
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  });

  it("retains dashboard and reports exact logout 503 detail", async () => {
    apiFetch.mockResolvedValueOnce(jsonResponse(user));
    render(<DashboardPage />);
    await screen.findByText("ada@example.com");
    apiFetch.mockResolvedValueOnce(
      jsonResponse({ detail: "Logout unavailable." }, 503),
    );
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Logout unavailable.",
    );
    expect(screen.getByText("You are signed in")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
    expect(apiFetch).toHaveBeenLastCalledWith("/api/v1/auth/logout/", {
      method: "POST",
    });
  });

  it("retains dashboard and reports logout network failure", async () => {
    apiFetch.mockResolvedValueOnce(jsonResponse(user));
    render(<DashboardPage />);
    await screen.findByText("ada@example.com");
    apiFetch.mockRejectedValueOnce(new Error("offline"));
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to reach service. Try again.",
    );
    expect(screen.getByText("You are signed in")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
