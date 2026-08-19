"use client";

import { useState } from "react";
import { backfillHistorical, backfillKalshiMarkets, backfillSettlements } from "@/lib/api";

export default function BackfillCard({ onDone }: { onDone: () => void }) {
  const [runningRecent, setRunningRecent] = useState(false);
  const [runningHistorical, setRunningHistorical] = useState(false);
  const [runningKalshi, setRunningKalshi] = useState(false);
  const [recentResult, setRecentResult] = useState<string | null>(null);
  const [historicalResult, setHistoricalResult] = useState<string | null>(null);
  const [kalshiResult, setKalshiResult] = useState<string | null>(null);
  const [days, setDays] = useState("365");

  async function handleRecent() {
    setRunningRecent(true);
    setRecentResult(null);
    try {
      const res = await backfillSettlements(14);
      setRecentResult(`Settlements now cover ${res.earliest} → ${res.latest} (${res.row_count} rows).`);
      onDone();
    } catch (e) {
      setRecentResult(e instanceof Error ? e.message : "Backfill failed");
    } finally {
      setRunningRecent(false);
    }
  }

  async function handleHistorical() {
    const n = parseInt(days, 10);
    if (!n || n <= 0) {
      setHistoricalResult("Enter a valid number of days");
      return;
    }
    setRunningHistorical(true);
    setHistoricalResult(null);
    try {
      const res = await backfillHistorical(n);
      setHistoricalResult(
        `Settlements: ${res.settlements.row_count} rows (${res.settlements.earliest} → ${res.settlements.latest}). ` +
          `Forecasts: ${res.forecasts.row_count} rows (${res.forecasts.earliest} → ${res.forecasts.latest}).`
      );
      onDone();
    } catch (e) {
      setHistoricalResult(e instanceof Error ? e.message : "Historical backfill failed");
    } finally {
      setRunningHistorical(false);
    }
  }

  async function handleKalshi() {
    setRunningKalshi(true);
    setKalshiResult(null);
    try {
      const res = await backfillKalshiMarkets();
      setKalshiResult(
        `${res.row_count} price snapshots across ${res.market_count} markets (${res.earliest} → ${res.latest}).`
      );
      onDone();
    } catch (e) {
      setKalshiResult(e instanceof Error ? e.message : "Kalshi backfill failed");
    } finally {
      setRunningKalshi(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <p className="text-sm font-medium">Historical backfill (IEM Mesonet)</p>
        <p className="text-xs text-[var(--foreground-secondary)]">
          Pulls both settlements and next-day GFS MOS forecasts from IEM&apos;s free archive
          (back to 2000+) — this is the real Phase 2 backtest dataset. Runs sequentially, one
          request per day, so a full year takes a few minutes.
        </p>
        <div className="flex items-center gap-2">
          <input
            type="number"
            value={days}
            onChange={(e) => setDays(e.target.value)}
            className="w-24 rounded-sm border border-[var(--card-border)] bg-[var(--input-bg)] px-2.5 py-1.5 text-sm outline-none focus:border-[var(--accent-forecast)]"
            min={1}
          />
          <span className="text-xs text-[var(--foreground-secondary)]">days back from today</span>
          <button
            onClick={handleHistorical}
            disabled={runningHistorical}
            className="rounded-sm bg-[var(--accent-forecast)] px-3 py-1.5 text-sm font-medium text-[#0b0e12] disabled:opacity-50"
          >
            {runningHistorical ? "Backfilling…" : "Run historical backfill"}
          </button>
        </div>
        {historicalResult && (
          <p className="font-mono text-xs text-[var(--foreground-secondary)]">{historicalResult}</p>
        )}
      </div>

      <div className="space-y-2 border-t border-[var(--card-border)] pt-4">
        <p className="text-sm font-medium">Quick NWS catch-up</p>
        <p className="text-xs text-[var(--foreground-secondary)]">
          NWS only exposes ~6–7 days of CLI report history — this just catches recent
          settlements up to what NWS currently has, using the same source as the live
          settlement-cron job.
        </p>
        <button
          onClick={handleRecent}
          disabled={runningRecent}
          className="rounded-sm border border-[var(--card-border)] px-3 py-1.5 text-sm font-medium hover:bg-[var(--table-head-bg)] disabled:opacity-50"
        >
          {runningRecent ? "Backfilling…" : "Backfill settlements (last ~7 days)"}
        </button>
        {recentResult && (
          <p className="font-mono text-xs text-[var(--foreground-secondary)]">{recentResult}</p>
        )}
      </div>

      <div className="space-y-2 border-t border-[var(--card-border)] pt-4">
        <p className="text-sm font-medium">Kalshi market price history</p>
        <p className="text-xs text-[var(--foreground-secondary)]">
          Pulls hourly bid/ask/price history for settled KXHIGHNY markets from Kalshi&apos;s
          candlesticks API. Only backfills markets that closed on or after 2026-08-14 — the date
          Kalshi switched KXHIGHNY&apos;s settlement source from NWS to The Weather Company —
          since mixing in older data would blend two different settlement regimes. Kalshi&apos;s
          API also only exposes settled markets back to roughly late June regardless, so this
          isn&apos;t a deep multi-year archive the way the weather backfill above is.
        </p>
        <button
          onClick={handleKalshi}
          disabled={runningKalshi}
          className="rounded-sm border border-[var(--card-border)] px-3 py-1.5 text-sm font-medium hover:bg-[var(--table-head-bg)] disabled:opacity-50"
        >
          {runningKalshi ? "Backfilling…" : "Backfill Kalshi market history"}
        </button>
        {kalshiResult && (
          <p className="font-mono text-xs text-[var(--foreground-secondary)]">{kalshiResult}</p>
        )}
      </div>
    </div>
  );
}
