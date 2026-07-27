"use client";

import Link from "next/link";
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import { AppPage } from "@/features/app-shell/app-page";
import { userFacingError } from "@/lib/errors";
import {
  listWorkInOffice,
  type WorkInOfficeRecord,
} from "@/features/work-in-office/api";
import { formatMessage, languageFromDocument, messagesFor } from "@/lib/i18n";

const attentionStates = new Set(["draft", "rejected"]);
type WorkInOfficeCopy = ReturnType<typeof messagesFor>["workInOffice"];

function reviewLabel(
  state: WorkInOfficeRecord["review_state"],
  copy: WorkInOfficeCopy,
) {
  const labels = {
    draft: copy.stateDraft,
    pending: copy.statePending,
    pending_assignment: copy.statePendingAssignment,
    approved: copy.stateApproved,
    rejected: copy.stateRejected,
    not_required: copy.stateNotRequired,
    expired_pending: copy.stateExpiredPending,
  } satisfies Record<WorkInOfficeRecord["review_state"], string>;

  return labels[state];
}

function locationLabel(
  value: WorkInOfficeRecord["location_choice"],
  copy: WorkInOfficeCopy,
) {
  if (value === "in_office") return copy.inOffice;
  if (value === "not_in_office") return copy.notInOffice;
  return copy.stateDraft;
}

function statusClass(state: WorkInOfficeRecord["review_state"]) {
  return state === "approved"
    ? "badge-success"
    : state === "pending"
      ? "badge-warning"
      : state === "rejected"
        ? "badge-error"
        : "badge-ghost";
}

function WorkInOfficeIndex() {
  const language = languageFromDocument();
  const copy = messagesFor(language).workInOffice;
  const [records, setRecords] = useState<WorkInOfficeRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [location, setLocation] = useState("");
  const [review, setReview] = useState("");
  const [date, setDate] = useState("");
  const [month, setMonth] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const statusRef = useRef<HTMLDivElement>(null);
  const searchParams = useSearchParams();
  const saved = searchParams.get("saved");
  useEffect(() => {
    const query = new URLSearchParams();
    if (location) query.set("location_choice", location);
    if (review) query.set("review_state", review);
    if (date) query.set("work_date", date);
    if (month) query.set("month", month);
    if (startDate) query.set("start_date", startDate);
    if (endDate) query.set("end_date", endDate);
    const suffix = query.size ? `?${query}` : "";
    void listWorkInOffice(suffix, copy.listRecordsFailed)
      .then(setRecords)
      .catch((reason) =>
        setError(userFacingError(reason, copy.listRecordsFailed)),
      );
  }, [
    copy.listRecordsFailed,
    date,
    endDate,
    location,
    month,
    review,
    startDate,
  ]);
  const attention = records.filter((record) =>
    attentionStates.has(record.review_state),
  );
  const savedRecord = records.find((record) => String(record.id) === saved);
  useEffect(() => {
    if (savedRecord) statusRef.current?.focus();
  }, [savedRecord]);
  const outcome =
    savedRecord?.review_state === "draft"
      ? copy.draftSaved
      : savedRecord?.review_state === "not_required"
        ? copy.notRequiredSaved
        : savedRecord?.review_state === "pending_assignment"
          ? copy.pendingAssignmentSaved
          : copy.submittedSaved;
  return (
    <AppPage contentClassName="space-y-7">
      <section>
        <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-primary font-semibold">{copy.eyebrow}</p>
            <h1 className="mt-1 text-3xl font-bold tracking-tight">
              {copy.title}
            </h1>
            <p className="text-base-content/70 mt-2 max-w-2xl">{copy.intro}</p>
          </div>
          <Link className="btn btn-primary" href="/work-in-office/new">
            {copy.logWorkLocation}
          </Link>
        </header>
        {saved ? (
          <div
            className="alert alert-success"
            role="status"
            ref={statusRef}
            tabIndex={-1}
          >
            <span>{formatMessage(copy.savedHighlight, { outcome })}</span>
          </div>
        ) : null}
        {error ? (
          <div className="alert alert-error" role="alert">
            <span>{error}</span>
          </div>
        ) : null}
        {attention.length ? (
          <section className="card bg-base-200 shadow-sm">
            <div className="card-body">
              <h2 className="card-title">{copy.needsAttention}</h2>
              <div className="flex flex-wrap gap-2">
                {attention.map((record) => (
                  <Link
                    className="btn btn-sm"
                    href={`/work-in-office/${record.id}`}
                    key={record.id}
                  >
                    {record.work_date}
                    {copy.dateActionSeparator}
                    {record.review_state === "rejected"
                      ? copy.correctRejection
                      : copy.finishDraft}
                  </Link>
                ))}
              </div>
            </div>
          </section>
        ) : null}
        <section className="card bg-base-200 shadow-sm">
          <div className="card-body">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <h2 className="card-title">{copy.thisMonth}</h2>
              <fieldset className="grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
                <label className="fieldset">
                  <span className="fieldset-legend">{copy.month}</span>
                  <input
                    className="input input-sm"
                    onChange={(event) => setMonth(event.target.value)}
                    type="month"
                    value={month}
                  />
                </label>
                <label className="fieldset">
                  <span className="fieldset-legend">{copy.date}</span>
                  <input
                    className="input input-sm"
                    onChange={(event) => setDate(event.target.value)}
                    type="date"
                    value={date}
                  />
                </label>
                <label className="fieldset">
                  <span className="fieldset-legend">{copy.from}</span>
                  <input
                    className="input input-sm"
                    onChange={(event) => setStartDate(event.target.value)}
                    type="date"
                    value={startDate}
                  />
                </label>
                <label className="fieldset">
                  <span className="fieldset-legend">{copy.to}</span>
                  <input
                    className="input input-sm"
                    onChange={(event) => setEndDate(event.target.value)}
                    type="date"
                    value={endDate}
                  />
                </label>
                <label className="fieldset">
                  <span className="fieldset-legend">{copy.location}</span>
                  <select
                    className="select select-sm"
                    onChange={(event) => setLocation(event.target.value)}
                    value={location}
                  >
                    <option value="">{copy.allLocations}</option>
                    <option value="in_office">{copy.inOffice}</option>
                    <option value="not_in_office">{copy.notInOffice}</option>
                  </select>
                </label>
                <label className="fieldset">
                  <span className="fieldset-legend">{copy.review}</span>
                  <select
                    className="select select-sm"
                    onChange={(event) => setReview(event.target.value)}
                    value={review}
                  >
                    <option value="">{copy.allStates}</option>
                    <option value="draft">{copy.stateDraft}</option>
                    <option value="pending">{copy.statePending}</option>
                    <option value="pending_assignment">
                      {copy.statePendingAssignment}
                    </option>
                    <option value="approved">{copy.stateApproved}</option>
                    <option value="rejected">{copy.stateRejected}</option>
                    <option value="not_required">
                      {copy.stateNotRequired}
                    </option>
                  </select>
                </label>
              </fieldset>
            </div>
            {records.length ? (
              <div className="overflow-x-auto">
                <table className="table">
                  <thead>
                    <tr>
                      <th>{copy.date}</th>
                      <th>{copy.location}</th>
                      <th>{copy.updated}</th>
                      <th>{copy.review}</th>
                      <th>
                        <span className="sr-only">{copy.open}</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {records.map((record) => (
                      <tr
                        className={
                          saved === String(record.id)
                            ? "bg-success/15"
                            : undefined
                        }
                        key={record.id}
                      >
                        <td>{record.work_date}</td>
                        <td>{locationLabel(record.location_choice, copy)}</td>
                        <td>
                          <span
                            aria-label={
                              record.note ? copy.includesNote : copy.noNote
                            }
                          >
                            {record.note ? copy.notePrefix : ""}
                            {new Date(record.updated_at).toLocaleString()}
                          </span>
                        </td>
                        <td>
                          <span
                            className={`badge ${statusClass(record.review_state)}`}
                          >
                            {reviewLabel(record.review_state, copy)}
                          </span>
                        </td>
                        <td>
                          <Link
                            className="btn btn-sm btn-ghost"
                            href={`/work-in-office/${record.id}`}
                          >
                            {copy.open}
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="alert alert-info alert-soft" role="status">
                <span>{copy.noMatchingRecords}</span>
              </div>
            )}
          </div>
        </section>
      </section>
    </AppPage>
  );
}

export default function WorkInOfficePage() {
  return (
    <Suspense
      fallback={
        <AppPage
          aria-live="polite"
          contentClassName="grid min-h-[calc(100vh-4rem)] place-items-center"
        >
          <span
            className="loading loading-spinner"
            aria-label={
              messagesFor(languageFromDocument()).workInOffice.loadingRecords
            }
          />
        </AppPage>
      }
    >
      <WorkInOfficeIndex />
    </Suspense>
  );
}
