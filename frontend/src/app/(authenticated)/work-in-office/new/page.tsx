"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { AppPage } from "@/features/app-shell/app-page";
import { RecordForm } from "@/features/work-in-office/record-form";
import { languageFromDocument, messagesFor } from "@/lib/i18n";

function NewWorkInOfficeForm() {
  const searchParams = useSearchParams();
  const initialDate = searchParams.get("date") ?? undefined;
  return <RecordForm initialDate={initialDate} />;
}

export default function NewWorkInOfficePage() {
  const copy = messagesFor(languageFromDocument()).workInOffice;

  return (
    <AppPage contentWidth="narrow">
      <section>
        <Link className="btn btn-ghost mb-5" href="/work-in-office">
          {copy.backToRecords}
        </Link>
        <Suspense fallback={<div className="skeleton h-96 w-full" />}>
          <NewWorkInOfficeForm />
        </Suspense>
      </section>
    </AppPage>
  );
}
