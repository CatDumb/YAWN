"use client";

import {
  BadgeCheck,
  Building2,
  CalendarDays,
  ChartNoAxesCombined,
  LayoutDashboard,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  ShieldCheck,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { apiFetch } from "../../lib/api";
import {
  formatMessage,
  languageFromDocument,
  messagesFor,
  type Language,
} from "../../lib/i18n";
import { currentUser, logout, responseDetail } from "../auth/api";
import type { CurrentUser } from "../auth/contracts";

const navigationStorageKey = "yawn.navigation-collapsed";
const navigationChangeEvent = "yawn:navigation-change";
const collapsedTooltipClass = [
  "tooltip",
  "tooltip-right",
  "max-lg:before:hidden",
  "max-lg:after:hidden",
].join(" ");

type NavigationItem = {
  href: string;
  icon: LucideIcon;
  label: string;
};

function isCurrentRoute(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function navigationSnapshot() {
  if (typeof window === "undefined") return false;
  return (
    document.documentElement.dataset.navigation === "collapsed" ||
    localStorage.getItem(navigationStorageKey) === "true"
  );
}

function subscribeToNavigation(callback: () => void) {
  window.addEventListener(navigationChangeEvent, callback);
  return () => window.removeEventListener(navigationChangeEvent, callback);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [language, setLanguage] = useState<Language>("en");
  const [approvalCount, setApprovalCount] = useState(0);
  const navigationToggleRef = useRef<HTMLInputElement>(null);
  const accountMenuRef = useRef<HTMLDetailsElement>(null);
  const isCollapsed = useSyncExternalStore(
    subscribeToNavigation,
    navigationSnapshot,
    () => false,
  );
  const copy = messagesFor(language);
  const routes: NavigationItem[] = [
    { href: "/dashboard", icon: LayoutDashboard, label: copy.shell.dashboard },
    {
      href: "/work-in-office",
      icon: Building2,
      label: copy.shell.workInOffice,
    },
    { href: "/planner", icon: CalendarDays, label: copy.shell.planner },
    { href: "/reports", icon: ChartNoAxesCombined, label: copy.shell.reports },
  ];

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
  useEffect(() => {
    if (navigationToggleRef.current)
      navigationToggleRef.current.checked = false;
    accountMenuRef.current?.removeAttribute("open");
  }, [pathname]);

  function toggleNavigation() {
    const collapsed = !isCollapsed;
    localStorage.setItem(navigationStorageKey, String(collapsed));
    document.documentElement.dataset.navigation = collapsed
      ? "collapsed"
      : "expanded";
    window.dispatchEvent(new Event(navigationChangeEvent));
  }

  function closeTransientNavigation() {
    if (navigationToggleRef.current)
      navigationToggleRef.current.checked = false;
    accountMenuRef.current?.removeAttribute("open");
  }

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
  const accountMenuLabel = formatMessage(copy.shell.accountMenuLabel, {
    name: fullName,
  });

  const renderNavigationItem = (
    item: NavigationItem,
    badge?: React.ReactNode,
    accessibleLabel = item.label,
  ) => {
    const active = isCurrentRoute(pathname, item.href);
    const Icon = item.icon;
    return (
      <li
        className={isCollapsed ? collapsedTooltipClass : undefined}
        data-tip={isCollapsed ? item.label : undefined}
        key={item.href}
      >
        <Link
          aria-current={active ? "page" : undefined}
          aria-label={accessibleLabel}
          className={`relative flex items-center gap-3 ${
            active ? "menu-active" : ""
          } ${isCollapsed ? "lg:justify-center" : ""}`}
          href={item.href}
          onClick={closeTransientNavigation}
        >
          <Icon aria-hidden="true" size={20} strokeWidth={2} />
          <span
            className={`app-navigation-expanded-only min-w-0 truncate transition-opacity duration-150 ${
              isCollapsed ? "lg:sr-only" : ""
            }`}
          >
            {item.label}
          </span>
          {badge}
        </Link>
      </li>
    );
  };

  return (
    <div className="drawer lg:drawer-open">
      <input
        className="drawer-toggle"
        id="app-navigation"
        ref={navigationToggleRef}
        type="checkbox"
      />
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
      <div className="drawer-side is-drawer-close:overflow-visible">
        <label
          aria-label={copy.shell.closeNavigation}
          className="drawer-overlay"
          htmlFor="app-navigation"
        />
        <aside
          className={`app-navigation-rail bg-base-200 text-base-content flex min-h-full w-72 flex-col overflow-visible p-4 transition-all duration-200 ease-out ${
            isCollapsed ? "lg:w-20 lg:p-2" : "lg:w-72 lg:p-4"
          }`}
        >
          <div
            className={`mb-6 flex items-center ${
              isCollapsed ? "lg:justify-center" : "justify-between"
            }`}
          >
            <Link
              aria-label="YAWN"
              className={`app-navigation-expanded-only px-3 text-lg font-bold transition-opacity duration-150 ${
                isCollapsed ? "lg:sr-only" : ""
              }`}
              href="/dashboard"
              onClick={closeTransientNavigation}
            >
              YAWN
            </Link>
            <button
              aria-controls="app-primary-navigation"
              aria-expanded={!isCollapsed}
              aria-label={
                isCollapsed
                  ? copy.shell.expandNavigation
                  : copy.shell.collapseNavigation
              }
              className="btn btn-ghost btn-square hidden lg:inline-flex"
              onClick={toggleNavigation}
              type="button"
            >
              {isCollapsed ? (
                <PanelLeftOpen aria-hidden="true" size={20} />
              ) : (
                <PanelLeftClose aria-hidden="true" size={20} />
              )}
            </button>
          </div>
          <nav
            aria-label={copy.shell.primaryNavigation}
            className="flex-1"
            id="app-primary-navigation"
          >
            <ul className="menu w-full gap-1">
              {routes.map((item) => renderNavigationItem(item))}
              {canApprove
                ? renderNavigationItem(
                    {
                      href: "/approvals",
                      icon: BadgeCheck,
                      label: copy.shell.approvals,
                    },
                    approvalCount ? (
                      <span
                        aria-label={formatMessage(
                          copy.shell.approvalPendingLabel,
                          {
                            count: approvalCount,
                          },
                        )}
                        className={`badge badge-primary badge-sm ${
                          isCollapsed
                            ? "lg:badge-xs absolute -top-1 -right-1"
                            : "ml-auto"
                        }`}
                      >
                        {approvalCount > 99 ? "99+" : approvalCount}
                      </span>
                    ) : undefined,
                    formatMessage(copy.shell.approvalPendingLabel, {
                      count: approvalCount,
                    }),
                  )
                : null}
              {canAdmin
                ? renderNavigationItem({
                    href: "/admin/",
                    icon: ShieldCheck,
                    label: copy.shell.administration,
                  })
                : null}
              {renderNavigationItem({
                href: "/settings",
                icon: Settings,
                label: copy.shell.settings,
              })}
            </ul>
          </nav>
          <div className="border-base-300 border-t pt-4">
            <details
              className={`dropdown dropdown-top w-full ${
                isCollapsed ? collapsedTooltipClass : ""
              }`}
              data-tip={isCollapsed ? accountMenuLabel : undefined}
              ref={accountMenuRef}
            >
              <summary
                aria-label={accountMenuLabel}
                className={`btn btn-ghost flex h-auto min-h-12 w-full list-none items-center gap-3 px-3 py-2 text-left ${
                  isCollapsed ? "lg:justify-center lg:px-0" : ""
                }`}
                role="button"
              >
                <div aria-hidden="true" className="avatar avatar-placeholder">
                  <div className="bg-primary text-primary-content w-10 rounded-full">
                    <span>{initials}</span>
                  </div>
                </div>
                <div
                  className={`app-navigation-expanded-only min-w-0 transition-opacity duration-150 ${
                    isCollapsed ? "lg:sr-only" : ""
                  }`}
                >
                  <p className="truncate font-semibold">{fullName}</p>
                  <p className="text-base-content/70 truncate text-sm">
                    {user.email}
                  </p>
                  <p className="text-base-content/70 truncate text-sm">
                    {membership?.role} · {membership?.company}
                  </p>
                </div>
              </summary>
              <ul className="menu dropdown-content bg-base-100 rounded-box z-50 mt-2 w-56 p-2 shadow">
                <li>
                  <Link href="/profile" onClick={closeTransientNavigation}>
                    <UserRound aria-hidden="true" size={18} />
                    {copy.shell.profile}
                  </Link>
                </li>
                <li>
                  <button
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
                    <LogOut aria-hidden="true" size={18} />
                    {copy.shell.logOut}
                  </button>
                </li>
              </ul>
            </details>
          </div>
        </aside>
      </div>
    </div>
  );
}
