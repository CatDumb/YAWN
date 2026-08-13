import { afterEach, describe, expect, it, vi } from "vitest";

const captureRequestError = vi.fn();
const init = vi.fn();

vi.mock("@sentry/nextjs", () => ({ captureRequestError, init }));

describe("instrumentation", () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllEnvs();
  });

  it("loads Sentry config for Node runtime", async () => {
    vi.resetModules();
    vi.stubEnv("NEXT_RUNTIME", "nodejs");

    const { onRequestError, register } = await import("./instrumentation");
    await register();

    expect(onRequestError).toBe(captureRequestError);
    expect(init).toHaveBeenCalledOnce();
  });
});
