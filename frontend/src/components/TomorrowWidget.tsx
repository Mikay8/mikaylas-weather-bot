"use client";

import { useState } from "react";
import type { ForecastVsActual, Recommendation } from "@/lib/api";
import { placeBet } from "@/lib/api";

function bracketLabel(r: Recommendation): string {
  if (r.strike_type === "greater") return `> ${r.bracket_low}°F`;
  if (r.strike_type === "less") return `< ${r.bracket_high}°F`;
  return `${r.bracket_low}–${r.bracket_high}°F`;
}

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

export default function TomorrowWidget({
  date,
  forecastHigh,
  topRecommendation,
  onBetPlaced,
}: {
  date: string;
  forecastHigh: number | null;
  topRecommendation: Recommendation | null;
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
    <div className="relative mb-5 overflow-hidden rounded-xl border border-[var(--card-border)] bg-gradient-to-br from-[#1a2a42] via-[#2a2450] to-[#3a2450] p-7">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div>
          <div className="text-[13px] font-semibold text-white/85">Tomorrow · {date}</div>
          <div className="mt-1.5 flex items-baseline gap-3">
            <span className="text-[48px] font-light leading-none tracking-tight text-white">
              {forecastHigh !== null ? `${forecastHigh}°` : "—"}
            </span>
            <span className="text-sm text-white/70">NWS forecast high</span>
          </div>
        </div>

        {topRecommendation ? (
          <div className="min-w-[260px] rounded-xl border border-white/20 bg-black/30 p-5 backdrop-blur">
            <div className="mb-2.5 flex items-center gap-2">
              <span className="rounded-sm bg-[#5fb88a] px-1.5 py-0.5 font-mono text-[9.5px] font-bold tracking-[0.08em] text-[#0b0e12]">
                {topRecommendation.recommend ? "RECOMMENDED" : "TOP MODEL PICK"}
              </span>
              <span className="font-mono text-xs text-white/85">{bracketLabel(topRecommendation)}</span>
            </div>
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
          </div>
        ) : (
          <div className="min-w-[260px] rounded-xl border border-white/20 bg-black/30 p-5 text-sm text-white/70 backdrop-blur">
            No scoreable market for tomorrow yet.
          </div>
        )}
      </div>

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
