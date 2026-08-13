# Subphase 3.5 Plan - Private Planner

Status: implemented; local validation evidence recorded 2026-07-24. Acceptance remains blocked by release-candidate, manual privacy/accessibility, operations, and owner evidence.

## Outcome

Employees can privately plan future Office/Home intentions as single dates, ranges, or selected-weekday series and see plan coverage without changing verified WIO, approval, eligibility, or ratio results.

## Dependencies

- Accepted Subphase 3.2R fiscal coordinator, exact cutoff, versioned eligibility inputs, and required-version convention.
- Subphase 3.4 raw-denominator verified ratio, finalized-revision step, and report contracts.
- Subphase 3.3 protected app and localization infrastructure.

## Workstreams

### 1. Private storage model

- Add `WorkIntentionSeries` for pattern/shared defaults and `WorkIntentionOccurrence` for materialized dates.
- Enforce one occurrence per employee/date.
- Store Office/Home, Firm/Flexible, optional private note up to 300 characters, version, and optional series link.
- Restrict every product API to owner only; managers and HR/admin receive no product access to content.
- Ensure logs never contain note, location, or commitment content.

### 2. Creation and conflict preview

- Support single date, continuous range, and selected weekdays within required start/end dates.
- Allow today or later only and remain inside current Active fiscal period.
- Skip ineligible dates and return reasons.
- Preview conflicts before bulk/recurring save.
- Offer Skip existing by default or Replace existing; never silently overwrite notes.
- Apply each bulk operation transactionally.

### 3. Series editing and deletion

- Support one occurrence, this-and-future, and whole-series edits.
- Materialize an occurrence override for one-date edits.
- Split series for this-and-future edits.
- Restrict series edits/removal to today and future; never bulk-rewrite elapsed dates.
- Allow manual removal of past single intentions.
- Provide brief undo for single deletion and confirmation for series deletion.

### 4. Eligibility changes and fiscal purge

- Retain later-ineligible occurrence as Excluded, remove it from projection, and show reason plus previous details.
- Disable content edits for excluded occurrences but allow deletion.
- Leave recurring pattern intact while skipping excluded occurrence.
- At final cutoff, purge notes, occurrences, and series together.
- Register purge with the shared finalization coordinator; the transaction must be idempotent and must not mark the period Final until claim expiration, ledger freeze, and Planner purge all succeed.
- Notify users before scheduled purge without exposing intention content.

### 5. Plan-coverage projection

- Layer projection over verified calculator plus current full-period configuration.
- Count Firm Office as minimum and Flexible Office as optimistic extension; Home adds no office credit.
- Return raw expected-fraction sum, covered whole-day range, uncovered fractional amount, and unplanned eligible days.
- Use the same raw expected denominator as verified Reports; never integer-ceil it for projection.
- Label output as plan coverage, never predicted approval or verified credit.
- Treat missing project assignment as Benched.

### 6. Planner UI

- Build `/planner`: projection summary, month calendar, editor/details panel, Single/Bulk/Recurring toolbar, and upcoming list.
- Use calendar-left/panel-right desktop layout and stacked mobile layout.
- Require explicit location and commitment unless later defaults exist.
- Use Monday week start and current month initially.
- Preserve unsaved input and explain `409 Conflict` recovery.
- Store Planner copy as translation keys/parameters and use shared locale-aware dates so Subphase 3.7 can add catalogs without changing contracts.

## Testing strategy

- Test ownership, privacy/log redaction, unique dates, date/fiscal boundaries, ineligible skips, preview/save agreement, transactional rollback, series split/override, concurrency, exclusion, raw-denominator projection, and idempotent coordinated purge.
- Test failure/retry across claim expiration, ledger freeze, and Planner purge; period must never become partly Final.
- Add keyboard/mobile browser journeys for all three creation modes and edit/delete scopes.

## Deliverables

- Private intention schema, APIs, projection service, purge job, notifications, and `/planner` UI.
- Stable upcoming-intentions and projection contracts for Dashboard.

## Exit criteria

- Planner actions never alter factual WIO or verified ratio.
- No non-owner product path can reveal intention content.
- Previewed operations, stored occurrences, projection, coordinated finalization, and purge agree under tests.

## Out of scope

- Monthly recurrence, arbitrary intervals, open-ended/cross-period series, attachments, rich text, and Planner audit history.
