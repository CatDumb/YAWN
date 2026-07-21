"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { apiFetch } from "../lib/api";

const accessRequestSchema = z.object({
  email: z.string().trim().email("Enter a valid email address."),
  first_name: z.string().trim().min(1, "Enter your first name.").max(150),
  last_name: z.string().trim().min(1, "Enter your last name.").max(150),
});

const loginSchema = z.object({
  email: z.string().trim().email("Enter a valid email address."),
});

type AccessRequestValues = z.infer<typeof accessRequestSchema>;
type LoginValues = z.infer<typeof loginSchema>;

type Membership = {
  company: string;
  company_id: number;
  role: string;
};

type CurrentUser = {
  email: string;
  first_name: string;
  id: number;
  last_name: string;
  memberships: Membership[];
};

type View = "access-request" | "access-confirmed" | "login" | "signed-in";

const GENERIC_SIGNUP_MESSAGE = "Your access request is pending review.";
const GENERIC_OTP_MESSAGE =
  "If your account is eligible, a sign-in code has been sent.";
const OTP_LENGTH = 6;

function normalizeEmail(email: string) {
  return email.trim().toLowerCase();
}

async function responseDetail(response: Response, fallback: string) {
  try {
    const data: unknown = await response.json();
    if (
      typeof data === "object" &&
      data !== null &&
      "detail" in data &&
      typeof data.detail === "string"
    ) {
      return data.detail;
    }
  } catch {
    // Generic UI copy is safer than exposing an unexpected response body.
  }
  return fallback;
}

function isCurrentUser(value: unknown): value is CurrentUser {
  return (
    typeof value === "object" &&
    value !== null &&
    "email" in value &&
    typeof value.email === "string" &&
    "memberships" in value &&
    Array.isArray(value.memberships)
  );
}

function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="bg-base-100 text-base-content min-h-screen px-4 py-10 sm:px-8">
      <section className="mx-auto w-full max-w-lg">
        <div className="mb-8 text-center">
          <p className="text-base-content/70 text-sm font-semibold tracking-widest uppercase">
            YAWN
          </p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">
            Workplace access
          </h1>
        </div>
        {children}
      </section>
    </main>
  );
}

function FieldError({
  message,
  visible = true,
}: {
  message?: string;
  visible?: boolean;
}) {
  if (!message || !visible) return null;
  return <p className="text-error mt-1 text-sm">{message}</p>;
}

export default function Home() {
  const [view, setView] = useState<View>("access-request");
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [loginEmail, setLoginEmail] = useState("");
  const [challengeId, setChallengeId] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [otpRequested, setOtpRequested] = useState(false);
  const otpInputs = useRef<Array<HTMLInputElement | null>>([]);

  const accessRequestForm = useForm<AccessRequestValues>({
    resolver: zodResolver(accessRequestSchema),
  });
  const accessRequestEmailInput = useWatch({
    control: accessRequestForm.control,
    name: "email",
  });
  const accessRequestFirstNameInput = useWatch({
    control: accessRequestForm.control,
    name: "first_name",
  });
  const accessRequestLastNameInput = useWatch({
    control: accessRequestForm.control,
    name: "last_name",
  });
  const loginForm = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
  });
  const loginEmailInput = useWatch({
    control: loginForm.control,
    name: "email",
  });

  useEffect(() => {
    void (async () => {
      try {
        const response = await apiFetch("/api/v1/users/me/");
        if (!response.ok) return;
        const data: unknown = await response.json();
        if (isCurrentUser(data)) {
          setCurrentUser(data);
          setView("signed-in");
        }
      } catch {
        // Keep public access request available when API is offline.
      }
    })();
  }, []);

  async function submitAccessRequest(values: AccessRequestValues) {
    setError(null);
    setNotice(null);
    setIsSubmitting(true);
    try {
      const response = await apiFetch("/api/v1/auth/sign-up/", {
        body: JSON.stringify({
          ...values,
          email: normalizeEmail(values.email),
        }),
        method: "POST",
      });
      if (!response.ok) {
        setError(
          await responseDetail(
            response,
            "Unable to submit request. Try again.",
          ),
        );
        return;
      }
      setView("access-confirmed");
    } catch {
      setError("Unable to submit request. Check connection and try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function requestOtp(values: LoginValues) {
    setError(null);
    setNotice(null);
    setIsSubmitting(true);
    try {
      const email = normalizeEmail(values.email);
      const response = await apiFetch("/api/v1/auth/otp/request/", {
        body: JSON.stringify({ email }),
        method: "POST",
      });
      if (!response.ok) {
        setError(
          await responseDetail(response, "Unable to request code. Try again."),
        );
        return;
      }
      const data: unknown = await response.json();
      const returnedChallengeId =
        typeof data === "object" &&
        data !== null &&
        "challenge_id" in data &&
        typeof data.challenge_id === "string"
          ? data.challenge_id
          : "";
      if (!returnedChallengeId) {
        setError("Unable to request code. Try again.");
        return;
      }
      setLoginEmail(email);
      setChallengeId(returnedChallengeId);
      setOtpCode("");
      setOtpRequested(true);
      setNotice(GENERIC_OTP_MESSAGE);
    } catch {
      setError("Unable to request code. Check connection and try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function verifyOtp(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    if (!new RegExp(`^\\d{${OTP_LENGTH}}$`).test(otpCode)) {
      setError("Enter the six-digit code from your email.");
      return;
    }
    setIsSubmitting(true);
    try {
      const response = await apiFetch("/api/v1/auth/otp/verify/", {
        body: JSON.stringify({
          challenge_id: challengeId,
          code: otpCode,
          email: loginEmail,
        }),
        method: "POST",
      });
      if (!response.ok) {
        setError(
          await responseDetail(
            response,
            "Invalid, expired, or unavailable sign-in code. Request a new code and try again.",
          ),
        );
        return;
      }
      const data: unknown = await response.json();
      if (!isCurrentUser(data)) {
        setError("Unable to finish sign-in. Try again.");
        return;
      }
      setCurrentUser(data);
      setView("signed-in");
    } catch {
      setError("Unable to verify code. Check connection and try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function setOtpDigits(startIndex: number, value: string) {
    const digits = value.replace(/\D/g, "").slice(0, OTP_LENGTH - startIndex);
    setOtpCode((current) => {
      const next = current
        .padEnd(OTP_LENGTH, " ")
        .slice(0, OTP_LENGTH)
        .split("");

      if (!digits) {
        next[startIndex] = " ";
      } else {
        digits.split("").forEach((digit, offset) => {
          next[startIndex + offset] = digit;
        });
      }

      return next.join("");
    });

    if (digits) {
      otpInputs.current[
        Math.min(startIndex + digits.length, OTP_LENGTH - 1)
      ]?.focus();
    }
  }

  async function logout() {
    setError(null);
    setIsSubmitting(true);
    try {
      const response = await apiFetch("/api/v1/auth/logout/", {
        method: "POST",
      });
      if (!response.ok) {
        setError(
          await responseDetail(response, "Unable to log out. Try again."),
        );
        return;
      }
      setCurrentUser(null);
      setOtpRequested(false);
      setView("access-request");
    } catch {
      setError("Unable to reach service. Try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function showLogin() {
    setError(null);
    setNotice(null);
    setOtpRequested(false);
    setView("login");
  }

  function showAccessRequest() {
    setError(null);
    setNotice(null);
    setOtpRequested(false);
    setView("access-request");
  }

  if (view === "signed-in" && currentUser) {
    return (
      <AuthShell>
        <article className="card bg-base-200">
          <div className="card-body">
            <h2 className="card-title">You are signed in</h2>
            <p>{currentUser.email}</p>
            <div className="divider">Memberships</div>
            <ul className="list">
              {currentUser.memberships.map((membership) => (
                <li
                  key={`${membership.company_id}-${membership.role}`}
                  className="list-row"
                >
                  <div>
                    <p className="font-semibold">{membership.company}</p>
                    <p className="text-base-content/70 text-sm">
                      {membership.role}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
            <p className="text-base-content/70 text-sm">
              Phase 2 identity placeholder.
            </p>
            {error ? (
              <div className="alert alert-error" role="alert">
                <span>{error}</span>
              </div>
            ) : null}
            <div className="card-actions justify-end">
              <button
                className="btn"
                disabled={isSubmitting}
                onClick={logout}
                type="button"
              >
                Log out
              </button>
            </div>
          </div>
        </article>
      </AuthShell>
    );
  }

  if (view === "access-confirmed") {
    return (
      <AuthShell>
        <article className="card bg-base-200">
          <div className="card-body">
            <h2 className="card-title">Request received</h2>
            <div className="alert alert-success" role="status">
              <span>{GENERIC_SIGNUP_MESSAGE}</span>
            </div>
            <p className="text-base-content/70">
              Already approved? Sign in with your email code.
            </p>
            <div className="card-actions justify-end">
              <button
                className="btn btn-primary"
                onClick={showLogin}
                type="button"
              >
                Sign in
              </button>
            </div>
          </div>
        </article>
      </AuthShell>
    );
  }

  if (view === "login") {
    return (
      <AuthShell>
        <article className="card bg-base-200">
          <div className="card-body">
            <h2 className="card-title">Sign in</h2>
            <p className="text-base-content/70">
              Use your approved work email.
            </p>
            {error ? (
              <div className="alert alert-error" role="alert">
                <span>{error}</span>
              </div>
            ) : null}
            {notice ? (
              <div className="alert alert-info" role="status">
                <span>{notice}</span>
              </div>
            ) : null}
            {otpRequested ? (
              <form className="space-y-5" onSubmit={verifyOtp}>
                <p className="text-sm">Code sent for {loginEmail}</p>
                <fieldset className="fieldset">
                  <legend className="fieldset-legend">Six-digit code</legend>
                  <div className="grid w-full grid-cols-6 gap-3">
                    {Array.from({ length: OTP_LENGTH }, (_, index) => (
                      <input
                        key={index}
                        aria-label={`Digit ${index + 1} of ${OTP_LENGTH}`}
                        autoComplete={index === 0 ? "one-time-code" : "off"}
                        className="input h-18 w-full min-w-0 px-0 text-center text-2xl"
                        inputMode="numeric"
                        maxLength={1}
                        onChange={(event) =>
                          setOtpDigits(index, event.target.value)
                        }
                        onKeyDown={(event) => {
                          if (
                            event.key === "Backspace" &&
                            !otpCode[index]?.trim() &&
                            index > 0
                          ) {
                            event.preventDefault();
                            setOtpDigits(index - 1, "");
                            otpInputs.current[index - 1]?.focus();
                          }
                        }}
                        onPaste={(event) => {
                          event.preventDefault();
                          setOtpDigits(
                            index,
                            event.clipboardData.getData("text"),
                          );
                        }}
                        ref={(input) => {
                          otpInputs.current[index] = input;
                        }}
                        type="text"
                        value={otpCode[index]?.trim() ?? ""}
                      />
                    ))}
                  </div>
                </fieldset>
                <div className="card-actions justify-between">
                  <button
                    className="btn btn-ghost"
                    onClick={() => setOtpRequested(false)}
                    type="button"
                  >
                    Use another email
                  </button>
                  <button
                    className="btn btn-primary"
                    disabled={isSubmitting}
                    type="submit"
                  >
                    Verify code
                  </button>
                </div>
              </form>
            ) : (
              <form
                className="space-y-5"
                onSubmit={loginForm.handleSubmit(requestOtp)}
              >
                <fieldset className="fieldset">
                  <legend className="fieldset-legend">Email</legend>
                  <input
                    {...loginForm.register("email")}
                    aria-label="Email"
                    className="input w-full"
                    inputMode="email"
                    placeholder="name@company.com"
                    type="email"
                  />
                  <FieldError
                    message={loginForm.formState.errors.email?.message}
                    visible={Boolean(loginEmailInput?.trim())}
                  />
                </fieldset>
                <div className="card-actions justify-between">
                  <button
                    className="btn btn-ghost"
                    onClick={showAccessRequest}
                    type="button"
                  >
                    Request access
                  </button>
                  <button
                    className="btn btn-primary"
                    disabled={isSubmitting}
                    type="submit"
                  >
                    Send code
                  </button>
                </div>
              </form>
            )}
          </div>
        </article>
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      <article className="card bg-base-200">
        <div className="card-body">
          <h2 className="card-title">Request access</h2>
          <p className="text-base-content/70">
            Submit your details for workplace access review.
          </p>
          {error ? (
            <div className="alert alert-error" role="alert">
              <span>{error}</span>
            </div>
          ) : null}
          <form
            className="space-y-4"
            onSubmit={accessRequestForm.handleSubmit(submitAccessRequest)}
          >
            <fieldset className="fieldset">
              <legend className="fieldset-legend">First name</legend>
              <input
                {...accessRequestForm.register("first_name")}
                aria-label="First name"
                className="input w-full"
                autoComplete="given-name"
              />
              <FieldError
                message={accessRequestForm.formState.errors.first_name?.message}
                visible={Boolean(accessRequestFirstNameInput?.trim())}
              />
            </fieldset>
            <fieldset className="fieldset">
              <legend className="fieldset-legend">Last name</legend>
              <input
                {...accessRequestForm.register("last_name")}
                aria-label="Last name"
                className="input w-full"
                autoComplete="family-name"
              />
              <FieldError
                message={accessRequestForm.formState.errors.last_name?.message}
                visible={Boolean(accessRequestLastNameInput?.trim())}
              />
            </fieldset>
            <fieldset className="fieldset">
              <legend className="fieldset-legend">Email</legend>
              <input
                {...accessRequestForm.register("email")}
                aria-label="Email"
                className="input w-full"
                inputMode="email"
                placeholder="name@company.com"
                type="email"
              />
              <FieldError
                message={accessRequestForm.formState.errors.email?.message}
                visible={Boolean(accessRequestEmailInput?.trim())}
              />
            </fieldset>
            <div className="card-actions justify-between pt-2">
              <button
                className="btn btn-ghost"
                onClick={showLogin}
                type="button"
              >
                Already approved? Sign in
              </button>
              <button
                className="btn btn-primary"
                disabled={isSubmitting}
                type="submit"
              >
                Request access
              </button>
            </div>
          </form>
        </div>
      </article>
    </AuthShell>
  );
}
