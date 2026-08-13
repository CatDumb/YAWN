# Subphase 3.4 Plan - Ratio and Reports

Status: implemented; local validation evidence recorded 2026-07-24. Acceptance remains blocked by release-candidate, manual, and owner evidence.

## Outcome

Employees can inspect raw-denominator fiscal-year verified progress, understand each day's calculation, calculate an in-period custom range, inspect finalized revision identity, and export a private factual CSV whose totals match the ledger.

## Dependencies

- Accepted Subphase 3.2R query-independent calculator, versioned inputs, exact cutoff, and finalized-ledger revision contract.
- Subphase 3.3 approval states, finalization expiration step, protected app foundation, and localization infrastructure.

## Workstreams

### 1. Ratio API

- Expose fiscal-year-to-date calculation through today for Active period.
- Return approved days, raw expected-fraction sum, upward-rounded two-decimal percentage, equation, deficit/excess, Pending and Pending assignment counts, eligible days remaining, period status, revision identity, and provisional/final state.
- Use `approved days / raw expected-fraction sum`; display the denominator to two decimals and never apply an integer ceiling.
- Cap only visual progress at 100%; preserve uncapped numeric result.
- Return exact per-day ledger from domain service, not a second calculation path.

### 2. Report range controls

- Support fiscal period, month, and custom range inside one fiscal period.
- Reject cross-period calculations.
- Allow historical period switching and finalized summaries without merging denominators.
- Explain that raw expected fractions are additive while independently displayed percentages may differ because each percentage rounds upward to two decimals.

### 3. Explainable ledger UI

- Build `/reports` with filters and summary.
- Include every calendar day; default UI to eligible days plus exceptions while keeping excluded rows discoverable.
- Show date, eligibility/reason, project status/rule version, expected fraction, location, review state, credit, and range rounding.
- Use desktop table and mobile disclosure rows.
- Use amber for recoverable Active/Reconciliation deficit and error styling only for locked final miss.
- Never count intentions or predict claim outcomes.

### 4. Finalized ledger revisions

- During Active/Reconciliation, read recalculated results from immutable effective-dated inputs.
- Register an idempotent finalization step that freezes complete per-day ledgers, summaries, and input-version references before the period becomes Final.
- Serve Final reports from the frozen revision.
- On audited reopen/correction, create a linked successor revision and retain prior revision metadata/history.
- Expose the revision identifier and correction status in report and CSV metadata.

### 5. Personal CSV export

- Export complete unfiltered ledger for selected fiscal/month/custom range.
- Include fiscal-period identifier/status, revision identifier, correction status, exact range, localized headers, and ISO-safe values.
- Exclude approver-note text, Planner intentions, and private Planner notes.
- Report generation state and failure without losing selected filters.
- Protect spreadsheet consumers against CSV formula injection.
- Build headers and generation messages through the localization infrastructure established in Subphase 3.3.

### 6. Performance and integrity

- Prevent per-day query growth through measured query plans/prefetching.
- Keep calculator output as shared source for screen and CSV.
- Add traceable operational errors without sensitive ledger or note content.
- Verify finalized report reads do not silently fall back to live recalculation.

## Testing strategy

- Contract-test raw-denominator math, upward percentage rounding, summary, ledger, filtering, period boundary, provisional/final revisions, and zero-denominator behavior.
- Compare UI and CSV totals against calculator fixtures.
- Test finalization retry, correction lineage, frozen-read enforcement, and historical base/assignment/rule changes.
- Test localization, encoding, formula injection, authorization, large-period performance, and private-field exclusion.

## Deliverables

- Ratio/report APIs and `/reports` UI.
- Complete explainable ledger.
- Frozen finalized-ledger revisions with correction lineage.
- Personal localized CSV export.
- Stable summary contract for later Dashboard use.

## Exit criteria

- A user can trace every numerator and denominator contribution to a ledger row.
- Final reports remain identical after later configuration changes unless an audited successor revision is created.
- CSV exactly matches complete ledger totals while excluding private data.
- Cross-period and unauthorized report access fail safely.

## Out of scope

- PDF, manager/admin exports, merged cross-year ratios, and standalone monthly compliance verdicts.
