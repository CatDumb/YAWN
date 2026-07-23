"use client";

import { useEffect, useState } from "react";

import { AppShell } from "../../features/app-shell/app-shell";
import { apiFetch } from "../../lib/api";
import {
  formatMessage,
  languageFromDocument,
  messagesFor,
} from "../../lib/i18n";

type Profile = {
  legal_name: string;
  email: string;
  company: string;
  role: string;
  base_location: string | null;
  manager: {
    name: string;
    effective_from: string;
    effective_to: string | null;
  } | null;
  project_assignment: {
    project: string;
    effective_from: string;
    effective_to: string | null;
  } | null;
  policy: {
    assignment_status: string;
    expected_fraction?: string;
    effective_from?: string;
    effective_to?: string | null;
  };
};
type Preference = {
  theme: "system" | "light" | "dark";
  language: "en" | "vi";
  reduced_motion: boolean;
  planner_location: "" | "office" | "home";
  planner_commitment: "" | "firm" | "flexible";
  week_start: 0 | 1;
  display_name: string;
  version: number;
};

export default function ProfilePage() {
  const language = languageFromDocument();
  const messages = messagesFor(language);
  const copy = messages.profile;
  const [profile, setProfile] = useState<Profile | null>(null);
  const [preference, setPreference] = useState<Preference | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([
      apiFetch("/api/v1/profile/"),
      apiFetch("/api/v1/preferences/"),
    ]).then(async ([profileResponse, preferenceResponse]) => {
      if (profileResponse.ok)
        setProfile((await profileResponse.json()) as Profile);
      if (preferenceResponse.ok) {
        const saved = (await preferenceResponse.json()) as Preference;
        setPreference(saved);
        setDisplayName(saved.display_name);
      }
    });
  }, []);

  async function saveDisplayName() {
    if (!preference) return;
    const next = { ...preference, display_name: displayName };
    const response = await apiFetch("/api/v1/preferences/", {
      method: "PUT",
      body: JSON.stringify(next),
    });
    if (response.ok) {
      setPreference((await response.json()) as Preference);
      setMessage(copy.saved);
    } else setMessage(copy.saveFailed);
  }

  return (
    <AppShell>
      <main className="min-h-screen px-4 py-8 sm:px-8">
        <section className="mx-auto max-w-3xl space-y-6">
          <header>
            <p className="text-primary font-semibold">{copy.eyebrow}</p>
            <h1 className="mt-1 text-3xl font-bold tracking-tight">
              {copy.title}
            </h1>
            <p className="text-base-content/70 mt-2">{copy.intro}</p>
          </header>
          {profile ? (
            <section className="card bg-base-200 shadow-sm">
              <div className="card-body">
                <dl className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <dt className="text-base-content/70 text-sm">
                      {copy.legalName}
                    </dt>
                    <dd>{profile.legal_name || copy.notSet}</dd>
                  </div>
                  <div>
                    <dt className="text-base-content/70 text-sm">
                      {copy.email}
                    </dt>
                    <dd>{profile.email}</dd>
                  </div>
                  <div>
                    <dt className="text-base-content/70 text-sm">
                      {copy.companyRole}
                    </dt>
                    <dd>
                      {profile.company} / {profile.role}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-base-content/70 text-sm">
                      {copy.baseLocation}
                    </dt>
                    <dd>{profile.base_location ?? copy.notAssigned}</dd>
                  </div>
                  <div>
                    <dt className="text-base-content/70 text-sm">
                      {copy.manager}
                    </dt>
                    <dd>
                      {profile.manager
                        ? formatMessage(
                            profile.manager.effective_to
                              ? copy.effectiveRange
                              : copy.effectiveFrom,
                            {
                              name: profile.manager.name || copy.unnamed,
                              from: profile.manager.effective_from,
                              to: profile.manager.effective_to ?? "",
                            },
                          )
                        : copy.notAssigned}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-base-content/70 text-sm">
                      {copy.projectAssignment}
                    </dt>
                    <dd>
                      {profile.project_assignment
                        ? formatMessage(
                            profile.project_assignment.effective_to
                              ? copy.effectiveRange
                              : copy.effectiveFrom,
                            {
                              name: profile.project_assignment.project,
                              from: profile.project_assignment.effective_from,
                              to: profile.project_assignment.effective_to ?? "",
                            },
                          )
                        : copy.benched}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-base-content/70 text-sm">
                      {copy.currentPolicy}
                    </dt>
                    <dd>
                      {profile.policy.assignment_status.replaceAll("_", " ")}
                      {profile.policy.expected_fraction
                        ? formatMessage(copy.expectedFraction, {
                            value: profile.policy.expected_fraction,
                          })
                        : copy.noActiveRule}
                    </dd>
                  </div>
                </dl>
              </div>
            </section>
          ) : (
            <div
              className="skeleton h-72 w-full"
              aria-label={copy.loadingProfile}
            />
          )}
          <section className="card bg-base-200 shadow-sm">
            <div className="card-body">
              <h2 className="card-title">{copy.preferredDisplayName}</h2>
              <p className="text-base-content/70 text-sm">{copy.displayHelp}</p>
              <label className="fieldset">
                <span className="fieldset-legend">{copy.displayName}</span>
                <input
                  className="input w-full"
                  maxLength={150}
                  onChange={(event) => setDisplayName(event.target.value)}
                  value={displayName}
                />
              </label>
              <div className="card-actions">
                <button
                  className="btn btn-primary"
                  disabled={!preference}
                  onClick={() => void saveDisplayName()}
                  type="button"
                >
                  {copy.saveDisplayName}
                </button>
              </div>
              {message ? (
                <div className="alert alert-info alert-soft mt-3" role="status">
                  <span>{message}</span>
                </div>
              ) : null}
            </div>
          </section>
        </section>
      </main>
    </AppShell>
  );
}
