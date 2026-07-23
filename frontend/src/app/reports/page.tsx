"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { AppShell } from "../../features/app-shell/app-shell";
import { apiFetch } from "../../lib/api";
import {
  formatMessage,
  languageFromDocument,
  messagesFor,
} from "../../lib/i18n";

type Report = {
  approved_days: string;
  expected_fraction_sum: string;
  expected_display: string;
  ratio_display: string;
  balance: string;
  percentage: string | null;
  pending_count: number;
  pending_assignment_count: number;
  period_state: string;
  revision: number | null;
  start_date: string;
  end_date: string;
  ledger: Array<{
    date: string;
    eligible: boolean;
    reason: string | null;
    assignment_status: string;
    rule_version: number | null;
    expected_fraction: string;
    approval_credit: string;
    review_state: string | null;
    location_choice: string | null;
  }>;
};

function visualProgress(percentage: string | null) {
  return percentage === null
    ? 0
    : Math.min(100, Math.max(0, Number(percentage)));
}

type ReportsCopy = ReturnType<typeof messagesFor>["reports"];

function assignmentLabel(value: string, copy: ReportsCopy) {
  if (value === "benched") return copy.assignmentBenched;
  if (value === "same_base") return copy.assignmentSameBase;
  if (value === "different_base") return copy.assignmentDifferentBase;
  return value;
}

function reviewLabel(value: string | null, copy: ReportsCopy) {
  if (value === null) return copy.noRecord;
  if (value === "draft") return copy.reviewDraft;
  if (value === "pending") return copy.reviewPending;
  if (value === "pending_assignment") return copy.reviewPendingAssignment;
  if (value === "approved") return copy.reviewApproved;
  if (value === "rejected") return copy.reviewRejected;
  if (value === "not_required") return copy.reviewNotRequired;
  if (value === "expired_pending") return copy.reviewExpiredPending;
  return value;
}

function periodStateLabel(value: string, copy: ReportsCopy) {
  if (value === "upcoming") return copy.periodUpcoming;
  if (value === "active") return copy.periodActive;
  if (value === "reconciliation") return copy.periodReconciliation;
  if (value === "final") return copy.periodFinal;
  return value;
}

export default function ReportsPage() {
  const language = languageFromDocument();
  const copy = messagesFor(language).reports;
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const loadedInitial = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const query = start && end ? `?start_date=${start}&end_date=${end}` : "";
    const response = await apiFetch(`/api/v1/reports/${query}`);
    if (!response.ok) {
      setError(
        ((await response.json()) as { detail?: string }).detail ??
          copy.calculateFailed,
      );
      setLoading(false);
      return;
    }
    const data = (await response.json()) as Report;
    setReport(data);
    setStart(data.start_date);
    setEnd(data.end_date);
    setLoading(false);
  }, [copy.calculateFailed, end, start]);

  async function exportCsv() {
    if (!start || !end) return;
    setExporting(true);
    setError(null);
    const language = document.documentElement.lang || "en";
    try {
      const response = await apiFetch(
        `/api/v1/reports/csv/?start_date=${start}&end_date=${end}&language=${language}`,
      );
      if (!response.ok) throw new Error(copy.exportFailed);
      const href = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = href;
      link.download = "work-in-office-report.csv";
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(href), 0);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : copy.exportFailed);
    } finally {
      setExporting(false);
    }
  }

  useEffect(() => {
    if (loadedInitial.current) return;
    loadedInitial.current = true;
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  return (
    <AppShell>
      <main className="min-h-screen px-4 py-8 sm:px-8">
        <section className="mx-auto max-w-6xl space-y-6">
          <header>
            <p className="text-primary font-semibold">{copy.eyebrow}</p>
            <h1 className="mt-1 text-3xl font-bold tracking-tight">
              {copy.title}
            </h1>
            <p className="text-base-content/70 mt-2">{copy.intro}</p>
          </header>

          <section className="card bg-base-200 shadow-sm">
            <div className="card-body">
              <fieldset className="grid gap-3 sm:grid-cols-3">
                <label className="fieldset">
                  <span className="fieldset-legend">{copy.from}</span>
                  <input
                    className="input w-full"
                    onChange={(event) => setStart(event.target.value)}
                    type="date"
                    value={start}
                  />
                </label>
                <label className="fieldset">
                  <span className="fieldset-legend">{copy.to}</span>
                  <input
                    className="input w-full"
                    onChange={(event) => setEnd(event.target.value)}
                    type="date"
                    value={end}
                  />
                </label>
                <div className="flex flex-wrap gap-2 self-end">
                  <button
                    className="btn btn-primary"
                    disabled={loading || !start || !end}
                    onClick={() => void load()}
                    type="button"
                  >
                    {loading ? copy.calculating : copy.calculate}
                  </button>
                  <button
                    className="btn"
                    disabled={!report || exporting}
                    onClick={() => void exportCsv()}
                    type="button"
                  >
                    {exporting ? copy.exporting : copy.exportCsv}
                  </button>
                </div>
              </fieldset>
              {error ? (
                <div className="alert alert-error mt-4" role="alert">
                  <span>{error}</span>
                </div>
              ) : null}
            </div>
          </section>

          {report ? (
            <>
              <section className="card bg-base-200 shadow-sm">
                <div className="card-body">
                  <h2 className="card-title">{report.ratio_display}</h2>
                  <p>
                    {formatMessage(copy.summaryLine, {
                      approved: report.approved_days,
                      expected: report.expected_display,
                      pending: report.pending_count,
                      pendingAssignment: report.pending_assignment_count,
                    })}
                  </p>
                  <p className="text-base-content/70 text-sm">
                    {formatMessage(copy.detailsLine, {
                      balance: report.balance,
                    })}
                  </p>
                  <progress
                    aria-label={formatMessage(copy.visualProgressLabel, {
                      ratio: report.ratio_display,
                    })}
                    className="progress progress-primary w-full"
                    max="100"
                    value={visualProgress(report.percentage)}
                  />
                  <p className="text-base-content/70 text-sm">
                    {periodStateLabel(report.period_state, copy)};{" "}
                    {report.revision
                      ? formatMessage(copy.finalizedRevision, {
                          revision: report.revision,
                        })
                      : copy.liveCalculation}
                  </p>
                </div>
              </section>
              <section
                className="overflow-x-auto"
                aria-label={copy.ledgerLabel}
              >
                <table className="table">
                  <thead>
                    <tr>
                      <th>{copy.date}</th>
                      <th>{copy.eligibility}</th>
                      <th>{copy.assignment}</th>
                      <th>{copy.rule}</th>
                      <th>{copy.expected}</th>
                      <th>{copy.wioReview}</th>
                      <th>{copy.approved}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.ledger.map((row) => (
                      <tr key={row.date}>
                        <td>{row.date}</td>
                        <td>{row.eligible ? copy.eligible : row.reason}</td>
                        <td>{assignmentLabel(row.assignment_status, copy)}</td>
                        <td>{row.rule_version ?? copy.noRule}</td>
                        <td>{row.expected_fraction}</td>
                        <td>{reviewLabel(row.review_state, copy)}</td>
                        <td>{row.approval_credit}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            </>
          ) : (
            <div className="alert alert-info alert-soft" role="status">
              <span>{copy.loadingInitial}</span>
            </div>
          )}
        </section>
      </main>
    </AppShell>
  );
}
