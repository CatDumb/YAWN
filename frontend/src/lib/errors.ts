import * as Sentry from "@sentry/nextjs";

export class ApiError<TField extends string = string> extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly fieldErrors: readonly TField[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function responseProblem<TField extends string>(
  response: Response,
  fallback: string,
  allowedFields: readonly TField[] = [],
) {
  if (response.status < 400 || response.status >= 500) {
    return { detail: fallback, fieldErrors: [] as TField[] };
  }

  try {
    const data: unknown = await response.json();
    const fieldErrors =
      typeof data === "object" && data !== null
        ? allowedFields.filter((field) => {
            const value = (data as Record<string, unknown>)[field];
            return (
              (typeof value === "string" && Boolean(value.trim())) ||
              (Array.isArray(value) && value.length > 0)
            );
          })
        : [];
    if (
      fieldErrors.length === 0 &&
      typeof data === "object" &&
      data !== null &&
      "detail" in data &&
      typeof data.detail === "string" &&
      data.detail.trim()
    )
      return { detail: data.detail, fieldErrors };
    return { detail: fallback, fieldErrors };
  } catch {
    // Malformed API responses must not become user-facing technical errors.
  }
  return { detail: fallback, fieldErrors: [] as TField[] };
}

export async function responseDetail(response: Response, fallback: string) {
  return (await responseProblem(response, fallback)).detail;
}

export async function apiErrorFromResponse<TField extends string = never>(
  response: Response,
  fallback: string,
  allowedFields: readonly TField[] = [],
) {
  const problem = await responseProblem(response, fallback, allowedFields);
  return new ApiError<TField>(
    problem.detail,
    response.status,
    problem.fieldErrors,
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
