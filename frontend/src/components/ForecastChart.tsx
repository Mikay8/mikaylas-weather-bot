"use client";

import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ForecastVsActual } from "@/lib/api";

type MonthOption = { key: string; label: string };

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function monthKeyOf(dateStr: string): string {
  return dateStr.slice(0, 7); // "YYYY-MM"
}

export default function ForecastChart({ data }: { data: ForecastVsActual[] }) {
  const [view, setView] = useState<"graph" | "calendar">("graph");
  const [month, setMonth] = useState<string>("all");

  const sorted = useMemo(
    () => [...data].sort((a, b) => a.target_date.localeCompare(b.target_date)),
    [data]
  );

  const monthOptions = useMemo<MonthOption[]>(() => {
    const keys = Array.from(new Set(sorted.map((d) => monthKeyOf(d.target_date)))).sort();
    const opts = keys.map((key) => {
      const [y, m] = key.split("-");
      return { key, label: `${MONTH_NAMES[Number(m) - 1]} ${y}` };
    });
    return view === "calendar" ? opts : [{ key: "all", label: "All months" }, ...opts];
  }, [sorted, view]);

  const effectiveMonth =
    view === "calendar" && month === "all" ? monthOptions[monthOptions.length - 1]?.key ?? "all" : month;

  const filtered = useMemo(
    () =>
      effectiveMonth === "all"
        ? sorted
        : sorted.filter((d) => monthKeyOf(d.target_date) === effectiveMonth),
    [sorted, effectiveMonth]
  );

  const chartData = filtered.map((d) => ({
    date: d.target_date.slice(5),
    Forecast: d.predicted_high,
    Actual: d.actual_high,
  }));

  const mae = useMemo(() => {
    const pairs = filtered.filter(
      (d) => d.predicted_high !== null && d.actual_high !== null
    );
    if (pairs.length === 0) return null;
    const sum = pairs.reduce(
      (s, d) => s + Math.abs((d.actual_high as number) - (d.predicted_high as number)),
      0
    );
    return (sum / pairs.length).toFixed(1);
  }, [filtered]);

  const calendarCells = useMemo(() => {
    if (view !== "calendar" || filtered.length === 0) return [];
    const withActual = filtered.filter((d) => d.actual_high !== null);
    if (withActual.length === 0) return [];
    const avg =
      withActual.reduce((s, d) => s + (d.actual_high as number), 0) / withActual.length;

    const firstDow = new Date(`${filtered[0].target_date}T00:00:00Z`).getUTCDay();
    const blanks = Array.from({ length: firstDow }, (_, i) => ({
      blank: true as const,
      key: `b${i}`,
    }));
    const cells = filtered.map((d) => {
      const dateNum = Number(d.target_date.slice(8, 10));
      const actual = d.actual_high;
      const isHot = actual !== null && actual >= avg;
      const isCold = actual !== null && actual < avg;
      const magnitude = actual !== null ? Math.min(0.28, 0.06 + Math.abs(actual - avg) / 60) : 0;
      const tint =
        actual === null
          ? "transparent"
          : isHot
          ? `rgba(217,164,65,${magnitude})`
          : `rgba(111,168,220,${magnitude})`;
      return {
        blank: false as const,
        key: d.target_date,
        dateNum,
        actual,
        isHot,
        isCold,
        tint,
      };
    });
    return [...blanks, ...cells];
  }, [view, filtered]);

  if (sorted.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-[var(--foreground-secondary)]">
        No forecast history yet.
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <select
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          className="rounded-sm border border-[var(--card-border)] bg-[var(--input-bg)] px-2.5 py-1.5 font-mono text-xs text-[var(--foreground)] outline-none focus:border-[var(--accent-forecast)]"
        >
          {monthOptions.map((mo) => (
            <option key={mo.key} value={mo.key}>
              {mo.label}
            </option>
          ))}
        </select>
        <div className="flex overflow-hidden rounded-sm border border-[var(--card-border)]">
          <button
            onClick={() => setView("graph")}
            className="px-3.5 py-1.5 font-sans text-xs font-semibold"
            style={{
              background: view === "graph" ? "#1a2028" : "transparent",
              color: view === "graph" ? "var(--foreground)" : "var(--foreground-secondary)",
            }}
          >
            Graph
          </button>
          <button
            onClick={() => {
              setView("calendar");
              if (month === "all") setMonth(effectiveMonth);
            }}
            className="border-l border-[var(--card-border)] px-3.5 py-1.5 font-sans text-xs font-semibold"
            style={{
              background: view === "calendar" ? "#1a2028" : "transparent",
              color: view === "calendar" ? "var(--foreground)" : "var(--foreground-secondary)",
            }}
          >
            Calendar
          </button>
        </div>
      </div>

      {view === "graph" ? (
        <>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData} margin={{ top: 8, right: 16, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
              <XAxis dataKey="date" tick={{ fontSize: 12, fill: "var(--chart-axis)" }} />
              <YAxis
                tick={{ fontSize: 12, fill: "var(--chart-axis)" }}
                unit="°F"
                domain={["dataMin - 3", "dataMax + 3"]}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--table-head-bg)",
                  border: "1px solid var(--card-border)",
                  borderRadius: 3,
                  fontSize: 13,
                  fontFamily: "var(--font-geist-mono)",
                }}
                labelStyle={{ color: "var(--foreground-secondary)" }}
              />
              <Line
                type="monotone"
                dataKey="Forecast"
                stroke="var(--accent-forecast)"
                strokeWidth={2}
                dot={{ r: 3 }}
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="Actual"
                stroke="var(--accent-actual)"
                strokeWidth={2}
                dot={{ r: 3 }}
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
          {mae !== null && (
            <div className="mt-2 text-right font-mono text-xs text-[var(--foreground-tertiary)]">
              mean abs. error: {mae}°F
            </div>
          )}
        </>
      ) : (
        <div>
          <div className="mb-2.5 font-mono text-[10px] uppercase tracking-[0.1em] text-[var(--foreground-tertiary)]">
            Daily highs relative to month average
          </div>
          {calendarCells.length === 0 ? (
            <div className="flex h-32 items-center justify-center text-sm text-[var(--foreground-secondary)]">
              No settled data for this month yet.
            </div>
          ) : (
            <>
              <div className="mb-1.5 grid grid-cols-7 gap-1.5">
                {["S", "M", "T", "W", "T", "F", "S"].map((d, i) => (
                  <div
                    key={i}
                    className="text-center font-mono text-[10px] text-[var(--foreground-tertiary)]"
                  >
                    {d}
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-7 gap-1.5">
                {calendarCells.map((c) =>
                  c.blank ? (
                    <div key={c.key} />
                  ) : (
                    <div
                      key={c.key}
                      className="flex min-h-[64px] flex-col items-center gap-1 rounded-sm border border-[var(--row-border)] p-1.5"
                      style={{ background: c.tint }}
                    >
                      <span className="self-start font-mono text-[10px] text-[var(--foreground-secondary)]">
                        {c.dateNum}
                      </span>
                      {c.actual !== null && (
                        <svg width="16" height="16" viewBox="0 0 24 24" className="mt-0.5">
                          {c.isHot ? (
                            <g>
                              <circle cx="12" cy="12" r="5.5" fill="var(--accent-actual)" />
                              <line x1="12" y1="1" x2="12" y2="4" stroke="var(--accent-actual)" strokeWidth="1.5" />
                              <line x1="12" y1="20" x2="12" y2="23" stroke="var(--accent-actual)" strokeWidth="1.5" />
                              <line x1="1" y1="12" x2="4" y2="12" stroke="var(--accent-actual)" strokeWidth="1.5" />
                              <line x1="20" y1="12" x2="23" y2="12" stroke="var(--accent-actual)" strokeWidth="1.5" />
                            </g>
                          ) : (
                            <g>
                              <line x1="12" y1="2" x2="12" y2="22" stroke="var(--accent-forecast)" strokeWidth="1.6" />
                              <line x1="4" y1="7" x2="20" y2="17" stroke="var(--accent-forecast)" strokeWidth="1.6" />
                              <line x1="20" y1="7" x2="4" y2="17" stroke="var(--accent-forecast)" strokeWidth="1.6" />
                            </g>
                          )}
                        </svg>
                      )}
                      {c.actual !== null && (
                        <span className="font-mono text-[11px] font-semibold text-[var(--foreground)]">
                          {c.actual}°
                        </span>
                      )}
                    </div>
                  )
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
