import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../lib/errors";

const { getWorkInOfficeMetadata, replace, saveWorkInOffice, undoSelfApproval } =
  vi.hoisted(() => ({
    getWorkInOfficeMetadata: vi.fn(),
    replace: vi.fn(),
    saveWorkInOffice: vi.fn(),
    undoSelfApproval: vi.fn(),
  }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh: vi.fn() }),
}));
vi.mock("./api", () => ({
  getWorkInOfficeMetadata,
  saveWorkInOffice,
  undoSelfApproval,
  WIO_EDITABLE_FIELDS: ["work_date", "location_choice", "note"],
}));

import { RecordForm } from "./record-form";

describe("RecordForm", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
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
      expect.objectContaining({
        location_choice: null,
        save_as_draft: true,
      }),
      undefined,
      "Unable to save work record. Try again.",
    );

    saveWorkInOffice.mockResolvedValueOnce({ id: 9 });
    fireEvent.change(screen.getByLabelText("Did you work in the office?"), {
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
    fireEvent.change(screen.getByLabelText("Did you work in the office?"), {
      target: { value: "not_in_office" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit record" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Record changed.",
    );
    expect(screen.getByRole("alert")).toHaveFocus();
    expect(
      screen.getByRole("button", { name: "Reload latest state" }),
    ).toBeVisible();
    expect(screen.getByLabelText("Did you work in the office?")).toHaveValue(
      "not_in_office",
    );
  });

  it("localizes field errors and focuses the first invalid control", async () => {
    saveWorkInOffice.mockRejectedValueOnce(
      new ApiError("Unable to save work record. Try again.", 400, [
        "work_date",
        "location_choice",
        "note",
      ]),
    );
    render(<RecordForm />);
    fireEvent.change(screen.getByLabelText("Did you work in the office?"), {
      target: { value: "in_office" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));

    expect(
      await screen.findByText("Choose a valid work date."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Choose whether you worked in the office."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Use plain text up to 500 characters."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/^Work date/)).toHaveFocus();
    expect(screen.getByLabelText(/^Work date/)).toHaveAttribute(
      "aria-describedby",
      "wio-work-date-error",
    );
    expect(
      screen.getByLabelText(/^Did you work in the office\?/),
    ).toHaveAttribute("aria-invalid", "true");
  });

  it("loads company timezone metadata while editing rejected records", async () => {
    getWorkInOfficeMetadata.mockResolvedValue({
      company_date: "2026-07-23",
      timezone: "America/New_York",
    });
    render(
      <RecordForm
        record={{
          id: 8,
          work_date: "2026-07-23",
          location_choice: "in_office",
          review_state: "rejected",
          note: "Visit",
          approver_note: "Correct evidence",
          version: 3,
          correction_deadline: "2026-07-24T00:00:00Z",
          created_at: "",
          updated_at: "",
        }}
      />,
    );

    expect(await screen.findByText(/America\/New_York/)).toBeInTheDocument();
    expect(screen.getByText(/Correct by Jul 23, 2026, 8:00 PM/)).toBeVisible();
    expect(getWorkInOfficeMetadata).toHaveBeenCalledWith(
      "Unable to load company date. Refresh and try again.",
    );
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

  it.each(["pending_assignment", "expired_pending"] as const)(
    "locks %s records",
    (reviewState) => {
      render(
        <RecordForm
          record={{
            id: 8,
            work_date: "2026-07-23",
            location_choice: "in_office",
            review_state: reviewState,
            note: "Visit",
            approver_note: "",
            version: 3,
            created_at: "",
            updated_at: "",
          }}
        />,
      );

      expect(
        screen.getByLabelText("Did you work in the office?"),
      ).toBeDisabled();
      expect(
        screen.getByRole("button", { name: "Submit record" }),
      ).toBeDisabled();
      expect(
        screen.queryByRole("button", { name: "Save draft" }),
      ).not.toBeInTheDocument();
    },
  );
});
