"use client";

import { useEffect, useRef, useState } from "react";

import { AppPage } from "@/features/app-shell/app-page";
import { apiFetch } from "@/lib/api";
import { formatMessage, languageFromDocument, messagesFor } from "@/lib/i18n";

type Claim = {
  id: number;
  employee_name: string;
  employee_email: string;
  base_location_name: string | null;
  work_date: string;
  note_present: boolean;
  review_state: "pending" | "pending_assignment";
  version: number;
  submitted_at: string | null;
};

type Assignee = { id: number; name: string; email: string };
type ManagerAuditEvent = {
  id: number;
  event_type: string;
  details: Record<string, string | number | null>;
  created_at: string;
};
type ManagerAuditPage = {
  results: ManagerAuditEvent[];
  next_page: number | null;
};
type Role = "employee" | "manager" | "hr_admin" | null;
type ApprovalsCopy = ReturnType<typeof messagesFor>["approvals"];
type WorkInOfficeCopy = ReturnType<typeof messagesFor>["workInOffice"];
type ApprovalCount = { count?: number; oldest_submitted_at?: string | null };

const PAGE_SIZE = 50;
const DAY_IN_MS = 24 * 60 * 60 * 1000;

function oldestSubmittedTime(claims: Claim[]): number | null {
  let oldest: number | null = null;
  for (const claim of claims) {
    if (!claim.submitted_at) continue;
    const time = Date.parse(claim.submitted_at);
    if (!Number.isFinite(time)) continue;
    if (oldest === null || time < oldest) oldest = time;
  }
  return oldest;
}

function oldestPendingAgeLabel(oldest: number, copy: ApprovalsCopy) {
  const days = Math.max(0, Math.floor((Date.now() - oldest) / DAY_IN_MS));
  if (days === 0) return copy.oldestPendingToday;
  if (days === 1) return copy.oldestPendingOneDay;
  return formatMessage(copy.oldestPendingManyDays, { days });
}

function localizedDateTime(value: string, language: "en" | "vi") {
  return new Intl.DateTimeFormat(language === "vi" ? "vi-VN" : "en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function auditActionLabel(eventType: string, copy: ApprovalsCopy) {
  const labels: Record<string, string> = {
    "work_logs.record_submitted": copy.auditSubmitted,
    "work_logs.record_rejected": copy.auditRejected,
    "work_logs.record_resubmitted": copy.auditResubmitted,
    "work_logs.record_approved": copy.auditApproved,
    "work_logs.record_pending_assignment_resolved":
      copy.auditAssignmentResolved,
    "work_logs.record_pending_reassigned": copy.auditReassigned,
  };
  return labels[eventType] ?? copy.auditUnknown;
}

function auditStateLabel(value: string | number, copy: WorkInOfficeCopy) {
  const labels: Record<string, string> = {
    pending: copy.statePending,
    pending_assignment: copy.statePendingAssignment,
    approved: copy.stateApproved,
    rejected: copy.stateRejected,
  };
  return labels[String(value)] ?? String(value);
}

function QueuePagination({
  copy,
  hasNext,
  onNext,
  onPrevious,
  page,
}: {
  copy: ApprovalsCopy;
  hasNext: boolean;
  onNext: () => void;
  onPrevious: () => void;
  page: number;
}) {
  if (page === 1 && !hasNext) return null;
  return (
    <nav
      aria-label={copy.paginationLabel}
      className="flex flex-wrap items-center justify-between gap-3"
    >
      <span className="text-base-content/60 text-sm">
        {formatMessage(copy.pageLabel, { page })}
      </span>
      <div className="join">
        <button
          className="btn btn-sm join-item"
          disabled={page === 1}
          onClick={onPrevious}
          type="button"
        >
          {copy.previousPage}
        </button>
        <button
          className="btn btn-sm join-item"
          disabled={!hasNext}
          onClick={onNext}
          type="button"
        >
          {copy.nextPage}
        </button>
      </div>
    </nav>
  );
}

function ClaimSummary({
  claim,
  copy,
  language,
}: {
  claim: Claim;
  copy: ApprovalsCopy;
  language: "en" | "vi";
}) {
  return (
    <dl className="grid gap-1 text-sm sm:grid-cols-2 lg:grid-cols-5">
      <div>
        <dt className="text-base-content/60">{copy.employee}</dt>
        <dd className="font-medium">{claim.employee_name}</dd>
        <dd className="text-base-content/60 text-xs">{claim.employee_email}</dd>
      </div>
      <div>
        <dt className="text-base-content/60">{copy.baseLocation}</dt>
        <dd>{claim.base_location_name ?? "—"}</dd>
      </div>
      <div>
        <dt className="text-base-content/60">{copy.workDate}</dt>
        <dd className="font-medium">{claim.work_date}</dd>
      </div>
      <div>
        <dt className="text-base-content/60">{copy.submitted}</dt>
        <dd>
          {claim.submitted_at
            ? localizedDateTime(claim.submitted_at, language)
            : "—"}
        </dd>
      </div>
      <div>
        <dt className="text-base-content/60">{copy.note}</dt>
        <dd>{claim.note_present ? copy.noteAvailable : "—"}</dd>
      </div>
    </dl>
  );
}

export default function ApprovalsPage() {
  const language = languageFromDocument();
  const messages = messagesFor(language);
  const copy = messages.approvals;
  const common = messages.common;
  const [claims, setClaims] = useState<Claim[]>([]);
  const [pendingAssignments, setPendingAssignments] = useState<Claim[]>([]);
  const [assignees, setAssignees] = useState<Assignee[]>([]);
  const [role, setRole] = useState<Role>(null);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [assigning, setAssigning] = useState<number | null>(null);
  const [assigneeId, setAssigneeId] = useState("");
  const [assignmentReason, setAssignmentReason] = useState("");
  const [undo, setUndo] = useState<Claim | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyClaim, setBusyClaim] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [managerQueueCount, setManagerQueueCount] = useState(0);
  const [assignmentHasNext, setAssignmentHasNext] = useState(false);
  const [oldestPendingTime, setOldestPendingTime] = useState<number | null>(
    null,
  );
  const [timelineClaim, setTimelineClaim] = useState<number | null>(null);
  const [timelineEvents, setTimelineEvents] = useState<ManagerAuditEvent[]>([]);
  const [timelineNextPage, setTimelineNextPage] = useState<number | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState<string | null>(null);
  const timelineClaimRef = useRef<number | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    async function load() {
      const loadMessages = messagesFor(language);
      const loadCopy = loadMessages.approvals;
      setError(null);
      setLoading(true);
      try {
        const current = await apiFetch("/api/v1/users/me/");
        if (!current.ok) {
          setError(loadCopy.notAuthorized);
          return;
        }
        const user = (await current.json()) as {
          memberships: Array<{ role: Role }>;
        };
        const currentRole = user.memberships[0]?.role ?? null;
        setRole(currentRole);
        if (currentRole === "manager") {
          setAssignmentHasNext(false);
          const [response, countResponse] = await Promise.all([
            apiFetch(`/api/v1/approvals/?page=${page}`),
            apiFetch("/api/v1/approvals/count/"),
          ]);
          if (!response.ok) {
            setError(loadCopy.loadClaimsFailed);
            return;
          }
          const nextClaims = (await response.json()) as Claim[];
          setClaims(nextClaims);
          if (countResponse.ok) {
            const body = (await countResponse.json()) as ApprovalCount;
            const oldest = body.oldest_submitted_at
              ? Date.parse(body.oldest_submitted_at)
              : NaN;
            setManagerQueueCount(body.count ?? nextClaims.length);
            setOldestPendingTime(Number.isFinite(oldest) ? oldest : null);
          } else {
            setManagerQueueCount(nextClaims.length);
            setOldestPendingTime(oldestSubmittedTime(nextClaims));
          }
          return;
        }
        if (currentRole === "hr_admin") {
          setManagerQueueCount(0);
          setOldestPendingTime(null);
          const [pending, managers] = await Promise.all([
            apiFetch(`/api/v1/approvals/ownership/?page=${page}`),
            apiFetch("/api/v1/approvals/assignees/"),
          ]);
          if (!pending.ok || !managers.ok) {
            setError(loadCopy.loadAssignmentsFailed);
            return;
          }
          setPendingAssignments((await pending.json()) as Claim[]);
          setAssignmentHasNext(
            pending.headers.get("X-Has-Next")?.toLowerCase() === "true",
          );
          setAssignees((await managers.json()) as Assignee[]);
          return;
        }
        setManagerQueueCount(0);
        setOldestPendingTime(null);
        setAssignmentHasNext(false);
        setError(loadCopy.notAuthorized);
      } catch {
        setError(loadMessages.shell.serviceError);
      } finally {
        setLoading(false);
      }
    }

    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [language, page, reloadToken]);

  async function decide(claim: Claim, action: "approve" | "reject") {
    setError(null);
    setBusyClaim(claim.id);
    try {
      const response = await apiFetch(
        `/api/v1/approvals/${claim.id}/${action}/`,
        {
          method: "POST",
          body: JSON.stringify(
            action === "reject"
              ? { version: claim.version, reason }
              : { version: claim.version },
          ),
        },
      );
      if (!response.ok) {
        setError(copy.decisionChanged);
        return;
      }
      const result = (await response.json()) as Claim;
      if (action === "approve") setUndo({ ...claim, version: result.version });
      setRejecting(null);
      setReason("");
      window.dispatchEvent(new Event("yawn:approvals"));
      setReloadToken((current) => current + 1);
    } catch {
      setError(copy.decisionSaveFailed);
    } finally {
      setBusyClaim(null);
    }
  }

  async function assign(claim: Claim) {
    setError(null);
    setBusyClaim(claim.id);
    try {
      const response = await apiFetch(`/api/v1/approvals/${claim.id}/assign/`, {
        method: "POST",
        body: JSON.stringify({
          version: claim.version,
          manager_membership_id: Number(assigneeId),
          reason: assignmentReason,
        }),
      });
      if (!response.ok) {
        setError(copy.assignmentChanged);
        return;
      }
      setAssigning(null);
      setAssigneeId("");
      setAssignmentReason("");
      window.dispatchEvent(new Event("yawn:approvals"));
      setReloadToken((current) => current + 1);
    } catch {
      setError(copy.assignmentSaveFailed);
    } finally {
      setBusyClaim(null);
    }
  }

  async function loadTimeline(claimId: number, timelinePage: number) {
    setTimelineLoading(true);
    setTimelineError(null);
    try {
      const response = await apiFetch(
        `/api/v1/approvals/${claimId}/timeline/?page=${timelinePage}`,
      );
      if (!response.ok) {
        if (timelineClaimRef.current === claimId) {
          setTimelineError(copy.historyLoadFailed);
        }
        return;
      }
      const body = (await response.json()) as ManagerAuditPage;
      if (timelineClaimRef.current !== claimId) return;
      setTimelineEvents((current) =>
        timelinePage === 1 ? body.results : [...current, ...body.results],
      );
      setTimelineNextPage(body.next_page);
    } catch {
      if (timelineClaimRef.current === claimId) {
        setTimelineError(copy.historyLoadFailed);
      }
    } finally {
      if (timelineClaimRef.current === claimId) {
        setTimelineLoading(false);
      }
    }
  }

  function toggleTimeline(claimId: number) {
    if (timelineClaim === claimId) {
      timelineClaimRef.current = null;
      setTimelineClaim(null);
      setTimelineEvents([]);
      setTimelineNextPage(null);
      setTimelineError(null);
      return;
    }
    timelineClaimRef.current = claimId;
    setTimelineClaim(claimId);
    setTimelineEvents([]);
    setTimelineNextPage(null);
    void loadTimeline(claimId, 1);
  }

  async function undoApproval() {
    if (!undo) return;
    setError(null);
    const response = await apiFetch(`/api/v1/approvals/${undo.id}/undo/`, {
      method: "POST",
      body: JSON.stringify({ version: undo.version }),
    });
    if (!response.ok) {
      setUndo(null);
      setError(copy.undoExpired);
      return;
    }
    setUndo(null);
    window.dispatchEvent(new Event("yawn:approvals"));
    setReloadToken((current) => current + 1);
  }

  useEffect(() => {
    if (!undo) return;
    const timer = window.setTimeout(() => setUndo(null), 10_000);
    return () => window.clearTimeout(timer);
  }, [undo]);

  function goToPage(nextPage: number) {
    setRejecting(null);
    setReason("");
    setAssigning(null);
    setAssigneeId("");
    setAssignmentReason("");
    timelineClaimRef.current = null;
    setTimelineClaim(null);
    setTimelineEvents([]);
    setTimelineNextPage(null);
    setTimelineError(null);
    setPage(Math.max(1, nextPage));
  }

  const oldestPending = role === "manager" ? oldestPendingTime : null;
  const managerHasNext = page * PAGE_SIZE < managerQueueCount;
  return (
    <AppPage>
      <section className="space-y-6">
        <header>
          <p className="text-primary font-semibold">{copy.eyebrow}</p>
          <h1 className="mt-1 text-3xl font-bold tracking-tight">
            {role === "hr_admin" ? copy.assignmentTitle : copy.pendingTitle}
          </h1>
          <p className="text-base-content/70 mt-2">
            {role === "hr_admin" ? copy.assignmentIntro : copy.pendingIntro}
          </p>
          {oldestPending !== null ? (
            <p className="text-base-content/60 mt-2 text-sm" role="status">
              {oldestPendingAgeLabel(oldestPending, copy)}
            </p>
          ) : null}
        </header>
        {error ? (
          <div className="alert alert-error" role="alert">
            <span>{error}</span>
          </div>
        ) : null}
        {undo ? (
          <div className="alert alert-info" role="status">
            <span>{copy.approvalSaved}</span>
            <button
              className="btn btn-sm"
              onClick={() => void undoApproval()}
              type="button"
            >
              {copy.undoApproval}
            </button>
          </div>
        ) : null}
        {loading ? (
          <div className="space-y-3" aria-label={copy.loading} role="status">
            <div className="skeleton h-32 w-full" />
            <div className="skeleton h-20 w-full" />
          </div>
        ) : null}
        {!loading && role === "manager" && claims.length ? (
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>{copy.employee}</th>
                  <th>{copy.baseLocation}</th>
                  <th>{copy.workDate}</th>
                  <th>{copy.submitted}</th>
                  <th>{copy.note}</th>
                  <th>{copy.decision}</th>
                </tr>
              </thead>
              <tbody>
                {claims.map((claim) => (
                  <tr key={claim.id}>
                    <td>
                      <span className="font-medium">{claim.employee_name}</span>
                      <span className="text-base-content/60 block text-xs">
                        {claim.employee_email}
                      </span>
                    </td>
                    <td>{claim.base_location_name ?? "—"}</td>
                    <td>{claim.work_date}</td>
                    <td>
                      {claim.submitted_at
                        ? localizedDateTime(claim.submitted_at, language)
                        : "—"}
                    </td>
                    <td>{claim.note_present ? copy.noteAvailable : "—"}</td>
                    <td>
                      <div className="space-y-3">
                        {rejecting === claim.id ? (
                          <div className="flex flex-wrap gap-2">
                            <label>
                              <span className="sr-only">
                                {copy.rejectionReason}
                              </span>
                              <input
                                autoFocus
                                className="input input-sm"
                                onChange={(event) =>
                                  setReason(event.target.value)
                                }
                                required
                                value={reason}
                              />
                            </label>
                            <button
                              className="btn btn-sm btn-error"
                              disabled={
                                !reason.trim() || busyClaim === claim.id
                              }
                              onClick={() => void decide(claim, "reject")}
                              type="button"
                            >
                              {copy.confirmRejection}
                            </button>
                            <button
                              className="btn btn-sm"
                              disabled={busyClaim === claim.id}
                              onClick={() => {
                                setRejecting(null);
                                setReason("");
                              }}
                              type="button"
                            >
                              {common.cancel}
                            </button>
                          </div>
                        ) : (
                          <div className="flex flex-wrap gap-2">
                            <button
                              className="btn btn-sm btn-primary"
                              disabled={busyClaim === claim.id}
                              onClick={() => void decide(claim, "approve")}
                              type="button"
                            >
                              {copy.approve}
                            </button>
                            <button
                              className="btn btn-sm"
                              disabled={busyClaim === claim.id}
                              onClick={() => setRejecting(claim.id)}
                              type="button"
                            >
                              {copy.reject}
                            </button>
                            <button
                              aria-controls={`claim-history-${claim.id}`}
                              aria-expanded={timelineClaim === claim.id}
                              className="btn btn-sm btn-ghost"
                              onClick={() => toggleTimeline(claim.id)}
                              type="button"
                            >
                              {timelineClaim === claim.id
                                ? copy.hideHistory
                                : copy.viewHistory}
                            </button>
                          </div>
                        )}
                        {timelineClaim === claim.id ? (
                          <div
                            className="border-base-300 min-w-64 border-t pt-3"
                            id={`claim-history-${claim.id}`}
                          >
                            {timelineError ? (
                              <p className="text-error text-sm" role="alert">
                                {timelineError}
                              </p>
                            ) : null}
                            {timelineEvents.length ? (
                              <ol className="space-y-3">
                                {timelineEvents.map((event) => (
                                  <li className="text-sm" key={event.id}>
                                    <p className="font-medium">
                                      {auditActionLabel(event.event_type, copy)}
                                    </p>
                                    <p className="text-base-content/60">
                                      {localizedDateTime(
                                        event.created_at,
                                        language,
                                      )}
                                    </p>
                                    {event.details.reason ? (
                                      <p>
                                        <span className="font-semibold">
                                          {copy.auditReason}:{" "}
                                        </span>
                                        {event.details.reason}
                                      </p>
                                    ) : null}
                                    {event.details.revision ? (
                                      <p>
                                        <span className="font-semibold">
                                          {copy.auditRevision}:{" "}
                                        </span>
                                        {event.details.revision}
                                      </p>
                                    ) : null}
                                    {event.details.from_state &&
                                    event.details.to_state ? (
                                      <p>
                                        <span className="font-semibold">
                                          {copy.auditTransition}:{" "}
                                        </span>
                                        {auditStateLabel(
                                          event.details.from_state,
                                          messages.workInOffice,
                                        )}{" "}
                                        →{" "}
                                        {auditStateLabel(
                                          event.details.to_state,
                                          messages.workInOffice,
                                        )}
                                      </p>
                                    ) : null}
                                  </li>
                                ))}
                              </ol>
                            ) : !timelineLoading && !timelineError ? (
                              <p className="text-base-content/60 text-sm">
                                {copy.historyEmpty}
                              </p>
                            ) : null}
                            {timelineLoading ? (
                              <span
                                aria-label={copy.loading}
                                className="loading loading-spinner loading-sm"
                                role="status"
                              />
                            ) : null}
                            {timelineNextPage && !timelineLoading ? (
                              <button
                                className="btn btn-sm btn-ghost mt-2"
                                onClick={() =>
                                  void loadTimeline(claim.id, timelineNextPage)
                                }
                                type="button"
                              >
                                {copy.loadOlderHistory}
                              </button>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : !loading && role === "manager" ? (
          <div className="alert alert-info alert-soft" role="status">
            <span>{page > 1 ? copy.noPageResults : copy.noAssigned}</span>
          </div>
        ) : null}
        {!loading && role === "manager" ? (
          <QueuePagination
            copy={copy}
            hasNext={managerHasNext}
            onNext={() => goToPage(page + 1)}
            onPrevious={() => goToPage(page - 1)}
            page={page}
          />
        ) : null}
        {!loading && role === "hr_admin" && pendingAssignments.length ? (
          <div className="space-y-3">
            {pendingAssignments.map((claim) => (
              <article className="card bg-base-200 shadow-sm" key={claim.id}>
                <div className="card-body gap-4">
                  <ClaimSummary claim={claim} copy={copy} language={language} />
                  {assigning === claim.id ? (
                    <div className="flex flex-wrap items-end gap-3">
                      <label className="form-control min-w-56 flex-1">
                        <span className="label-text">{copy.activeManager}</span>
                        <select
                          className="select select-bordered"
                          onChange={(event) =>
                            setAssigneeId(event.target.value)
                          }
                          value={assigneeId}
                        >
                          <option value="">{copy.chooseManager}</option>
                          {assignees.map((manager) => (
                            <option key={manager.id} value={manager.id}>
                              {manager.name} ({manager.email})
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="form-control min-w-56 flex-1">
                        <span className="label-text">
                          {copy.assignmentReason}
                        </span>
                        <input
                          className="input input-bordered"
                          onChange={(event) =>
                            setAssignmentReason(event.target.value)
                          }
                          value={assignmentReason}
                        />
                      </label>
                      <button
                        className="btn btn-primary"
                        disabled={
                          !assigneeId ||
                          !assignmentReason.trim() ||
                          busyClaim === claim.id
                        }
                        onClick={() => void assign(claim)}
                        type="button"
                      >
                        {claim.review_state === "pending"
                          ? copy.reassignManager
                          : copy.assignManager}
                      </button>
                      <button
                        className="btn"
                        disabled={busyClaim === claim.id}
                        onClick={() => {
                          setAssigning(null);
                          setAssigneeId("");
                          setAssignmentReason("");
                        }}
                        type="button"
                      >
                        {common.cancel}
                      </button>
                    </div>
                  ) : assignees.length ? (
                    <button
                      className="btn btn-outline self-start"
                      onClick={() => setAssigning(claim.id)}
                      type="button"
                    >
                      {claim.review_state === "pending"
                        ? copy.reassignManager
                        : copy.assignManager}
                    </button>
                  ) : (
                    <p className="text-warning text-sm" role="status">
                      {copy.noManagers}
                    </p>
                  )}
                </div>
              </article>
            ))}
          </div>
        ) : !loading && role === "hr_admin" ? (
          <div className="alert alert-info alert-soft" role="status">
            <span>{page > 1 ? copy.noPageResults : copy.noAssignments}</span>
          </div>
        ) : null}
        {!loading && role === "hr_admin" ? (
          <QueuePagination
            copy={copy}
            hasNext={assignmentHasNext}
            onNext={() => goToPage(page + 1)}
            onPrevious={() => goToPage(page - 1)}
            page={page}
          />
        ) : null}
      </section>
    </AppPage>
  );
}
