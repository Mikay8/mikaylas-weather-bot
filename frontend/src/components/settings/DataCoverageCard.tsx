"use client";

import type { DataCoverage, TableCoverage } from "@/lib/api";

function Row({ label, coverage }: { label: string; coverage: TableCoverage }) {
  return (
    <div className="flex items-center justify-between rounded-md bg-[var(--table-head-bg)] px-3 py-2.5">
      <span className="text-sm font-medium">{label}</span>
      <span className="text-xs text-neutral-500">
        {coverage.row_count === 0
          ? "no data yet"
          : `${coverage.earliest} → ${coverage.latest} (${coverage.row_count} rows)`}
      </span>
    </div>
  );
}

export default function DataCoverageCard({ coverage }: { coverage: DataCoverage | null }) {
  if (!coverage) return <p className="text-sm text-neutral-500">Loading data coverage…</p>;
  return (
    <div className="space-y-2">
      <Row label="Forecasts" coverage={coverage.forecasts} />
      <Row label="Market snapshots" coverage={coverage.market_snapshots} />
      <Row label="Settlements" coverage={coverage.settlements} />
    </div>
  );
}
