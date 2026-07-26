# Subphase 3.6 Plan - App Shell and Dashboard

Status: implemented; local validation evidence recorded 2026-07-24. Acceptance remains blocked by release-candidate browser/accessibility and owner evidence.

## Outcome

Signed-in users receive a responsive, role-aware app shell and Two Horizons dashboard that joins today's action, verified fiscal progress, monthly activity, and private upcoming plans without embedding edit forms or manager workflow.

## Dependencies

- Subphase 3.3 shared protected app foundation and route metadata.
- Subphases 3.2-3.5 APIs for WIO, approvals count, ratio, heatmap data, and intentions.
- Raw-denominator ratio, Pending assignment, finalized revision, and early localization contracts.
- Existing YAWN design tokens and daisyUI conventions.

## Workstreams

### 1. Complete and polish protected app shell

- Extend the shared shell established in Subphase 3.3; do not create a second auth/navigation boundary.
- Complete persistent desktop sidebar and mobile top bar/modal drawer.
- Order navigation: Dashboard, Work-in-office, Planner, Reports, conditional Approvals, conditional Administration, Settings.
- Make Administration open Django Admin for HR/admin only.
- Add bottom user bar with initials, full name, active role, company, Profile, and Log out.
- Truncate long names visually while preserving complete accessible label.
- Enforce access again at route and API layers.
- Migrate WIO, Approvals, Reports, and Planner pages into the shared shell and remove page-specific session wrappers.

### 2. Two Horizons dashboard

- Lead first viewport with today's WIO state/action and fiscal verified progress plus plan coverage.
- Show approved/raw-expected equation, upward-rounded uncapped result, recoverable deficit or excess, Pending and Pending assignment claims, remaining eligible days, cutoff/revision state.
- Keep intentions visually distinct from earned credit.
- Add attention notice for drafts and rejected claims.
- Use navigation actions only: Record WIO, Continue draft, Fix rejected WIO, View ratio details.

### 3. Adjustable-month heatmap

- Build compact monthly grid with independent month selection across fiscal years.
- Represent approved, Pending assignment, pending, rejected, Not in office, draft, Expired pending, ineligible, Office intention, Home intention, and empty states using color plus symbol.
- Return the existing Planner intention commitment with each heatmap day so Firm and Flexible yellow treatments remain distinguishable.
- Keep a persistent visible legend and full accessible label per cell. Every legend item must render a small square swatch with the same semantic fill, border, and state treatment as its corresponding heatmap cell, beside its non-color symbol and text label; color names alone do not meet this requirement.
- Map cells to valid detail/create/edit actions; closed/ineligible cells explain why.
- Preserve month grid on empty success and dim only selected-month heatmap/activity content during month load; Today, ratio, and upcoming intentions stay stable.

### 4. Activity modules

- Show five newest WIO records from selected month.
- Show five upcoming intentions from today independent of selected month.
- Respect required desktop structure and mobile order.
- Keep approval queue entirely outside Dashboard.

### 5. Independent loading and failure behavior

- Load Today, ratio, heatmap, upcoming intentions, and activity independently after auth restoration.
- Use stable shape-matching skeletons.
- Give each failed module local error plus Retry while leaving others usable.
- Never infer or retain unlabeled ratio values after calculation failure.
- Use concise empty states with at most one CTA.
- Build all module copy and date labels through shared localization contracts; Subphase 3.7 supplies final catalogs and completeness enforcement.

## Testing strategy

- Test role navigation plus direct route/API denial.
- Test each heatmap state/action and accessible label, including Pending assignment and Expired pending. Verify every persistent legend item visibly renders its corresponding square swatch while retaining adjacent non-color symbol and text.
- Test month/fiscal independence, partial failures, retries, stale-month display, empty responses, mobile order, keyboard drawer/focus, reduced motion, zoom, and screen readers.

## Deliverables

- Completed protected responsive app shell with all Phase 3 feature pages migrated into it.
- `/dashboard` Two Horizons implementation.
- Adjustable-month accessible heatmap.
- Recent activity, upcoming intentions, attention, and local error modules.

## Exit criteria

- First viewport answers today's next action and fiscal outlook.
- Dashboard stays useful when any one data module fails.
- Heatmap meaning and actions remain understandable without color, pointer, or tooltip.

## Out of scope

- Dashboard edit forms, approval queue/module, icon-only collapsed sidebar, yearly heatmap, and export button.
