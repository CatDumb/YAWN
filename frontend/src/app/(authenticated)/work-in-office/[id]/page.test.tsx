import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/errors";

const { deleteWorkInOffice, getWorkInOffice, replace } = vi.hoisted(() => ({
  deleteWorkInOffice: vi.fn(),
  getWorkInOffice: vi.fn(),
  replace: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("@/features/work-in-office/api", () => ({
  deleteWorkInOffice,
  getWorkInOffice,
  saveWorkInOffice: vi.fn(),
}));

import WorkInOfficeDetailPage from "./page";

const record = {
  id: 4,
  work_date: "2026-07-23",
  location_choice: null,
  review_state: "draft",
  note: "",
  approver_note: "",
  version: 1,
  created_at: "",
  updated_at: "",
  audit_timeline: [
    {
      event_type: "work_logs.record_saved",
      metadata: {},
      created_at: "2026-07-23T01:00:00Z",
    },
  ],
};

describe("WorkInOfficeDetailPage", () => {
  beforeEach(() => {
    getWorkInOffice.mockReset();
    deleteWorkInOffice.mockReset();
    replace.mockReset();
  });
  afterEach(cleanup);

  it("shows audit history and deletes a draft", async () => {
    getWorkInOffice.mockResolvedValue(record);
    deleteWorkInOffice.mockResolvedValue(undefined);
    render(<WorkInOfficeDetailPage params={Promise.resolve({ id: "4" })} />);
    expect(await screen.findByText("Record history")).toBeInTheDocument();
    expect(screen.getByText("record saved")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete draft" }));
    await waitFor(() =>
      expect(deleteWorkInOffice).toHaveBeenCalledWith(
        "4",
        1,
        "Unable to delete draft.",
      ),
    );
    expect(replace).toHaveBeenCalledWith("/work-in-office");
  });

  it("shows detail failure", async () => {
    getWorkInOffice.mockRejectedValue(new ApiError("No record.", 404));
    render(<WorkInOfficeDetailPage params={Promise.resolve({ id: "4" })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("No record.");
  });
});
