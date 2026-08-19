"use client";

import { useEffect, useState } from "react";

export function fmtCountdown(ms: number): string {
  if (ms <= 0) return "closed";
  const totalSeconds = Math.floor(ms / 1000);
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export default function Countdown({
  closeTime,
  className,
  urgentClassName,
}: {
  closeTime: string | null;
  className?: string;
  urgentClassName?: string;
}) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, []);

  if (!closeTime) return null;
  const remainingMs = new Date(closeTime).getTime() - now;
  const urgent = remainingMs <= 3_600_000;

  return (
    <span className={urgent ? urgentClassName ?? className : className}>
      {fmtCountdown(remainingMs)}
    </span>
  );
}
