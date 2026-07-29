"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
  deleteWorkInOffice,
  getWorkInOffice,
  getWorkInOfficeTimeline,
  type WorkInOfficeRecordDetail,
} from "@/features/work-in-office/api";
import { AppPage } from "@/features/app-shell/app-page";
import { userFacingError } from "@/lib/errors";
import { RecordForm } from "@/features/work-in-office/record-form";
import { languageFromDocument, messagesFor } from "@/lib/i18n";

type WorkInOfficeCopy = ReturnType<typeof messagesFor>["workInOffice"];

function auditActionLabel(eventType: string, copy: WorkInOfficeCopy) {
  const labels: Record<string, string> = {
    "work_logs.record_draft_saved": copy.auditDraftSaved,
    "work_logs.record_draft_deleted": copy.auditDraftDeleted,
    "work_logs.record_submitted": copy.auditSubmitted,
    "work_logs.record_self_approved": copy.auditSelfApproved,
    "work_logs.record_not_in_office": copy.auditNotInOffice,
    "work_logs.record_not_in_office_updated": copy.auditNotInOfficeUpdated,
    "work_logs.record_rejected": copy.auditRejected,
    "work_logs.record_resubmitted": copy.auditResubmitted,
    "work_logs.record_rejection_corrected_not_in_office":
      copy.auditRejectionCorrectedNotInOffice,
    "work_logs.record_approved": copy.auditApproved,
    "work_logs.record_pending_assignment_resolved":
      copy.auditPendingAssignmentResolved,
    "work_logs.record_pending_reassigned": copy.auditPendingReassigned,
    "work_logs.record_expired_pending": copy.auditExpiredPending,
    "work_logs.self_approval_undone": copy.auditSelfApprovalUndone,
    "work_logs.approval_undone": copy.auditApprovalUndone,
    "work_logs.rejection_correction_extended":
      copy.auditCorrectionDeadlineExtended,
    "work_logs.pending_owner_migrated": copy.auditPendingOwnerMigrated,
    "work_logs.pending_assignment_migrated":
      copy.auditPendingAssignmentMigrated,
    "work_logs.self_approval_migration_reverted":
      copy.auditSelfApprovalMigrationReverted,
    "work_logs.self_approval_migrated": copy.auditSelfApprovalMigrated,
    "work_logs.record_older_date_overridden": copy.auditOlderDateOverridden,
    "work_logs.approval_reversed_by_admin": copy.auditApprovalReversedByAdmin,
  };
  return labels[eventType] ?? copy.auditUnknownAction;
}

function auditLocationLabel(
  location: string | number | null,
  copy: WorkInOfficeCopy,
) {
  if (location === "in_office") return copy.inOffice;
  if (location === "not_in_office") return copy.notInOffice;
  return copy.auditEmptyValue;
}

function auditText(value: string | number | null, copy: WorkInOfficeCopy) {
  return value === null || value === "" ? copy.auditEmptyValue : String(value);
}

function auditRoleLabel(role: string | number, copy: WorkInOfficeCopy) {
  const labels: Record<string, string> = {
    employee: copy.auditRoleEmployee,
    manager: copy.auditRoleManager,
    hr_admin: copy.auditRoleHrAdmin,
    superuser: copy.auditRoleSuperuser,
    system: copy.auditRoleSystem,
  };
  return labels[String(role)] ?? copy.auditRoleUnknown;
}

function auditStateLabel(state: string | number, copy: WorkInOfficeCopy) {
  const labels: Record<string, string> = {
    draft: copy.stateDraft,
    pending: copy.statePending,
    pending_assignment: copy.statePendingAssignment,
    approved: copy.stateApproved,
    rejected: copy.stateRejected,
    not_required: copy.stateNotRequired,
    expired_pending: copy.stateExpiredPending,
  };
  return labels[String(state)] ?? copy.auditStateUnknown;
}

export default function WorkInOfficeDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const language = languageFromDocument();
  const copy = messagesFor(language).workInOffice;
  const router = useRouter();
  const [record, setRecord] = useState<WorkInOfficeRecordDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  useEffect(() => {
    void params.then(({ id }) =>
      getWorkInOffice(id, copy.loadRecordFailed)
        .then(setRecord)
        .catch((reason) =>
          setError(userFacingError(reason, copy.loadRecordFailed)),
        ),
    );
  }, [copy.loadRecordFailed, params]);
  async function deleteDraft() {
    if (!record) return;
    try {
      await deleteWorkInOffice(
        String(record.id),
        record.version,
        copy.deleteDraftFailed,
      );
      router.replace("/work-in-office");
    } catch (reason) {
      setError(userFacingError(reason, copy.deleteDraftFailed));
    }
  }

  async function loadOlderHistory() {
    if (!record?.audit_timeline_next_page) return;
    setHistoryError(null);
    setHistoryLoading(true);
    try {
      const page = await getWorkInOfficeTimeline(
        String(record.id),
        record.audit_timeline_next_page,
        copy.historyLoadFailed,
      );
      setRecord((current) =>
        current
          ? {
              ...current,
              audit_timeline: [...current.audit_timeline, ...page.results],
              audit_timeline_next_page: page.next_page,
            }
          : current,
      );
    } catch (reason) {
      setHistoryError(userFacingError(reason, copy.historyLoadFailed));
    } finally {
      setHistoryLoading(false);
    }
  }
  return (
    <AppPage contentWidth="narrow">
      <section>
        <Link className="btn btn-ghost mb-5" href="/work-in-office">
          {copy.backToRecords}
        </Link>
        {error ? (
          <div className="alert alert-error" role="alert">
            <span>{error}</span>
          </div>
        ) : null}
        {record ? (
          <>
            <RecordForm record={record} />
            {record.review_state === "draft" ? (
              <div className="mt-4 text-right">
                <button
                  className="btn btn-error btn-outline"
                  onClick={() => void deleteDraft()}
                  type="button"
                >
                  {copy.deleteDraft}
                </button>
              </div>
            ) : null}
            <section className="card bg-base-200 mt-6 shadow-sm">
              <div className="card-body">
                <h2 className="card-title">{copy.recordHistory}</h2>
                <ul className="timeline timeline-vertical timeline-compact">
                  {record.audit_timeline.map((event) => (
                    <li key={event.id}>
                      <div aria-hidden="true" className="timeline-middle">
                        •
                      </div>
                      <div className="timeline-end timeline-box">
                        {auditActionLabel(event.event_type, copy)}
                        <p className="text-base-content/70 mt-1 text-sm">
                          {new Date(event.created_at).toLocaleString(
                            language === "vi" ? "vi-VN" : "en-US",
                          )}
                        </p>
                        <dl className="text-base-content/70 mt-2 grid gap-1 text-sm">
                          {event.metadata.actor_role ? (
                            <div>
                              <dt className="inline font-semibold">
                                {copy.auditActorRole}:{" "}
                              </dt>
                              <dd className="inline">
                                {auditRoleLabel(
                                  event.metadata.actor_role,
                                  copy,
                                )}
                              </dd>
                            </div>
                          ) : null}
                          {event.metadata.reason ? (
                            <div>
                              <dt className="inline font-semibold">
                                {copy.auditReason}:{" "}
                              </dt>
                              <dd className="inline">
                                {event.metadata.reason}
                              </dd>
                            </div>
                          ) : null}
                          {event.metadata.revision ? (
                            <div>
                              <dt className="inline font-semibold">
                                {copy.auditRevision}:{" "}
                              </dt>
                              <dd className="inline">
                                {event.metadata.revision}
                              </dd>
                            </div>
                          ) : null}
                          {event.metadata.from_state &&
                          event.metadata.to_state ? (
                            <div>
                              <dt className="inline font-semibold">
                                {copy.auditTransition}:{" "}
                              </dt>
                              <dd className="inline">
                                {auditStateLabel(
                                  event.metadata.from_state,
                                  copy,
                                )}{" "}
                                →{" "}
                                {auditStateLabel(event.metadata.to_state, copy)}
                              </dd>
                            </div>
                          ) : null}
                          {event.metadata.previous_location_choice !==
                          undefined ? (
                            <div>
                              <dt className="inline font-semibold">
                                {copy.auditPreviousLocation}:{" "}
                              </dt>
                              <dd className="inline">
                                {auditLocationLabel(
                                  event.metadata.previous_location_choice,
                                  copy,
                                )}
                              </dd>
                            </div>
                          ) : null}
                          {event.metadata.location_choice !== undefined ? (
                            <div>
                              <dt className="inline font-semibold">
                                {copy.auditCurrentLocation}:{" "}
                              </dt>
                              <dd className="inline">
                                {auditLocationLabel(
                                  event.metadata.location_choice,
                                  copy,
                                )}
                              </dd>
                            </div>
                          ) : null}
                          {event.metadata.previous_note !== undefined ? (
                            <div>
                              <dt className="inline font-semibold">
                                {copy.auditPreviousNote}:{" "}
                              </dt>
                              <dd className="inline">
                                {auditText(event.metadata.previous_note, copy)}
                              </dd>
                            </div>
                          ) : null}
                          {event.metadata.note !== undefined ? (
                            <div>
                              <dt className="inline font-semibold">
                                {copy.auditCurrentNote}:{" "}
                              </dt>
                              <dd className="inline">
                                {auditText(event.metadata.note, copy)}
                              </dd>
                            </div>
                          ) : null}
                          {event.metadata.rejection_reason ? (
                            <div>
                              <dt className="inline font-semibold">
                                {copy.auditRejectionReason}:{" "}
                              </dt>
                              <dd className="inline">
                                {event.metadata.rejection_reason}
                              </dd>
                            </div>
                          ) : null}
                          {event.metadata.previous_correction_deadline ? (
                            <div>
                              <dt className="inline font-semibold">
                                {copy.auditPreviousDeadline}:{" "}
                              </dt>
                              <dd className="inline">
                                {new Date(
                                  String(
                                    event.metadata.previous_correction_deadline,
                                  ),
                                ).toLocaleString(
                                  language === "vi" ? "vi-VN" : "en-US",
                                )}
                              </dd>
                            </div>
                          ) : null}
                        </dl>
                      </div>
                    </li>
                  ))}
                </ul>
                {historyError ? (
                  <p className="text-error text-sm" role="alert">
                    {historyError}
                  </p>
                ) : null}
                {record.audit_timeline_next_page ? (
                  <button
                    className="btn btn-sm btn-ghost self-start"
                    disabled={historyLoading}
                    onClick={() => void loadOlderHistory()}
                    type="button"
                  >
                    {historyLoading ? (
                      <span
                        aria-hidden="true"
                        className="loading loading-spinner loading-sm"
                      />
                    ) : null}
                    {copy.loadOlderHistory}
                  </button>
                ) : null}
              </div>
            </section>
          </>
        ) : !error ? (
          <span
            className="loading loading-spinner"
            aria-label={copy.loadingRecord}
          />
        ) : null}
      </section>
    </AppPage>
  );
}
