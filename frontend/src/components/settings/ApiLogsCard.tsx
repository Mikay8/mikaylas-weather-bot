"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchApiLogs, type ApiLogEntry } from "@/lib/api";

const SOURCES = ["all", "nws", "iem", "ecmwf", "open_meteo", "kalshi"] as const;

function statusColor(entry: ApiLogEntry): string {
  if (entry.error || !entry.status_code) return "text-[var(--negative)]";
  if (entry.status_code >= 400) return "text-[var(--negative)]";
  return "text-[var(--positive)]";
}

function LogRow({ entry }: { entry: ApiLogEntry }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-[var(--card-border)] last:border-b-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 px-3 py-2 text-left text-xs hover:bg-[var(--table-head-bg)]"
      >
        <span className="w-16 shrink-0 font-mono text-[var(--foreground-tertiary)]">
          {new Date(entry.created_at).toLocaleTimeString()}
        </span>
        <span className="w-20 shrink-0 rounded-sm bg-[var(--table-head-bg)] px-1.5 py-0.5 text-center font-mono uppercase text-[var(--foreground-secondary)]">
          {entry.source}
        </span>
        <span className="w-14 shrink-0 font-mono text-[var(--foreground-secondary)]">{entry.method}</span>
        <span className="min-w-0 flex-1 truncate font-mono text-[var(--foreground-secondary)]">
          {entry.url}
        </span>
        <span className={`w-20 shrink-0 text-right font-mono ${statusColor(entry)}`}>
          {entry.status_code ?? "ERR"}
        </span>
        <span className="w-16 shrink-0 text-right font-mono text-[var(--foreground-tertiary)]">
          {entry.latency_ms != null ? `${entry.latency_ms}ms` : "—"}
        </span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-[var(--card-border)] bg-[var(--table-head-bg)] px-3 py-3 font-mono text-[11px]">
          <div>
            <div className="mb-1 text-[var(--foreground-tertiary)]">URL</div>
            <div className="break-all text-[var(--foreground-secondary)]">{entry.url}</div>
          </div>
          {entry.request_body && (
            <div>
              <div className="mb-1 text-[var(--foreground-tertiary)]">Request body</div>
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all text-[var(--foreground-secondary)]">
                {entry.request_body}
              </pre>
            </div>
          )}
          {entry.error ? (
            <div>
              <div className="mb-1 text-[var(--foreground-tertiary)]">Error</div>
              <div className="text-[var(--negative)]">{entry.error}</div>
            </div>
          ) : (
            <div>
              <div className="mb-1 text-[var(--foreground-tertiary)]">Response body</div>
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all text-[var(--foreground-secondary)]">
                {entry.response_body}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ApiLogsCard() {
  const [logs, setLogs] = useState<ApiLogEntry[] | null>(null);
  const [source, setSource] = useState<(typeof SOURCES)[number]>("all");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((src: (typeof SOURCES)[number]) => {
    setLoading(true);
    setError(null);
    fetchApiLogs(src === "all" ? undefined : src)
      .then(setLogs)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load API logs"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load(source);
  }, [load, source]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1.5">
          {SOURCES.map((s) => (
            <button
              key={s}
              onClick={() => setSource(s)}
              className={`rounded-sm border px-2.5 py-1 font-mono text-[11px] uppercase ${
                source === s
                  ? "border-[var(--accent-forecast)] bg-[var(--accent-forecast)] text-[#0b0e12]"
                  : "border-[var(--card-border)] text-[var(--foreground-secondary)] hover:bg-[var(--table-head-bg)]"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <button
          onClick={() => load(source)}
          disabled={loading}
          className="rounded-sm border border-[var(--card-border)] px-3 py-1.5 text-xs font-medium hover:bg-[var(--table-head-bg)] disabled:opacity-50"
        >
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {error && <p className="text-xs text-[var(--negative)]">{error}</p>}

      {!logs || logs.length === 0 ? (
        <p className="text-sm text-[var(--foreground-secondary)]">
          {logs === null ? "Loading…" : "No API calls logged in the last 24 hours."}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-sm border border-[var(--card-border)]">
          <div className="min-w-[560px]">
            <div className="flex items-center gap-3 border-b border-[var(--card-border)] bg-[var(--table-head-bg)] px-3 py-1.5 font-mono text-[10px] uppercase tracking-wide text-[var(--foreground-tertiary)]">
              <span className="w-16 shrink-0">Time</span>
              <span className="w-20 shrink-0">Source</span>
              <span className="w-14 shrink-0">Method</span>
              <span className="min-w-0 flex-1">URL</span>
              <span className="w-20 shrink-0 text-right">Status</span>
              <span className="w-16 shrink-0 text-right">Latency</span>
            </div>
            <div className="max-h-[480px] overflow-y-auto">
              {logs.map((entry) => (
                <LogRow key={entry.id} entry={entry} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
