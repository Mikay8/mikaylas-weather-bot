"use client";

import { useMemo } from "react";
import type { ForecastPull } from "@/lib/api";

const MIN_SAMPLE_DAYS = 20; // rough floor for a believable per-lead-time calibration

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

function hoursUntil(from: string, to: string): number {
  return (new Date(to).getTime() - new Date(from).getTime()) / 3_600_000;
}

export default function ForecastDrift({
  pulls,
  targetDate,
  closeTime,
  daysWithMultiplePulls,
}: {
  pulls: ForecastPull[];
  targetDate: string;
  closeTime: string | null;
  daysWithMultiplePulls: number;
}) {
  const dayPulls = useMemo(
    () =>
      pulls
        .filter((p) => p.target_date === targetDate && p.predicted_high !== null)
        .sort((a, b) => a.forecast_time.localeCompare(b.forecast_time)),
    [pulls, targetDate]
  );

  const calibrationReady = daysWithMultiplePulls >= MIN_SAMPLE_DAYS;

  if (dayPulls.length === 0) {
    return null;
  }

  return (
    <div className="mt-5 border-t border-[var(--card-border)] pt-4">
      <div className="mb-2.5 flex items-center justify-between">
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--foreground-tertiary)]">
          Forecast history for {targetDate}
        </span>
        {dayPulls.length > 1 && (
          <span className="font-mono text-[10px] text-[var(--foreground-tertiary)]">
            {dayPulls.length} pulls
          </span>
        )}
      </div>

      <div className="space-y-1.5">
        {dayPulls.map((p, i) => {
          const prev = i > 0 ? dayPulls[i - 1] : null;
          const delta =
            prev && prev.predicted_high !== null && p.predicted_high !== null
              ? p.predicted_high - prev.predicted_high
              : null;
          const hoursToClose = closeTime ? hoursUntil(p.forecast_time, closeTime) : null;
          return (
            <div
              key={p.id}
              className="flex items-center justify-between rounded-sm border border-[var(--row-border)] bg-[var(--table-head-bg)] px-3 py-1.5 text-xs"
            >
              <span className="font-mono text-[var(--foreground-secondary)]">
                {fmtTime(p.forecast_time)}
                {hoursToClose !== null && (
                  <span className="ml-2 text-[var(--foreground-tertiary)]">
                    ({hoursToClose > 0 ? `${hoursToClose.toFixed(0)}h before close` : "after close"})
                  </span>
                )}
              </span>
              <span className="flex items-center gap-2 font-mono font-medium">
                {p.predicted_high}°F
                {delta !== null && delta !== 0 && (
                  <span
                    className={delta > 0 ? "text-[var(--negative)]" : "text-[var(--accent-forecast)]"}
                  >
                    ({delta > 0 ? "+" : ""}
                    {delta}°)
                  </span>
                )}
              </span>
            </div>
          );
        })}
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-[var(--foreground-tertiary)]">
        {calibrationReady ? (
          "Enough days with multiple pulls have accumulated to calibrate accuracy by lead time — see Settings."
        ) : (
          <>
            Not enough history yet to say which pull time is most accurate ({daysWithMultiplePulls}/
            {MIN_SAMPLE_DAYS} days with multiple same-day pulls collected). This will unlock once enough
            data accumulates — no guess is shown in the meantime.
          </>
        )}
      </p>
    </div>
  );
}
