"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import {
  getWorkInOfficeMetadata,
  saveWorkInOffice,
  type WorkInOfficeRecord,
} from "./api";
import {
  formatMessage,
  languageFromDocument,
  messagesFor,
} from "../../lib/i18n";
import { ApiError, userFacingError } from "../../lib/errors";

type Props = { record?: WorkInOfficeRecord; initialDate?: string };

export function RecordForm({ record, initialDate }: Props) {
  const copy = messagesFor(languageFromDocument()).workInOffice;
  const router = useRouter();
  const [workDate, setWorkDate] = useState(
    record?.work_date ?? initialDate ?? "",
  );
  const [timezone, setTimezone] = useState<string | null>(null);
  const hasAppliedServerDate = useRef(Boolean(record || initialDate));
  const [choice, setChoice] = useState<"in_office" | "not_in_office" | "">(
    record?.location_choice ?? "",
  );
  const [note, setNote] = useState(record?.note ?? "");
  const [error, setError] = useState<string | null>(null);
  const [isConflict, setIsConflict] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (record) return;
    void getWorkInOfficeMetadata(copy.companyDateFailed)
      .then((metadata) => {
        setTimezone(metadata.timezone);
        if (!hasAppliedServerDate.current) {
          setWorkDate(metadata.company_date);
          hasAppliedServerDate.current = true;
        }
      })
      .catch(() => setError(copy.companyDateFailed));
  }, [copy.companyDateFailed, record]);

  async function save(mode: "draft" | "submit") {
    setError(null);
    setIsConflict(false);
    setIsSaving(true);
    try {
      const saved = await saveWorkInOffice(
        {
          work_date: workDate,
          location_choice: mode === "draft" ? null : choice || null,
          note,
          version: record?.version,
        },
        record ? String(record.id) : undefined,
        copy.saveRecordFailed,
      );
      router.replace(`/work-in-office?saved=${saved.id}`);
    } catch (reason) {
      setIsConflict(reason instanceof ApiError && reason.status === 409);
      setError(userFacingError(reason, copy.saveRecordFailed));
    } finally {
      setIsSaving(false);
    }
  }

  const locked =
    record?.review_state === "pending" || record?.review_state === "approved";
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
          <div className="alert alert-error" role="alert">
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
            <span>{copy.lockedReview}</span>
          </div>
        ) : null}
        {record?.review_state === "rejected" ? (
          <div className="alert alert-warning" role="status">
            <span>
              {formatMessage(copy.rejectedPrefix, {
                note: record.approver_note || copy.reviewChanges,
              })}
              {record.correction_deadline
                ? formatMessage(copy.correctBy, {
                    date: new Date(record.correction_deadline).toLocaleString(),
                  })
                : ""}
            </span>
          </div>
        ) : null}
        <label className="fieldset">
          <span className="fieldset-legend">{copy.workDate}</span>
          <input
            className="input w-full"
            disabled={
              locked || record?.review_state === "rejected" || !workDate
            }
            onChange={(event) => setWorkDate(event.target.value)}
            required
            type="date"
            value={workDate}
          />
        </label>
        <label className="fieldset">
          <span className="fieldset-legend">{copy.workLocation}</span>
          <select
            className="select w-full"
            disabled={locked}
            onChange={(event) => setChoice(event.target.value as typeof choice)}
            required
            value={choice}
          >
            <option value="">{copy.chooseLocation}</option>
            <option value="in_office">{copy.yesInOffice}</option>
            <option value="not_in_office">{copy.noElsewhere}</option>
          </select>
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
              className="textarea w-full"
              disabled={locked}
              maxLength={500}
              onChange={(event) => setNote(event.target.value)}
              placeholder={copy.notePlaceholder}
              rows={4}
              value={note}
            />
          </label>
        ) : null}
        <div className="card-actions justify-between">
          <button
            className="btn btn-ghost"
            disabled={isSaving || locked}
            onClick={() => void save("draft")}
            type="button"
          >
            {copy.saveDraft}
          </button>
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
