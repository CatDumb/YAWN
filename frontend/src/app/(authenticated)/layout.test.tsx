import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/features/app-shell/app-shell", () => ({
  AppShell: ({ children }: { children: ReactNode }) => (
    <div data-testid="app-shell">{children}</div>
  ),
}));

import AuthenticatedLayout from "./layout";

describe("AuthenticatedLayout", () => {
  it("provides one shared shell boundary for protected route content", () => {
    render(
      <AuthenticatedLayout>
        <p>Protected page</p>
      </AuthenticatedLayout>,
    );

    expect(screen.getByTestId("app-shell")).toHaveTextContent("Protected page");
  });
});
