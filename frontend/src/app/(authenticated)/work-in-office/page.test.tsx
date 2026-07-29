import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/errors";

const { getWorkInOffice, listWorkInOffice, replace, searchParams } = vi.hoisted(
  () => ({
    getWorkInOffice: vi.fn(),
    listWorkInOffice: vi.fn(),
    replace: vi.fn(),
    searchParams: new URLSearchParams("saved=2"),
  }),
);
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => searchParams,
}));
vi.mock("@/features/work-in-office/api", () => ({
  getWorkInOffice,
  listWorkInOffice,
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
    updated_at: "2026-07-23T00:00:00Z",
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
    updated_at: "2026-07-22T00:00:00Z",
  },
];

describe("WorkInOfficePage", () => {
  beforeEach(() => {
    getWorkInOffice.mockReset();
    listWorkInOffice.mockReset();
    replace.mockReset();
  });
  afterEach(cleanup);

  it("shows attention, saved status, and filters", async () => {
    listWorkInOffice.mockImplementation((query: string) =>
      Promise.resolve(
        query === "?attention=true" ? [records[1]] : [records[0]],
      ),
    );
    render(<WorkInOfficePage />);
    expect(
      await screen.findByText(/Submitted for approval/),
    ).toBeInTheDocument();
    expect(screen.getByText("Needs your attention")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Record WIO" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Finish draft/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Expired pending" }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Review"), {
      target: { value: "pending" },
    });
    expect(
      screen.getByRole("link", { name: /Finish draft/ }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("cell", { name: "Pending" }),
    ).toBeInTheDocument();
    const updated = new Intl.DateTimeFormat("en-US", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(records[0].updated_at));
    expect(
      screen.getByRole("cell", {
        name: new RegExp(
          `No note.*${updated.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`,
        ),
      }),
    ).toBeInTheDocument();
    expect(listWorkInOffice).toHaveBeenLastCalledWith(
      "?review_state=pending",
      "Unable to load work records. Try again.",
      expect.any(AbortSignal),
    );

    fireEvent.change(screen.getByLabelText("Month"), {
      target: { value: "2026-07" },
    });
    fireEvent.change(screen.getByLabelText("Date"), {
      target: { value: "2026-07-23" },
    });
    await waitFor(() =>
      expect(listWorkInOffice).toHaveBeenLastCalledWith(
        "?review_state=pending&work_date=2026-07-23",
        "Unable to load work records. Try again.",
        expect.any(AbortSignal),
      ),
    );
  });

  it("keeps the list usable when a stale saved highlight cannot load", async () => {
    listWorkInOffice.mockImplementation((query: string) =>
      Promise.resolve(query === "?attention=true" ? [records[1]] : []),
    );
    getWorkInOffice.mockRejectedValue(
      new ApiError("Saved record missing.", 404),
    );

    render(<WorkInOfficePage />);

    expect(
      await screen.findByRole("link", { name: /2026-07-22/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Saved record missing.",
    );
  });
});
