"use client";

import type { Recommendation, Trade } from "@/lib/api";
import DayWidget from "@/components/DayWidget";

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
  return (
    <div className="mb-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
      <div className="relative overflow-hidden rounded-xl border border-[var(--card-border)] bg-gradient-to-br from-[#1a2a42] via-[#2a2450] to-[#3a2450] p-7">
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
      <div className="relative overflow-hidden rounded-xl border border-[var(--card-border)] bg-gradient-to-br from-[#1a2a42] via-[#2a2450] to-[#3a2450] p-7">
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
  );
}
