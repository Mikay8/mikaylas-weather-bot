"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import DataFreshness from "@/components/DataFreshness";
import ForecastChart from "@/components/ForecastChart";
import MarketsTable from "@/components/MarketsTable";
import TomorrowWidget from "@/components/TomorrowWidget";
import TradeHistory from "@/components/TradeHistory";
import WalletPanel from "@/components/WalletPanel";
import {
  fetchForecastVsActual,
  fetchMarkets,
  fetchRecommendations,
  fetchStatus,
  fetchWallet,
  resolveTrades,
  type DataStatus,
  type ForecastVsActual,
  type MarketSnapshot,
  type Recommendation,
  type Wallet,
} from "@/lib/api";

export default function Home() {
  const [forecastData, setForecastData] = useState<ForecastVsActual[]>([]);
  const [markets, setMarkets] = useState<MarketSnapshot[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [status, setStatus] = useState<DataStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadAll = useCallback(async () => {
    try {
      await resolveTrades().catch(() => {});
      const [f, m, w, s, r] = await Promise.all([
        fetchForecastVsActual(),
        fetchMarkets(),
        fetchWallet(),
        fetchStatus(),
        fetchRecommendations().catch(() => []),
      ]);
      setForecastData(f);
      setMarkets(m);
      setWallet(w);
      setStatus(s);
      setRecommendations(r);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
    const interval = setInterval(loadAll, 30_000);
    return () => clearInterval(interval);
  }, [loadAll]);

  // Station/market date is NYC local (America/New_York), not the browser's zone.
  const nyTomorrow = (() => {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/New_York",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
    const y = Number(parts.find((p) => p.type === "year")!.value);
    const mo = Number(parts.find((p) => p.type === "month")!.value);
    const d = Number(parts.find((p) => p.type === "day")!.value);
    const todayNY = new Date(Date.UTC(y, mo - 1, d));
    todayNY.setUTCDate(todayNY.getUTCDate() + 1);
    return todayNY.toISOString().slice(0, 10);
  })();

  const tomorrowMarkets = markets.filter((m) => m.target_date === nyTomorrow);
  const tomorrowRecommendations = recommendations.filter((r) => r.target_date === nyTomorrow);
  const tomorrowForecast =
    forecastData.find((f) => f.target_date === nyTomorrow)?.predicted_high ?? null;
  const topTomorrowRecommendation =
    [...tomorrowRecommendations].sort(
      (a, b) => (b.fee_adjusted_edge ?? -1) - (a.fee_adjusted_edge ?? -1)
    )[0] ?? null;

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-[var(--foreground-secondary)]">
        Loading…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-2 text-sm">
        <p className="text-[var(--negative)]">Failed to reach the API: {error}</p>
        <p className="text-[var(--foreground-secondary)]">
          Is the backend running? (uvicorn weatherbot.api.main:app --port 8000)
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="sticky top-0 z-40 flex items-center justify-center gap-2.5 border-b border-[var(--paper-banner-border)] bg-[var(--paper-banner-bg)] px-7 py-2.5">
        <span
          className="inline-block h-[7px] w-[7px] rounded-full bg-[var(--accent-forecast)]"
          style={{ boxShadow: "0 0 8px var(--accent-forecast)" }}
        />
        <span className="font-mono text-xs font-semibold tracking-[0.12em] text-[var(--paper-banner-fg)]">
          SIMULATED / PAPER TRADING — no real orders are ever placed
        </span>
      </div>

      <main className="mx-auto max-w-[1360px] px-7 pb-16 pt-8">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-6">
          <div>
            <h1 className="text-[26px] font-bold tracking-tight">Mikayla&apos;s Weather Bot</h1>
            <p className="mt-1.5 font-mono text-[13px] text-[var(--foreground-secondary)]">
              NYC daily-high forecasts vs. Kalshi KXHIGHNY · paper trading only
            </p>
            {status && <DataFreshness status={status} />}
          </div>
          <div className="flex overflow-hidden rounded border border-[var(--card-border)]">
            <span className="bg-[#1a2028] px-[18px] py-[9px] font-sans text-[13px] font-semibold">
              Dashboard
            </span>
            <Link
              href="/settings"
              className="border-l border-[var(--card-border)] px-[18px] py-[9px] font-sans text-[13px] font-semibold text-[var(--foreground-secondary)] no-underline hover:bg-[var(--table-head-bg)] hover:text-[var(--foreground)]"
            >
              Settings
            </Link>
          </div>
        </header>

        <TomorrowWidget
          date={nyTomorrow}
          forecastHigh={tomorrowForecast}
          topRecommendation={topTomorrowRecommendation}
          onBetPlaced={loadAll}
        />

        <div className="mb-5 rounded border border-[var(--card-border)] bg-[var(--card-bg)] p-6">
          <h2 className="mb-[18px] text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--foreground-tertiary)]">
            Forecast vs. Actual High (°F)
          </h2>
          <ForecastChart data={forecastData} />
          <div className="mt-4 flex gap-5">
            <span className="flex items-center gap-1.5 text-xs text-[var(--foreground-secondary)]">
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-[var(--accent-forecast)]" />
              Forecast
            </span>
            <span className="flex items-center gap-1.5 text-xs text-[var(--foreground-secondary)]">
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-[var(--accent-actual)]" />
              Actual (NWS CLI)
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.4fr_1fr]">
          <div className="rounded border border-[var(--card-border)] bg-[var(--card-bg)] p-6">
            <h2 className="mb-[18px] text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--foreground-tertiary)]">
              Tomorrow&apos;s KXHIGHNY Markets ({nyTomorrow})
            </h2>
            {tomorrowMarkets.length === 0 ? (
              <p className="text-sm text-[var(--foreground-secondary)]">
                No open markets for tomorrow yet — run the Kalshi ingest script.
              </p>
            ) : (
              <MarketsTable
                markets={tomorrowMarkets}
                recommendations={tomorrowRecommendations}
                onBetPlaced={loadAll}
              />
            )}
          </div>

          <div className="rounded border border-[var(--paper-banner-border)] border-dashed bg-[var(--paper-banner-bg)] p-6">
            <div className="mb-1 flex items-center gap-2.5">
              <h2 className="text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--paper-banner-fg)]">
                Paper Wallet
              </h2>
              <span className="rounded-sm border border-[var(--paper-banner-border)] bg-[#12283a] px-2 py-0.5 font-mono text-[10px] tracking-[0.08em] text-[var(--accent-forecast)]">
                SIMULATED
              </span>
            </div>
            <p className="mb-5 text-xs text-[var(--foreground-secondary)]">
              Not connected to a real Kalshi account.
            </p>
            {wallet && <WalletPanel wallet={wallet} />}
          </div>
        </div>

        <div className="mt-5 rounded border border-[var(--card-border)] bg-[var(--card-bg)] p-6">
          <h2 className="mb-[18px] text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--foreground-tertiary)]">
            Trade History
          </h2>
          {wallet && (
            <TradeHistory trades={wallet.settled_trades} startingBalance={wallet.starting_balance} />
          )}
        </div>
      </main>
    </>
  );
}
