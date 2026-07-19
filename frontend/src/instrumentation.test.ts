import { afterEach, describe, expect, it, vi } from "vitest";

const captureRequestError = vi.fn();
const init = vi.fn();

vi.mock("@sentry/nextjs", () => ({ captureRequestError, init }));

describe("instrumentation", () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllEnvs();
  });

  it.each(["nodejs", "edge"])(
    "loads Sentry config for %s runtime",
    async (runtime) => {
      vi.resetModules();
      vi.stubEnv("NEXT_RUNTIME", runtime);

      const { onRequestError, register } = await import("./instrumentation");
      await register();

      expect(onRequestError).toBe(captureRequestError);
      expect(init).toHaveBeenCalledOnce();
    },
  );
});
