"use client";

import { useCallback, useEffect, useState } from "react";
import DataFreshness from "@/components/DataFreshness";
import ForecastChart from "@/components/ForecastChart";
import MarketsTable from "@/components/MarketsTable";
import WalletPanel from "@/components/WalletPanel";
import {
  fetchForecastVsActual,
  fetchMarkets,
  fetchStatus,
  fetchWallet,
  resolveTrades,
  type DataStatus,
  type ForecastVsActual,
  type MarketSnapshot,
  type Wallet,
} from "@/lib/api";

export default function Home() {
  const [forecastData, setForecastData] = useState<ForecastVsActual[]>([]);
  const [markets, setMarkets] = useState<MarketSnapshot[]>([]);
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [status, setStatus] = useState<DataStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadAll = useCallback(async () => {
    try {
      await resolveTrades().catch(() => {});
      const [f, m, w, s] = await Promise.all([
        fetchForecastVsActual(),
        fetchMarkets(),
        fetchWallet(),
        fetchStatus(),
      ]);
      setForecastData(f);
      setMarkets(m);
      setWallet(w);
      setStatus(s);
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

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-neutral-500">
        Loading…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-2 text-sm">
        <p className="text-red-500">Failed to reach the API: {error}</p>
        <p className="text-neutral-500">
          Is the backend running? (uvicorn weatherbot.api.main:app --port 8000)
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="sticky top-0 z-40 flex items-center justify-center gap-2 bg-[var(--paper-banner-bg)] px-4 py-2 text-center text-sm font-semibold text-[var(--paper-banner-fg)]">
        <span aria-hidden="true">🧪</span>
        PAPER TRADING — simulated money only. No real orders are ever placed.
      </div>
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <header className="mb-8">
          <h1 className="text-2xl font-semibold">Mikayla&apos;s Weather Bot</h1>
          <p className="text-sm text-neutral-500">
            NYC daily high forecasts vs. Kalshi KXHIGHNY markets — paper trading only.
          </p>
          {status && <DataFreshness status={status} />}
        </header>

        <div className="mb-8 rounded-xl border border-[var(--card-border)] bg-[var(--card-bg)] p-5">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-neutral-500">
            Forecast vs. actual high (°F)
          </h2>
          <ForecastChart data={forecastData} />
          <div className="mt-2 flex gap-4 text-xs text-neutral-500">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full bg-[var(--accent-forecast)]" />
              Forecast
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full bg-[var(--accent-actual)]" />
              Actual (NWS CLI)
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_360px]">
          <div className="rounded-xl border border-[var(--card-border)] bg-[var(--card-bg)] p-5">
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-neutral-500">
              Live KXHIGHNY markets
            </h2>
            {markets.length === 0 ? (
              <p className="text-sm text-neutral-500">
                No open markets loaded yet — run the Kalshi ingest script.
              </p>
            ) : (
              <MarketsTable markets={markets} onBetPlaced={loadAll} />
            )}
          </div>

          <div className="rounded-xl border border-[var(--card-border)] bg-[var(--card-bg)] p-5">
            <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-neutral-500">
              Paper wallet
            </h2>
            <p className="mb-4 text-xs text-neutral-500">
              Simulated balance — not connected to a real Kalshi account.
            </p>
            {wallet && <WalletPanel wallet={wallet} />}
          </div>
        </div>
      </main>
    </>
  );
}
