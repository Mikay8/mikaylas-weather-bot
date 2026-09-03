import type { CalibrationProposal } from "@/lib/api";

const OUTCOME_LABELS: Record<CalibrationProposal["outcome"], string> = {
  pr_opened: "PR opened",
  threshold_not_met: "No pattern yet",
  no_pattern: "No coherent pattern",
  backtest_rejected: "Backtest rejected change",
};

const OUTCOME_STYLES: Record<CalibrationProposal["outcome"], string> = {
  pr_opened: "border-[#2f6b4a] bg-[#123a26] text-[#7fd9a8]",
  threshold_not_met: "border-[var(--card-border)] bg-[var(--table-head-bg)] text-[var(--foreground-tertiary)]",
  no_pattern: "border-[var(--card-border)] bg-[var(--table-head-bg)] text-[var(--foreground-tertiary)]",
  backtest_rejected: "border-[#8a5a1f] bg-[#3a2a12] text-[#f0b866]",
};

export default function CalibrationProposalCard({
  proposal,
}: {
  proposal: CalibrationProposal;
}) {
  return (
    <div className="rounded border border-[var(--card-border)] bg-[var(--card-bg)] p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-xs text-[var(--foreground-secondary)]">
          {new Date(proposal.created_at).toLocaleString()}
        </span>
        <span
          className={
            "inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.06em] " +
            OUTCOME_STYLES[proposal.outcome]
          }
        >
          {OUTCOME_LABELS[proposal.outcome]}
        </span>
      </div>

      {proposal.old_factor !== null && proposal.new_factor !== null && (
        <p className="mb-1.5 font-mono text-[13px] text-[var(--foreground)]">
          STDEV_INFLATION_FACTOR: {proposal.old_factor} &rarr; {proposal.new_factor}
        </p>
      )}

      {proposal.reasoning && (
        <p className="mb-2.5 text-[13px] leading-relaxed text-[var(--foreground-secondary)]">
          {proposal.reasoning}
        </p>
      )}

      {proposal.pr_url && (
        <a
          href={proposal.pr_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded border border-[var(--card-border)] px-3 py-1.5 font-sans text-xs font-semibold text-[var(--foreground)] no-underline hover:bg-[var(--table-head-bg)]"
        >
          View PR →
        </a>
      )}
    </div>
  );
}
