"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body>
        <main className="hero bg-base-100 text-base-content min-h-screen">
          <div className="hero-content">
            <div className="card bg-base-200 max-w-lg">
              <div className="card-body">
                <h1 className="card-title text-error">Something went wrong</h1>
                <p>The error was recorded. Try loading this page again.</p>
                <div className="card-actions justify-end">
                  <button className="btn" onClick={reset} type="button">
                    Try again
                  </button>
                </div>
              </div>
            </div>
          </div>
        </main>
      </body>
    </html>
  );
}
