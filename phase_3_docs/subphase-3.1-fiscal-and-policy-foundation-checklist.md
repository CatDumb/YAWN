# Subphase 3.1 Checklist - Fiscal and Policy Foundation

Status: local implementation validation proven 2026-07-24; release acceptance BLOCKED. Reconcile this checklist only after [3.2R](subphase-3.2r-baseline-remediation-gate-checklist.md) proves the corrected fiscal, history, ratio, and migration contracts in a release candidate.

## Fiscal periods

- [ ] `FiscalPeriod` stores name, dates, exact timezone-aware cutoff, and persisted lifecycle state.
- [ ] Overlapping fiscal periods are rejected.
- [ ] At most one period can be Active.
- [ ] Default cutoff supports 14-day reconciliation.
- [ ] Audited reopen/correction path exists.
- [ ] Idempotent coordinator audits the fixed expire, freeze, and purge checkpoints before Final.
- [ ] Clone-previous-period admin workflow requires review before save.

## Policy data

- [ ] Base locations and projects are manageable in Django Admin.
- [ ] Employee project assignments are effective-dated.
- [ ] Employee and project base-location history is effective-dated.
- [ ] Benched, Same base, and Different base derive without daily employee choice.
- [ ] Each status has complete effective-dated rule coverage.
- [ ] Rule and assignment gaps/overlaps are rejected.
- [ ] Historically used versions cannot be changed or deleted.

## Exclusions and calculator

- [ ] Holidays, approved leave, and remote exceptions affect eligibility.
- [ ] Overlapping exclusions are deduplicated and explained.
- [ ] Ledger includes every calendar day.
- [ ] Raw expected fractions sum without integer ceiling.
- [ ] Official percentage uses approved/raw-expected and rounds upward to two decimal places.
- [ ] Approved whole-day WIO contributes one day.
- [ ] Zero expected days returns `N/A`.
- [ ] Calculator accepts an explicit as-of date.
- [ ] Projection remains separate from verified ratio calculation.
- [ ] Calculator is query-independent and finalized-ledger revision contract exists.

## Quality and exit gate

- [ ] Migrations apply cleanly and reverse where supported.
- [ ] Boundary, leap-day, timezone, fraction, gap, and overlap tests pass.
- [ ] Admin permissions and audit tests pass.
- [ ] Historical reproducibility test passes.
- [ ] Subphase 3.1 acceptance is reconciled through 3.2R.

## 2026-07-24 evidence classification

Environment: local Windows, Django `config.settings.test`; operator: Codex; artifact: local coverage XML. `uv run pytest --cov-report=xml:...` passed 114/114 at 83.43%; migration drift/apply and Django system check passed.

- **PROVEN locally:** fiscal lifecycle, effective-dated inputs, calculator, history, boundary, and finalization contracts exercised by backend tests.
- **OPEN:** checklist-to-3.2R evidence mapping.
- **BLOCKED:** production-like migration rehearsal, rollback/repair report, RC evidence, and named acceptance owner. Boxes remain unchecked because local tests are not release acceptance.
