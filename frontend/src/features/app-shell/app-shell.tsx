"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { currentUser, logout, responseDetail } from "../auth/api";
import type { CurrentUser } from "../auth/contracts";
import {
  formatMessage,
  languageFromDocument,
  messagesFor,
  type Language,
} from "../../lib/i18n";
import { apiFetch } from "../../lib/api";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [language, setLanguage] = useState<Language>("en");
  const [approvalCount, setApprovalCount] = useState(0);
  const copy = messagesFor(language);
  const routes = [
    [copy.shell.dashboard, "/dashboard"],
    [copy.shell.workInOffice, "/work-in-office"],
    [copy.shell.planner, "/planner"],
    [copy.shell.reports, "/reports"],
  ] as const;

  useEffect(() => {
    void currentUser()
      .then(async ({ response, user: restored }) => {
        if (restored) setUser(restored);
        else if (response.status === 401 || response.status === 403)
          router.replace("/");
        else setError(await responseDetail(response, copy.shell.sessionError));
      })
      .catch(() => setError(copy.shell.serviceError));
  }, [copy.shell.serviceError, copy.shell.sessionError, router]);
  useEffect(() => {
    const syncLanguage = () => setLanguage(languageFromDocument());
    syncLanguage();
    window.addEventListener("yawn:preferences", syncLanguage);
    return () => window.removeEventListener("yawn:preferences", syncLanguage);
  }, []);
  useEffect(() => {
    const hasApprovalRole = user?.memberships.some(
      (membership) =>
        membership.role === "manager" || membership.role === "hr_admin",
    );
    if (!hasApprovalRole) return;
    const refresh = () => {
      void apiFetch("/api/v1/approvals/count/")
        .then(async (response) => {
          if (!response.ok) return;
          const body = (await response.json()) as { count?: number };
          setApprovalCount(body.count ?? 0);
        })
        .catch(() => setApprovalCount(0));
    };
    refresh();
    window.addEventListener("focus", refresh);
    window.addEventListener("yawn:approvals", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      window.removeEventListener("yawn:approvals", refresh);
    };
  }, [user]);

  if (error) {
    return (
      <main className="min-h-screen p-6">
        <div className="alert alert-error" role="alert">
          <span>{error}</span>
        </div>
      </main>
    );
  }
  if (!user) {
    return (
      <main className="min-h-screen p-6" aria-live="polite">
        <span
          className="loading loading-spinner"
          aria-label={copy.shell.restoringSession}
        />
      </main>
    );
  }
  const membership = user.memberships[0];
  const canApprove =
    membership?.role === "manager" || membership?.role === "hr_admin";
  const canAdmin = membership?.role === "hr_admin";
  const fullName =
    [user.first_name, user.last_name].filter(Boolean).join(" ") || user.email;
  const initials = fullName
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="drawer lg:drawer-open">
      <input className="drawer-toggle" id="app-navigation" type="checkbox" />
      <div className="drawer-content bg-base-100 min-h-screen">
        <div className="navbar bg-base-200 px-4 lg:hidden">
          <div className="navbar-start">
            <label
              aria-label={copy.shell.openNavigation}
              className="btn btn-ghost drawer-button"
              htmlFor="app-navigation"
            >
              {copy.shell.openNavigation}
            </label>
          </div>
          <div className="navbar-center font-bold">YAWN</div>
        </div>
        {children}
      </div>
      <div className="drawer-side">
        <label
          aria-label={copy.shell.closeNavigation}
          className="drawer-overlay"
          htmlFor="app-navigation"
        />
        <aside className="bg-base-200 text-base-content flex min-h-full w-72 flex-col p-4">
          <p className="mb-6 px-3 text-lg font-bold">YAWN</p>
          <nav aria-label={copy.shell.primaryNavigation} className="flex-1">
            <ul className="menu w-full gap-1">
              {routes.map(([label, href]) => (
                <li key={href}>
                  <Link href={href}>{label}</Link>
                </li>
              ))}
              {canApprove ? (
                <li>
                  <Link
                    aria-label={formatMessage(copy.shell.approvalPendingLabel, {
                      count: approvalCount,
                    })}
                    href="/approvals"
                  >
                    {copy.shell.approvals}
                    {approvalCount ? (
                      <span className="badge badge-primary badge-sm">
                        {approvalCount > 99 ? "99+" : approvalCount}
                      </span>
                    ) : null}
                  </Link>
                </li>
              ) : null}
              {canAdmin ? (
                <li>
                  <a href="/admin/">{copy.shell.administration}</a>
                </li>
              ) : null}
              <li>
                <Link href="/settings">{copy.shell.settings}</Link>
              </li>
            </ul>
          </nav>
          <div className="border-base-300 border-t pt-4">
            <div className="flex items-center gap-3 px-3 py-2">
              <div aria-label={fullName} className="avatar avatar-placeholder">
                <div className="bg-primary text-primary-content w-10 rounded-full">
                  <span>{initials}</span>
                </div>
              </div>
              <div className="min-w-0">
                <p className="truncate font-semibold">{fullName}</p>
                <p className="text-base-content/70 truncate text-sm">
                  {user.email}
                </p>
                <p className="text-base-content/70 truncate text-sm">
                  {membership?.role} · {membership?.company}
                </p>
              </div>
            </div>
            <div className="mt-2 flex gap-1">
              <Link className="btn btn-ghost btn-sm" href="/profile">
                {copy.shell.profile}
              </Link>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() =>
                  void logout()
                    .then(async (response) => {
                      if (
                        response.ok ||
                        response.status === 401 ||
                        response.status === 403
                      )
                        router.replace("/");
                      else
                        setError(
                          await responseDetail(
                            response,
                            copy.shell.logoutError,
                          ),
                        );
                    })
                    .catch(() => setError(copy.shell.serviceError))
                }
                type="button"
              >
                {copy.shell.logOut}
              </button>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
