import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock("../../lib/api", () => ({ apiFetch }));

import { TransitionBaselineCard } from "./transition-baseline-card";

function response(payload: unknown) {
  return { ok: true, json: async () => payload } as Response;
}

describe("TransitionBaselineCard", () => {
  beforeEach(() => {
    apiFetch.mockReset();
  });
  afterEach(cleanup);

  it("shows self-service form while employee remains eligible", async () => {
    apiFetch.mockResolvedValueOnce(
      response({
        eligible: true,
        lock_reason: null,
        latest_cutoff_month: "2026-06",
        baseline: null,
      }),
    );
    render(<TransitionBaselineCard onSaved={vi.fn()} />);

    expect(
      await screen.findByRole("heading", {
        name: "Bring your previous WIO balance",
      }),
    ).toBeVisible();
    expect(screen.getByLabelText("Legacy target days")).toBeVisible();
    expect(screen.getByLabelText("Legacy achieved days")).toHaveValue(0);
    expect(screen.getByLabelText("Legacy cutoff month")).toHaveValue("2026-06");
    expect(screen.getByLabelText("Legacy cutoff month")).toHaveAttribute(
      "max",
      "2026-06",
    );
  });

  it("shows locked saved balance without editable fields", async () => {
    apiFetch.mockResolvedValueOnce(
      response({
        eligible: false,
        lock_reason: "A post-cutoff WIO record exists.",
        latest_cutoff_month: null,
        baseline: {
          cutoff_month: "2026-06",
          cutoff_date: "2026-06-30",
          target_days: "10.50",
          achieved_days: "8.25",
          ratio_display: "78.58%",
          version: 1,
          can_edit: false,
        },
      }),
    );
    render(<TransitionBaselineCard onSaved={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "Transition balance locked",
      ),
    );
    expect(
      screen.queryByLabelText("Legacy target days"),
    ).not.toBeInTheDocument();
  });
});
