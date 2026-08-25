"use client";

import type { SourceHealth } from "@/lib/api";

function Row({ label, entry }: { label: string; entry: SourceHealth["nws"] | undefined }) {
  if (!entry) return null;
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-sm border border-[var(--card-border)] bg-[var(--table-head-bg)] px-3 py-2.5">
      <div className="flex items-center gap-2">
        <span
          className={`inline-block h-2 w-2 shrink-0 rounded-full ${
            entry.reachable ? "bg-[var(--positive)]" : "bg-[var(--negative)]"
          }`}
          style={{
            boxShadow: entry.reachable
              ? "0 0 6px var(--positive)"
              : "0 0 6px var(--negative)",
          }}
        />
        <span className="text-sm font-medium">{label}</span>
      </div>
      <span className="break-all font-mono text-xs text-[var(--foreground-secondary)]">
        {entry.reachable
          ? `${entry.latency_ms}ms (HTTP ${entry.status_code})`
          : entry.error ?? "unreachable"}
      </span>
    </div>
  );
}

export default function SourceHealthCard({ health }: { health: SourceHealth | null }) {
  if (!health)
    return <p className="text-sm text-[var(--foreground-secondary)]">Checking source health…</p>;
  return (
    <div className="space-y-2">
      <Row label="NWS (api.weather.gov)" entry={health.nws} />
      <Row label="Kalshi (external-api.kalshi.com)" entry={health.kalshi} />
    </div>
  );
}
