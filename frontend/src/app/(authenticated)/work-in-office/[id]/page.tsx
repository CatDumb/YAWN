"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
  deleteWorkInOffice,
  getWorkInOffice,
  type WorkInOfficeRecordDetail,
} from "@/features/work-in-office/api";
import { AppPage } from "@/features/app-shell/app-page";
import { userFacingError } from "@/lib/errors";
import { RecordForm } from "@/features/work-in-office/record-form";
import { languageFromDocument, messagesFor } from "@/lib/i18n";

export default function WorkInOfficeDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const copy = messagesFor(languageFromDocument()).workInOffice;
  const router = useRouter();
  const [record, setRecord] = useState<WorkInOfficeRecordDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
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
                    <li key={`${event.event_type}-${event.created_at}`}>
                      <div className="timeline-middle">•</div>
                      <div className="timeline-end timeline-box">
                        {event.event_type
                          .replace("work_logs.", "")
                          .replaceAll("_", " ")}
                        <p className="text-base-content/70 mt-1 text-sm">
                          {new Date(event.created_at).toLocaleString()}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
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
