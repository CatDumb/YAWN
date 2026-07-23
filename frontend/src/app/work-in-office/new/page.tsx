"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { RecordForm } from "../../../features/work-in-office/record-form";
import { AppShell } from "../../../features/app-shell/app-shell";
import { languageFromDocument, messagesFor } from "../../../lib/i18n";

function NewWorkInOfficeForm() {
  const searchParams = useSearchParams();
  const initialDate = searchParams.get("date") ?? undefined;
  return <RecordForm initialDate={initialDate} />;
}

export default function NewWorkInOfficePage() {
  const copy = messagesFor(languageFromDocument()).workInOffice;

  return (
    <AppShell>
      <main className="bg-base-100 min-h-screen px-4 py-8 sm:px-8">
        <section className="mx-auto max-w-2xl">
          <Link className="btn btn-ghost mb-5" href="/work-in-office">
            {copy.backToRecords}
          </Link>
          <Suspense fallback={<div className="skeleton h-96 w-full" />}>
            <NewWorkInOfficeForm />
          </Suspense>
        </section>
      </main>
    </AppShell>
  );
}
