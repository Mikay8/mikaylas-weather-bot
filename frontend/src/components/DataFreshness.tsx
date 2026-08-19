"use client";

import type { DataStatus } from "@/lib/api";

function minutesAgo(iso: string | null, now: Date): number | null {
  if (!iso) return null;
  return Math.round((now.getTime() - new Date(iso).getTime()) / 60000);
}

function ageLabel(mins: number | null): string {
  if (mins === null) return "never pulled";
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  return `${hours}h ago`;
}

// Data is only ever as fresh as the last manual/cron pull — no continuous
// live stream. Flag anything stale so it isn't mistaken for real-time.
const STALE_MINUTES = 180;

export default function DataFreshness({ status }: { status: DataStatus }) {
  const now = new Date(status.server_time);
  const forecastAge = minutesAgo(status.last_forecast_pull, now);
  const marketAge = minutesAgo(status.last_market_pull, now);

  const stale =
    forecastAge === null ||
    marketAge === null ||
    forecastAge > STALE_MINUTES ||
    marketAge > STALE_MINUTES;

  return (
    <div
      className={`mt-2 inline-flex flex-wrap items-center gap-x-3 gap-y-1 rounded-sm border px-2.5 py-1 font-mono text-xs ${
        stale
          ? "border-[var(--no-border)] bg-[var(--no-bg)] text-[var(--no-fg)]"
          : "border-[var(--card-border)] bg-[var(--table-head-bg)] text-[var(--foreground-secondary)]"
      }`}
    >
      <span className="font-medium">{stale ? "⚠ Data may be stale" : "Data current"}</span>
      <span>Forecast pulled {ageLabel(forecastAge)}</span>
      <span>Markets pulled {ageLabel(marketAge)}</span>
      <span>Settlements through {status.last_settlement_date ?? "—"}</span>
    </div>
  );
}
