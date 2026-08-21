"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { logout } from "@/app/actions";
import Countdown from "@/components/Countdown";
import DataFreshness from "@/components/DataFreshness";
import ForecastAgreementBanner from "@/components/ForecastAgreement";
import ForecastChart from "@/components/ForecastChart";
import ForecastDrift from "@/components/ForecastDrift";
import MarketsTable from "@/components/MarketsTable";
import SplitDayWidget from "@/components/SplitDayWidget";
import TradeHistory from "@/components/TradeHistory";
import WalletPanel from "@/components/WalletPanel";
import {
  DEMO_MODE,
  fetchForecastVsActual,
  fetchForecasts,
  fetchMarkets,
  fetchRecommendations,
  fetchStatus,
  fetchWallet,
  resolveTrades,
  type DataStatus,
  type ForecastPull,
  type ForecastVsActual,
  type MarketSnapshot,
  type Recommendation,
  type Wallet,
} from "@/lib/api";

export default function Home() {
  const [forecastData, setForecastData] = useState<ForecastVsActual[]>([]);
  const [forecastPulls, setForecastPulls] = useState<ForecastPull[]>([]);
  const [markets, setMarkets] = useState<MarketSnapshot[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [status, setStatus] = useState<DataStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [marketsDay, setMarketsDay] = useState<"today" | "tomorrow">("today");

  const loadAll = useCallback(async () => {
    try {
      if (!DEMO_MODE) await resolveTrades().catch(() => {});
      const [f, fp, m, w, s, r] = await Promise.all([
        fetchForecastVsActual(),
        fetchForecasts(500).catch(() => []),
        fetchMarkets(),
        fetchWallet(),
        fetchStatus(),
        fetchRecommendations().catch(() => []),
      ]);
      setForecastData(f);
      setForecastPulls(fp);
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
  const nyToday = (() => {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/New_York",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
    const y = Number(parts.find((p) => p.type === "year")!.value);
    const mo = Number(parts.find((p) => p.type === "month")!.value);
    const d = Number(parts.find((p) => p.type === "day")!.value);
    return new Date(Date.UTC(y, mo - 1, d)).toISOString().slice(0, 10);
  })();
  const nyTomorrow = (() => {
    const d = new Date(`${nyToday}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() + 1);
    return d.toISOString().slice(0, 10);
  })();

  function topPick(recs: Recommendation[]): Recommendation | null {
    return (
      [...recs].sort((a, b) => (b.fee_adjusted_edge ?? -1) - (a.fee_adjusted_edge ?? -1))[0] ??
      null
    );
  }

  const todayMarkets = markets.filter((m) => m.target_date === nyToday);
  const todayRecommendations = recommendations.filter((r) => r.target_date === nyToday);
  const todayForecast = forecastData.find((f) => f.target_date === nyToday)?.predicted_high ?? null;
  const topTodayRecommendation = topPick(todayRecommendations);
  const todayOpenTrades = wallet ? wallet.open_trades.filter((t) => t.target_date === nyToday) : [];
  const todayCloseTime = todayMarkets.find((m) => m.close_time)?.close_time ?? null;

  const tomorrowMarkets = markets.filter((m) => m.target_date === nyTomorrow);
  const tomorrowRecommendations = recommendations.filter((r) => r.target_date === nyTomorrow);
  const tomorrowForecast =
    forecastData.find((f) => f.target_date === nyTomorrow)?.predicted_high ?? null;
  const topTomorrowRecommendation = topPick(tomorrowRecommendations);
  const tomorrowOpenTrades = wallet
    ? wallet.open_trades.filter((t) => t.target_date === nyTomorrow)
    : [];

  const displayedMarkets = marketsDay === "today" ? todayMarkets : tomorrowMarkets;
  const displayedRecommendations =
    marketsDay === "today" ? todayRecommendations : tomorrowRecommendations;
  const displayedDate = marketsDay === "today" ? nyToday : nyTomorrow;
  const displayedCloseTime = marketsDay === "today" ? todayCloseTime : null;

  const daysWithMultiplePulls = new Set(
    Object.entries(
      forecastPulls.reduce<Record<string, number>>((acc, p) => {
        acc[p.target_date] = (acc[p.target_date] ?? 0) + 1;
        return acc;
      }, {})
    )
      .filter(([, count]) => count > 1)
      .map(([date]) => date)
  ).size;

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
      <div className="sticky top-0 z-40 flex items-center justify-center gap-2.5 border-b border-[var(--paper-banner-border)] bg-[var(--paper-banner-bg)] px-4 py-2.5 text-center sm:px-7">
        <span
          className="inline-block h-[7px] w-[7px] shrink-0 rounded-full bg-[var(--accent-forecast)]"
          style={{ boxShadow: "0 0 8px var(--accent-forecast)" }}
        />
        <span className="font-mono text-[11px] font-semibold tracking-[0.08em] text-[var(--paper-banner-fg)] sm:text-xs sm:tracking-[0.12em]">
          {DEMO_MODE
            ? "DEMO — VIEW ONLY — trading and settings are disabled"
            : "SIMULATED / PAPER TRADING — no real orders are ever placed"}
        </span>
      </div>

      <main className="mx-auto min-w-0 w-full max-w-[1360px] px-4 pb-16 pt-8 sm:px-7">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight sm:text-[26px]">Mikayla&apos;s Weather Bot</h1>
            <p className="mt-1.5 font-mono text-[13px] text-[var(--foreground-secondary)]">
              NYC daily-high forecasts vs. Kalshi KXHIGHNY · paper trading only
            </p>
            {status && <DataFreshness status={status} />}
          </div>
          <div className="flex items-center gap-3">
            <div className="flex overflow-hidden rounded border border-[var(--card-border)]">
              <span className="bg-[#1a2028] px-[18px] py-[9px] font-sans text-[13px] font-semibold">
                Dashboard
              </span>
              {!DEMO_MODE && (
                <Link
                  href="/settings"
                  className="border-l border-[var(--card-border)] px-[18px] py-[9px] font-sans text-[13px] font-semibold text-[var(--foreground-secondary)] no-underline hover:bg-[var(--table-head-bg)] hover:text-[var(--foreground)]"
                >
                  Settings
                </Link>
              )}
            </div>
            {!DEMO_MODE && (
              <form action={logout}>
                <button
                  type="submit"
                  className="rounded border border-[var(--card-border)] px-3 py-1.5 font-sans text-xs font-medium text-[var(--foreground-secondary)] hover:bg-[var(--table-head-bg)] hover:text-[var(--foreground)]"
                >
                  Log out
                </button>
              </form>
            )}
          </div>
        </header>

        <ForecastAgreementBanner />

        <SplitDayWidget
          today={{
            date: nyToday,
            forecastHigh: todayForecast,
            topRecommendation: topTodayRecommendation,
            openTrades: todayOpenTrades,
            closeTime: todayCloseTime,
          }}
          tomorrow={{
            date: nyTomorrow,
            forecastHigh: tomorrowForecast,
            topRecommendation: topTomorrowRecommendation,
            openTrades: tomorrowOpenTrades,
          }}
          onBetPlaced={loadAll}
        />

        <div className="mb-5 rounded border border-[var(--paper-banner-border)] border-dashed bg-[var(--paper-banner-bg)] p-6">
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

        <div className="mb-5 rounded border border-[var(--card-border)] bg-[var(--card-bg)] p-6">
          <h2 className="mb-[18px] text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--foreground-tertiary)]">
            Forecast vs. Actual High (°F)
          </h2>
          <p className="mb-4 text-xs text-[var(--foreground-secondary)]">
            One data point per day: that day&apos;s single highest temperature — not an average, not
            an hourly reading.
          </p>
          <ForecastChart data={forecastData} />
        </div>

        <div className="mb-5 rounded border border-[var(--card-border)] bg-[var(--card-bg)] p-6">
          <div className="mb-[18px] flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--foreground-tertiary)]">
              KXHIGHNY Markets — Daily High (°F) ({displayedDate})
            </h2>
            <div className="flex items-center gap-3">
              {marketsDay === "today" && todayCloseTime && (
                <span className="font-mono text-xs text-[var(--foreground-secondary)]">
                  Closes in{" "}
                  <Countdown
                    closeTime={todayCloseTime}
                    className="font-semibold text-[var(--foreground)]"
                    urgentClassName="font-semibold text-[var(--negative)]"
                  />
                </span>
              )}
              <div className="flex overflow-hidden rounded-sm border border-[var(--card-border)]">
                <button
                  onClick={() => setMarketsDay("today")}
                  className="px-3.5 py-1.5 font-sans text-xs font-semibold"
                  style={{
                    background: marketsDay === "today" ? "#1a2028" : "transparent",
                    color:
                      marketsDay === "today"
                        ? "var(--foreground)"
                        : "var(--foreground-secondary)",
                  }}
                >
                  Today
                </button>
                <button
                  onClick={() => setMarketsDay("tomorrow")}
                  className="border-l border-[var(--card-border)] px-3.5 py-1.5 font-sans text-xs font-semibold"
                  style={{
                    background: marketsDay === "tomorrow" ? "#1a2028" : "transparent",
                    color:
                      marketsDay === "tomorrow"
                        ? "var(--foreground)"
                        : "var(--foreground-secondary)",
                  }}
                >
                  Tomorrow
                </button>
              </div>
            </div>
          </div>
          {displayedMarkets.length === 0 ? (
            <p className="text-sm text-[var(--foreground-secondary)]">
              No open markets for {marketsDay} yet — run the Kalshi ingest script.
            </p>
          ) : (
            <MarketsTable
              markets={displayedMarkets}
              recommendations={displayedRecommendations}
              onBetPlaced={loadAll}
            />
          )}
          <ForecastDrift
            pulls={forecastPulls}
            targetDate={displayedDate}
            closeTime={displayedCloseTime}
            daysWithMultiplePulls={daysWithMultiplePulls}
          />
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
