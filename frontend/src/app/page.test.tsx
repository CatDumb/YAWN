import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { apiFetch, replace } = vi.hoisted(() => ({
  apiFetch: vi.fn(),
  replace: vi.fn(),
}));

vi.mock("../lib/api", () => ({ apiFetch }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

import Home from "./page";

const jsonResponse = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    headers: { "Content-Type": "application/json" },
    status,
  });

function renderAnonymousHome() {
  render(<Home />);
}

async function fillAccessRequest() {
  fireEvent.change(screen.getByLabelText("First name"), {
    target: { value: " Ada " },
  });
  fireEvent.change(screen.getByLabelText("Last name"), {
    target: { value: " Lovelace " },
  });
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: "ADA@EXAMPLE.COM" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Request access" }));
}

describe("Home", () => {
  beforeEach(() => {
    apiFetch.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("starts with native-validated access request and generic confirmation", async () => {
    renderAnonymousHome();

    fireEvent.click(screen.getByRole("button", { name: "Request access" }));
    expect(apiFetch).not.toHaveBeenCalled();

    apiFetch.mockResolvedValueOnce(jsonResponse({ detail: "ignored" }, 202));
    await fillAccessRequest();

    expect(await screen.findByText("Request received")).toBeInTheDocument();
    expect(
      screen.getByText("Your access request is pending review."),
    ).toBeInTheDocument();
    expect(apiFetch).toHaveBeenLastCalledWith("/api/v1/auth/sign-up/", {
      body: JSON.stringify({
        email: "ada@example.com",
        first_name: "Ada",
        last_name: "Lovelace",
      }),
      method: "POST",
    });
  });

  it("uses native constraints to block invalid access requests", () => {
    renderAnonymousHome();
    const firstName = screen.getByLabelText("First name");
    const lastName = screen.getByLabelText("Last name");
    const email = screen.getByLabelText("Email");

    fireEvent.click(screen.getByRole("button", { name: "Request access" }));
    expect(apiFetch).not.toHaveBeenCalled();
    expect(firstName).toBeInvalid();

    fireEvent.change(firstName, { target: { value: "   " } });
    fireEvent.change(lastName, { target: { value: "Lovelace" } });
    fireEvent.change(email, { target: { value: "ada@example.com" } });
    expect(firstName).toBeInvalid();

    fireEvent.change(firstName, { target: { value: "A".repeat(151) } });
    expect(firstName).toHaveAttribute("maxlength", "150");
    fireEvent.submit(
      screen.getByRole("button", { name: "Request access" }).closest("form")!,
    );
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("moves approved user through OTP sign-in and navigates to dashboard", async () => {
    renderAnonymousHome();
    fireEvent.click(
      screen.getByRole("button", { name: "Already approved? Sign in" }),
    );
    apiFetch.mockResolvedValueOnce(
      jsonResponse(
        { challenge_id: "35eb0786-1a30-4b0a-a292-7a596218de00" },
        202,
      ),
    );

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "ADA@EXAMPLE.COM" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send code" }));

    expect(await screen.findByText("ada@example.com")).toBeInTheDocument();
    expect(
      screen.getByText("Only approved accounts receive sign-in emails."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Resend available in 60 seconds" }),
    ).toBeDisabled();
    const otpInput = screen.getByRole("textbox", {
      name: "Six-digit code",
    });
    expect(otpInput).toHaveAttribute("autocomplete", "one-time-code");
    expect(otpInput).toHaveAttribute("maxlength", "6");
    apiFetch.mockResolvedValueOnce(
      jsonResponse({
        email: "ada@example.com",
        first_name: "Ada",
        id: 1,
        last_name: "Lovelace",
        memberships: [{ company: "Example", company_id: 1, role: "employee" }],
      }),
    );
    fireEvent.change(otpInput, {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify code" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
    expect(apiFetch).toHaveBeenLastCalledWith("/api/v1/auth/otp/verify/", {
      body: JSON.stringify({
        challenge_id: "35eb0786-1a30-4b0a-a292-7a596218de00",
        code: "123456",
        email: "ada@example.com",
      }),
      method: "POST",
    });
  });

  it("shows invalid code and lets user return to email entry", async () => {
    renderAnonymousHome();
    fireEvent.click(
      screen.getByRole("button", { name: "Already approved? Sign in" }),
    );
    apiFetch.mockResolvedValueOnce(
      jsonResponse({ challenge_id: "challenge" }, 202),
    );
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "ada@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send code" }));
    await screen.findByText("ada@example.com");
    apiFetch.mockResolvedValueOnce(
      jsonResponse({ detail: "Invalid or expired code." }, 400),
    );
    fireEvent.change(screen.getByLabelText("Six-digit code"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify code" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Invalid or expired code.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Use another email" }));
    expect(
      screen.getByRole("button", { name: "Send code" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Request access" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("clears OTP notice when switching to access request", async () => {
    renderAnonymousHome();
    fireEvent.click(
      screen.getByRole("button", { name: "Already approved? Sign in" }),
    );
    apiFetch.mockResolvedValueOnce(
      jsonResponse({ challenge_id: "challenge" }, 202),
    );
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "ada@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send code" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "If your account is eligible, a sign-in code has been sent.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Use another email" }));
    fireEvent.click(screen.getByRole("button", { name: "Request access" }));

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("uses native email validation before requesting an OTP", () => {
    renderAnonymousHome();
    fireEvent.click(
      screen.getByRole("button", { name: "Already approved? Sign in" }),
    );

    const email = screen.getByRole("textbox", { name: "Email" });
    fireEvent.change(email, { target: { value: "not-an-email" } });
    fireEvent.click(screen.getByRole("button", { name: "Send code" }));

    expect(apiFetch).not.toHaveBeenCalled();
    expect(email).toBeInvalid();
  });

  it("keeps access request available after API outage", async () => {
    renderAnonymousHome();
    apiFetch.mockRejectedValueOnce(new Error("offline"));

    await fillAccessRequest();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Check connection and try again.",
    );
    expect(
      screen.getByRole("button", { name: "Request access" }),
    ).toBeInTheDocument();
  });
});
