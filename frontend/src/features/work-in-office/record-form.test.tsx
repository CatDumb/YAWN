import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../lib/errors";

const { getWorkInOfficeMetadata, replace, saveWorkInOffice, undoSelfApproval } = vi.hoisted(
  () => ({
    getWorkInOfficeMetadata: vi.fn(),
    replace: vi.fn(),
    saveWorkInOffice: vi.fn(),
    undoSelfApproval: vi.fn(),
  }),
);
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, refresh: vi.fn() }) }));
vi.mock("./api", () => ({ getWorkInOfficeMetadata, saveWorkInOffice, undoSelfApproval }));

import { RecordForm } from "./record-form";

describe("RecordForm", () => {
  beforeEach(() => {
    replace.mockReset();
    saveWorkInOffice.mockReset();
    undoSelfApproval.mockReset();
    getWorkInOfficeMetadata.mockResolvedValue({
      company_date: "2026-07-23",
      timezone: "Asia/Ho_Chi_Minh",
    });
  });
  afterEach(cleanup);

  it("saves explicit drafts and submits an office claim", async () => {
    saveWorkInOffice.mockResolvedValueOnce({ id: 8 });
    render(<RecordForm />);
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/work-in-office?saved=8"),
    );
    expect(saveWorkInOffice).toHaveBeenCalledWith(
      expect.objectContaining({ location_choice: null }),
      undefined,
      "Unable to save work record. Try again.",
    );

    saveWorkInOffice.mockResolvedValueOnce({ id: 9 });
    fireEvent.change(screen.getByLabelText("Work location"), {
      target: { value: "in_office" },
    });
    fireEvent.change(screen.getByLabelText(/Note/), {
      target: { value: "Visit" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit record" }));
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/work-in-office?saved=9"),
    );
  });

  it("keeps form input on a stale conflict", async () => {
    const conflict = new ApiError("Record changed.", 409);
    saveWorkInOffice.mockRejectedValueOnce(conflict);
    render(<RecordForm />);
    fireEvent.change(screen.getByLabelText("Work location"), {
      target: { value: "not_in_office" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit record" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Record changed.",
    );
    expect(
      screen.getByRole("button", { name: "Reload latest state" }),
    ).toBeVisible();
    expect(screen.getByLabelText("Work location")).toHaveValue("not_in_office");
  });

  it("offers self-approval undo only for self-approved records", async () => {
    undoSelfApproval.mockResolvedValueOnce({ id: 8 });
    render(
      <RecordForm
        record={{
          id: 8,
          work_date: "2026-07-23",
          location_choice: "in_office",
          review_state: "approved",
          approval_method: "self_approved",
          note: "Visit",
          approver_note: "",
          version: 3,
          created_at: "",
          updated_at: "",
        }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Undo self-approval" }));
    await waitFor(() =>
      expect(undoSelfApproval).toHaveBeenCalledWith(
        8,
        3,
        "Unable to undo self-approval.",
      ),
    );
  });
});
