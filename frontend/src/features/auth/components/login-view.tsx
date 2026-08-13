import { OTP_LENGTH, type AuthFlow } from "../use-auth-flow";

import { AuthShell } from "./auth-shell";

export function LoginView({ flow }: { flow: AuthFlow }) {
  const { error, isSubmitting, login, notice, showAccessRequest } = flow;

  return (
    <AuthShell>
      <article className="card bg-base-200 shadow-sm">
        <div className="card-body gap-5 p-6 sm:p-8">
          <h2 className="card-title">Sign in</h2>
          <p className="text-base-content/70">Use your approved work email.</p>
          {error ? (
            <div
              className="alert alert-error alert-vertical sm:alert-horizontal gap-2 text-sm"
              role="alert"
            >
              <span>{error}</span>
            </div>
          ) : null}
          {notice ? (
            <div
              className="alert alert-info alert-vertical sm:alert-horizontal gap-2 text-sm"
              role="status"
            >
              <span>{notice}</span>
            </div>
          ) : null}
          {login.otpRequested ? (
            <form
              aria-busy={isSubmitting}
              className="space-y-5"
              onSubmit={login.verifyOtp}
            >
              <div className="space-y-1 text-sm">
                <p>
                  Check <span className="font-semibold">{login.email}</span> for
                  a sign-in code.
                </p>
                <p className="text-base-content/70">
                  Only approved accounts receive sign-in emails.
                </p>
              </div>
              <fieldset
                aria-describedby={
                  login.otpError ? "sign-in-otp-error" : undefined
                }
                aria-invalid={login.otpError ? true : undefined}
                className="fieldset"
              >
                <legend className="fieldset-legend">Six-digit code</legend>
                <label className="otp otp-lg w-full">
                  {Array.from({ length: OTP_LENGTH }, (_, index) => (
                    <span aria-hidden="true" key={index} />
                  ))}
                  <input
                    aria-describedby={
                      login.otpError ? "sign-in-otp-error" : undefined
                    }
                    aria-invalid={login.otpError ? true : undefined}
                    aria-label="Six-digit code"
                    autoComplete="one-time-code"
                    inputMode="numeric"
                    maxLength={OTP_LENGTH}
                    onChange={(event) => login.setOtpValue(event.target.value)}
                    pattern={`\\d{${OTP_LENGTH}}`}
                    required
                    type="text"
                    value={login.otpCode.trim()}
                  />
                </label>
                {login.otpError ? (
                  <p className="text-error mt-1 text-sm" id="sign-in-otp-error">
                    {login.otpError}
                  </p>
                ) : null}
              </fieldset>
              <button
                className="btn btn-link self-start px-0"
                disabled={isSubmitting || login.resendSecondsRemaining > 0}
                onClick={login.resendOtp}
                type="button"
              >
                {login.resendSecondsRemaining > 0
                  ? `Resend available in ${login.resendSecondsRemaining} seconds`
                  : "Resend code"}
              </button>
              <div className="space-y-2">
                <button
                  className="btn btn-primary btn-block"
                  disabled={isSubmitting}
                  type="submit"
                >
                  Verify code
                </button>
                <button
                  className="btn btn-link self-start px-0"
                  onClick={login.showEmailEntry}
                  type="button"
                >
                  Use another email
                </button>
              </div>
            </form>
          ) : (
            <form
              aria-busy={isSubmitting}
              className="space-y-5"
              onSubmit={login.requestOtp}
            >
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
              <div className="space-y-2">
                <button
                  className="btn btn-primary btn-block"
                  disabled={isSubmitting}
                  type="submit"
                >
                  {isSubmitting ? "Sending code…" : "Send code"}
                </button>
                <button
                  className="btn btn-link self-start px-0"
                  onClick={showAccessRequest}
                  type="button"
                >
                  Request access
                </button>
              </div>
            </form>
          )}
        </div>
      </article>
    </AuthShell>
  );
}
