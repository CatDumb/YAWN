"use client";

import { Info } from "lucide-react";
import { useId, useState } from "react";

type Stream = {
  days: string;
  ratio: string;
  balance: string;
};

export function AuditStreamComparison({
  approved,
  selfSubmitted,
  selfApprovalApplies,
  approvedLabel,
  selfSubmittedLabel,
  expectedLabel,
  balanceLabel,
  explanation,
}: {
  approved: Stream;
  selfSubmitted: Stream;
  selfApprovalApplies: boolean;
  approvedLabel: string;
  selfSubmittedLabel: string;
  expectedLabel: string;
  balanceLabel: string;
  explanation: string;
}) {
  const [open, setOpen] = useState(false);
  const explanationId = useId();
  const streams = [
    [approvedLabel, approved],
    [selfSubmittedLabel, selfSubmitted],
  ] as const;

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        {streams.map(([label, stream]) => (
          <div
            className="stats stats-vertical bg-base-100 w-full shadow-sm"
            key={label}
          >
            <div className="stat gap-1 px-4 py-3">
              <div className="stat-title">{label}</div>
              <div className="stat-value text-2xl">{stream.ratio}</div>
              <div className="stat-desc">
                {stream.days} / {expectedLabel}
              </div>
              <div className="stat-desc">
                {balanceLabel}: {stream.balance}
              </div>
            </div>
          </div>
        ))}
      </div>
      {selfApprovalApplies ? (
        <div>
          <button
            aria-controls={explanationId}
            aria-expanded={open}
            aria-label={explanation}
            className="btn btn-ghost btn-xs"
            onClick={() => setOpen((value) => !value)}
            type="button"
          >
            <Info aria-hidden="true" size={16} />
            <span className="sr-only">{explanation}</span>
          </button>
          {open ? (
            <p className="text-base-content/70 mt-1 text-sm" id={explanationId}>
              {explanation}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
