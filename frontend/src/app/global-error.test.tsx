import { createElement } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { captureException } = vi.hoisted(() => ({ captureException: vi.fn() }));

vi.mock("@sentry/nextjs", () => ({ captureException }));

import GlobalError from "./global-error";

describe("GlobalError", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("captures the error and retries when requested", () => {
    const error = new Error("Request failed");
    const reset = vi.fn();

    render(createElement(GlobalError, { error, reset }));

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Something went wrong",
    );
    expect(captureException).toHaveBeenCalledWith(error);

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(reset).toHaveBeenCalledOnce();
  });
});
