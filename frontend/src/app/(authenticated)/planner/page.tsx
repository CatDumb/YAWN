"use client";

import { useCallback, useEffect, useState } from "react";

import { AppPage } from "@/features/app-shell/app-page";
import { apiFetch } from "@/lib/api";
import { responseDetail } from "@/lib/errors";
import { formatMessage, languageFromDocument, messagesFor } from "@/lib/i18n";

type PreviewDay = {
  date: string;
  eligible: boolean;
  existing: boolean;
  reason: string | null;
};
type Intention = {
  id: number;
  date: string;
  location: string;
  commitment: string;
  note: string;
  excluded_reason: string;
  series_id: number | null;
  version: number;
};
type PlannerPreference = {
  planner_location: "" | "office" | "home";
  planner_commitment: "" | "firm" | "flexible";
};
type Projection = {
  period_name: string;
  expected_fraction_sum: string;
  minimum_planned_fraction: string;
  maximum_planned_fraction: string;
  gap_after_maximum: string;
  firm_office_days: number;
  flexible_office_days: number;
  unplanned_eligible_days: number;
};

type PlannerCopy = ReturnType<typeof messagesFor>["planner"];

function locationLabel(value: string, copy: PlannerCopy) {
  if (value === "office") return copy.office;
  if (value === "home") return copy.home;
  return value;
}

function commitmentLabel(value: string, copy: PlannerCopy) {
  if (value === "firm") return copy.firm;
  if (value === "flexible") return copy.flexible;
  return value;
}

export default function PlannerPage() {
  const language = languageFromDocument();
  const copy = messagesFor(language).planner;
  const weekdays = [
    copy.mondayShort,
    copy.tuesdayShort,
    copy.wednesdayShort,
    copy.thursdayShort,
    copy.fridayShort,
    copy.saturdayShort,
    copy.sundayShort,
  ];
  const today = new Date().toISOString().slice(0, 10);
  const [startDate, setStartDate] = useState(today);
  const [endDate, setEndDate] = useState(today);
  const [mode, setMode] = useState<"single" | "bulk" | "recurring">("single");
  const [location, setLocation] = useState("office");
  const [commitment, setCommitment] = useState("firm");
  const [note, setNote] = useState("");
  const [selectedWeekdays, setSelectedWeekdays] = useState<number[]>([]);
  const [replace, setReplace] = useState(false);
  const [preview, setPreview] = useState<PreviewDay[] | null>(null);
  const [previewKey, setPreviewKey] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [intentions, setIntentions] = useState<Intention[]>([]);
  const [pendingDelete, setPendingDelete] = useState<Intention | null>(null);
  const [projection, setProjection] = useState<Projection | null>(null);
  const [projectionError, setProjectionError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Intention | null>(null);
  const [editLocation, setEditLocation] = useState("office");
  const [editCommitment, setEditCommitment] = useState("firm");
  const [editNote, setEditNote] = useState("");
  const [editScope, setEditScope] = useState<"one" | "future" | "series">(
    "one",
  );
  const [confirmSeriesDelete, setConfirmSeriesDelete] = useState(false);

  const payload = {
    start_date: startDate,
    end_date: mode === "single" ? startDate : endDate,
    location,
    commitment,
    note,
    weekdays:
      mode === "recurring" && selectedWeekdays.length
        ? selectedWeekdays
        : undefined,
  };
  const recurrenceValid = mode !== "recurring" || selectedWeekdays.length > 0;
  const payloadKey = JSON.stringify(payload);

  async function read(response: Response) {
    if (!response.ok) {
      setMessage(await responseDetail(response, copy.saveFailed));
      return null;
    }
    return (await response.json()) as PreviewDay[] | { created?: number };
  }

  async function previewChanges() {
    setMessage(null);
    const body = await read(
      await apiFetch("/api/v1/planner/preview/", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    );
    if (Array.isArray(body)) {
      setPreview(body);
      setPreviewKey(payloadKey);
    }
  }

  async function save() {
    const body = await read(
      await apiFetch("/api/v1/planner/", {
        method: "POST",
        body: JSON.stringify({ ...payload, replace }),
      }),
    );
    if (body && !Array.isArray(body)) {
      setMessage(formatMessage(copy.savedCount, { count: body.created ?? 0 }));
      setPreview(null);
      setPreviewKey(null);
      void loadIntentions();
      void loadProjection();
    }
  }

  const loadIntentions = useCallback(async () => {
    const response = await apiFetch("/api/v1/planner/");
    if (!response.ok) {
      setMessage(copy.loadIntentionsFailed);
      return;
    }
    setIntentions((await response.json()) as Intention[]);
  }, [copy.loadIntentionsFailed]);
  const loadProjection = useCallback(async () => {
    const response = await apiFetch("/api/v1/planner/projection/");
    if (!response.ok) {
      setProjectionError(await responseDetail(response, copy.coverageFailed));
      return;
    }
    setProjection((await response.json()) as Projection);
    setProjectionError(null);
  }, [copy.coverageFailed]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadIntentions(), 0);
    return () => window.clearTimeout(timer);
  }, [loadIntentions]);
  useEffect(() => {
    const timer = window.setTimeout(() => void loadProjection(), 0);
    return () => window.clearTimeout(timer);
  }, [loadProjection]);
  useEffect(() => {
    void apiFetch("/api/v1/preferences/").then(async (response) => {
      if (!response.ok) return;
      const preference = (await response.json()) as PlannerPreference;
      if (preference.planner_location) setLocation(preference.planner_location);
      if (preference.planner_commitment)
        setCommitment(preference.planner_commitment);
    });
  }, []);

  useEffect(() => {
    if (!pendingDelete) return;
    const timer = window.setTimeout(() => {
      void (async () => {
        const response = await apiFetch(
          `/api/v1/planner/${pendingDelete.id}/?version=${pendingDelete.version}`,
          { method: "DELETE" },
        );
        if (!response.ok) {
          setMessage(copy.deleteChanged);
          void loadIntentions();
        }
        setPendingDelete(null);
      })();
    }, 5_000);
    return () => window.clearTimeout(timer);
  }, [copy.deleteChanged, loadIntentions, pendingDelete]);

  function scheduleDelete(intention: Intention) {
    setIntentions((current) =>
      current.filter((item) => item.id !== intention.id),
    );
    setPendingDelete(intention);
    setMessage(copy.deleteScheduled);
  }

  function undoDelete() {
    if (!pendingDelete) return;
    setIntentions((current) =>
      [...current, pendingDelete].sort((a, b) => a.date.localeCompare(b.date)),
    );
    setPendingDelete(null);
    setMessage(copy.deleteUndone);
  }

  function beginEdit(intention: Intention) {
    setEditing(intention);
    setEditLocation(intention.location);
    setEditCommitment(intention.commitment);
    setEditNote(intention.note);
    setEditScope("one");
    setConfirmSeriesDelete(false);
  }

  async function saveEdit() {
    if (!editing) return;
    const response = await apiFetch(`/api/v1/planner/${editing.id}/`, {
      method: "PATCH",
      body: JSON.stringify({
        version: editing.version,
        scope: editScope,
        location: editLocation,
        commitment: editCommitment,
        note: editNote,
      }),
    });
    if (!response.ok) {
      setMessage(await responseDetail(response, copy.editChanged));
      return;
    }
    setEditing(null);
    setMessage(copy.updated);
    void loadIntentions();
    void loadProjection();
  }

  async function deleteSeries() {
    if (!editing) return;
    const response = await apiFetch(
      `/api/v1/planner/${editing.id}/?version=${editing.version}&scope=series&confirm=true`,
      { method: "DELETE" },
    );
    if (!response.ok) {
      setMessage(await responseDetail(response, copy.deleteSeriesFailed));
      return;
    }
    setEditing(null);
    setConfirmSeriesDelete(false);
    setMessage(copy.seriesDeleted);
    void loadIntentions();
    void loadProjection();
  }

  return (
    <AppPage contentWidth="medium">
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
            <h2 className="card-title">{copy.coverageTitle}</h2>
            <p className="text-base-content/70 text-sm">{copy.coverageIntro}</p>
            {projection ? (
              <dl className="grid gap-3 sm:grid-cols-2">
                <div>
                  <dt className="text-base-content/70 text-sm">
                    {copy.rawExpectedFraction}
                  </dt>
                  <dd>{projection.expected_fraction_sum}</dd>
                </div>
                <div>
                  <dt className="text-base-content/70 text-sm">
                    {copy.firmMinimum}
                  </dt>
                  <dd>
                    {formatMessage(copy.firmMinimumValue, {
                      value: projection.minimum_planned_fraction,
                      days: projection.firm_office_days,
                    })}
                  </dd>
                </div>
                <div>
                  <dt className="text-base-content/70 text-sm">
                    {copy.flexibleMaximum}
                  </dt>
                  <dd>
                    {formatMessage(copy.flexibleMaximumValue, {
                      value: projection.maximum_planned_fraction,
                      days: projection.flexible_office_days,
                    })}
                  </dd>
                </div>
                <div>
                  <dt className="text-base-content/70 text-sm">
                    {copy.unplannedEligibleDays}
                  </dt>
                  <dd>
                    {formatMessage(copy.unplannedGapValue, {
                      days: projection.unplanned_eligible_days,
                      gap: projection.gap_after_maximum,
                    })}
                  </dd>
                </div>
              </dl>
            ) : projectionError ? (
              <div className="alert alert-error" role="alert">
                <span>{projectionError}</span>
                <button
                  className="btn btn-sm"
                  onClick={() => void loadProjection()}
                  type="button"
                >
                  {copy.retry}
                </button>
              </div>
            ) : (
              <div
                className="skeleton h-24 w-full"
                aria-label={copy.loadingCoverage}
              />
            )}
          </div>
        </section>
        <section className="card bg-base-200 shadow-sm">
          <div className="card-body">
            <fieldset className="grid gap-4 sm:grid-cols-2">
              <fieldset className="fieldset sm:col-span-2">
                <legend className="fieldset-legend">{copy.planningMode}</legend>
                <div className="join" role="radiogroup">
                  {(["single", "bulk", "recurring"] as const).map((item) => (
                    <button
                      aria-checked={mode === item}
                      className={`btn join-item ${mode === item ? "btn-primary" : ""}`}
                      key={item}
                      onClick={() => {
                        setMode(item);
                        if (item === "single") setEndDate(startDate);
                      }}
                      role="radio"
                      type="button"
                    >
                      {item === "single"
                        ? copy.singleDate
                        : item === "bulk"
                          ? copy.bulkRange
                          : copy.selectedWeekdays}
                    </button>
                  ))}
                </div>
              </fieldset>
              <label className="fieldset">
                <span className="fieldset-legend">{copy.startDate}</span>
                <input
                  className="input w-full"
                  type="date"
                  value={startDate}
                  onChange={(event) => {
                    setStartDate(event.target.value);
                    if (mode === "single") setEndDate(event.target.value);
                  }}
                />
              </label>
              <label className="fieldset">
                <span className="fieldset-legend">{copy.endDate}</span>
                <input
                  className="input w-full"
                  disabled={mode === "single"}
                  type="date"
                  value={endDate}
                  onChange={(event) => setEndDate(event.target.value)}
                />
              </label>
              <label className="fieldset">
                <span className="fieldset-legend">{copy.location}</span>
                <select
                  className="select w-full"
                  value={location}
                  onChange={(event) => setLocation(event.target.value)}
                >
                  <option value="office">{copy.office}</option>
                  <option value="home">{copy.home}</option>
                </select>
              </label>
              <label className="fieldset">
                <span className="fieldset-legend">{copy.commitment}</span>
                <select
                  className="select w-full"
                  value={commitment}
                  onChange={(event) => setCommitment(event.target.value)}
                >
                  <option value="firm">{copy.firm}</option>
                  <option value="flexible">{copy.flexible}</option>
                </select>
              </label>
              {mode === "recurring" ? (
                <fieldset className="fieldset sm:col-span-2">
                  <legend className="fieldset-legend">
                    {copy.repeatOnWeekdays}
                  </legend>
                  <div className="flex flex-wrap gap-3">
                    {weekdays.map((label, index) => (
                      <label className="label cursor-pointer gap-2" key={label}>
                        <input
                          className="checkbox"
                          checked={selectedWeekdays.includes(index)}
                          onChange={() =>
                            setSelectedWeekdays((current) =>
                              current.includes(index)
                                ? current.filter((day) => day !== index)
                                : [...current, index],
                            )
                          }
                          type="checkbox"
                        />
                        <span>{label}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              ) : null}
              <label className="fieldset sm:col-span-2">
                <span className="fieldset-legend">{copy.privateNote}</span>
                <textarea
                  className="textarea w-full"
                  maxLength={300}
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                />
              </label>
            </fieldset>
            <label className="label mt-4 cursor-pointer justify-start gap-3">
              <input
                className="checkbox"
                checked={replace}
                onChange={(event) => setReplace(event.target.checked)}
                type="checkbox"
              />
              <span>{copy.replaceExisting}</span>
            </label>
            <div className="card-actions mt-4">
              <button
                className="btn"
                disabled={!recurrenceValid}
                onClick={() => void previewChanges()}
                type="button"
              >
                {copy.previewChanges}
              </button>
              <button
                className="btn btn-primary"
                disabled={
                  !preview || previewKey !== payloadKey || !recurrenceValid
                }
                onClick={() => void save()}
                type="button"
              >
                {copy.saveIntentions}
              </button>
            </div>
            {message ? (
              <div className="alert alert-info alert-soft mt-4" role="status">
                <span>{message}</span>
                {pendingDelete ? (
                  <button
                    className="btn btn-sm"
                    onClick={undoDelete}
                    type="button"
                  >
                    {copy.undo}
                  </button>
                ) : null}
              </div>
            ) : null}
            {preview && previewKey !== payloadKey ? (
              <p className="text-warning mt-3 text-sm">{copy.previewStale}</p>
            ) : null}
          </div>
        </section>
        {preview ? (
          <section className="card bg-base-200 shadow-sm">
            <div className="card-body">
              <h2 className="card-title">{copy.previewTitle}</h2>
              <ul className="list">
                {preview.map((day) => (
                  <li className="list-row" key={day.date}>
                    <span>{day.date}</span>
                    <span className="text-base-content/70">
                      {day.eligible
                        ? day.existing
                          ? copy.existingIntention
                          : copy.readyToSave
                        : day.reason}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </section>
        ) : null}
        <section className="card bg-base-200 shadow-sm">
          <div className="card-body">
            <h2 className="card-title">{copy.upcomingTitle}</h2>
            <p className="text-base-content/70 text-sm">{copy.upcomingIntro}</p>
            {intentions.length ? (
              <ul className="list">
                {intentions.map((intention) => (
                  <li className="list-row" key={intention.id}>
                    <span>{intention.date}</span>
                    <span>
                      {formatMessage(copy.intentionLine, {
                        commitment: commitmentLabel(intention.commitment, copy),
                        location: locationLabel(intention.location, copy),
                      })}
                      {intention.excluded_reason
                        ? formatMessage(copy.excludedSuffix, {
                            reason: intention.excluded_reason,
                          })
                        : ""}
                    </span>
                    <button
                      className="btn btn-ghost btn-sm"
                      disabled={
                        Boolean(pendingDelete) ||
                        Boolean(intention.excluded_reason)
                      }
                      onClick={() => beginEdit(intention)}
                      type="button"
                    >
                      {copy.edit}
                    </button>
                    <button
                      className="btn btn-ghost btn-sm"
                      disabled={Boolean(pendingDelete)}
                      onClick={() => scheduleDelete(intention)}
                      type="button"
                    >
                      {copy.delete}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-base-content/70">{copy.noSavedIntentions}</p>
            )}
          </div>
        </section>
        {editing ? (
          <section className="card bg-base-200 shadow-sm">
            <div className="card-body">
              <h2 className="card-title">
                {formatMessage(copy.editTitle, { date: editing.date })}
              </h2>
              <fieldset className="grid gap-3 sm:grid-cols-2">
                <label className="fieldset">
                  <span className="fieldset-legend">{copy.location}</span>
                  <select
                    className="select w-full"
                    onChange={(event) => setEditLocation(event.target.value)}
                    value={editLocation}
                  >
                    <option value="office">{copy.office}</option>
                    <option value="home">{copy.home}</option>
                  </select>
                </label>
                <label className="fieldset">
                  <span className="fieldset-legend">{copy.commitment}</span>
                  <select
                    className="select w-full"
                    onChange={(event) => setEditCommitment(event.target.value)}
                    value={editCommitment}
                  >
                    <option value="firm">{copy.firm}</option>
                    <option value="flexible">{copy.flexible}</option>
                  </select>
                </label>
                <label className="fieldset sm:col-span-2">
                  <span className="fieldset-legend">{copy.privateNote}</span>
                  <textarea
                    className="textarea w-full"
                    maxLength={300}
                    onChange={(event) => setEditNote(event.target.value)}
                    value={editNote}
                  />
                </label>
                {editing.series_id ? (
                  <label className="fieldset sm:col-span-2">
                    <span className="fieldset-legend">
                      {copy.applyChangesTo}
                    </span>
                    <select
                      className="select w-full"
                      onChange={(event) =>
                        setEditScope(event.target.value as typeof editScope)
                      }
                      value={editScope}
                    >
                      <option value="one">{copy.thisOccurrenceOnly}</option>
                      <option value="future">{copy.thisAndFuture}</option>
                      <option value="series">{copy.wholeSeriesToday}</option>
                    </select>
                  </label>
                ) : null}
              </fieldset>
              {confirmSeriesDelete ? (
                <div className="alert alert-warning" role="alert">
                  <span>{copy.confirmSeriesDelete}</span>
                  <button
                    className="btn btn-error btn-sm"
                    onClick={() => void deleteSeries()}
                    type="button"
                  >
                    {copy.confirmSeriesDeleteAction}
                  </button>
                  <button
                    className="btn btn-sm"
                    onClick={() => setConfirmSeriesDelete(false)}
                    type="button"
                  >
                    {copy.cancel}
                  </button>
                </div>
              ) : null}
              <div className="card-actions">
                <button
                  className="btn"
                  onClick={() => setEditing(null)}
                  type="button"
                >
                  {copy.cancel}
                </button>
                {editing.series_id ? (
                  <button
                    className="btn btn-ghost"
                    onClick={() => setConfirmSeriesDelete(true)}
                    type="button"
                  >
                    {copy.deleteSeriesToday}
                  </button>
                ) : null}
                <button
                  className="btn btn-primary"
                  onClick={() => void saveEdit()}
                  type="button"
                >
                  {copy.saveChanges}
                </button>
              </div>
            </div>
          </section>
        ) : null}
      </section>
    </AppPage>
  );
}
