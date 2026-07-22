import type { AuthFlow } from "../use-auth-flow";

import { AuthShell } from "./auth-shell";
import { FieldError } from "./field-error";

export function AccessRequestView({ flow }: { flow: AuthFlow }) {
  const { accessRequest, error, isSubmitting, showLogin } = flow;
  const firstNameError =
    accessRequest.form.formState.errors.first_name?.message;
  const lastNameError = accessRequest.form.formState.errors.last_name?.message;
  const emailError = accessRequest.form.formState.errors.email?.message;
  const hasAttemptedSubmit = accessRequest.form.formState.submitCount > 0;
  const showFirstNameError =
    hasAttemptedSubmit || Boolean(accessRequest.firstNameInput?.trim());
  const showLastNameError =
    hasAttemptedSubmit || Boolean(accessRequest.lastNameInput?.trim());
  const showEmailError =
    hasAttemptedSubmit || Boolean(accessRequest.emailInput?.trim());
  const hasFieldErrors = Boolean(firstNameError || lastNameError || emailError);

  return (
    <AuthShell>
      <article className="card bg-base-200 shadow-sm">
        <div className="card-body gap-5 p-6 sm:p-8">
          <h2 className="card-title">Request access</h2>
          <p className="text-base-content/70">
            HR/admin reviews access requests. If approved, we’ll email you
            sign-in instructions.
          </p>
          {hasAttemptedSubmit && hasFieldErrors ? (
            <div
              className="alert alert-error alert-vertical sm:alert-horizontal gap-2 text-sm"
              role="alert"
            >
              <span>Check the highlighted fields and try again.</span>
            </div>
          ) : null}
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
            noValidate
            onSubmit={accessRequest.form.handleSubmit(accessRequest.submit)}
          >
            <fieldset className="fieldset">
              <legend className="fieldset-legend">First name</legend>
              <input
                {...accessRequest.form.register("first_name")}
                aria-label="First name"
                aria-describedby={
                  firstNameError && showFirstNameError
                    ? "access-request-first-name-error"
                    : undefined
                }
                aria-invalid={
                  firstNameError && showFirstNameError ? true : undefined
                }
                className="input w-full"
                autoComplete="given-name"
                maxLength={150}
                required
              />
              <FieldError
                id="access-request-first-name-error"
                message={firstNameError}
                visible={showFirstNameError}
              />
            </fieldset>
            <fieldset className="fieldset">
              <legend className="fieldset-legend">Last name</legend>
              <input
                {...accessRequest.form.register("last_name")}
                aria-label="Last name"
                aria-describedby={
                  lastNameError && showLastNameError
                    ? "access-request-last-name-error"
                    : undefined
                }
                aria-invalid={
                  lastNameError && showLastNameError ? true : undefined
                }
                className="input w-full"
                autoComplete="family-name"
                maxLength={150}
                required
              />
              <FieldError
                id="access-request-last-name-error"
                message={lastNameError}
                visible={showLastNameError}
              />
            </fieldset>
            <fieldset className="fieldset">
              <legend className="fieldset-legend">Email</legend>
              <input
                {...accessRequest.form.register("email")}
                aria-label="Email"
                aria-describedby={
                  emailError && showEmailError
                    ? "access-request-email-error"
                    : undefined
                }
                aria-invalid={emailError && showEmailError ? true : undefined}
                className="input w-full"
                inputMode="email"
                placeholder="name@company.com"
                required
                type="email"
              />
              <FieldError
                id="access-request-email-error"
                message={emailError}
                visible={showEmailError}
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
