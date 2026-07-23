# Subphase 3.5 Checklist - Private Planner

Status: local implementation validation proven 2026-07-24; release acceptance BLOCKED by RC/manual privacy/accessibility/operations/owner evidence.

## Privacy and storage

- [ ] Series and materialized occurrence models exist.
- [ ] Database enforces one intention per employee/date.
- [ ] Note is plain text and limited to 300 characters.
- [ ] Only owner can access intention content through product APIs/UI.
- [ ] Managers and HR/admin have no product content access.
- [ ] Operational/security logs exclude note, location, and commitment.

## Creation and conflict handling

- [ ] Single, bulk range, and selected-weekday recurring modes work.
- [ ] New intentions start today or later within current Active fiscal period.
- [ ] Ineligible dates are skipped with reasons.
- [ ] Bulk/recurring conflict preview runs before save.
- [ ] Skip existing is default; Replace existing is explicit.
- [ ] Existing notes are never silently overwritten.
- [ ] Bulk writes are atomic.

## Editing, exclusion, and deletion

- [ ] One-occurrence edit creates an override.
- [ ] This-and-future edit splits series correctly.
- [ ] Whole-series operation changes only today/future occurrences.
- [ ] Elapsed series dates are never bulk-rewritten.
- [ ] Single delete has brief undo; series delete requires confirmation.
- [ ] Later-ineligible intention becomes Excluded and leaves projection.
- [ ] Excluded intention remains readable/deletable but not editable.

## Projection, purge, and UI

- [ ] Firm Office defines minimum and Flexible Office defines optimistic maximum.
- [ ] Home adds no office credit.
- [ ] Projection shows coverage range, gap, and unplanned eligible days.
- [ ] Projection uses raw expected-fraction sum without integer ceiling.
- [ ] UI never labels projection as verified credit or predicted approval.
- [ ] Finalization coordinator purges notes, occurrences, and series together idempotently.
- [ ] Period cannot become Final unless claim expiration, ledger freeze, and Planner purge all succeed.
- [ ] Retry never duplicates revisions, expirations, or purge effects.
- [ ] Pre-purge notification exists without private content.
- [ ] Planner copy uses shared translation-key and locale-aware date contracts.
- [ ] Desktop, mobile, keyboard, conflict, privacy, projection, and purge tests pass.
- [ ] Subphase 3.6 may begin.

## 2026-07-24 evidence classification

Environment: local Windows, Django test settings and jsdom component suite; operator: Codex; artifacts: temporary backend coverage XML and frontend coverage output. Backend full suite passed 114/114; frontend 37/37 passed. Planner page contracts cover recurring preview, atomic save response, edit, and series deletion.

- **PROVEN locally:** owner-private storage/API, preview/save/replace/series/finalization contracts and Planner UI mutation paths.
- **OPEN:** checklist acceptance mapping and release-candidate privacy/export/operations evidence.
- **BLOCKED:** RC manual privacy/keyboard/mobile review, purge operations rehearsal, named owner, and sign-off. Boxes remain unchecked deliberately.
