import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/features/work-in-office/api", () => ({
  getWorkInOfficeMetadata: vi.fn().mockResolvedValue({
    company_date: "2026-07-23",
    timezone: "Asia/Ho_Chi_Minh",
  }),
  saveWorkInOffice: vi.fn(),
}));

import NewWorkInOfficePage from "./page";

describe("NewWorkInOfficePage", () => {
  afterEach(cleanup);

  it("renders a new record form without saving a record", async () => {
    render(<NewWorkInOfficePage />);
    await waitFor(() =>
      expect(screen.getByText("Record WIO")).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: "Save draft" }),
    ).toBeInTheDocument();
  });
});
