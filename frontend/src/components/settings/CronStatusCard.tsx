"use client";

import { useState } from "react";
import type { CronStatus } from "@/lib/api";
import { triggerCronJob } from "@/lib/api";

function statusColor(status?: string): string {
  if (!status) return "text-neutral-500";
  if (status === "SUCCESS") return "text-[var(--positive)]";
  if (status === "FAILED" || status === "CRASHED") return "text-[var(--negative)]";
  return "text-neutral-500";
}

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "never";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.round(mins / 60)}h ago`;
  return `${Math.round(mins / 1440)}d ago`;
}

export default function CronStatusCard({
  cronStatus,
  onRefresh,
}: {
  cronStatus: CronStatus | null;
  onRefresh: () => void;
}) {
  const [triggering, setTriggering] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function handleTrigger(key: string) {
    setTriggering(key);
    setMessage(null);
    try {
      await triggerCronJob(key);
      setMessage(`Triggered ${key} pull — check back in a minute for status.`);
      setTimeout(onRefresh, 3000);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Trigger failed");
    } finally {
      setTriggering(null);
    }
  }

  if (!cronStatus) {
    return <p className="text-sm text-neutral-500">Loading cron status…</p>;
  }

  const entries = Object.entries(cronStatus) as [string, CronStatus[keyof CronStatus]][];
  const hasTokenError = entries.some((e) => e[1].error?.includes("RAILWAY_TOKEN"));

  if (hasTokenError) {
    return (
      <p className="rounded-md bg-[var(--table-head-bg)] px-3 py-2 text-sm text-neutral-500">
        Cron status/trigger requires a Railway project token. Set{" "}
        <code className="rounded bg-black/10 px-1 py-0.5 text-xs dark:bg-white/10">
          RAILWAY_TOKEN
        </code>{" "}
        in the backend&apos;s .env to enable this.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {message && <p className="text-xs text-neutral-500">{message}</p>}
      {entries.map(([key, entry]) => (
        <div
          key={key}
          className="flex items-center justify-between rounded-md bg-[var(--table-head-bg)] px-3 py-2.5"
        >
          <div>
            <p className="text-sm font-medium">{entry.name}</p>
            <p className="text-xs text-neutral-500">{entry.schedule_label}</p>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className={`text-xs font-medium ${statusColor(entry.last_run_status)}`}>
                {entry.last_run_status ?? "unknown"}
              </p>
              <p className="text-xs text-neutral-500">{timeAgo(entry.last_run_at)}</p>
            </div>
            <button
              onClick={() => handleTrigger(key)}
              disabled={triggering === key}
              className="rounded-md bg-[var(--accent-forecast)] px-2.5 py-1 text-xs font-medium text-white disabled:opacity-50"
            >
              {triggering === key ? "Running…" : "Run now"}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
