import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));

vi.mock("@/lib/api", () => ({ apiFetch }));

import ApprovalsPage from "./(authenticated)/approvals/page";
import DashboardPage from "./(authenticated)/dashboard/page";
import PlannerPage from "./(authenticated)/planner/page";
import ProfilePage from "./(authenticated)/profile/page";
import ReportsPage from "./(authenticated)/reports/page";
import SettingsPage from "./(authenticated)/settings/page";

const preference = {
  theme: "light",
  language: "en",
  reduced_motion: false,
  planner_location: "office",
  planner_commitment: "firm",
  week_start: 1,
  display_name: "Ada",
  version: 1,
};

const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status });

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => {
    resolve = next;
  });
  return { promise, resolve };
}

function responseFor(url: string) {
  if (url === "/api/v1/dashboard/today/") {
    return response({
      record_id: 3,
      review_state: "draft",
      eligibility_reason: null,
      attention: [3],
    });
  }
  if (url === "/api/v1/dashboard/ratio/") {
    return response({
      available: true,
      ratio_display: "111.12%",
      approved_days: "2",
      expected_display: "1.80",
      balance: "0.20",
      remaining_eligible_days: 5,
      pending_count: 1,
      pending_assignment_count: 1,
      period_state: "Active",
      reconciliation_cutoff: "2026-08-01T00:00:00Z",
      revision: 2,
    });
  }
  if (url.startsWith("/api/v1/dashboard/activity/")) {
    return response({
      records: [{ id: 3, date: "2026-07-24", state: "approved" }],
      intentions: [
        { id: 4, date: "2026-07-28", location: "office", commitment: "firm" },
      ],
    });
  }
  if (url.startsWith("/api/v1/dashboard/heatmap/")) {
    return response([
      {
        date: "2026-07-01",
        action: "none",
        record_id: null,
      },
      {
        date: "2026-07-20",
        action: "open",
        record_id: 3,
        review_state: "approved",
      },
      {
        date: "2026-07-21",
        action: "open",
        record_id: 4,
        review_state: "pending",
      },
      {
        date: "2026-07-22",
        action: "open",
        record_id: 5,
        review_state: "pending_assignment",
      },
      {
        date: "2026-07-23",
        action: "open",
        record_id: 6,
        review_state: "rejected",
      },
      {
        date: "2026-07-24",
        action: "open",
        record_id: 7,
        review_state: "expired_pending",
      },
      {
        date: "2026-07-25",
        action: "open",
        record_id: 8,
        review_state: "not_required",
      },
      {
        date: "2026-07-26",
        action: "open",
        record_id: 9,
        review_state: "draft",
      },
      {
        date: "2026-07-27",
        action: "create",
        record_id: null,
        intention: "office",
        commitment: "firm",
      },
      {
        date: "2026-07-28",
        action: "none",
        record_id: null,
        intention: "home",
        commitment: "flexible",
      },
      {
        date: "2026-07-29",
        action: "none",
        record_id: null,
        ineligible_reason: "Holiday",
      },
      {
        date: "2026-07-30",
        action: "none",
        record_id: null,
      },
    ]);
  }
  if (url === "/api/v1/profile/") {
    return response({
      legal_name: "Ada Lovelace",
      email: "ada@example.com",
      company: "Example",
      role: "employee",
      base_location: "HCM",
      manager: {
        name: "Grace",
        effective_from: "2026-01-01",
        effective_to: null,
      },
      project_assignment: {
        project: "Analytical engine",
        effective_from: "2026-01-01",
        effective_to: null,
      },
      policy: { assignment_status: "same_base", expected_fraction: "1.00" },
    });
  }
  if (url === "/api/v1/work-in-office/meta/") {
    return response({
      company_date: "2026-07-24",
      timezone: "Asia/Ho_Chi_Minh",
      fiscal_period: {
        name: "FY26",
        state: "active",
        start_date: "2026-01-01",
        end_date: "2026-12-31",
      },
    });
  }
  if (url.startsWith("/api/v1/reports/csv/")) return response("csv");
  if (url.startsWith("/api/v1/reports/")) {
    return response({
      approved_days: "2",
      expected_fraction_sum: "1.80",
      expected_display: "1.80",
      ratio_display: "111.12%",
      balance: "0.20",
      percentage: "111.12",
      pending_count: 1,
      pending_assignment_count: 1,
      period_state: "final",
      revision: 1,
      start_date: "2026-07-01",
      end_date: "2026-07-24",
      ledger: [
        ["2026-07-17", "benched", "draft"],
        ["2026-07-18", "same_base", "pending"],
        ["2026-07-19", "different_base", "pending_assignment"],
        ["2026-07-20", "same_base", "approved"],
        ["2026-07-21", "different_base", "rejected"],
        ["2026-07-22", "benched", "not_required"],
        ["2026-07-23", "same_base", "expired_pending"],
        ["2026-07-24", "different_base", null],
      ].map(([date, assignment_status, review_state]) => ({
        date,
        eligible: review_state !== "expired_pending",
        reason: review_state === "expired_pending" ? "Deadline closed" : null,
        assignment_status,
        rule_version: review_state === null ? null : 1,
        expected_fraction: "1.00",
        approval_credit: "1.00",
        review_state,
        location_choice: "in_office",
      })),
    });
  }
  if (url === "/api/v1/auth/me/") {
    return response({ memberships: [{ role: "manager" }] });
  }
  if (url.startsWith("/api/v1/approvals/?")) {
    return response([
      {
        id: 7,
        employee_name: "Ada Lovelace",
        employee_email: "ada@example.com",
        base_location_name: "HCM",
        work_date: "2026-07-24",
        note_present: true,
        version: 1,
        submitted_at: "2026-07-24T01:00:00Z",
      },
    ]);
  }
  if (url === "/api/v1/approvals/count/") {
    return response({ count: 1, oldest_submitted_at: "2026-07-24T01:00:00Z" });
  }
  if (url === "/api/v1/approvals/7/approve/") return response({ version: 2 });
  if (url === "/api/v1/approvals/7/reject/") return response({ version: 2 });
  if (url === "/api/v1/approvals/7/undo/") return response({ version: 3 });
  if (url === "/api/v1/planner/") {
    return response([
      {
        id: 4,
        date: "2026-07-28",
        location: "office",
        commitment: "firm",
        note: "Private",
        excluded_reason: "",
        series_id: 2,
        version: 1,
      },
    ]);
  }
  if (url === "/api/v1/planner/projection/") {
    return response({
      period_name: "FY26",
      expected_fraction_sum: "10.00",
      minimum_planned_fraction: "2.00",
      maximum_planned_fraction: "3.00",
      gap_after_maximum: "7.00",
      firm_office_days: 2,
      flexible_office_days: 1,
      unplanned_eligible_days: 7,
    });
  }
  if (url === "/api/v1/planner/preview/") {
    return response([
      { date: "2026-07-28", eligible: true, existing: true, reason: null },
      { date: "2026-07-29", eligible: true, existing: false, reason: null },
      {
        date: "2026-07-30",
        eligible: false,
        existing: false,
        reason: "Holiday",
      },
    ]);
  }
  return response(preference);
}

describe("Phase 3 page contracts", () => {
  beforeEach(() => {
    document.documentElement.lang = "en";
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn(() => ({
        addEventListener: vi.fn(),
        matches: false,
        removeEventListener: vi.fn(),
      })),
    });
    apiFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/v1/preferences/" && init?.method === "PUT") {
        return Promise.resolve(response(JSON.parse(String(init.body))));
      }
      return Promise.resolve(responseFor(url));
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders profile and persists preferred display name with its versioned preference", async () => {
    render(<ProfilePage />);

    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Display name"), {
      target: { value: "Ada B." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save display name" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Preferred display name saved.",
    );
    expect(apiFetch).toHaveBeenLastCalledWith(
      "/api/v1/preferences/",
      expect.objectContaining({ method: "PUT" }),
    );
  });

  it("renders factual reports from one shared report response", async () => {
    render(<ReportsPage />);

    expect(await screen.findByText("111.12%")).toBeInTheDocument();
    expect(screen.getByLabelText("Ratio ledger")).toHaveTextContent(
      "Same base",
    );
    expect(screen.getAllByText("Approved")).toHaveLength(2);
  });

  it("exports the currently rendered factual report without changing its range", async () => {
    const createObjectUrl = vi.fn(() => "blob:report");
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: createObjectUrl,
    });
    render(<ReportsPage />);

    await screen.findByText("111.12%");
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/reports/csv/?start_date=2026-07-01"),
      ),
    );
    expect(createObjectUrl).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
  });

  it("renders settings context and persists changed theme preferences", async () => {
    render(<SettingsPage />);

    expect(await screen.findByText("Asia/Ho_Chi_Minh")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Theme"), {
      target: { value: "dark" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save preferences" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Settings saved.",
    );
    expect(document.documentElement.dataset.theme).toBe("yawn-dark");
  });

  it("keeps settings editable when a versioned preference save fails", async () => {
    apiFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/v1/preferences/" && init?.method === "PUT") {
        return Promise.resolve(response({ detail: "Conflict" }, 409));
      }
      return Promise.resolve(responseFor(url));
    });
    render(<SettingsPage />);

    await screen.findByText("Asia/Ho_Chi_Minh");
    fireEvent.click(screen.getByRole("button", { name: "Save preferences" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Unable to save settings.",
    );
  });

  it("renders scoped manager approval queue with claim summary", async () => {
    render(<ApprovalsPage />);

    expect(
      await screen.findByRole("heading", {
        name: "Pending work-in-office claims",
      }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByText("Note available")).toBeInTheDocument();
  });

  it("records manager approval, undo, and rejection reason through scoped actions", async () => {
    render(<ApprovalsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));
    expect(
      await screen.findByText(
        "Approval saved. Undo remains available for 10 seconds.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Undo approval" }));
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        "/api/v1/approvals/7/undo/",
        expect.objectContaining({ method: "POST" }),
      ),
    );

    fireEvent.click(await screen.findByRole("button", { name: "Reject" }));
    fireEvent.change(screen.getByLabelText("Rejection reason"), {
      target: { value: "Missing evidence" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm rejection" }));
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        "/api/v1/approvals/7/reject/",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("renders HR assignment work and submits an audited assignment", async () => {
    apiFetch.mockImplementation((url: string) => {
      if (url === "/api/v1/auth/me/") {
        return Promise.resolve(
          response({ memberships: [{ role: "hr_admin" }] }),
        );
      }
      if (url.startsWith("/api/v1/approvals/pending-assignment/")) {
        return Promise.resolve(
          response([
            {
              id: 8,
              employee_name: "Ada Lovelace",
              employee_email: "ada@example.com",
              base_location_name: "HCM",
              work_date: "2026-07-24",
              note_present: false,
              version: 1,
              submitted_at: "2026-07-24T01:00:00Z",
            },
          ]),
        );
      }
      if (url === "/api/v1/approvals/assignees/") {
        return Promise.resolve(
          response([{ id: 9, name: "Grace", email: "grace@example.com" }]),
        );
      }
      if (url === "/api/v1/approvals/8/assign/")
        return Promise.resolve(response({}));
      return Promise.resolve(responseFor(url));
    });
    render(<ApprovalsPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Assign manager" }),
    );
    fireEvent.change(screen.getByLabelText("Active manager"), {
      target: { value: "9" },
    });
    fireEvent.change(screen.getByLabelText("Assignment reason"), {
      target: { value: "Effective owner confirmed" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Assign manager" }));
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        "/api/v1/approvals/8/assign/",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("renders Monday-first heatmap calendar, aligned legend, and non-color states", async () => {
    render(<DashboardPage />);

    expect(await screen.findByText("111.12%")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Dashboard month"), {
      target: { value: "2026-07" },
    });
    expect(
      await screen.findByLabelText(/Jul 1.*empty eligible date/),
    ).toBeInTheDocument();
    const heatmap = screen.getByLabelText("Monthly work-in-office heatmap");
    expect(
      [...heatmap.querySelectorAll('[data-testid="heatmap-weekday"]')].map(
        (heading) => heading.textContent,
      ),
    ).toEqual(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]);
    const leadingDays = heatmap.querySelectorAll("[data-heatmap-leading-day]");
    expect(leadingDays).toHaveLength(2);
    leadingDays.forEach((day) =>
      expect(day).toHaveAttribute("aria-hidden", "true"),
    );
    expect(heatmap.children[9]).toHaveAttribute(
      "aria-label",
      expect.stringMatching(/Jul 1.*empty eligible date/),
    );
    expect(
      screen.getByRole("link", { name: /Jul 20.*approved/ }),
    ).toHaveAttribute("href", "/work-in-office/3");
    expect(
      screen.getByLabelText(/Jul 29.*Ineligible: Holiday/),
    ).toHaveAttribute("aria-disabled", "true");
    expect(screen.getAllByText("firm office intention")).toHaveLength(2);
    expect(
      screen.getByRole("heading", { name: "Heatmap legend" }),
    ).toBeInTheDocument();
    expect(screen.getByText("flexible home intention")).toBeInTheDocument();
    expect(screen.getByText("empty eligible date")).toBeInTheDocument();
    const legend = screen.getByRole("heading", { name: "Heatmap legend" })
      .nextElementSibling as HTMLUListElement;
    expect(legend).toHaveClass("grid");
    expect(legend.children).toHaveLength(13);
    [...legend.children].forEach((item) => {
      expect(item).toHaveClass("grid-cols-[1rem_0.75rem_0.5rem_minmax(0,1fr)]");
      expect(item.children[0]).toHaveAttribute("aria-hidden", "true");
      expect(item.children[1]).toHaveAttribute("aria-hidden", "true");
      expect(item.children[2]).toHaveAttribute("aria-hidden", "true");
      expect(item.children[2]).toHaveTextContent(":");
    });
    expect(screen.getAllByText("✓").length).toBeGreaterThan(1);
    expect(screen.getAllByText("⌛").length).toBeGreaterThan(1);
    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    await waitFor(() =>
      expect(
        apiFetch.mock.calls.some(([url]) => String(url).includes("month=")),
      ).toBe(true),
    );
  });

  it("retries each dashboard request without passing click events as signals", async () => {
    const failedPaths = new Set([
      "/api/v1/dashboard/today/",
      "/api/v1/dashboard/ratio/",
      "/api/v1/dashboard/activity/?year=2026&month=07",
      "/api/v1/dashboard/heatmap/?year=2026&month=07",
    ]);
    const retryCalls: Array<[string, RequestInit | undefined]> = [];
    apiFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.signal && typeof init.signal.aborted !== "boolean")
        return Promise.reject(
          new TypeError("Failed to convert value to AbortSignal"),
        );
      if (failedPaths.delete(url))
        return Promise.resolve(
          response({ detail: "Service unavailable" }, 503),
        );
      if (url.startsWith("/api/v1/dashboard/")) retryCalls.push([url, init]);
      return Promise.resolve(responseFor(url));
    });

    render(<DashboardPage />);

    const retryButtons = await screen.findAllByRole("button", {
      name: "Retry",
    });
    expect(retryButtons).toHaveLength(5);
    retryButtons.forEach((button) => fireEvent.click(button));

    await waitFor(() =>
      expect(screen.queryByText("Service unavailable")).toBeNull(),
    );
    expect(screen.queryByText(/AbortSignal/)).toBeNull();
    expect(retryCalls.map(([url]) => url)).toEqual(
      expect.arrayContaining([
        "/api/v1/dashboard/today/",
        "/api/v1/dashboard/ratio/",
        "/api/v1/dashboard/activity/?year=2026&month=07",
        "/api/v1/dashboard/heatmap/?year=2026&month=07",
      ]),
    );
    retryCalls.forEach(([, init]) => expect(init?.signal).toBeUndefined());
  });

  it("localizes Monday-first heatmap headings in Vietnamese", async () => {
    document.documentElement.lang = "vi";
    render(<DashboardPage />);

    await screen.findByText("111.12%");
    const heatmap = screen.getByLabelText(
      "Bản đồ nhiệt làm việc tại văn phòng theo tháng",
    );
    expect(
      [...heatmap.querySelectorAll('[data-testid="heatmap-weekday"]')].map(
        (heading) => heading.textContent,
      ),
    ).toEqual(["T2", "T3", "T4", "T5", "T6", "T7", "CN"]);
  });

  it("keeps stable modules visible and ignores superseded month responses", async () => {
    const activityRequests: Array<ReturnType<typeof deferred<Response>>> = [];
    const heatmapRequests: Array<ReturnType<typeof deferred<Response>>> = [];
    let deferMonthly = false;
    apiFetch.mockImplementation((url: string) => {
      if (deferMonthly && url.startsWith("/api/v1/dashboard/activity/")) {
        const request = deferred<Response>();
        activityRequests.push(request);
        return request.promise;
      }
      if (deferMonthly && url.startsWith("/api/v1/dashboard/heatmap/")) {
        const request = deferred<Response>();
        heatmapRequests.push(request);
        return request.promise;
      }
      return Promise.resolve(responseFor(url));
    });
    render(<DashboardPage />);

    expect(await screen.findByText("111.12%")).toBeInTheDocument();
    const stableCalls = apiFetch.mock.calls.filter(([url]) =>
      ["/api/v1/dashboard/today/", "/api/v1/dashboard/ratio/"].includes(
        String(url),
      ),
    ).length;
    deferMonthly = true;

    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    await waitFor(() => {
      expect(activityRequests).toHaveLength(1);
      expect(heatmapRequests).toHaveLength(1);
    });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => {
      expect(activityRequests).toHaveLength(2);
      expect(heatmapRequests).toHaveLength(2);
    });

    expect(
      apiFetch.mock.calls.filter(([url]) =>
        ["/api/v1/dashboard/today/", "/api/v1/dashboard/ratio/"].includes(
          String(url),
        ),
      ),
    ).toHaveLength(stableCalls);
    expect(screen.getByText("111.12%")).toBeInTheDocument();
    expect(screen.queryByLabelText("Loading dashboard module")).toBeNull();
    const heatmapModule = screen.getByLabelText(
      "Monthly work-in-office heatmap",
    ).parentElement;
    const recentRecordsModule = screen
      .getByRole("heading", { name: "Recent WIO records" })
      .closest("section")?.parentElement;
    const upcomingPlansModule = screen
      .getByRole("heading", { name: "Upcoming private plans" })
      .closest("section")?.parentElement;
    expect(heatmapModule).toHaveAttribute("aria-busy", "true");
    expect(heatmapModule).toHaveClass("opacity-60");
    expect(recentRecordsModule).toHaveClass("opacity-60");
    expect(upcomingPlansModule).not.toHaveClass("opacity-60");

    activityRequests[0].resolve(
      response({
        records: [{ id: 10, date: "2025-01-01", state: "approved" }],
        intentions: [],
      }),
    );
    heatmapRequests[0].resolve(response([]));
    await Promise.resolve();
    expect(screen.queryByText("Jan 1, 2025")).not.toBeInTheDocument();

    activityRequests[1].resolve(
      response({
        records: [{ id: 11, date: "2026-01-01", state: "approved" }],
        intentions: [],
      }),
    );
    heatmapRequests[1].resolve(response([]));
    expect(await screen.findByText("Jan 1, 2026")).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByLabelText("Monthly work-in-office heatmap").parentElement,
      ).not.toHaveAttribute("aria-busy"),
    );
  });

  it("renders private plan coverage and preview workflow", async () => {
    render(<PlannerPage />);

    expect(await screen.findByText("Plan coverage")).toBeInTheDocument();
    expect(
      await screen.findByText("2.00 across 2 office day(s)"),
    ).toBeInTheDocument();
    expect(await screen.findByText("Firm Office")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Preview changes" }));

    expect(
      await screen.findByRole("heading", { name: "Preview" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Your upcoming intentions")).toBeInTheDocument();
  });

  it("saves previews and edits or deletes a future Planner series", async () => {
    apiFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/v1/planner/" && init?.method === "POST") {
        return Promise.resolve(response({ created: 1 }));
      }
      if (url === "/api/v1/planner/4/" && init?.method === "PATCH") {
        return Promise.resolve(response({}));
      }
      if (url.startsWith("/api/v1/planner/4/?") && init?.method === "DELETE") {
        return Promise.resolve(response({}));
      }
      return Promise.resolve(responseFor(url));
    });
    render(<PlannerPage />);

    await screen.findByText("Firm Office");
    fireEvent.click(screen.getByRole("radio", { name: "Selected weekdays" }));
    fireEvent.click(screen.getByLabelText("Mon"));
    fireEvent.change(screen.getByLabelText("Location"), {
      target: { value: "home" },
    });
    fireEvent.change(screen.getByLabelText("Commitment"), {
      target: { value: "flexible" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Preview changes" }));
    await screen.findByRole("heading", { name: "Preview" });
    expect(screen.getByText("Existing intention")).toBeInTheDocument();
    expect(screen.getByText("Ready to save")).toBeInTheDocument();
    expect(screen.getByText("Holiday")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save intentions" }));
    expect(
      await screen.findByText(/1 private intention\(s\) saved/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    await screen.findByRole("heading", { name: "Edit 2026-07-28" });
    fireEvent.click(
      screen.getByRole("button", { name: "Delete series from today" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm series delete" }),
    );
    expect(
      await screen.findByText("Today and future series intentions deleted."),
    ).toBeInTheDocument();
  });
});
