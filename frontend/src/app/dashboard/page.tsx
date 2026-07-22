"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { currentUser, logout, responseDetail } from "../../features/auth/api";
import type { CurrentUser } from "../../features/auth/contracts";
import { AuthShell } from "../../features/auth/components/auth-shell";
import { isInvalidSessionStatus } from "../../features/auth/use-auth-flow";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const result = await currentUser();
        if (result.user) {
          setUser(result.user);
          return;
        }
        if (isInvalidSessionStatus(result.response.status)) {
          router.replace("/");
          return;
        }
        setError(
          await responseDetail(
            result.response,
            "Unable to restore session. Try again.",
          ),
        );
      } catch {
        setError("Unable to reach service. Try again.");
      }
    })();
  }, [router]);

  async function handleLogout() {
    setError(null);
    setIsSubmitting(true);
    try {
      const response = await logout();
      if (response.ok || isInvalidSessionStatus(response.status)) {
        setUser(null);
        router.replace("/");
        return;
      }
      setError(await responseDetail(response, "Unable to log out. Try again."));
    } catch {
      setError("Unable to reach service. Try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthShell>
      <article className="card bg-base-200">
        <div className="card-body">
          <h2 className="card-title">You are signed in</h2>
          {user ? (
            <>
              <p>{user.email}</p>
              <div className="divider">Memberships</div>
              <ul className="list">
                {user.memberships.map((membership) => (
                  <li
                    key={`${membership.company_id}-${membership.role}`}
                    className="list-row"
                  >
                    <div>
                      <p className="font-semibold">{membership.company}</p>
                      <p className="text-base-content/70 text-sm">
                        {membership.role}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          <p className="text-base-content/70 text-sm">
            Phase 2 identity placeholder.
          </p>
          {error ? (
            <div className="alert alert-error" role="alert">
              <span>{error}</span>
            </div>
          ) : null}
          <div className="card-actions justify-end">
            <button
              className="btn"
              disabled={isSubmitting}
              onClick={handleLogout}
              type="button"
            >
              Log out
            </button>
          </div>
        </div>
      </article>
    </AuthShell>
  );
}
