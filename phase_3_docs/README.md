# Phase 3 Subphase Index

Phase 3 is split into nine delivery subphases plus one mandatory remediation gate. `overall.md` remains the product and scope authority. These files turn its delivery sequence into implementation plans and completion checklists.

| Subphase | Name | Status | Plan | Checklist |
| --- | --- | --- | --- | --- |
| 3.0 | Phase 2 Prerequisite Gate | Validated locally; RC acceptance blocked | [Plan](subphase-3.0-phase-2-prerequisite-gate-plan.md) | [Checklist](subphase-3.0-phase-2-prerequisite-gate-checklist.md) |
| 3.1 | Fiscal and Policy Foundation | Validated locally; RC acceptance blocked | [Plan](subphase-3.1-fiscal-and-policy-foundation-plan.md) | [Checklist](subphase-3.1-fiscal-and-policy-foundation-checklist.md) |
| 3.2 | WIO Records | Validated locally; RC acceptance blocked | [Plan](subphase-3.2-wio-records-plan.md) | [Checklist](subphase-3.2-wio-records-checklist.md) |
| 3.2R | Baseline Remediation Gate | Validated locally; RC acceptance blocked | [Plan](subphase-3.2r-baseline-remediation-gate-plan.md) | [Checklist](subphase-3.2r-baseline-remediation-gate-checklist.md) |
| 3.3 | Manager Approval | Validated locally; RC acceptance blocked | [Plan](subphase-3.3-manager-approval-plan.md) | [Checklist](subphase-3.3-manager-approval-checklist.md) |
| 3.4 | Ratio and Reports | Validated locally; RC acceptance blocked | [Plan](subphase-3.4-ratio-and-reports-plan.md) | [Checklist](subphase-3.4-ratio-and-reports-checklist.md) |
| 3.5 | Private Planner | Validated locally; RC acceptance blocked | [Plan](subphase-3.5-private-planner-plan.md) | [Checklist](subphase-3.5-private-planner-checklist.md) |
| 3.6 | App Shell and Dashboard | Validated locally; RC acceptance blocked | [Plan](subphase-3.6-app-shell-and-dashboard-plan.md) | [Checklist](subphase-3.6-app-shell-and-dashboard-checklist.md) |
| 3.7 | Preferences and Localization | Validated locally; RC acceptance blocked | [Plan](subphase-3.7-preferences-and-localization-plan.md) | [Checklist](subphase-3.7-preferences-and-localization-checklist.md) |
| 3.8 | Hardening and Release Gate | Local hardening validated; release blocked | [Plan](subphase-3.8-hardening-and-release-gate-plan.md) | [Checklist](subphase-3.8-hardening-and-release-gate-checklist.md) |

## Execution rules

- Complete subphases in numeric order unless a plan explicitly identifies safe parallel work.
- Treat 3.2R acceptance as a hard dependency of releasing 3.3, even though implementation exists through 3.8.
- Treat each checklist's exit gate as required before dependent work is released.
- Distinguish implementation from acceptance; unchecked acceptance boxes remain open even when code exists.
- Keep frontend and backend authorization independent; hidden navigation is never an access control.
- Keep all deadlines and date eligibility based on server time in `Asia/Ho_Chi_Minh`.
- Update `overall.md` first when a product decision changes scope, privacy, fiscal calculation, workflow, or ordering.

## Release evidence

- Subphase 3.8 release evidence and runbook: [Release evidence ledger](subphase-3.8-release-evidence.md)
