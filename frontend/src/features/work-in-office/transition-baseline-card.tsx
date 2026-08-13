"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { apiFetch } from "../../lib/api";
import { apiErrorFromResponse, userFacingError } from "../../lib/errors";
import { languageFromDocument, messagesFor } from "../../lib/i18n";

type Baseline = {
  cutoff_month: string;
  cutoff_date: string;
  target_days: string;
  achieved_days: string;
  ratio_display: string;
  version: number;
  can_edit: boolean;
};

type BaselineState = {
  eligible: boolean;
  lock_reason: string | null;
  latest_cutoff_month: string | null;
  baseline: Baseline | null;
};

function previousMonth() {
  const now = new Date();
  now.setDate(1);
  now.setMonth(now.getMonth() - 1);
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function TransitionBaselineCard({ onSaved }: { onSaved: () => void }) {
  const language = languageFromDocument();
  const copy = messagesFor(language).dashboard;
  const common = messagesFor(language).common;
  const [state, setState] = useState<BaselineState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [cutoffMonth, setCutoffMonth] = useState(previousMonth);
  const [targetDays, setTargetDays] = useState("");
  const [achievedDays, setAchievedDays] = useState("0");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiFetch("/api/v1/transition-baseline/");
      if (!response.ok)
        throw await apiErrorFromResponse(response, copy.transitionUnavailable);
      const payload = (await response.json()) as BaselineState;
      setState(payload);
      if (payload.baseline) {
        setCutoffMonth(payload.baseline.cutoff_month);
        setTargetDays(payload.baseline.target_days);
        setAchievedDays(payload.baseline.achieved_days);
      } else if (payload.latest_cutoff_month) {
        setCutoffMonth(payload.latest_cutoff_month);
      }
    } catch (loadError) {
      setError(userFacingError(loadError, copy.transitionUnavailable));
    } finally {
      setLoading(false);
    }
  }, [copy.transitionUnavailable]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  if (loading)
    return (
      <div aria-label={copy.loadingModule} className="skeleton h-48 w-full" />
    );
  if (error)
    return (
      <div className="alert alert-error" role="alert">
        <span>{error}</span>
        <button
          className="btn btn-sm"
          onClick={() => void load()}
          type="button"
        >
          {common.retry}
        </button>
      </div>
    );
  if (!state?.eligible && !state?.baseline) return null;

  const baseline = state?.baseline;
  const locked = Boolean(baseline && !baseline.can_edit);
  const preview =
    Number(targetDays) > 0
      ? `${((Number(achievedDays || 0) / Number(targetDays)) * 100).toFixed(2)}%`
      : "N/A";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!window.confirm(copy.transitionConfirm)) return;
    setSaving(true);
    setError(null);
    try {
      const response = await apiFetch("/api/v1/transition-baseline/", {
        method: baseline ? "PUT" : "POST",
        body: JSON.stringify({
          cutoff_month: cutoffMonth,
          target_days: targetDays,
          achieved_days: achievedDays,
          ...(baseline ? { version: baseline.version } : {}),
        }),
      });
      if (!response.ok)
        throw await apiErrorFromResponse(response, copy.transitionSaveFailed);
      await load();
      onSaved();
    } catch (saveError) {
      setError(userFacingError(saveError, copy.transitionSaveFailed));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="card bg-base-200 shadow-sm">
      <div className="card-body">
        <div>
          <h2 className="card-title">{copy.transitionTitle}</h2>
          <p className="text-base-content/70 text-sm">{copy.transitionIntro}</p>
        </div>
        {locked ? (
          <div className="alert alert-info" role="status">
            <span>
              {copy.transitionLocked}: {baseline?.achieved_days} /{" "}
              {baseline?.target_days} ({baseline?.ratio_display}).{" "}
              {state?.lock_reason}
            </span>
          </div>
        ) : (
          <form className="space-y-4" onSubmit={submit}>
            <fieldset className="fieldset">
              <legend className="fieldset-legend">
                {copy.transitionCutoff}
              </legend>
              <input
                aria-label={copy.transitionCutoff}
                className="input w-full sm:max-w-xs"
                max={state?.latest_cutoff_month ?? previousMonth()}
                onChange={(event) => setCutoffMonth(event.target.value)}
                required
                type="month"
                value={cutoffMonth}
              />
              <p className="label">{copy.transitionCutoffHelp}</p>
            </fieldset>
            <div className="grid gap-4 sm:grid-cols-2">
              <fieldset className="fieldset">
                <legend className="fieldset-legend">
                  {copy.transitionTarget}
                </legend>
                <input
                  aria-label={copy.transitionTarget}
                  className="input w-full"
                  inputMode="decimal"
                  min="0"
                  onChange={(event) => setTargetDays(event.target.value)}
                  required
                  step="0.01"
                  type="number"
                  value={targetDays}
                />
              </fieldset>
              <fieldset className="fieldset">
                <legend className="fieldset-legend">
                  {copy.transitionAchieved}
                </legend>
                <input
                  aria-label={copy.transitionAchieved}
                  className="input w-full"
                  inputMode="decimal"
                  min="0"
                  onChange={(event) => setAchievedDays(event.target.value)}
                  required
                  step="0.01"
                  type="number"
                  value={achievedDays}
                />
              </fieldset>
            </div>
            <div className="alert alert-info" role="status">
              <span>{`${achievedDays || "0"} / ${targetDays || "0"} · ${preview}`}</span>
            </div>
            <div className="card-actions">
              <button
                className="btn btn-primary"
                disabled={saving}
                type="submit"
              >
                {saving ? copy.transitionSaving : copy.transitionSave}
              </button>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}
