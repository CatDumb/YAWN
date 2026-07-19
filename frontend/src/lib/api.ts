const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);

let csrfToken: string | undefined;
let csrfTokenRequest: Promise<string | undefined> | undefined;

function getCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  return document.cookie
    .split(";")
    .map((cookie) => cookie.trim())
    .find((cookie) => cookie.startsWith(`${name}=`))
    ?.split("=")[1];
}

async function getCsrfToken(): Promise<string | undefined> {
  const cookieToken = getCookie("csrftoken");
  if (cookieToken) return decodeURIComponent(cookieToken);
  if (csrfToken) return csrfToken;
  if (typeof window === "undefined") return undefined;

  csrfTokenRequest ??= fetch(`${API_URL}/api/v1/auth/csrf/`, {
    headers: { Accept: "application/json" },
    credentials: "include",
  })
    .then(async (response) => {
      if (!response.ok) throw new Error("Unable to obtain CSRF token.");
      const data: unknown = await response.json();
      csrfToken =
        typeof data === "object" &&
        data !== null &&
        "csrfToken" in data &&
        typeof data.csrfToken === "string"
          ? data.csrfToken
          : undefined;
      return csrfToken;
    })
    .finally(() => {
      csrfTokenRequest = undefined;
    });

  return csrfTokenRequest;
}

export async function apiFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (
    init.body &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  )
    headers.set("Content-Type", "application/json");

  if (!SAFE_METHODS.has((init.method ?? "GET").toUpperCase())) {
    const csrfToken = await getCsrfToken();
    if (csrfToken) headers.set("X-CSRFToken", csrfToken);
  }

  return fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
}
