import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/errors";

const {
  deleteWorkInOffice,
  getWorkInOffice,
  getWorkInOfficeMetadata,
  getWorkInOfficeTimeline,
  replace,
} = vi.hoisted(() => ({
  deleteWorkInOffice: vi.fn(),
  getWorkInOffice: vi.fn(),
  getWorkInOfficeMetadata: vi.fn(),
  getWorkInOfficeTimeline: vi.fn(),
  replace: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("@/features/work-in-office/api", () => ({
  deleteWorkInOffice,
  getWorkInOffice,
  getWorkInOfficeMetadata,
  getWorkInOfficeTimeline,
  saveWorkInOffice: vi.fn(),
  undoSelfApproval: vi.fn(),
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
      id: 21,
      event_type: "work_logs.record_resubmitted",
      metadata: {
        actor_role: "employee",
        reason: "Corrected attendance",
        revision: 2,
        from_state: "rejected",
        to_state: "pending",
        previous_location_choice: "in_office",
        location_choice: "not_in_office",
        previous_note: "Old badge note",
        note: "",
        rejection_reason: "Evidence mismatch",
        previous_correction_deadline: "2026-07-24T23:59:00Z",
      },
      created_at: "2026-07-23T01:00:00Z",
    },
  ],
  audit_timeline_next_page: null,
};

describe("WorkInOfficeDetailPage", () => {
  beforeEach(() => {
    getWorkInOffice.mockReset();
    getWorkInOfficeTimeline.mockReset();
    getWorkInOfficeMetadata.mockResolvedValue({
      company_date: "2026-07-23",
      timezone: "Asia/Ho_Chi_Minh",
    });
    deleteWorkInOffice.mockReset();
    replace.mockReset();
  });
  afterEach(cleanup);

  it("shows audit history and deletes a draft", async () => {
    getWorkInOffice.mockResolvedValue(record);
    deleteWorkInOffice.mockResolvedValue(undefined);
    render(<WorkInOfficeDetailPage params={Promise.resolve({ id: "4" })} />);
    expect(await screen.findByText("Record history")).toBeInTheDocument();
    expect(screen.getByText("Corrected and resubmitted")).toBeInTheDocument();
    expect(screen.getByText("Employee")).toBeInTheDocument();
    expect(screen.getByText("Corrected attendance")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText(/Rejected.*Pending/)).toBeInTheDocument();
    expect(screen.getByText("Old badge note")).toBeInTheDocument();
    expect(screen.getByText("Evidence mismatch")).toBeInTheDocument();
    expect(screen.getByText("Corrected location:")).toBeInTheDocument();
    expect(screen.getAllByText("None")).not.toHaveLength(0);
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

  it("loads older audit history without replacing the first page", async () => {
    getWorkInOffice.mockResolvedValue({
      ...record,
      audit_timeline_next_page: 2,
    });
    getWorkInOfficeTimeline.mockResolvedValue({
      results: [
        {
          id: 20,
          event_type: "work_logs.record_submitted",
          metadata: { actor_role: "employee" },
          created_at: "2026-07-22T01:00:00Z",
        },
      ],
      next_page: null,
    });

    render(<WorkInOfficeDetailPage params={Promise.resolve({ id: "4" })} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Load older history" }),
    );

    await waitFor(() =>
      expect(getWorkInOfficeTimeline).toHaveBeenCalledWith(
        "4",
        2,
        "Unable to load older history. Try again.",
      ),
    );
    expect(screen.getByText("Corrected and resubmitted")).toBeInTheDocument();
    expect(screen.getByText("Submitted")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Load older history" }),
    ).not.toBeInTheDocument();
  });
});
