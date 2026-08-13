# Subphase 3.4 Checklist - Ratio and Reports

Status: local implementation validation proven 2026-07-24; release acceptance BLOCKED by RC/manual/owner evidence.

## Summary and ranges

- [ ] Fiscal-year-to-date summary runs through today.
- [ ] Summary exposes equation, raw expected-fraction sum, upward-rounded two-decimal percent, deficit/excess, Pending/Pending assignment counts, remaining days, period state, and revision identity.
- [ ] Official ratio uses approved days divided by raw expected-fraction sum without integer ceiling.
- [ ] Equation displays expected sum to two decimal places.
- [ ] Visual progress caps at 100% without capping displayed percentage.
- [ ] Zero expected days displays `N/A`.
- [ ] Fiscal, month, and custom ranges stay within one fiscal period.
- [ ] Cross-period request is rejected clearly.
- [ ] Range help explains additive raw fractions and independently rounded percentages.
- [ ] Intentions never enter verified totals.

## Ledger UI

- [ ] Complete response includes every calendar day.
- [ ] Default view shows eligible days plus exceptions.
- [ ] Excluded rows remain available.
- [ ] Each row explains eligibility, rule, expected fraction, WIO/review, credit, and rounding.
- [ ] Desktop table and mobile disclosures are keyboard accessible.
- [ ] Active/Reconciliation deficit uses warning treatment.
- [ ] Only locked final miss uses error treatment.

## CSV

- [ ] Export uses same calculation output as UI.
- [ ] Export contains complete unfiltered selected range.
- [ ] Fiscal ID/status, revision/correction identity, and exact range are included.
- [ ] Headers follow selected language; data values stay ISO-safe.
- [ ] Approver notes and all Planner data are excluded.
- [ ] Formula-injection protection is tested.
- [ ] Generation status and errors preserve current filters.

## Finalized revisions

- [ ] Active/Reconciliation results use immutable versioned inputs.
- [ ] Idempotent cutoff step freezes complete ledger, summary, and input references.
- [ ] Final reports and CSV read frozen revision rather than live configuration.
- [ ] Audited correction creates linked successor revision without erasing predecessor history.
- [ ] Finalization retry creates no duplicate or partial official revision.

## Quality and exit gate

- [ ] UI totals, API totals, and CSV totals match fixture results.
- [ ] Authorization and cross-company tests pass.
- [ ] Period-boundary, finalization, localization, encoding, and performance tests pass.
- [ ] Subphase 3.5 may begin.

## 2026-07-24 evidence classification

Environment: local Windows, Django test settings and jsdom component suite; operator: Codex; artifacts: temporary backend coverage XML and frontend coverage output. Backend full suite passed 114/114; frontend 37/37 passed. Reports page contracts cover shared ledger states and CSV export initiation.

- **PROVEN locally:** raw-denominator summary/ledger/CSV/frozen-revision contracts, privacy/formula safeguards, and report UI output.
- **OPEN:** checklist acceptance mapping and release-candidate export parity artifacts.
- **BLOCKED:** RC CSV/browser verification, manual accessibility/responsive review, named owner, and sign-off. Boxes remain unchecked deliberately.
