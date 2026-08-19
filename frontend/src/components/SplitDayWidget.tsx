"use client";

import { useEffect, useState } from "react";
import type { Recommendation, Trade } from "@/lib/api";
import DayWidget from "@/components/DayWidget";

type TimeOfDay = "morning" | "day" | "night";

const GRADIENTS: Record<TimeOfDay, string> = {
  // 5am-11am: cool blue easing into a soft sunrise gold.
  morning: "bg-gradient-to-br from-[#1e3450] via-[#3a3a5a] to-[#5a4a3a]",
  // 11am-6pm: brighter, clearer blue-sky tones.
  day: "bg-gradient-to-br from-[#1e4a6e] via-[#2c4a78] to-[#3a5a8a]",
  // 6pm-5am: deep navy/purple night sky.
  night: "bg-gradient-to-br from-[#1a2a42] via-[#2a2450] to-[#3a2450]",
};

function timeOfDayInNY(): TimeOfDay {
  const hour = Number(
    new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      hour: "numeric",
      hour12: false,
    }).format(new Date())
  );
  if (hour >= 5 && hour < 11) return "morning";
  if (hour >= 11 && hour < 18) return "day";
  return "night";
}

function useTimeOfDay(): TimeOfDay {
  const [tod, setTod] = useState<TimeOfDay>(() => timeOfDayInNY());

  useEffect(() => {
    const interval = setInterval(() => setTod(timeOfDayInNY()), 60_000);
    return () => clearInterval(interval);
  }, []);

  return tod;
}

export default function SplitDayWidget({
  today,
  tomorrow,
  onBetPlaced,
}: {
  today: {
    date: string;
    forecastHigh: number | null;
    topRecommendation: Recommendation | null;
    openTrades: Trade[];
    closeTime: string | null;
  };
  tomorrow: {
    date: string;
    forecastHigh: number | null;
    topRecommendation: Recommendation | null;
    openTrades: Trade[];
  };
  onBetPlaced: () => void;
}) {
  const timeOfDay = useTimeOfDay();

  return (
    <div
      className={`relative mb-5 overflow-hidden rounded-xl border border-[var(--card-border)] transition-[background] duration-1000 ${GRADIENTS[timeOfDay]}`}
    >
      <div className="grid grid-cols-1 divide-y divide-white/10 lg:grid-cols-2 lg:divide-x lg:divide-y-0">
        <div className="p-7">
          <DayWidget
            label="Today"
            date={today.date}
            forecastHigh={today.forecastHigh}
            topRecommendation={today.topRecommendation}
            openTrades={today.openTrades}
            closeTime={today.closeTime}
            showCountdown
            onBetPlaced={onBetPlaced}
          />
        </div>
        <div className="p-7">
          <DayWidget
            label="Tomorrow"
            date={tomorrow.date}
            forecastHigh={tomorrow.forecastHigh}
            topRecommendation={tomorrow.topRecommendation}
            openTrades={tomorrow.openTrades}
            closeTime={null}
            showCountdown={false}
            onBetPlaced={onBetPlaced}
          />
        </div>
      </div>
    </div>
  );
}
