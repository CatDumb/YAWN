import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { apiFetch as apiFetchType } from "../lib/api";
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
  let apiFetch: typeof apiFetchType;

  beforeEach(async () => {
    vi.resetModules();
    ({ apiFetch } = await import("../lib/api"));
    Object.defineProperty(document, "cookie", {
      configurable: true,
      value: "",
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does not label FormData uploads as JSON", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ csrfToken: "api-token" }), {
          status: 200,
        }),
      )
      .mockResolvedValue(new Response(null, { status: 204 }));

    await apiFetch("/upload/", {
      body: new FormData(),
      method: "POST",
    });

    const [, init] = fetchMock.mock.calls[1];
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

  it("uses CSRF token returned by API when cookie is cross-origin", async () => {
    Object.defineProperty(document, "cookie", {
      configurable: true,
      value: "",
    });
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ csrfToken: "api-token" }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    await apiFetch("/auth/otp/verify/", {
      body: JSON.stringify({ code: "123456" }),
      method: "POST",
    });

    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://localhost:8000/api/v1/auth/csrf/",
    );
    const [, init] = fetchMock.mock.calls[1];
    expect(new Headers(init?.headers).get("X-CSRFToken")).toBe("api-token");
  });
});
