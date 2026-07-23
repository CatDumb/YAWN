"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "../../features/app-shell/app-shell";
import { apiFetch } from "../../lib/api";
import {
  formatMessage,
  languageFromDocument,
  messagesFor,
} from "../../lib/i18n";

type DashboardCopy = ReturnType<typeof messagesFor>["dashboard"];

type Today = {
  date: string;
  record_id: number | null;
  review_state: string | null;
  eligibility_reason: string | null;
  attention: Array<{ id: number; date: string; state: string }>;
};
type Ratio = {
  available: boolean;
  message?: string;
  approved_days: string;
  expected_display: string;
  ratio_display: string;
  balance: string;
  remaining_eligible_days: number | null;
  pending_count: number;
  pending_assignment_count: number;
  period_state: string;
  reconciliation_cutoff: string | null;
  revision: number | null;
};
type Activity = {
  records: Array<{ id: number; date: string; state: string }>;
  intentions: Array<{
    id: number;
    date: string;
    location: string;
    commitment: string;
  }>;
};
type HeatmapDay = {
  date: string;
  record_id: number | null;
  review_state: string | null;
  intention: string | null;
  ineligible_reason: string | null;
  unavailable_reason: string | null;
  action: "open" | "create" | null;
};

function formatDate(value: string) {
  const locale =
    typeof document === "undefined" ? "en" : document.documentElement.lang;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(
    new Date(`${value}T00:00:00`),
  );
}

function reviewStateLabel(value: string | null, copy: DashboardCopy) {
  if (value === "approved") return copy.stateApproved;
  if (value === "pending") return copy.statePending;
  if (value === "pending_assignment") return copy.statePendingAssignment;
  if (value === "rejected") return copy.stateRejected;
  if (value === "expired_pending") return copy.stateExpiredPending;
  if (value === "not_required") return copy.stateNotRequired;
  if (value === "draft") return copy.stateDraft;
  return value?.replaceAll("_", " ") ?? "";
}

function locationLabel(value: string, copy: DashboardCopy) {
  if (value === "office") return copy.locationOffice;
  if (value === "home") return copy.locationHome;
  return value;
}

function commitmentLabel(value: string, copy: DashboardCopy) {
  if (value === "firm") return copy.commitmentFirm;
  if (value === "flexible") return copy.commitmentFlexible;
  return value;
}

function stateLabel(day: HeatmapDay, copy: DashboardCopy) {
  if (day.ineligible_reason)
    return formatMessage(copy.ineligibleReason, {
      reason: day.ineligible_reason,
    });
  if (day.unavailable_reason) return day.unavailable_reason;
  if (day.review_state) return reviewStateLabel(day.review_state, copy);
  if (day.intention)
    return formatMessage(copy.intentionState, {
      intention: locationLabel(day.intention, copy),
    });
  return copy.emptyState;
}

function heatmapMarker(day: HeatmapDay) {
  if (day.ineligible_reason) return "X";
  if (day.review_state === "approved") return "A";
  if (day.review_state === "pending") return "P";
  if (day.review_state === "pending_assignment") return "M";
  if (day.review_state === "rejected") return "R";
  if (day.review_state === "expired_pending") return "E";
  if (day.review_state === "not_required") return "N";
  if (day.review_state === "draft") return "D";
  if (day.intention === "office") return "O";
  if (day.intention === "home") return "H";
  return "";
}

function shiftMonth(value: string, increment: number) {
  const base = value ? new Date(`${value}-01T00:00:00`) : new Date();
  base.setMonth(base.getMonth() + increment);
  return `${base.getFullYear()}-${String(base.getMonth() + 1).padStart(2, "0")}`;
}

function Module({
  children,
  error,
  loading,
  loadingLabel,
  retry,
  retryLabel,
  preserveContent = false,
}: {
  children: React.ReactNode;
  error: string | null;
  loading: boolean;
  loadingLabel: string;
  retry: () => void;
  retryLabel: string;
  preserveContent?: boolean;
}) {
  if (loading && !preserveContent)
    return <div className="skeleton h-40 w-full" aria-label={loadingLabel} />;
  if (error)
    return (
      <div className="alert alert-error" role="alert">
        <span>{error}</span>
        <button className="btn btn-sm" onClick={retry} type="button">
          {retryLabel}
        </button>
      </div>
    );
  return <div className={loading ? "opacity-60" : undefined}>{children}</div>;
}

export default function DashboardPage() {
  const language = languageFromDocument();
  const messages = messagesFor(language);
  const copy = messages.dashboard;
  const common = messages.common;
  const [today, setToday] = useState<Today | null>(null);
  const [todayError, setTodayError] = useState<string | null>(null);
  const [todayLoading, setTodayLoading] = useState(true);
  const [ratio, setRatio] = useState<Ratio | null>(null);
  const [ratioError, setRatioError] = useState<string | null>(null);
  const [ratioLoading, setRatioLoading] = useState(true);
  const [activity, setActivity] = useState<Activity | null>(null);
  const [activityError, setActivityError] = useState<string | null>(null);
  const [activityLoading, setActivityLoading] = useState(true);
  const [heatmap, setHeatmap] = useState<HeatmapDay[] | null>(null);
  const [heatmapError, setHeatmapError] = useState<string | null>(null);
  const [heatmapLoading, setHeatmapLoading] = useState(true);
  const [selectedMonth, setSelectedMonth] = useState(() =>
    new Date().toISOString().slice(0, 7),
  );
  const request = useCallback(
    async <T,>(
      path: string,
      setValue: (value: T) => void,
      setError: (value: string | null) => void,
      setLoading: (value: boolean) => void,
    ) => {
      setLoading(true);
      setError(null);
      try {
        const response = await apiFetch(path);
        const payload = (await response.json()) as T & { detail?: string };
        if (!response.ok)
          throw new Error(payload.detail ?? copy.moduleUnavailable);
        setValue(payload);
      } catch (error) {
        setError(
          error instanceof Error ? error.message : copy.moduleUnavailable,
        );
      } finally {
        setLoading(false);
      }
    },
    [copy.moduleUnavailable],
  );
  const monthQuery = selectedMonth
    ? `?year=${selectedMonth.slice(0, 4)}&month=${selectedMonth.slice(5, 7)}`
    : "";
  const loadToday = useCallback(
    () =>
      void request<Today>(
        "/api/v1/dashboard/today/",
        setToday,
        setTodayError,
        setTodayLoading,
      ),
    [request],
  );
  const loadRatio = useCallback(
    () =>
      void request<Ratio>(
        "/api/v1/dashboard/ratio/",
        setRatio,
        setRatioError,
        setRatioLoading,
      ),
    [request],
  );
  const loadActivity = useCallback(
    () =>
      void request<Activity>(
        `/api/v1/dashboard/activity/${monthQuery}`,
        setActivity,
        setActivityError,
        setActivityLoading,
      ),
    [monthQuery, request],
  );
  const loadHeatmap = useCallback(
    () =>
      void request<HeatmapDay[]>(
        `/api/v1/dashboard/heatmap/${monthQuery}`,
        setHeatmap,
        setHeatmapError,
        setHeatmapLoading,
      ),
    [monthQuery, request],
  );
  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadToday();
      loadRatio();
      loadActivity();
      loadHeatmap();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadActivity, loadHeatmap, loadRatio, loadToday]);

  const todayHref = today?.record_id
    ? `/work-in-office/${today.record_id}`
    : today?.eligibility_reason
      ? null
      : "/work-in-office/new";
  const todayAction = today?.record_id
    ? today.review_state === "draft"
      ? copy.continueDraft
      : today.review_state === "rejected"
        ? copy.fixRejectedWio
        : copy.openWio
    : copy.recordWio;

  return (
    <AppShell>
      <main className="min-h-screen px-4 py-8 sm:px-8">
        <section className="mx-auto max-w-6xl space-y-6">
          <header>
            <p className="text-primary font-semibold">{copy.eyebrow}</p>
            <h1 className="mt-1 text-3xl font-bold tracking-tight">
              {copy.title}
            </h1>
            <p className="text-base-content/70 mt-2 max-w-2xl">{copy.intro}</p>
          </header>

          <div className="grid gap-5 lg:grid-cols-2">
            <Module
              error={todayError}
              loading={todayLoading}
              loadingLabel={copy.loadingModule}
              retry={loadToday}
              retryLabel={common.retry}
            >
              <section className="card bg-base-200 shadow-sm">
                <div className="card-body">
                  <h2 className="card-title">{copy.todayTitle}</h2>
                  <p>
                    {today?.eligibility_reason
                      ? formatMessage(copy.unavailableReason, {
                          reason: today.eligibility_reason,
                        })
                      : today?.review_state
                        ? formatMessage(copy.currentState, {
                            state: reviewStateLabel(today.review_state, copy),
                          })
                        : copy.noRecordYet}
                  </p>
                  {todayHref ? (
                    <div className="card-actions">
                      <Link className="btn btn-primary" href={todayHref}>
                        {todayAction}
                      </Link>
                    </div>
                  ) : null}
                  {today?.attention.length ? (
                    <div className="alert alert-warning mt-2" role="status">
                      <span>{copy.attentionNeeded}</span>
                      <Link className="btn btn-sm" href="/work-in-office">
                        {copy.reviewWio}
                      </Link>
                    </div>
                  ) : null}
                </div>
              </section>
            </Module>
            <Module
              error={ratioError}
              loading={ratioLoading}
              loadingLabel={copy.loadingModule}
              retry={loadRatio}
              retryLabel={common.retry}
            >
              <section className="card bg-base-200 shadow-sm">
                <div className="card-body">
                  <h2 className="card-title">{copy.ratioTitle}</h2>
                  {ratio?.available ? (
                    <>
                      <p className="text-2xl font-bold">
                        {ratio.ratio_display}
                      </p>
                      <p>
                        {formatMessage(copy.ratioSummary, {
                          approved: ratio.approved_days,
                          expected: ratio.expected_display,
                        })}
                      </p>
                      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                        <div>
                          <dt className="text-base-content/70">
                            {copy.deficitOrExcess}
                          </dt>
                          <dd>{ratio.balance}</dd>
                        </div>
                        <div>
                          <dt className="text-base-content/70">
                            {copy.remainingEligibleDays}
                          </dt>
                          <dd>
                            {ratio.remaining_eligible_days ??
                              copy.policyCoverageIncomplete}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-base-content/70">
                            {copy.pendingClaims}
                          </dt>
                          <dd>{ratio.pending_count}</dd>
                        </div>
                        <div>
                          <dt className="text-base-content/70">
                            {copy.pendingAssignment}
                          </dt>
                          <dd>{ratio.pending_assignment_count}</dd>
                        </div>
                      </dl>
                      <p className="text-base-content/70 text-sm">
                        {ratio.period_state}
                        {ratio.reconciliation_cutoff
                          ? formatMessage(copy.cutoffSuffix, {
                              date: formatDate(
                                ratio.reconciliation_cutoff.slice(0, 10),
                              ),
                            })
                          : ""}
                        {ratio.revision
                          ? formatMessage(copy.revisionSuffix, {
                              revision: ratio.revision,
                            })
                          : ""}
                      </p>
                    </>
                  ) : (
                    <p>{ratio?.message}</p>
                  )}
                  <div className="card-actions">
                    <Link className="btn" href="/reports">
                      {copy.viewRatioDetails}
                    </Link>
                  </div>
                </div>
              </section>
            </Module>
          </div>

          <section className="card bg-base-200 shadow-sm">
            <div className="card-body">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <h2 className="card-title">{copy.monthlyActivity}</h2>
                  <p className="text-base-content/70 text-sm">
                    {copy.monthHelp}
                  </p>
                </div>
                <div className="join" aria-label={copy.chooseMonth}>
                  <button
                    className="btn join-item"
                    onClick={() =>
                      setSelectedMonth(shiftMonth(selectedMonth, -1))
                    }
                    type="button"
                  >
                    {copy.previous}
                  </button>
                  <input
                    aria-label={copy.dashboardMonth}
                    className="input join-item"
                    onChange={(event) => setSelectedMonth(event.target.value)}
                    type="month"
                    value={selectedMonth}
                  />
                  <button
                    className="btn join-item"
                    onClick={() =>
                      setSelectedMonth(shiftMonth(selectedMonth, 1))
                    }
                    type="button"
                  >
                    {copy.next}
                  </button>
                </div>
              </div>
              <Module
                error={heatmapError}
                loading={heatmapLoading}
                loadingLabel={copy.loadingModule}
                preserveContent={Boolean(heatmap)}
                retry={loadHeatmap}
                retryLabel={common.retry}
              >
                <div
                  className="mt-4 grid grid-cols-7 gap-1"
                  aria-label={copy.heatmapLabel}
                >
                  {heatmap?.map((day) => {
                    const label = formatMessage(copy.heatmapDayLabel, {
                      date: formatDate(day.date),
                      state: stateLabel(day, copy),
                    });
                    const content = (
                      <>
                        <span>
                          {new Date(`${day.date}T00:00:00`).getDate()}
                        </span>
                        <span aria-hidden="true" className="font-bold">
                          {heatmapMarker(day)}
                        </span>
                      </>
                    );
                    const href =
                      day.action === "open" && day.record_id
                        ? `/work-in-office/${day.record_id}`
                        : day.action === "create"
                          ? `/work-in-office/new?date=${day.date}`
                          : null;
                    return href ? (
                      <Link
                        aria-label={label}
                        className="btn btn-sm min-h-11"
                        href={href}
                        key={day.date}
                      >
                        {content}
                      </Link>
                    ) : (
                      <span
                        aria-disabled="true"
                        aria-label={label}
                        className="btn btn-sm min-h-11 cursor-default"
                        key={day.date}
                        title={stateLabel(day, copy)}
                      >
                        {content}
                      </span>
                    );
                  })}
                </div>
                <p className="text-base-content/70 mt-3 text-sm">
                  {copy.legend}
                </p>
                <p className="text-base-content/70 mt-1 text-sm">
                  {copy.nonColorHelp}
                </p>
              </Module>
            </div>
          </section>

          <Module
            error={activityError}
            loading={activityLoading}
            loadingLabel={copy.loadingModule}
            retry={loadActivity}
            retryLabel={common.retry}
          >
            <section className="grid gap-5 lg:grid-cols-2">
              <div className="card bg-base-200 shadow-sm">
                <div className="card-body">
                  <h2 className="card-title">{copy.recentRecords}</h2>
                  {activity?.records.length ? (
                    <ul className="list">
                      {activity.records.map((record) => (
                        <li className="list-row" key={record.id}>
                          <span>{formatDate(record.date)}</span>
                          <span className="badge badge-soft">
                            {reviewStateLabel(record.state, copy)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-base-content/70">
                      {copy.noRecordsThisMonth}
                    </p>
                  )}
                </div>
              </div>
              <div className="card bg-base-200 shadow-sm">
                <div className="card-body">
                  <h2 className="card-title">{copy.upcomingPlans}</h2>
                  {activity?.intentions.length ? (
                    <ul className="list">
                      {activity.intentions.map((intention) => (
                        <li className="list-row" key={`plan-${intention.id}`}>
                          <span>{formatDate(intention.date)}</span>
                          <span>
                            {formatMessage(copy.planIntention, {
                              commitment: commitmentLabel(
                                intention.commitment,
                                copy,
                              ),
                              location: locationLabel(intention.location, copy),
                            })}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-base-content/70">
                      {copy.noUpcomingIntentions}
                    </p>
                  )}
                </div>
              </div>
            </section>
          </Module>
        </section>
      </main>
    </AppShell>
  );
}
