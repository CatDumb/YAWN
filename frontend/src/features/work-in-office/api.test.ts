import { beforeEach, describe, expect, it, vi } from "vitest";

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock("../../lib/api", () => ({ apiFetch }));

import {
  deleteWorkInOffice,
  getWorkInOffice,
  listWorkInOffice,
  saveWorkInOffice,
} from "./api";

const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
    status,
  });

describe("work-in-office API", () => {
  beforeEach(() => apiFetch.mockReset());

  it("uses personal record endpoints and payloads", async () => {
    apiFetch.mockResolvedValueOnce(response([]));
    await listWorkInOffice("?review_state=draft", "Unable to load.");
    expect(apiFetch).toHaveBeenLastCalledWith(
      "/api/v1/work-in-office/?review_state=draft",
    );

    apiFetch.mockResolvedValueOnce(response({ id: 2 }));
    await getWorkInOffice("2", "Unable to load.");
    expect(apiFetch).toHaveBeenLastCalledWith("/api/v1/work-in-office/2/");

    apiFetch.mockResolvedValueOnce(response({ id: 2 }, 201));
    await saveWorkInOffice(
      { work_date: "2026-07-23" },
      undefined,
      "Unable to save.",
    );
    expect(apiFetch).toHaveBeenLastCalledWith("/api/v1/work-in-office/", {
      body: JSON.stringify({ work_date: "2026-07-23" }),
      method: "POST",
    });

    apiFetch.mockResolvedValueOnce(response({ id: 2 }));
    await saveWorkInOffice(
      { work_date: "2026-07-23", version: 1 },
      "2",
      "Unable to save.",
    );
    expect(apiFetch).toHaveBeenLastCalledWith("/api/v1/work-in-office/2/", {
      body: JSON.stringify({ work_date: "2026-07-23", version: 1 }),
      method: "PUT",
    });

    apiFetch.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await deleteWorkInOffice("2", 1, "Unable to delete.");
    expect(apiFetch).toHaveBeenLastCalledWith(
      "/api/v1/work-in-office/2/?version=1",
      {
        headers: { "X-Requested-With": "XMLHttpRequest" },
        method: "DELETE",
      },
    );
  });

  it("keeps API failure detail", async () => {
    apiFetch.mockResolvedValueOnce(
      response({ detail: "Date is closed." }, 400),
    );
    await expect(listWorkInOffice("", "Fallback.")).rejects.toMatchObject({
      message: "Date is closed.",
      status: 400,
    });
  });
});
