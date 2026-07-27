import * as Sentry from "@sentry/nextjs";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function responseDetail(response: Response, fallback: string) {
  if (response.status < 400 || response.status >= 500) return fallback;

  try {
    const data: unknown = await response.json();
    if (
      typeof data === "object" &&
      data !== null &&
      "detail" in data &&
      typeof data.detail === "string" &&
      data.detail.trim()
    )
      return data.detail;
  } catch {
    // Malformed API responses must not become user-facing technical errors.
  }
  return fallback;
}

export async function apiErrorFromResponse(
  response: Response,
  fallback: string,
) {
  return new ApiError(
    await responseDetail(response, fallback),
    response.status,
  );
}

export function isAbortError(reason: unknown) {
  return (
    typeof reason === "object" &&
    reason !== null &&
    "name" in reason &&
    reason.name === "AbortError"
  );
}

export function userFacingError(reason: unknown, fallback: string) {
  if (reason instanceof ApiError) return reason.message;
  if (!isAbortError(reason)) Sentry.captureException(reason);
  return fallback;
}
