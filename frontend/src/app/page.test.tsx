import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));

vi.mock("../lib/api", () => ({ apiFetch }));

import Home from "./page";

const anonymousResponse = () => new Response(null, { status: 401 });
const jsonResponse = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    headers: { "Content-Type": "application/json" },
    status,
  });

function renderAnonymousHome() {
  apiFetch.mockResolvedValueOnce(anonymousResponse());
  render(<Home />);
}

async function fillAccessRequest() {
  fireEvent.change(screen.getByLabelText("First name"), {
    target: { value: "Ada" },
  });
  fireEvent.change(screen.getByLabelText("Last name"), {
    target: { value: "Lovelace" },
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

  it("starts with validated access request and generic confirmation", async () => {
    renderAnonymousHome();

    fireEvent.click(screen.getByRole("button", { name: "Request access" }));

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

  it("hides access-request name validation after fields are cleared", async () => {
    renderAnonymousHome();
    const firstName = screen.getByLabelText("First name");
    const lastName = screen.getByLabelText("Last name");

    fireEvent.change(firstName, { target: { value: "a".repeat(151) } });
    fireEvent.change(lastName, { target: { value: "a".repeat(151) } });
    fireEvent.click(screen.getByRole("button", { name: "Request access" }));
    await waitFor(() => {
      expect(document.querySelectorAll("p.text-error")).toHaveLength(2);
    });

    fireEvent.change(firstName, { target: { value: "" } });
    fireEvent.change(lastName, { target: { value: "" } });

    await waitFor(() => {
      expect(document.querySelectorAll("p.text-error")).toHaveLength(0);
    });
  });

  it("moves approved user through OTP sign-in and renders identity placeholder", async () => {
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

    expect(
      await screen.findByText("Code sent for ada@example.com"),
    ).toBeInTheDocument();
    const otpInputs = screen.getAllByRole("textbox", {
      name: /Digit \d of 6/,
    });
    expect(otpInputs).toHaveLength(6);
    otpInputs.forEach((input) => {
      expect(input).toHaveClass(
        "input",
        "h-18",
        "w-full",
        "min-w-0",
        "px-0",
        "text-center",
        "text-2xl",
      );
    });
    apiFetch.mockResolvedValueOnce(
      jsonResponse({
        email: "ada@example.com",
        first_name: "Ada",
        id: 1,
        last_name: "Lovelace",
        memberships: [{ company: "Example", company_id: 1, role: "employee" }],
      }),
    );
    fireEvent.change(otpInputs[0], {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify code" }));

    expect(await screen.findByText("You are signed in")).toBeInTheDocument();
    expect(screen.getByText("Example")).toBeInTheDocument();
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
    await screen.findByText("Code sent for ada@example.com");
    apiFetch.mockResolvedValueOnce(
      jsonResponse({ detail: "Invalid or expired code." }, 400),
    );
    fireEvent.change(screen.getByLabelText("Digit 1 of 6"), {
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

  it("hides the sign-in email validation message after the email is cleared", async () => {
    renderAnonymousHome();
    fireEvent.click(
      screen.getByRole("button", { name: "Already approved? Sign in" }),
    );

    const email = screen.getByRole("textbox", { name: "Email" });
    fireEvent.change(email, { target: { value: "not-an-email" } });
    fireEvent.submit(
      screen.getByRole("button", { name: "Send code" }).closest("form")!,
    );

    expect(
      await screen.findByText("Enter a valid email address."),
    ).toBeInTheDocument();

    fireEvent.change(email, { target: { value: "" } });

    await waitFor(() => {
      expect(
        screen.queryByText("Enter a valid email address."),
      ).not.toBeInTheDocument();
    });
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

  it("restores existing session and logs out to access request", async () => {
    apiFetch.mockResolvedValueOnce(
      jsonResponse({
        email: "ada@example.com",
        first_name: "Ada",
        id: 1,
        last_name: "Lovelace",
        memberships: [{ company: "Example", company_id: 1, role: "employee" }],
      }),
    );
    render(<Home />);

    expect(await screen.findByText("You are signed in")).toBeInTheDocument();
    apiFetch.mockResolvedValueOnce(new Response(null, { status: 204 }));
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Request access" }),
      ).toBeInTheDocument(),
    );
    expect(apiFetch).toHaveBeenLastCalledWith("/api/v1/auth/logout/", {
      method: "POST",
    });
  });

  it("keeps signed-in state when logout fails", async () => {
    apiFetch.mockResolvedValueOnce(
      jsonResponse({
        email: "ada@example.com",
        first_name: "Ada",
        id: 1,
        last_name: "Lovelace",
        memberships: [{ company: "Example", company_id: 1, role: "employee" }],
      }),
    );
    render(<Home />);

    expect(await screen.findByText("You are signed in")).toBeInTheDocument();
    apiFetch.mockResolvedValueOnce(
      jsonResponse({ detail: "Logout unavailable." }, 503),
    );
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Logout unavailable.",
    );
    expect(screen.getByText("You are signed in")).toBeInTheDocument();
  });
});
