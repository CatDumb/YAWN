import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { listWorkInOffice, searchParams } = vi.hoisted(() => ({
  listWorkInOffice: vi.fn(),
  searchParams: new URLSearchParams("saved=2"),
}));
vi.mock("next/navigation", () => ({ useSearchParams: () => searchParams }));
vi.mock("../../features/work-in-office/api", () => ({ listWorkInOffice }));
vi.mock("../../features/app-shell/app-shell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => children,
}));

import WorkInOfficePage from "./page";

const records = [
  {
    id: 2,
    work_date: "2026-07-23",
    location_choice: "in_office",
    review_state: "pending",
    note: "",
    approver_note: "",
    version: 1,
    created_at: "",
    updated_at: "",
  },
  {
    id: 3,
    work_date: "2026-07-22",
    location_choice: null,
    review_state: "draft",
    note: "",
    approver_note: "",
    version: 1,
    created_at: "",
    updated_at: "",
  },
];

describe("WorkInOfficePage", () => {
  beforeEach(() => listWorkInOffice.mockReset());
  afterEach(cleanup);

  it("shows attention, saved status, and filters", async () => {
    listWorkInOffice.mockResolvedValue(records);
    render(<WorkInOfficePage />);
    expect(
      await screen.findByText(/Submitted for manager review/),
    ).toBeInTheDocument();
    expect(screen.getByText("Needs your attention")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Finish draft/ }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Review"), {
      target: { value: "pending" },
    });
    expect(
      await screen.findByRole("cell", { name: "Pending" }),
    ).toBeInTheDocument();
    expect(listWorkInOffice).toHaveBeenLastCalledWith(
      "?review_state=pending",
      "Unable to load work records. Try again.",
    );
  });
});
