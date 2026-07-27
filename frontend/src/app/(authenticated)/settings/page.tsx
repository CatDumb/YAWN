"use client";

import { useEffect, useState } from "react";

import { AppPage } from "@/features/app-shell/app-page";
import { apiFetch } from "@/lib/api";
import { messagesFor } from "@/lib/i18n";

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
type Context = {
  company_date: string;
  timezone: string;
  fiscal_period: {
    name: string;
    state: string;
    start_date: string;
    end_date: string;
  } | null;
};

const initial: Preference = {
  theme: "system",
  language: "en",
  reduced_motion: false,
  planner_location: "",
  planner_commitment: "",
  week_start: 1,
  display_name: "",
  version: 1,
};

function applyPreference(preference: Preference) {
  localStorage.setItem("yawn.preferences", JSON.stringify(preference));
  const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme =
    preference.theme === "dark" || (preference.theme === "system" && dark)
      ? "yawn-dark"
      : "yawn-light";
  document.documentElement.lang = preference.language;
  document.documentElement.dataset.reducedMotion = preference.reduced_motion
    ? "reduce"
    : "";
  window.dispatchEvent(new Event("yawn:preferences"));
}

export default function SettingsPage() {
  const [preference, setPreference] = useState(initial);
  const [context, setContext] = useState<Context | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const copy = messagesFor(preference.language).settings;

  useEffect(() => {
    void Promise.all([
      apiFetch("/api/v1/preferences/"),
      apiFetch("/api/v1/work-in-office/meta/"),
    ]).then(async ([preferenceResponse, contextResponse]) => {
      if (preferenceResponse.ok) {
        const saved = (await preferenceResponse.json()) as Preference;
        setPreference(saved);
        applyPreference(saved);
      }
      if (contextResponse.ok)
        setContext((await contextResponse.json()) as Context);
    });
  }, []);
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if (preference.theme === "system") applyPreference(preference);
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [preference]);

  async function save() {
    setSaving(true);
    setMessage(null);
    const response = await apiFetch("/api/v1/preferences/", {
      method: "PUT",
      body: JSON.stringify(preference),
    });
    if (response.ok) {
      const saved = (await response.json()) as Preference;
      setPreference(saved);
      applyPreference(saved);
      setMessage(copy.settingsSaved);
    } else setMessage(copy.settingsSaveFailed);
    setSaving(false);
  }

  async function logOut() {
    const response = await apiFetch("/api/v1/auth/logout/", { method: "POST" });
    if (response.ok) window.location.assign("/");
    else setMessage(copy.logoutFailed);
  }

  return (
    <AppPage contentWidth="narrow">
      <section className="space-y-6">
        <header>
          <p className="text-primary font-semibold">{copy.eyebrow}</p>
          <h1 className="mt-1 text-3xl font-bold tracking-tight">
            {copy.title}
          </h1>
          <p className="text-base-content/70 mt-2">{copy.intro}</p>
        </header>
        <section className="card bg-base-200 shadow-sm">
          <div className="card-body">
            <fieldset className="grid gap-4">
              <label className="fieldset">
                <span className="fieldset-legend">{copy.theme}</span>
                <select
                  className="select w-full"
                  onChange={(event) =>
                    setPreference({
                      ...preference,
                      theme: event.target.value as Preference["theme"],
                    })
                  }
                  value={preference.theme}
                >
                  <option value="system">{copy.system}</option>
                  <option value="light">{copy.light}</option>
                  <option value="dark">{copy.dark}</option>
                </select>
              </label>
              <label className="fieldset">
                <span className="fieldset-legend">{copy.language}</span>
                <select
                  className="select w-full"
                  onChange={(event) =>
                    setPreference({
                      ...preference,
                      language: event.target.value as Preference["language"],
                    })
                  }
                  value={preference.language}
                >
                  <option value="en">{copy.english}</option>
                  <option value="vi">{copy.vietnamese}</option>
                </select>
              </label>
              <label className="label cursor-pointer justify-start gap-3">
                <input
                  checked={preference.reduced_motion}
                  className="checkbox"
                  onChange={(event) =>
                    setPreference({
                      ...preference,
                      reduced_motion: event.target.checked,
                    })
                  }
                  type="checkbox"
                />
                <span>{copy.reducedMotion}</span>
              </label>
              <div className="divider">{copy.plannerDefaults}</div>
              <label className="fieldset">
                <span className="fieldset-legend">{copy.defaultLocation}</span>
                <select
                  className="select w-full"
                  onChange={(event) =>
                    setPreference({
                      ...preference,
                      planner_location: event.target
                        .value as Preference["planner_location"],
                    })
                  }
                  value={preference.planner_location}
                >
                  <option value="">{copy.askEachTime}</option>
                  <option value="office">{copy.office}</option>
                  <option value="home">{copy.home}</option>
                </select>
              </label>
              <label className="fieldset">
                <span className="fieldset-legend">
                  {copy.defaultCommitment}
                </span>
                <select
                  className="select w-full"
                  onChange={(event) =>
                    setPreference({
                      ...preference,
                      planner_commitment: event.target
                        .value as Preference["planner_commitment"],
                    })
                  }
                  value={preference.planner_commitment}
                >
                  <option value="">{copy.askEachTime}</option>
                  <option value="firm">{copy.firm}</option>
                  <option value="flexible">{copy.flexible}</option>
                </select>
              </label>
              <label className="fieldset">
                <span className="fieldset-legend">{copy.weekStarts}</span>
                <select
                  className="select w-full"
                  onChange={(event) =>
                    setPreference({
                      ...preference,
                      week_start: Number(event.target.value) as 0 | 1,
                    })
                  }
                  value={preference.week_start}
                >
                  <option value={1}>{copy.monday}</option>
                  <option value={0}>{copy.sunday}</option>
                </select>
              </label>
            </fieldset>
            <div className="card-actions mt-5">
              <button
                className="btn btn-primary"
                disabled={saving}
                onClick={() => void save()}
                type="button"
              >
                {saving ? `${copy.savePreferences}...` : copy.savePreferences}
              </button>
            </div>
            {message ? (
              <div className="alert alert-info alert-soft mt-4" role="status">
                <span>{message}</span>
              </div>
            ) : null}
          </div>
        </section>
        <section className="card bg-base-200 shadow-sm">
          <div className="card-body">
            <h2 className="card-title">{copy.companyContext}</h2>
            {context ? (
              <dl className="grid gap-3 text-sm">
                <div>
                  <dt className="text-base-content/70">
                    {copy.companyTimezone}
                  </dt>
                  <dd>{context.timezone}</dd>
                </div>
                <div>
                  <dt className="text-base-content/70">
                    {copy.currentFiscalPeriod}
                  </dt>
                  <dd>
                    {context.fiscal_period
                      ? `${context.fiscal_period.name} / ${context.fiscal_period.state} / ${context.fiscal_period.start_date} to ${context.fiscal_period.end_date}`
                      : copy.noPeriod}
                  </dd>
                </div>
              </dl>
            ) : (
              <span
                className="loading loading-spinner loading-sm"
                aria-label={copy.loadingCompanyContext}
              />
            )}
          </div>
        </section>
        <section className="card bg-base-200 shadow-sm">
          <div className="card-body">
            <h2 className="card-title">{copy.session}</h2>
            <div className="card-actions">
              <button
                className="btn"
                onClick={() => void logOut()}
                type="button"
              >
                {messagesFor(preference.language).shell.logOut}
              </button>
            </div>
          </div>
        </section>
      </section>
    </AppPage>
  );
}
