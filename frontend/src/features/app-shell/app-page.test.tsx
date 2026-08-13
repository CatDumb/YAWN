import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AppPage } from "./app-page";

describe("AppPage", () => {
  afterEach(cleanup);

  it("uses a shared wide canvas by default and forwards main attributes", () => {
    render(
      <AppPage aria-busy="true" aria-label="Loading dashboard">
        Content
      </AppPage>,
    );

    const main = screen.getByRole("main", { name: "Loading dashboard" });
    const content = screen.getByText("Content");

    expect(main).toHaveAttribute("aria-busy", "true");
    expect(main).toHaveClass("bg-base-100", "min-h-screen", "px-4", "sm:px-8");
    expect(content).toHaveClass("app-page-content", "w-full", "max-w-none");
    expect(content).toHaveAttribute("data-content-width", "wide");
    expect(content?.parentElement).toHaveClass(
      "app-page-canvas",
      "mx-auto",
      "max-w-6xl",
    );
  });

  it.each([
    ["narrow", "max-w-2xl"],
    ["medium", "max-w-3xl"],
  ] as const)("maps %s content to %s", (contentWidth, widthClass) => {
    render(<AppPage contentWidth={contentWidth}>Content</AppPage>);

    const content = screen.getByText("Content");

    expect(content).toHaveClass(widthClass);
    expect(content).toHaveAttribute("data-content-width", contentWidth);
  });

  it("keeps content left-aligned while allowing controlled class extensions", () => {
    render(
      <AppPage className="print:p-0" contentClassName="space-y-6">
        Content
      </AppPage>,
    );

    expect(screen.getByRole("main")).toHaveClass("print:p-0");
    expect(screen.getByText("Content")).toHaveClass("space-y-6");
  });
});
