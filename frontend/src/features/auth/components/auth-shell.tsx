import type { ReactNode } from "react";

export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <main className="bg-base-100 text-base-content min-h-screen px-4 py-10 sm:px-8">
      <section className="mx-auto w-full max-w-lg">
        <div className="mb-8 text-center">
          <p className="text-primary text-sm font-bold tracking-widest uppercase">
            YAWN
          </p>
          <p className="text-base-content/70 mt-1 text-sm">
            Hybrid work, clearly logged.
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
