import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { AuditStreamComparison } from "./audit-stream-comparison";

it("shows both streams and an accessible privileged explanation", () => {
  render(
    <AuditStreamComparison
      approved={{ days: "1", ratio: "50%", balance: "-1" }}
      approvedLabel="Approved"
      balanceLabel="Balance"
      expectedLabel="2"
      selfApprovalApplies
      explanation="Auto-approved"
      selfSubmitted={{ days: "2", ratio: "100%", balance: "0" }}
      selfSubmittedLabel="Self-submitted"
    />,
  );

  expect(screen.getByText("Approved")).toBeVisible();
  expect(screen.getAllByText("Self-submitted")).toHaveLength(1);
  const toggle = screen.getByRole("button", { name: "Auto-approved" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(screen.getAllByText("Auto-approved")).toHaveLength(2);
});
