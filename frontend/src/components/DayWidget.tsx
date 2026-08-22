"use client";

import { useState } from "react";
import type { HourlyWeather, Recommendation, Trade } from "@/lib/api";
import { DEMO_MODE, placeBet } from "@/lib/api";
import Countdown from "@/components/Countdown";
import { TodayHourlyStrip, TomorrowHourlyStrip } from "@/components/HourlyStrip";
import TradeSourceBadge from "@/components/TradeSourceBadge";

function bracketLabel(r: { kalshi_label?: string | null; strike_type?: string | null; bracket_low?: number | null; bracket_high?: number | null }): string {
  if (r.kalshi_label) return r.kalshi_label;
  if (r.strike_type === "greater") return `> ${r.bracket_low}°F`;
  if (r.strike_type === "less") return `< ${r.bracket_high}°F`;
  return `${r.bracket_low}–${r.bracket_high}°F`;
}

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-9 w-9 text-[#f5c451]" aria-hidden>
      <circle cx="12" cy="12" r="4.5" fill="currentColor" />
      <g stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
        <path d="M12 2.5v2.5M12 19v2.5M21.5 12H19M5 12H2.5M18.4 5.6l-1.8 1.8M7.4 16.6l-1.8 1.8M18.4 18.4l-1.8-1.8M7.4 7.4 5.6 5.6" />
      </g>
    </svg>
  );
}

function SnowflakeIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-9 w-9 text-[#7ec8f0]" aria-hidden>
      <g stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2.5v19M4.5 7l15 10M19.5 7l-15 10" />
        <path d="M12 2.5 9.8 4.6M12 2.5l2.2 2.1M12 21.5l-2.2-2.1M12 21.5l2.2-2.1" />
        <path d="M4.5 7 6.9 6.6M4.5 7l.6 2.4M19.5 7l-2.4-.4M19.5 7l-.6 2.4M19.5 17l-2.4.4M19.5 17l-.6-2.4M4.5 17l2.4.4M4.5 17l.6-2.4" />
      </g>
    </svg>
  );
}

function CloseCountdown({ closeTime }: { closeTime: string | null }) {
  if (!closeTime) return null;
  return (
    <div className="mt-2 flex items-center gap-1.5 font-mono text-xs text-white/70">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden>
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
        <path d="M12 7v5l3.5 2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
      Market closes in{" "}
      <Countdown
        closeTime={closeTime}
        className="font-semibold text-white"
        urgentClassName="font-semibold text-[#e2564f]"
      />
    </div>
  );
}

export default function DayWidget({
  label,
  date,
  forecastHigh,
  currentTemp = null,
  topRecommendation,
  openTrades,
  closeTime,
  showCountdown,
  hourly,
  hourlyMode,
  onBetPlaced,
}: {
  label: string;
  date: string;
  forecastHigh: number | null;
  currentTemp?: number | null;
  topRecommendation: Recommendation | null;
  openTrades: Trade[];
  closeTime: string | null;
  showCountdown: boolean;
  hourly?: HourlyWeather | null;
  hourlyMode?: "today" | "tomorrow";
  onBetPlaced: () => void;
}) {
  const [amount, setAmount] = useState("25");
  const [placing, setPlacing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<"yes" | "no" | null>(null);

  async function submitBet(side: "yes" | "no") {
    if (!topRecommendation) return;
    const amt = parseFloat(amount);
    if (!amt || amt <= 0) {
      setError("Enter a valid amount");
      return;
    }
    setPlacing(true);
    setError(null);
    try {
      await placeBet(topRecommendation.contract_id, side, amt);
      setConfirming(null);
      setAmount("25");
      onBetPlaced();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to place bet");
    } finally {
      setPlacing(false);
    }
  }

  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-white/60">
            New York, NY
          </div>
          <div className="mt-1 text-[13px] font-semibold text-white/85">
            {label} · {date}
          </div>
          {currentTemp !== null ? (
            <div className="mt-1.5 flex items-center gap-5">
              <div className="flex items-center gap-2.5">
                {currentTemp >= 50 ? <SunIcon /> : <SnowflakeIcon />}
                <div className="flex items-baseline gap-1.5">
                  <span className="text-[48px] font-light leading-none tracking-tight text-white">
                    {Math.round(currentTemp)}°
                  </span>
                  <span className="text-sm text-white/70">now</span>
                </div>
              </div>
              <div className="flex items-baseline gap-1.5 border-l border-white/15 pl-5">
                <span className="text-2xl font-light leading-none tracking-tight text-white">
                  {forecastHigh !== null ? `${forecastHigh}°` : "—"}
                </span>
                <span className="text-sm text-white/70">high</span>
              </div>
            </div>
          ) : (
            <div className="mt-1.5 flex items-center gap-3">
              {forecastHigh !== null && (forecastHigh >= 50 ? <SunIcon /> : <SnowflakeIcon />)}
              <div className="flex items-baseline gap-3">
                <span className="text-[48px] font-light leading-none tracking-tight text-white">
                  {forecastHigh !== null ? `${forecastHigh}°` : "—"}
                </span>
                <span className="text-sm text-white/70">forecast high</span>
              </div>
            </div>
          )}
          {showCountdown && <CloseCountdown closeTime={closeTime} />}
        </div>

        {topRecommendation ? (
          <div className="min-w-[260px] rounded-xl border border-white/20 bg-black/30 p-5 backdrop-blur">
            <div className="mb-2.5 flex items-center gap-2">
              <span className="rounded-sm bg-[#5fb88a] px-1.5 py-0.5 font-mono text-[9.5px] font-bold tracking-[0.08em] text-[#0b0e12]">
                {topRecommendation.recommend ? "RECOMMENDED" : "TOP MODEL PICK"}
              </span>
              <span className="font-mono text-xs text-white/85">{bracketLabel(topRecommendation)}</span>
            </div>
            {topRecommendation.forecast_stale && (
              <div className="mb-2.5 flex items-center gap-1.5 rounded-sm border border-[#d9a441]/40 bg-[#d9a441]/10 px-2 py-1">
                <span className="font-mono text-[9.5px] font-bold tracking-[0.08em] text-[#e6c273]">
                  ⚠ STALE FORECAST
                </span>
                <span className="font-mono text-[10px] text-white/60">
                  last pulled {new Date(topRecommendation.forecast_time).toLocaleString(undefined, {
                    timeZone: "America/New_York",
                    month: "short",
                    day: "numeric",
                    hour: "numeric",
                    minute: "2-digit",
                  })}
                </span>
              </div>
            )}
            <div className="mb-4 flex gap-5">
              <div>
                <div className="text-[9.5px] uppercase tracking-[0.08em] text-white/60">Market</div>
                <div className="mt-0.5 font-mono text-sm text-white">
                  {pct(topRecommendation.market_prob)}
                </div>
              </div>
              <div>
                <div className="text-[9.5px] uppercase tracking-[0.08em] text-white/60">Model</div>
                <div className="mt-0.5 font-mono text-sm text-white">
                  {pct(topRecommendation.model_prob)}
                </div>
              </div>
              <div>
                <div className="text-[9.5px] uppercase tracking-[0.08em] text-white/60">Edge</div>
                <div className="mt-0.5 font-mono text-sm font-bold text-[#8de3b0]">
                  {topRecommendation.fee_adjusted_edge !== null
                    ? pct(topRecommendation.fee_adjusted_edge)
                    : "—"}
                </div>
              </div>
            </div>
            {DEMO_MODE ? (
              <p className="text-center font-mono text-[11px] uppercase tracking-[0.08em] text-white/60">
                View only — trading disabled in demo
              </p>
            ) : (
              <div className="flex gap-2.5">
                <button
                  onClick={() => setConfirming("yes")}
                  className="flex-1 rounded-lg bg-[#5fb88a] py-2.5 font-mono text-[13px] font-bold text-[#0b0e12]"
                >
                  BUY YES
                </button>
                <button
                  onClick={() => setConfirming("no")}
                  className="flex-1 rounded-lg bg-[#e2564f] py-2.5 font-mono text-[13px] font-bold text-white"
                >
                  BUY NO
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="min-w-[260px] rounded-xl border border-white/20 bg-black/30 p-5 text-sm text-white/70 backdrop-blur">
            No scoreable market for {label.toLowerCase()} yet.
          </div>
        )}
      </div>

      {hourly && hourlyMode === "today" && <TodayHourlyStrip data={hourly} />}
      {hourly && hourlyMode === "tomorrow" && (
        <TomorrowHourlyStrip data={hourly} tomorrowDate={date} />
      )}

      {openTrades.length > 0 && (
        <div className="mt-5 space-y-2 border-t border-white/10 pt-4">
          <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-white/60">
            Active position{openTrades.length > 1 ? "s" : ""}
          </div>
          {openTrades.map((t) => (
            <div
              key={t.id}
              className="flex items-center justify-between rounded-lg border border-white/15 bg-black/25 px-4 py-2.5"
            >
              <div className="flex items-center gap-2.5">
                <TradeSourceBadge isBot={t.is_bot_trade} variant="dark" />
                <span
                  className={
                    "inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.06em] " +
                    (t.side === "yes"
                      ? "border-[var(--yes-border)] bg-[var(--yes-bg)] text-[var(--yes-fg)]"
                      : "border-[var(--no-border)] bg-[var(--no-bg)] text-[var(--no-fg)]")
                  }
                >
                  {t.side}
                </span>
                <span className="font-mono text-xs text-white/90">{bracketLabel(t)}</span>
              </div>
              <span className="font-mono text-xs text-white/70">
                {Math.round(t.price * 100)}¢ · ${t.size.toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      )}

      {confirming && topRecommendation && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-sm rounded border border-[var(--card-border)] bg-[var(--card-bg)] p-5 shadow-xl">
            <h4 className="mb-1 text-base font-semibold">
              Simulated bet: {confirming.toUpperCase()} on {bracketLabel(topRecommendation)}
            </h4>
            <p className="mb-3 font-mono text-xs text-[var(--foreground-tertiary)]">
              {topRecommendation.contract_id}
            </p>
            <p className="mb-4 rounded-sm border border-[var(--paper-banner-border)] bg-[var(--paper-banner-bg)] px-2.5 py-1.5 text-xs font-medium text-[var(--paper-banner-fg)]">
              Paper money only — this will not place a real order on Kalshi.
            </p>
            <label className="mb-1 block text-xs font-medium text-[var(--foreground-secondary)]">
              Amount (simulated $)
            </label>
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="mb-3 w-full rounded-sm border border-[var(--card-border)] bg-[var(--input-bg)] px-3 py-2 text-sm outline-none focus:border-[var(--accent-forecast)]"
              min={1}
              step={1}
            />
            {error && <p className="mb-3 text-xs text-[var(--negative)]">{error}</p>}
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setConfirming(null)}
                className="rounded-sm px-3 py-1.5 text-sm text-[var(--foreground-secondary)] hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                onClick={() => submitBet(confirming)}
                disabled={placing}
                className="rounded-sm bg-[var(--accent-forecast)] px-3 py-1.5 text-sm font-medium text-[#0b0e12] disabled:opacity-50"
              >
                {placing ? "Placing…" : "Place paper bet"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
