"use client";

import { effectiveCurrent, type HourlyPoint, type HourlyWeather } from "@/lib/api";

function SunIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className="text-[#f5c451]" aria-hidden>
      <circle cx="12" cy="12" r="4.5" fill="currentColor" />
      <g stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
        <path d="M12 2.5v2.5M12 19v2.5M21.5 12H19M5 12H2.5M18.4 5.6l-1.8 1.8M7.4 16.6l-1.8 1.8M18.4 18.4l-1.8-1.8M7.4 7.4 5.6 5.6" />
      </g>
    </svg>
  );
}

function SnowflakeIcon({ size = 14 }: { size?: number }) {
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

function fmtHour(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric" }).replace(" ", "");
}

function nyDateKey(iso: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date(iso));
}

function HourCell({
  point,
  isNow,
  isPast,
}: {
  point: HourlyPoint;
  isNow: boolean;
  isPast: boolean;
}) {
  return (
    <div
      className={
        "flex min-w-[52px] flex-col items-center gap-1.5 rounded-lg px-2 py-2.5 " +
        (isNow ? "bg-white/15" : isPast ? "opacity-50" : "")
      }
    >
      <span className="font-mono text-[10px] uppercase tracking-[0.04em] text-white/60">
        {isNow ? "Now" : fmtHour(point.timestamp)}
      </span>
      {point.temperature >= 50 ? <SunIcon /> : <SnowflakeIcon />}
      <span className="font-mono text-xs font-semibold text-white">
        {Math.round(point.temperature)}°
      </span>
    </div>
  );
}

export function TodayHourlyStrip({ data }: { data: HourlyWeather }) {
  const current = effectiveCurrent(data);
  if (!current) return null;

  // The latest "past" observation and "current" can share a timestamp (both
  // are the most recent reading) — drop that duplicate before merging.
  const past = data.past.filter((p) => p.timestamp !== current.timestamp);
  const todayKey = nyDateKey(current.timestamp);
  const futureToday = data.future.filter((p) => nyDateKey(p.timestamp) === todayKey);
  const points = [...past, current, ...futureToday];
  const nowIndex = past.length;

  return (
    <div className="mt-4 border-t border-white/10 pt-3">
      <div className="mb-2 flex items-baseline gap-2">
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-white/50">
          {data.current ? "Now" : "Latest"}
        </span>
        <span className="font-mono text-sm font-medium text-white/90">
          {Math.round(current.temperature)}°F
          {current.condition ? ` · ${current.condition}` : ""}
        </span>
      </div>
      <div className="flex gap-1 overflow-x-auto pb-1">
        {points.map((p, i) => (
          <HourCell key={p.timestamp} point={p} isNow={i === nowIndex} isPast={i < nowIndex} />
        ))}
      </div>
    </div>
  );
}

export function TomorrowHourlyStrip({
  data,
  tomorrowDate,
}: {
  data: HourlyWeather;
  tomorrowDate: string;
}) {
  const points = data.future.filter((p) => nyDateKey(p.timestamp) === tomorrowDate);
  if (points.length === 0) return null;

  return (
    <div className="mt-4 border-t border-white/10 pt-3">
      <div className="mb-2 flex items-baseline gap-2">
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-white/50">
          Hourly forecast
        </span>
      </div>
      <div className="flex gap-1 overflow-x-auto pb-1">
        {points.map((p) => (
          <HourCell key={p.timestamp} point={p} isNow={false} isPast={false} />
        ))}
      </div>
    </div>
  );
}
