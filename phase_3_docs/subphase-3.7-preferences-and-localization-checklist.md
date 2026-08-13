# Subphase 3.7 Checklist - Preferences and Localization

Status: local implementation validation proven 2026-07-24; release acceptance BLOCKED by RC theme/language accessibility and owner evidence.

## Preferences and settings

- [ ] Owner-only preferences store theme, language, reduced motion, Planner defaults, and week start.
- [ ] Authenticated preferences persist server-side.
- [ ] Anonymous fallback works before login and reconciles after login.
- [ ] Settings shows read-only timezone and current fiscal period.
- [ ] Settings includes logout.
- [ ] Planner consumes configured defaults without changing historical intentions.

## Theme and motion

- [ ] Only System, Light, and Dark are exposed.
- [ ] System mode follows live OS changes.
- [ ] First paint uses stored/pre-auth theme without flash.
- [ ] All semantic states meet contrast in Light and Dark.
- [ ] Reduced-motion override affects all relevant transitions.

## Language

- [ ] All translation contracts introduced in Subphases 3.3-3.6 have English and Vietnamese entries.
- [ ] English is default until chosen; browser locale is first-visit hint.
- [ ] English and Vietnamese cover UI, validation, dates, ratio, Planner, Phase 3 email copy, and CSV headers.
- [ ] User-entered notes remain unchanged.
- [ ] URLs have no locale prefix.
- [ ] Document language updates on switch.
- [ ] Missing translation fails CI.
- [ ] Translation parameter mismatch fails CI.
- [ ] No hard-coded Phase 3 user-facing string bypasses localization.
- [ ] No mixed-language supported screen remains.

## Profile and exit gate

- [ ] Profile shows required identity and effective assignment fields.
- [ ] Preferred display name is editable.
- [ ] Legal name, email, role, base, manager, and assignment stay read-only.
- [ ] Persistence, reconciliation, theme, localization, long-text, mobile, zoom, and accessibility tests pass.
- [ ] Subphase 3.8 may begin.

## 2026-07-24 evidence classification

Environment: local Windows jsdom/frontend build stack; operator: Codex; artifacts: frontend coverage output. `npm run i18n:check`, lint, format check, standard typecheck, build, and coverage all passed. Settings/Profile contracts cover persisted versioned preferences and conflict feedback.

- **PROVEN locally:** preference/profile implementation, EN/VI catalog integrity, theme persistence behavior, and typed frontend contracts.
- **OPEN:** checklist acceptance mapping.
- **BLOCKED:** RC Light/Dark/System + EN/VI visual/accessibility matrix, anonymous-to-auth cross-device evidence, named owner, and sign-off. Boxes remain unchecked deliberately.
