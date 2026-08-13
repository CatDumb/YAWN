"use client";

import { languageFromDocument, messagesFor } from "@/lib/i18n";
import { AppPage } from "@/features/app-shell/app-page";

export default function AuthenticatedLoading() {
  const copy = messagesFor(languageFromDocument()).common;

  return (
    <AppPage aria-busy="true">
      <div className="space-y-6" role="status">
        <span className="sr-only">{copy.loading}</span>
        <header className="space-y-3">
          <div className="skeleton h-5 w-28" />
          <div className="skeleton h-9 w-64 max-w-full" />
          <div className="skeleton h-5 w-full max-w-2xl" />
        </header>
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="skeleton h-56 w-full" />
          <div className="skeleton h-56 w-full" />
        </div>
        <div className="skeleton h-72 w-full" />
      </div>
    </AppPage>
  );
}
