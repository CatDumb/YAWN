# WIO transition baseline

Use this one-time, employee-entered carry-forward when moving from another WIO system. It is not a CSV import and does not copy legacy daily logs.

## Employee workflow

On Dashboard, choose **Bring your previous WIO balance** and enter:

- a completed legacy cutoff month;
- legacy target days; and
- legacy achieved days.

Both day values accept non-negative decimals with two places. If target is zero, achieved must also be zero. Achieved may exceed target. The saved ratio is `achieved / target`; zero target displays `N/A`.

The baseline represents all legacy history through the final day of the selected month. Its cutoff must precede the employee's earliest owned local WIO record; it is therefore valid to add a June balance after starting to log WIO in July. Existing post-cutoff WIO stays untouched, but means the newly saved baseline locks immediately. HR/admin can then correct only target and achieved days with an audit reason.

Planner intentions and WIO awaiting a manager's approval for other employees never affect this setup. Only the signed-in employee's own WIO dates matter.

## Ratio and reporting

YAWN records the baseline as one **Legacy carry-forward** ledger row on cutoff month-end:

`live target = legacy target + new expected project-status fractions`

`live achieved = legacy achieved + new approved in-office WIO days`

Reports containing cutoff include this synthetic row. Reports starting after cutoff contain local history only. Reports ending before cutoff return an error because legacy daily detail is unavailable. The carry-forward is limited to its fiscal period and is included in CSV exports and finalized ledger revisions.

## API

`GET /api/v1/transition-baseline/` returns setup eligibility or current baseline, lock state, version, derived ratio, and `latest_cutoff_month`. The picker uses `latest_cutoff_month` as its maximum valid completed month.

`POST /api/v1/transition-baseline/` creates baseline:

```json
{
  "cutoff_month": "2026-06",
  "target_days": "10.50",
  "achieved_days": "8.25"
}
```

`PUT /api/v1/transition-baseline/` updates an unlocked baseline and requires its current `version`. Validation failures return `400`; stale or missing update versions return `409`. A `400` overlap response means an owned WIO exists on or before the requested cutoff; choose a cutoff before that employee's earliest WIO record.

## Worked example

Legacy through June: target `10.50`, achieved `8.25`. July adds `1.50` expected days from project-status policy and one approved office record. Live result is `9.25 / 12.00`, displayed as `77.09%`.

For example, a manager with two pending WIO records dated in July may still enter a June balance. `GET` returns `latest_cutoff_month: "2026-06"`; saving the June balance preserves those July records and immediately returns a locked baseline. A July Planner intention does not change that result.

## Boundaries

- Only one baseline exists per employee membership.
- Cutoff must be completed, precede the earliest owned local WIO record, and remain in the same unfinalized fiscal period as that first post-cutoff record.
- Dates on or before cutoff cannot receive new WIO, including HR older-date overrides.
- No baseline is created automatically for existing users.
