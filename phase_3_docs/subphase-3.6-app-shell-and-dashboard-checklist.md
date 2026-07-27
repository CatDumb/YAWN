# Subphase 3.6 Checklist - App Shell and Dashboard

Status: local implementation validation proven 2026-07-24; release acceptance BLOCKED by RC/manual accessibility and owner evidence.

## App shell

- [ ] Existing Subphase 3.3 shell is extended rather than duplicated.
- [ ] Desktop sidebar and mobile modal drawer work.
- [x] Navigation-item hover and keyboard-focus targets fill the sidebar's padded inner lane; focused Playwright regression passed 2026-07-27 (local evidence only).
- [ ] Navigation order matches Phase 3 information architecture.
- [ ] Approvals appears only for eligible managers.
- [ ] Administration appears only for HR/admin and opens Django Admin.
- [ ] Route and API authorization remains independent of navigation visibility.
- [ ] User bar shows initials, full name, role, company, Profile, and Log out.
- [ ] Long names retain full accessible label.
- [ ] WIO, Approvals, Reports, Planner, and Dashboard share one session/navigation boundary.

## Dashboard modules

- [ ] Today's WIO card shows correct contextual action.
- [ ] Fiscal summary uses raw expected sum, upward-rounded percentage, and distinguishes verified progress from plan coverage.
- [ ] Deficit/excess, pending claims, remaining days, and cutoff state appear.
- [ ] Pending assignment count and finalized revision/correction state appear when applicable.
- [ ] Draft/rejected attention notice links to owning WIO surface.
- [ ] Recent activity shows five records from selected month.
- [ ] Upcoming list shows five intentions from today independent of selected month.
- [ ] Dashboard contains no edit forms or approval module.

## Heatmap

- [ ] Month can move across fiscal years independently of ratio period.
- [x] Localized weekday headers run Monday through Sunday, and day 1 aligns under its real weekday with leading cells non-interactive and accessibility-hidden; focused dashboard regression test passed 2026-07-27.
- [x] Every required WIO, Pending assignment, Expired pending, intention, exclusion, and empty state is represented by automated frontend coverage.
- [x] Meaning never relies on color alone; visible symbols and labels have automated coverage.
- [x] Persistent visible legend shows a small square swatch for every state, matching its heatmap cell's semantic fill, border, and state treatment; each swatch sits beside a visible non-color symbol and text label.
- [x] Legend is one vertical column with aligned decorative swatch, symbol, colon, and accessible text label in every row; focused dashboard regression test passed 2026-07-27.
- [ ] Every cell has complete accessible label.
- [ ] Cell actions follow record/date eligibility rules.
- [ ] Closed and ineligible cells explain why.
- [ ] Empty successful month retains grid.

## Resilience and exit gate

- [ ] Session restores before module requests.
- [ ] Each module loads, fails, and retries independently.
- [ ] Skeletons preserve final layout shape.
- [x] Old selected-month heatmap/activity data is visibly dimmed during replacement load while Today, ratio, and upcoming intentions remain stable; covered by deferred-response frontend regression test.
- [ ] Ratio failure never displays guessed data.
- [ ] Dashboard copy and dates use shared localization contracts.
- [ ] Mobile order, keyboard, screen-reader, 200% zoom, and partial-failure tests pass.
- [ ] Subphase 3.7 may begin.

## 2026-07-24 evidence classification

Environment: local Windows browser/test stack; operator: Codex; artifacts: frontend coverage output and Playwright output. Frontend 37/37 passes all configured coverage thresholds; local Playwright browser suite passed 2/2. Dashboard contract test exercises independent modules, all heatmap state labels, and month navigation.

- **PROVEN locally:** one shell boundary, dashboard data-module isolation, accessible non-color heatmap labels, and local browser/WIO integration.
- **OPEN:** checklist acceptance mapping.
- **BLOCKED:** RC screen-reader, 200% zoom, touch, mobile, reduced-motion, and partial-failure manual evidence; named owner/sign-off. Boxes remain unchecked deliberately.
