"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import {
  getWorkInOfficeMetadata,
  saveWorkInOffice,
  undoSelfApproval,
  WIO_EDITABLE_FIELDS,
  type WorkInOfficeEditableField,
  type WorkInOfficeRecord,
} from "./api";
import {
  formatMessage,
  languageFromDocument,
  messagesFor,
} from "../../lib/i18n";
import { ApiError, userFacingError } from "../../lib/errors";

type Props = { record?: WorkInOfficeRecord; initialDate?: string };
type DraftChoice = "in_office" | "not_in_office" | "";

function takeConflictDraft(record?: WorkInOfficeRecord): {
  choice?: DraftChoice;
  note?: string;
} {
  if (typeof window === "undefined" || !record) return {};
  const key = `wio-conflict-draft:${record.id}`;
  const savedDraft = window.sessionStorage.getItem(key);
  if (!savedDraft) return {};
  try {
    const parsed = JSON.parse(savedDraft) as unknown;
    if (!parsed || typeof parsed !== "object") return {};
    const candidate = parsed as { choice?: unknown; note?: unknown };
    return {
      choice:
        candidate.choice === "" ||
        candidate.choice === "in_office" ||
        candidate.choice === "not_in_office"
          ? candidate.choice
          : undefined,
      note: typeof candidate.note === "string" ? candidate.note : undefined,
    };
  } catch {
    return {};
  } finally {
    window.sessionStorage.removeItem(key);
  }
}

export function RecordForm({ record, initialDate }: Props) {
  const language = languageFromDocument();
  const copy = messagesFor(language).workInOffice;
  const router = useRouter();
  const [workDate, setWorkDate] = useState(
    record?.work_date ?? initialDate ?? "",
  );
  const [timezone, setTimezone] = useState<string | null>(null);
  const hasAppliedServerDate = useRef(Boolean(record || initialDate));
  const [conflictDraft] = useState(() => takeConflictDraft(record));
  const [choice, setChoice] = useState<DraftChoice>(
    conflictDraft.choice ?? record?.location_choice ?? "",
  );
  const [note, setNote] = useState(conflictDraft.note ?? record?.note ?? "");
  const [error, setError] = useState<string | null>(null);
  const [isConflict, setIsConflict] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isUndoing, setIsUndoing] = useState(false);
  const errorRef = useRef<HTMLDivElement>(null);
  const workDateRef = useRef<HTMLInputElement>(null);
  const locationRef = useRef<HTMLSelectElement>(null);
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const [fieldErrors, setFieldErrors] = useState<WorkInOfficeEditableField[]>(
    [],
  );
  const shouldApplyServerDate = !record;

  useEffect(() => {
    void getWorkInOfficeMetadata(copy.companyDateFailed)
      .then((metadata) => {
        setTimezone(metadata.timezone);
        if (shouldApplyServerDate && !hasAppliedServerDate.current) {
          setWorkDate(metadata.company_date);
          hasAppliedServerDate.current = true;
        }
      })
      .catch(() => setError(copy.companyDateFailed));
  }, [copy.companyDateFailed, shouldApplyServerDate]);

  useEffect(() => {
    if (!error) return;
    const target = [
      fieldErrors.includes("work_date") ? workDateRef.current : null,
      fieldErrors.includes("location_choice") ? locationRef.current : null,
      fieldErrors.includes("note") ? noteRef.current : null,
    ].find((control) => control && !control.disabled);
    if (target) target.focus();
    else errorRef.current?.focus();
  }, [error, fieldErrors]);

  async function save(mode: "draft" | "submit") {
    setError(null);
    setFieldErrors([]);
    setIsConflict(false);
    setIsSaving(true);
    try {
      const saved = await saveWorkInOffice(
        {
          work_date: workDate,
          location_choice: choice || null,
          note,
          save_as_draft: mode === "draft",
          version: record?.version,
        },
        record ? String(record.id) : undefined,
        copy.saveRecordFailed,
      );
      router.replace(
        saved.approval_method === "self_approved"
          ? `/work-in-office/${saved.id}`
          : `/work-in-office?saved=${saved.id}`,
      );
    } catch (reason) {
      const conflict = reason instanceof ApiError && reason.status === 409;
      const invalidFields =
        reason instanceof ApiError
          ? reason.fieldErrors.filter(
              (field): field is WorkInOfficeEditableField =>
                WIO_EDITABLE_FIELDS.includes(
                  field as WorkInOfficeEditableField,
                ),
            )
          : [];
      setIsConflict(conflict);
      if (conflict && record) {
        window.sessionStorage.setItem(
          `wio-conflict-draft:${record.id}`,
          JSON.stringify({ choice, note }),
        );
      }
      setFieldErrors(invalidFields);
      setError(
        invalidFields.length
          ? copy.checkFormFields
          : userFacingError(reason, copy.saveRecordFailed),
      );
    } finally {
      setIsSaving(false);
    }
  }

  async function undoApproval() {
    if (!record) return;
    setError(null);
    setFieldErrors([]);
    setIsConflict(false);
    setIsUndoing(true);
    try {
      const saved = await undoSelfApproval(
        record.id,
        record.version,
        copy.undoSelfApprovalFailed,
      );
      router.replace(`/work-in-office/${saved.id}`);
      router.refresh();
    } catch (reason) {
      setIsConflict(reason instanceof ApiError && reason.status === 409);
      setError(userFacingError(reason, copy.undoSelfApprovalFailed));
    } finally {
      setIsUndoing(false);
    }
  }

  const locked = new Set([
    "pending",
    "pending_assignment",
    "approved",
    "expired_pending",
  ]).has(record?.review_state ?? "");
  const canSaveDraft = !record || record.review_state === "draft";
  const correctionDeadline =
    record?.correction_deadline && timezone
      ? new Intl.DateTimeFormat(language, {
          dateStyle: "medium",
          timeStyle: "short",
          timeZone: timezone,
        }).format(new Date(record.correction_deadline))
      : null;
  return (
    <form
      className="card bg-base-200 shadow-sm"
      onSubmit={(event) => {
        event.preventDefault();
        void save("submit");
      }}
    >
      <div className="card-body gap-5">
        <div>
          <h1 className="card-title text-2xl">
            {record ? copy.updateRecord : copy.logWorkLocation}
          </h1>
          <p className="text-base-content/70 mt-1">{copy.formIntro}</p>
        </div>
        {error ? (
          <div
            className="alert alert-error"
            ref={errorRef}
            role="alert"
            tabIndex={-1}
          >
            <span>{error}</span>
            {isConflict ? (
              <button
                className="btn btn-sm"
                onClick={() => window.location.reload()}
                type="button"
              >
                {copy.reloadLatest}
              </button>
            ) : null}
          </div>
        ) : null}
        {timezone ? (
          <div className="alert alert-info alert-soft" role="status">
            <span>{formatMessage(copy.deadlineTimezone, { timezone })}</span>
          </div>
        ) : null}
        {locked ? (
          <div className="alert alert-warning" role="status">
            <div className="flex w-full flex-wrap items-center justify-between gap-3">
              <span>{copy.lockedReview}</span>
              {record?.approval_method === "self_approved" ? (
                <button
                  className="btn btn-sm btn-ghost"
                  disabled={isUndoing}
                  onClick={() => void undoApproval()}
                  type="button"
                >
                  {isUndoing ? (
                    <span className="loading loading-spinner loading-xs" />
                  ) : null}
                  {copy.undoSelfApproval}
                </button>
              ) : null}
            </div>
          </div>
        ) : null}
        {record?.review_state === "rejected" ? (
          <div className="alert alert-warning" role="status">
            <span>
              {formatMessage(copy.rejectedPrefix, {
                note: record.approver_note || copy.reviewChanges,
              })}
              {correctionDeadline
                ? formatMessage(copy.correctBy, {
                    date: correctionDeadline,
                  })
                : ""}
            </span>
          </div>
        ) : null}
        <label className="fieldset">
          <span className="fieldset-legend">{copy.workDate}</span>
          <input
            aria-describedby={
              fieldErrors.includes("work_date")
                ? "wio-work-date-error"
                : undefined
            }
            aria-invalid={fieldErrors.includes("work_date") ? true : undefined}
            className="input w-full"
            disabled={
              locked || record?.review_state === "rejected" || !workDate
            }
            onChange={(event) => setWorkDate(event.target.value)}
            required
            ref={workDateRef}
            type="date"
            value={workDate}
          />
          {fieldErrors.includes("work_date") ? (
            <p className="text-error mt-1 text-sm" id="wio-work-date-error">
              {copy.workDateInvalid}
            </p>
          ) : null}
        </label>
        <label className="fieldset">
          <span className="fieldset-legend">{copy.workLocation}</span>
          <select
            aria-describedby={
              fieldErrors.includes("location_choice")
                ? "wio-location-choice-error"
                : undefined
            }
            aria-invalid={
              fieldErrors.includes("location_choice") ? true : undefined
            }
            className="select w-full"
            disabled={locked}
            onChange={(event) => setChoice(event.target.value as typeof choice)}
            required
            ref={locationRef}
            value={choice}
          >
            <option value="">{copy.chooseLocation}</option>
            <option value="in_office">{copy.yesInOffice}</option>
            <option value="not_in_office">{copy.noElsewhere}</option>
          </select>
          {fieldErrors.includes("location_choice") ? (
            <p
              className="text-error mt-1 text-sm"
              id="wio-location-choice-error"
            >
              {copy.workLocationInvalid}
            </p>
          ) : null}
        </label>
        {choice === "in_office" ? (
          <label className="fieldset">
            <span className="fieldset-legend">
              {copy.note}{" "}
              <span className="text-base-content/60 font-normal">
                {copy.noteLimit}
              </span>
            </span>
            <textarea
              aria-describedby={
                fieldErrors.includes("note") ? "wio-note-error" : undefined
              }
              aria-invalid={fieldErrors.includes("note") ? true : undefined}
              className="textarea w-full"
              disabled={locked}
              maxLength={500}
              onChange={(event) => setNote(event.target.value)}
              placeholder={copy.notePlaceholder}
              ref={noteRef}
              rows={4}
              value={note}
            />
            {fieldErrors.includes("note") ? (
              <p className="text-error mt-1 text-sm" id="wio-note-error">
                {copy.noteInvalid}
              </p>
            ) : null}
          </label>
        ) : null}
        <div className="card-actions justify-between">
          {canSaveDraft ? (
            <button
              className="btn btn-ghost"
              disabled={isSaving || locked}
              onClick={() => void save("draft")}
              type="button"
            >
              {copy.saveDraft}
            </button>
          ) : (
            <span />
          )}
          <button
            className="btn btn-primary"
            disabled={isSaving || locked || !choice}
            type="submit"
          >
            {isSaving ? (
              <span className="loading loading-spinner loading-sm" />
            ) : null}{" "}
            {copy.submitRecord}
          </button>
        </div>
      </div>
    </form>
  );
}
