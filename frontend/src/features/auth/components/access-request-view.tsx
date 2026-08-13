import type { AuthFlow } from "../use-auth-flow";

import { AuthShell } from "./auth-shell";

export function AccessRequestView({ flow }: { flow: AuthFlow }) {
  const { accessRequest, error, isSubmitting, showLogin } = flow;

  return (
    <AuthShell>
      <article className="card bg-base-200 shadow-sm">
        <div className="card-body gap-5 p-6 sm:p-8">
          <h2 className="card-title">Request access</h2>
          <p className="text-base-content/70">
            HR/admin reviews access requests. If approved, we’ll email you
            sign-in instructions.
          </p>
          {error ? (
            <div
              className="alert alert-error alert-vertical sm:alert-horizontal gap-2 text-sm"
              role="alert"
            >
              <span>{error}</span>
            </div>
          ) : null}
          <form
            aria-busy={isSubmitting}
            className="space-y-5"
            onSubmit={accessRequest.submit}
          >
            <fieldset className="fieldset">
              <legend className="fieldset-legend">First name</legend>
              <input
                aria-label="First name"
                className="input w-full"
                autoComplete="given-name"
                maxLength={150}
                name="first_name"
                pattern=".*\S.*"
                required
                title="Enter a name with at least one non-space character."
              />
            </fieldset>
            <fieldset className="fieldset">
              <legend className="fieldset-legend">Last name</legend>
              <input
                aria-label="Last name"
                className="input w-full"
                autoComplete="family-name"
                maxLength={150}
                name="last_name"
                pattern=".*\S.*"
                required
                title="Enter a name with at least one non-space character."
              />
            </fieldset>
            <fieldset className="fieldset">
              <legend className="fieldset-legend">Email</legend>
              <input
                aria-label="Email"
                className="input w-full"
                inputMode="email"
                name="email"
                placeholder="name@company.com"
                required
                type="email"
              />
            </fieldset>
            <div className="card-actions flex-col items-stretch gap-1 pt-1">
              <button
                className="btn btn-primary btn-block"
                disabled={isSubmitting}
                type="submit"
              >
                {isSubmitting ? (
                  <>
                    <span
                      aria-hidden="true"
                      className="loading loading-spinner loading-xs"
                    />
                    Sending request…
                  </>
                ) : (
                  "Request access"
                )}
              </button>
              <button
                className="btn btn-link self-start px-0"
                onClick={showLogin}
                type="button"
              >
                Already approved? Sign in
              </button>
            </div>
          </form>
        </div>
      </article>
    </AuthShell>
  );
}
