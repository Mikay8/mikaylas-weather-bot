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

const DAY_NAMES = [
  "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
];

function monthKeyOf(dateStr: string): string {
  return dateStr.slice(0, 7); // "YYYY-MM"
}

function SunIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className="text-[#f5c451]" aria-hidden>
      <circle cx="12" cy="12" r="4.5" fill="currentColor" />
      <g stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
        <path d="M12 2.5v2.5M12 19v2.5M21.5 12H19M5 12H2.5M18.4 5.6l-1.8 1.8M7.4 16.6l-1.8 1.8M18.4 18.4l-1.8-1.8M7.4 7.4 5.6 5.6" />
      </g>
    </svg>
  );
}

function SnowflakeIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className="text-[#7ec8f0]" aria-hidden>
      <g stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2.5v19M4.5 7l15 10M19.5 7l-15 10" />
        <path d="M12 2.5 9.8 4.6M12 2.5l2.2 2.1M12 21.5l-2.2-2.1M12 21.5l2.2-2.1" />
        <path d="M4.5 7 6.9 6.6M4.5 7l.6 2.4M19.5 7l-2.4-.4M19.5 7l-.6 2.4M19.5 17l-2.4.4M19.5 17l-.6-2.4M4.5 17l2.4.4M4.5 17l.6-2.4" />
      </g>
    </svg>
  );
}

function WeatherIcon({ temp, size }: { temp: number; size?: number }) {
  return temp >= 50 ? <SunIcon size={size} /> : <SnowflakeIcon size={size} />;
}

export default function ForecastChart({ data }: { data: ForecastVsActual[] }) {
  const [view, setView] = useState<"graph" | "calendar">("graph");
  const [month, setMonth] = useState<string>("all");
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

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
    fullDate: d.target_date,
    Forecast: d.predicted_high,
    "Open-Meteo": d.open_meteo_predicted_high,
    ECMWF: d.ecmwf_predicted_high,
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

    const firstDow = new Date(`${filtered[0].target_date}T00:00:00Z`).getUTCDay();
    const blanks = Array.from({ length: firstDow }, (_, i) => ({
      blank: true as const,
      key: `b${i}`,
    }));
    const cells = filtered.map((d) => {
      const dateNum = Number(d.target_date.slice(8, 10));
      const actual = d.actual_high;
      const predicted = d.predicted_high;
      const error = actual !== null && predicted !== null ? Math.abs(actual - predicted) : null;
      // Green = forecast was accurate, red = forecast missed by a lot.
      const tint =
        error === null
          ? "transparent"
          : error <= 1
          ? "rgba(95,184,138,0.16)"
          : error <= 3
          ? "rgba(217,164,65,0.14)"
          : "rgba(226,86,79,0.16)";
      return {
        blank: false as const,
        key: d.target_date,
        date: d.target_date,
        dateNum,
        actual,
        predicted,
        error,
        tint,
      };
    });
    return [...blanks, ...cells];
  }, [view, filtered]);

  const selectedDay = useMemo(
    () => (selectedDate ? sorted.find((d) => d.target_date === selectedDate) ?? null : null),
    [selectedDate, sorted]
  );

  const selectedDayLabel = useMemo(() => {
    if (!selectedDate) return "";
    const d = new Date(`${selectedDate}T00:00:00Z`);
    return `${DAY_NAMES[d.getUTCDay()]}, ${MONTH_NAMES[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
  }, [selectedDate]);

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
            <LineChart
              data={chartData}
              margin={{ top: 8, right: 16, left: -16, bottom: 0 }}
              onClick={(e) => {
                const raw = e?.activeTooltipIndex ?? e?.activeIndex;
                const idx = typeof raw === "string" ? Number(raw) : raw;
                if (typeof idx === "number" && !Number.isNaN(idx) && chartData[idx]) {
                  setSelectedDate(chartData[idx].fullDate);
                }
              }}
              className="cursor-pointer"
            >
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
                dataKey="Open-Meteo"
                stroke="var(--accent-open-meteo)"
                strokeWidth={2}
                strokeDasharray="4 3"
                dot={{ r: 2.5 }}
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="ECMWF"
                stroke="var(--accent-ecmwf)"
                strokeWidth={2}
                strokeDasharray="2 3"
                dot={{ r: 2.5 }}
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
          <div className="mt-2 flex flex-wrap items-center gap-4 font-mono text-[10px] uppercase tracking-[0.08em] text-[var(--foreground-tertiary)]">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-0.5 w-3.5" style={{ background: "var(--accent-forecast)" }} />
              Forecast high (NWS)
            </span>
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block h-0.5 w-3.5"
                style={{
                  background:
                    "repeating-linear-gradient(90deg, var(--accent-open-meteo) 0 4px, transparent 4px 7px)",
                }}
              />
              Open-Meteo
            </span>
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block h-0.5 w-3.5"
                style={{
                  background: "repeating-linear-gradient(90deg, var(--accent-ecmwf) 0 2px, transparent 2px 5px)",
                }}
              />
              ECMWF
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-0.5 w-3.5" style={{ background: "var(--accent-actual)" }} />
              Actual high (NWS CLI)
            </span>
          </div>
          {mae !== null && (
            <div className="mt-2 text-right font-mono text-xs text-[var(--foreground-tertiary)]">
              mean abs. error: {mae}°F
            </div>
          )}
        </>
      ) : (
        <div>
          <div className="mb-2.5 flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.1em] text-[var(--foreground-tertiary)]">
            <span>Forecast accuracy</span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-sm" style={{ background: "rgba(95,184,138,0.6)" }} />
              ≤1°F off
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-sm" style={{ background: "rgba(217,164,65,0.6)" }} />
              2–3°F off
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-sm" style={{ background: "rgba(226,86,79,0.6)" }} />
              &gt;3°F off
            </span>
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
                    <button
                      key={c.key}
                      type="button"
                      onClick={() => c.actual !== null && setSelectedDate(c.date)}
                      disabled={c.actual === null}
                      className="flex min-h-[64px] flex-col items-center gap-1 rounded-sm border border-[var(--row-border)] p-1.5 text-left transition-colors enabled:cursor-pointer enabled:hover:border-[var(--accent-forecast)] disabled:opacity-60"
                      style={{ background: c.tint }}
                    >
                      <span className="self-start font-mono text-[10px] text-[var(--foreground-secondary)]">
                        {c.dateNum}
                      </span>
                      {c.actual !== null && (
                        <span className="mt-0.5">
                          <WeatherIcon temp={c.actual} size={16} />
                        </span>
                      )}
                      {c.actual !== null && (
                        <span className="font-mono text-[11px] font-semibold text-[var(--foreground)]">
                          {c.actual}°
                        </span>
                      )}
                    </button>
                  )
                )}
              </div>
            </>
          )}
        </div>
      )}

      {selectedDay && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          onClick={() => setSelectedDate(null)}
        >
          <div
            className="w-full max-w-sm overflow-hidden rounded-xl border border-[var(--card-border)] bg-[var(--card-bg)] shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="bg-gradient-to-br from-[#1a2a42] via-[#2a2450] to-[#3a2450] px-6 py-5">
              <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-white/60">
                New York, NY · Daily high
              </div>
              <div className="mt-1 flex items-center justify-between">
                <div className="text-[15px] font-semibold text-white">{selectedDayLabel}</div>
                <button
                  onClick={() => setSelectedDate(null)}
                  className="rounded-sm p-1 text-white/60 hover:bg-white/10 hover:text-white"
                  aria-label="Close"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                    <path
                      d="M6 6l12 12M18 6 6 18"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                    />
                  </svg>
                </button>
              </div>
            </div>

            {(() => {
              const secondary = [
                selectedDay.open_meteo_predicted_high !== null && {
                  key: "open-meteo",
                  label: "Open-Meteo forecast",
                  value: selectedDay.open_meteo_predicted_high,
                },
                selectedDay.ecmwf_predicted_high !== null && {
                  key: "ecmwf",
                  label: "ECMWF forecast",
                  value: selectedDay.ecmwf_predicted_high,
                },
              ].filter((s): s is { key: string; label: string; value: number } => s !== false);
              const colCount = 2 + secondary.length;
              const gridColsClass =
                colCount === 4 ? "grid-cols-4" : colCount === 3 ? "grid-cols-3" : "grid-cols-2";
              return (
                <div className={`grid divide-x divide-[var(--card-border)] ${gridColsClass}`}>
                  <div className="flex flex-col items-center gap-2 px-5 py-6">
                    <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-[var(--foreground-tertiary)]">
                      NWS forecast
                    </span>
                    {selectedDay.predicted_high !== null ? (
                      <>
                        <WeatherIcon temp={selectedDay.predicted_high} size={32} />
                        <span className="font-mono text-3xl font-light text-[var(--foreground)]">
                          {selectedDay.predicted_high}°
                        </span>
                      </>
                    ) : (
                      <span className="py-3 text-sm text-[var(--foreground-secondary)]">—</span>
                    )}
                  </div>
                  {secondary.map((s) => (
                    <div key={s.key} className="flex flex-col items-center gap-2 px-5 py-6">
                      <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-[var(--foreground-tertiary)]">
                        {s.label}
                      </span>
                      <WeatherIcon temp={s.value} size={32} />
                      <span className="font-mono text-3xl font-light text-[var(--foreground)]">{s.value}°</span>
                    </div>
                  ))}
                  <div className="flex flex-col items-center gap-2 px-5 py-6">
                    <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-[var(--foreground-tertiary)]">
                      Actual high (NWS CLI)
                    </span>
                    {selectedDay.actual_high !== null ? (
                      <>
                        <WeatherIcon temp={selectedDay.actual_high} size={32} />
                        <span className="font-mono text-3xl font-light text-[var(--foreground)]">
                          {selectedDay.actual_high}°
                        </span>
                      </>
                    ) : (
                      <span className="py-3 text-sm text-[var(--foreground-secondary)]">—</span>
                    )}
                  </div>
                </div>
              );
            })()}

            {selectedDay.predicted_high !== null && selectedDay.actual_high !== null && (
              <div className="border-t border-[var(--card-border)] bg-[var(--table-head-bg)] px-6 py-4">
                {(() => {
                  const diff = selectedDay.actual_high - selectedDay.predicted_high;
                  const error = Math.abs(diff);
                  const accuracy = Math.max(0, 100 - error * 10);
                  const accuracyColor =
                    error <= 1
                      ? "text-[var(--positive)]"
                      : error <= 3
                      ? "text-[#d9a441]"
                      : "text-[var(--negative)]";
                  return (
                    <>
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-[var(--foreground-tertiary)]">
                          Forecast accuracy
                        </span>
                        <span className={`font-mono text-sm font-bold ${accuracyColor}`}>
                          {accuracy.toFixed(0)}%
                        </span>
                      </div>
                      <div className="mt-1.5 text-center font-mono text-xs font-medium text-[var(--foreground-secondary)]">
                        {diff === 0 ? (
                          "Forecast was exact"
                        ) : (
                          <>
                            Actual was{" "}
                            <span className="font-semibold text-[var(--foreground)]">
                              {error}°F {diff > 0 ? "warmer" : "cooler"}
                            </span>{" "}
                            than forecast
                          </>
                        )}
                      </div>
                    </>
                  );
                })()}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
