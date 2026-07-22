import { apiFetch } from "../../lib/api";

import { isCurrentUser, type CurrentUser } from "./contracts";
import type { AccessRequestValues } from "./schemas";

export function normalizeEmail(email: string) {
  return email.trim().toLowerCase();
}

export async function responseDetail(response: Response, fallback: string) {
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

export function submitAccessRequest(values: AccessRequestValues) {
  return apiFetch("/api/v1/auth/sign-up/", {
    body: JSON.stringify({ ...values, email: normalizeEmail(values.email) }),
    method: "POST",
  });
}

export function requestOtp(email: string) {
  return apiFetch("/api/v1/auth/otp/request/", {
    body: JSON.stringify({ email: normalizeEmail(email) }),
    method: "POST",
  });
}

export function verifyOtp(challengeId: string, email: string, code: string) {
  return apiFetch("/api/v1/auth/otp/verify/", {
    body: JSON.stringify({ challenge_id: challengeId, code, email }),
    method: "POST",
  });
}

export type CurrentUserResult = {
  response: Response;
  user: CurrentUser | null;
};

export async function currentUser(): Promise<CurrentUserResult> {
  const response = await apiFetch("/api/v1/users/me/");
  if (!response.ok) return { response, user: null };
  const data: unknown = await response.json();
  return { response, user: isCurrentUser(data) ? data : null };
}

export function logout() {
  return apiFetch("/api/v1/auth/logout/", { method: "POST" });
}
