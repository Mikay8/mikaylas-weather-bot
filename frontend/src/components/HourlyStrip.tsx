"use client";

import { useEffect, useState } from "react";
import { fetchHourlyWeather, type HourlyPoint, type HourlyWeather } from "@/lib/api";

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

export default function HourlyStrip() {
  const [data, setData] = useState<HourlyWeather | null>(null);

  useEffect(() => {
    fetchHourlyWeather()
      .then(setData)
      .catch(() => {});
    const interval = setInterval(() => {
      fetchHourlyWeather()
        .then(setData)
        .catch(() => {});
    }, 300_000);
    return () => clearInterval(interval);
  }, []);

  if (!data || !data.current) return null;

  // The latest "past" observation and "current" can share a timestamp (both
  // are the most recent reading) — drop that duplicate before merging.
  const past = data.past.filter((p) => p.timestamp !== data.current!.timestamp);
  const points = [...past, data.current, ...data.future];
  const nowIndex = past.length;

  return (
    <div className="mt-4 border-t border-white/10 pt-3">
      <div className="mb-2 flex items-baseline gap-2">
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-white/50">
          Current
        </span>
        <span className="font-mono text-sm font-medium text-white/90">
          {Math.round(data.current.temperature)}°F
          {data.current.condition ? ` · ${data.current.condition}` : ""}
        </span>
      </div>
      <div className="flex gap-1 overflow-x-auto pb-1">
        {points.map((p, i) => (
          <HourCell
            key={p.timestamp}
            point={p}
            isNow={i === nowIndex}
            isPast={i < nowIndex}
          />
        ))}
      </div>
    </div>
  );
}
