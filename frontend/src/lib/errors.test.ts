import { afterEach, describe, expect, it, vi } from "vitest";

const { captureException } = vi.hoisted(() => ({
  captureException: vi.fn(),
}));

vi.mock("@sentry/nextjs", () => ({ captureException }));

import {
  ApiError,
  apiErrorFromResponse,
  responseDetail,
  userFacingError,
} from "./errors";

describe("frontend error policy", () => {
  afterEach(() => captureException.mockClear());

  it("keeps structured 4xx domain detail", async () => {
    const response = new Response(
      JSON.stringify({ detail: "Date is closed." }),
      {
        status: 400,
      },
    );

    expect(await responseDetail(response, "Try again.")).toBe(
      "Date is closed.",
    );
  });

  it("hides 5xx and malformed response detail", async () => {
    const serverFailure = new Response(
      JSON.stringify({ detail: "SQL failed" }),
      {
        status: 503,
      },
    );
    const malformedFailure = new Response("not json", { status: 400 });

    expect(await responseDetail(serverFailure, "Try again.")).toBe(
      "Try again.",
    );
    expect(await responseDetail(malformedFailure, "Try again.")).toBe(
      "Try again.",
    );
  });

  it("preserves expected API errors without telemetry", async () => {
    const error = await apiErrorFromResponse(
      new Response(JSON.stringify({ detail: "Record changed." }), {
        status: 409,
      }),
      "Unable to save record.",
    );

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(409);
    expect(userFacingError(error, "Fallback.")).toBe("Record changed.");
    expect(captureException).not.toHaveBeenCalled();
  });

  it("keeps only allowlisted field names and discards raw validation values", async () => {
    const error = await apiErrorFromResponse(
      new Response(
        JSON.stringify({
          work_date: ["private date detail"],
          note: ["private note detail"],
          unknown: ["SQL detail"],
        }),
        { status: 400 },
      ),
      "Check the form.",
      ["work_date", "location_choice", "note"] as const,
    );

    expect(error.message).toBe("Check the form.");
    expect(error.fieldErrors).toEqual(["work_date", "note"]);
    expect(JSON.stringify(error)).not.toMatch(/private|SQL/);
  });

  it("hides and reports unexpected exceptions", () => {
    const error = new TypeError("AbortSignal conversion failed");

    expect(userFacingError(error, "Module unavailable.")).toBe(
      "Module unavailable.",
    );
    expect(captureException).toHaveBeenCalledWith(error);
    expect(userFacingError("unexpected", "Module unavailable.")).toBe(
      "Module unavailable.",
    );
    expect(captureException).toHaveBeenCalledWith("unexpected");
  });

  it("does not report deliberate aborts", () => {
    const error = new DOMException("Request cancelled", "AbortError");

    expect(userFacingError(error, "Module unavailable.")).toBe(
      "Module unavailable.",
    );
    expect(captureException).not.toHaveBeenCalled();
  });
});
