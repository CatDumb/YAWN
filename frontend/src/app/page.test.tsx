import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import Home from "./page";

describe("Home", () => {
  it("shows foundation status and core capabilities", () => {
    render(<Home />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Work-in-office tracking",
    );
    expect(screen.getByText("Foundation active")).toBeInTheDocument();
    expect(screen.getByText("Secure access")).toBeInTheDocument();
  });
});

describe("apiFetch", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does not label FormData uploads as JSON", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 204 }));

    await apiFetch("/upload/", {
      body: new FormData(),
      method: "POST",
    });

    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init?.headers).has("Content-Type")).toBe(false);
  });

  it("adds JSON and CSRF headers for JSON requests", async () => {
    Object.defineProperty(document, "cookie", {
      configurable: true,
      value: "csrftoken=token-value",
    });
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 204 }));

    await apiFetch("/logs/", {
      body: JSON.stringify({ status: "draft" }),
      method: "POST",
    });

    const [, init] = fetchMock.mock.calls[0];
    const headers = new Headers(init?.headers);
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("X-CSRFToken")).toBe("token-value");
  });
});
