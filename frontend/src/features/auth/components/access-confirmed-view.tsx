import { GENERIC_SIGNUP_MESSAGE, type AuthFlow } from "../use-auth-flow";

import { AuthShell } from "./auth-shell";

export function AccessConfirmedView({ flow }: { flow: AuthFlow }) {
  return (
    <AuthShell>
      <article className="card bg-base-200 shadow-sm">
        <div className="card-body gap-5 p-6 sm:p-8">
          <h2 className="card-title">Request received</h2>
          <div
            className="alert alert-success alert-vertical sm:alert-horizontal gap-2 text-sm"
            role="status"
          >
            <span>{GENERIC_SIGNUP_MESSAGE}</span>
          </div>
          <p className="text-base-content/70">
            HR/admin will email sign-in instructions if your request is
            approved.
          </p>
          <div className="card-actions justify-end">
            <button
              className="btn btn-primary w-full sm:w-auto"
              onClick={flow.showLogin}
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
