"use client";

import type { DataCoverage, TableCoverage } from "@/lib/api";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

function formatCost(usd: number): string {
  if (usd < 0.01) return "<$0.01/mo";
  return `$${usd.toFixed(2)}/mo`;
}

function Row({
  label,
  coverage,
  totalBytes,
}: {
  label: string;
  coverage: TableCoverage;
  totalBytes: number;
}) {
  const pct = totalBytes > 0 ? Math.round((coverage.size_bytes / totalBytes) * 100) : 0;
  return (
    <div className="flex flex-col gap-2 rounded-sm border border-[var(--card-border)] bg-[var(--table-head-bg)] px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
      <div className="flex items-center justify-between gap-3 sm:block">
        <span className="text-sm font-medium">{label}</span>
        <span className="font-mono text-xs text-[var(--foreground-secondary)] sm:hidden">
          {coverage.row_count === 0 ? "no data yet" : `${coverage.row_count} rows`}
        </span>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 font-mono text-xs text-[var(--foreground-secondary)] sm:justify-end">
        <span className="hidden sm:inline">
          {coverage.row_count === 0
            ? "no data yet"
            : `${coverage.earliest} → ${coverage.latest} (${coverage.row_count} rows)`}
        </span>
        <span className="sm:hidden">
          {coverage.row_count === 0 ? null : `${coverage.earliest} → ${coverage.latest}`}
        </span>
        <span className="whitespace-nowrap text-[var(--foreground-tertiary)]">
          {formatBytes(coverage.size_bytes)} · {pct}%
        </span>
        <span className="whitespace-nowrap font-medium text-[var(--foreground)]">
          {formatCost(coverage.est_cost_usd_month)}
        </span>
      </div>
    </div>
  );
}

const LABELS: Record<keyof DataCoverage, string> = {
  forecasts: "Forecasts",
  market_snapshots: "Market snapshots",
  settlements: "Settlements",
  trades: "Trades",
  api_call_logs: "API logs",
};

export default function DataCoverageCard({ coverage }: { coverage: DataCoverage | null }) {
  if (!coverage)
    return <p className="text-sm text-[var(--foreground-secondary)]">Loading data coverage…</p>;

  const tables = Object.keys(LABELS) as (keyof DataCoverage)[];
  const totalBytes = tables.reduce((sum, key) => sum + coverage[key].size_bytes, 0);
  const totalCost = tables.reduce((sum, key) => sum + coverage[key].est_cost_usd_month, 0);

  return (
    <div className="space-y-2">
      {tables.map((key) => (
        <Row key={key} label={LABELS[key]} coverage={coverage[key]} totalBytes={totalBytes} />
      ))}
      <div className="flex items-center justify-between border-t border-[var(--card-border)] px-3 pt-3 font-mono text-xs text-[var(--foreground-secondary)]">
        <span>Total</span>
        <span>
          {formatBytes(totalBytes)} · {formatCost(totalCost)}
        </span>
      </div>
      <p className="px-3 pt-1 text-[11px] text-[var(--foreground-tertiary)]">
        Cost is an estimate from Railway&apos;s volume rate ($
        {(0.00000006 * 86400 * 30.44).toFixed(2)}/GB/month), not a real per-table bill — Railway
        meters the whole volume, not individual tables, and storage this small is unlikely to be
        what drives your bill.
      </p>
    </div>
  );
}
