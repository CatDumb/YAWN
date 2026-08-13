# Subphase 3.7 Plan - Preferences and Localization

Status: implemented; local validation evidence recorded 2026-07-24. Acceptance remains blocked by release-candidate theme/language accessibility and owner evidence.

## Outcome

Users can persist theme, language, reduced-motion, and Planner defaults; inspect profile/assignment context; and use every Phase 3 flow in English or Vietnamese before and after sign-in without theme flash or mixed-language screens.

## Dependencies

- Stable Phase 3 routes and copy from Subphases 3.2-3.6.
- Existing public authentication surface and authenticated user model.
- Translation-key, parameter, locale-aware date, rejection-email, CSV, Planner, shell, and Dashboard contracts established in Subphases 3.3-3.6.

## Workstreams

### 1. Preferences model and API

- Add/update `UserPreference` for theme, language, reduced-motion override, Planner default location/commitment, and week start.
- Validate allowed values and enforce owner-only access.
- Persist authenticated choices server-side.
- Use local pre-auth fallback and reconcile it after login.

### 2. Theme

- Support only System, Light, and Dark.
- Follow OS theme changes live in System mode.
- Apply pre-hydration theme selection to prevent visible flash.
- Verify semantic state tokens and contrast independently in both themes.
- Keep novelty daisyUI themes unavailable.

### 3. Localization

- Complete English and Vietnamese catalogs for the keys/contracts already introduced across UI, validation, dates, ratio explanations, Planner, rejection email, and CSV headers.
- Use English until chosen; browser locale is first-visit hint only.
- Keep URLs unprefixed and set document language correctly.
- Leave user-entered notes unchanged.
- Make missing translations fail CI and remove hard-coded user-facing strings.
- Add a migration audit that finds and converts remaining hard-coded Phase 3 copy without changing API semantics.

### 4. Settings

- Build `/settings` for theme, language, Planner defaults, week start, reduced motion, read-only company timezone/current fiscal period, and logout.
- Make updates optimistic only where rollback is clear; otherwise show save state.
- Ensure controls, validation, announcements, and help text localize accessibly.

### 5. Profile

- Build `/profile` showing full name, email, company, role, base location, manager, and active project/policy assignment with effective dates.
- Permit editing preferred display name only.
- Keep legal/full name, email, role, base, manager, and assignment admin-managed.

### 6. Cross-product adaptation

- Audit every Phase 3 page, Pending assignment/Expired pending state, finalized revision/correction state, empty/error/loading state, dialog, email, and CSV path in both languages and themes.
- Test long Vietnamese text, mobile widths, 200% zoom, date formatting, and screen-reader labels.
- Respect reduced-motion choice across transitions, skeletons, drawer, and undo feedback.

## Testing strategy

- Add preference ownership/persistence tests and anonymous-to-auth reconciliation tests.
- Run translation completeness checks in CI.
- Contract-test that translation parameters remain type/shape compatible across both catalogs.
- Add browser coverage for first visit, OS theme change, reload, sign-in/out, language switch, and cross-device server persistence.
- Complete visual/accessibility checks in both languages and themes.

## Deliverables

- Preference storage/API, pre-auth fallback, theme bootstrap, translation catalogs/checks, `/settings`, and `/profile`.
- Localized Phase 3 UI, validation, email copy, and CSV headers.

## Exit criteria

- Selected settings persist correctly before and after sign-in.
- No mixed-language screens or first-paint theme flash remain in supported journeys.
- English/Vietnamese and Light/Dark/System combinations meet accessibility and layout requirements.

## Out of scope

- Locale-prefixed routes, extra daisyUI themes, editable admin-managed identity fields, and translation of user notes.
