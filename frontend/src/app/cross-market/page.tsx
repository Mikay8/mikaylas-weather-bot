"use client";

import Link from "next/link";
import { Fragment, useCallback, useEffect, useState } from "react";
import { logout } from "@/app/actions";
import {
  DEMO_MODE,
  fetchCrossMarketHistory,
  fetchCrossMarketPairs,
  fetchCrossMarketSummary,
  triggerCrossMarketScan,
  type CrossMarketPair,
  type CrossMarketSnapshot,
  type CrossMarketSummary,
} from "@/lib/api";

function cents(v: number | null, digits = 1): string {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(digits)}¢`;
}

function signedCents(v: number | null): string {
  if (v === null || v === undefined) return "—";
  const c = v * 100;
  return `${c >= 0 ? "+" : ""}${c.toFixed(2)}¢`;
}

function book(bid: number | null, ask: number | null): string {
  if (bid === null && ask === null) return "no book";
  return `${cents(bid)} / ${cents(ask)}`;
}

function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  return hrs < 24 ? `${hrs}h ago` : `${Math.round(hrs / 24)}d ago`;
}

const DIRECTION_LABELS: Record<string, string> = {
  buy_yes_kalshi_buy_no_polymarket: "Buy YES Kalshi · NO Polymarket",
  buy_yes_polymarket_buy_no_kalshi: "Buy YES Polymarket · NO Kalshi",
};

function SummaryCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded border border-[var(--card-border)] px-4 py-3">
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-[var(--foreground-secondary)]">
        {label}
      </div>
      <div className="mt-1 text-xl font-bold">{value}</div>
      {sub && <div className="mt-0.5 font-mono text-[11px] text-[var(--foreground-secondary)]">{sub}</div>}
    </div>
  );
}

function HistoryPanel({ pairId }: { pairId: number }) {
  const [rows, setRows] = useState<CrossMarketSnapshot[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCrossMarketHistory(pairId)
      .then(setRows)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load history"));
  }, [pairId]);

  if (error) return <div className="px-4 py-3 text-[13px] text-red-400">{error}</div>;
  if (!rows) return <div className="px-4 py-3 text-[13px] text-[var(--foreground-secondary)]">Loading history…</div>;
  return (
    <div className="overflow-x-auto px-4 py-3">
      <table className="w-full font-mono text-[12px]">
        <thead>
          <tr className="text-left text-[var(--foreground-secondary)]">
            <th className="pb-1 pr-4 font-medium">Scanned</th>
            <th className="pb-1 pr-4 font-medium">Kalshi YES bid/ask</th>
            <th className="pb-1 pr-4 font-medium">Polymarket YES bid/ask</th>
            <th className="pb-1 pr-4 font-medium">Manifold</th>
            <th className="pb-1 pr-4 font-medium">Mid gap</th>
            <th className="pb-1 font-medium">Net edge</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-[var(--card-border)]">
              <td className="py-1 pr-4">{new Date(r.scanned_at).toLocaleString()}</td>
              <td className="py-1 pr-4">{book(r.kalshi_yes_bid, r.kalshi_yes_ask)}</td>
              <td className="py-1 pr-4">{book(r.poly_yes_bid, r.poly_yes_ask)}</td>
              <td className="py-1 pr-4">{r.manifold_prob === null ? "—" : `${(r.manifold_prob * 100).toFixed(0)}%`}</td>
              <td className="py-1 pr-4">{cents(r.mid_gap, 2)}</td>
              <td className="py-1" style={{ color: (r.arb_edge ?? 0) > 0 ? "#4ade80" : undefined }}>
                {signedCents(r.arb_edge)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function CrossMarketPage() {
  const [pairs, setPairs] = useState<CrossMarketPair[]>([]);
  const [summary, setSummary] = useState<CrossMarketSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  const load = useCallback(() => {
    return Promise.all([fetchCrossMarketPairs(), fetchCrossMarketSummary()])
      .then(([p, s]) => {
        setPairs(p);
        setSummary(s);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load cross-market data"));
  }, []);

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, [load]);

  const onScan = async () => {
    setScanning(true);
    try {
      await triggerCrossMarketScan();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-[var(--foreground-secondary)]">
        Loading…
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
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4 sm:gap-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight sm:text-[26px]">Cross-Market</h1>
            <p className="mt-1.5 font-mono text-[13px] text-[var(--foreground-secondary)]">
              The same event on Kalshi vs. Polymarket — executable bid/ask only, net of Kalshi&apos;s
              taker fee. Manifold shown as a play-money reference, never traded on.
            </p>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <div className="flex overflow-hidden rounded border border-[var(--card-border)]">
              <Link
                href="/"
                className="px-3 py-[9px] font-sans text-[13px] font-semibold text-[var(--foreground-secondary)] no-underline hover:bg-[var(--table-head-bg)] hover:text-[var(--foreground)] sm:px-[18px]"
              >
                Dashboard
              </Link>
              <Link
                href="/analytics"
                className="border-l border-[var(--card-border)] px-3 py-[9px] font-sans text-[13px] font-semibold text-[var(--foreground-secondary)] no-underline hover:bg-[var(--table-head-bg)] hover:text-[var(--foreground)] sm:px-[18px]"
              >
                Analytics
              </Link>
              <span className="border-l border-[var(--card-border)] bg-[#1a2028] px-3 py-[9px] font-sans text-[13px] font-semibold sm:px-[18px]">
                Cross-Market
              </span>
              {!DEMO_MODE && (
                <Link
                  href="/settings"
                  className="border-l border-[var(--card-border)] px-3 py-[9px] font-sans text-[13px] font-semibold text-[var(--foreground-secondary)] no-underline hover:bg-[var(--table-head-bg)] hover:text-[var(--foreground)] sm:px-[18px]"
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

        {error && (
          <div className="mb-4 rounded border border-red-900 bg-red-950/40 px-4 py-3 text-[13px] text-red-300">
            {error}
          </div>
        )}

        <section className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <SummaryCard label="Pairs tracked" value={String(summary?.pairs_tracked ?? 0)} />
          <SummaryCard
            label="Last scan"
            value={timeAgo(summary?.last_scan_at ?? null)}
            sub={summary?.last_scan_at ? new Date(summary.last_scan_at).toLocaleString() : undefined}
          />
          <SummaryCard
            label="Opportunities now"
            value={String(summary?.opportunities_now ?? 0)}
            sub="net edge > 0¢"
          />
          <SummaryCard label="Best edge now" value={signedCents(summary?.best_edge_now ?? null)} />
          <SummaryCard label="Avg mid gap" value={cents(summary?.avg_mid_gap ?? null, 2)} />
        </section>

        {!DEMO_MODE && (
          <div className="mb-6 flex items-center gap-3">
            <button
              onClick={onScan}
              disabled={scanning}
              className="rounded border border-[var(--card-border)] px-4 py-2 font-sans text-[13px] font-semibold hover:bg-[var(--table-head-bg)] disabled:opacity-50"
            >
              {scanning ? "Scanning… (~15s)" : "Scan now"}
            </button>
            <span className="font-mono text-[12px] text-[var(--foreground-secondary)]">
              The scanner also runs every 15 minutes on its own.
            </span>
          </div>
        )}

        {pairs.length === 0 ? (
          <div className="rounded border border-[var(--card-border)] px-4 py-8 text-center text-[13px] text-[var(--foreground-secondary)]">
            No matched pairs yet. {DEMO_MODE ? "Check back after the next scheduled scan." : "Run a scan to compare current markets."}
          </div>
        ) : (
          <div className="overflow-x-auto rounded border border-[var(--card-border)]">
            <table className="w-full min-w-[900px] text-[13px]">
              <thead>
                <tr className="bg-[var(--table-head-bg)] text-left font-mono text-[11px] uppercase tracking-[0.06em] text-[var(--foreground-secondary)]">
                  <th className="px-4 py-2.5 font-medium">Event</th>
                  <th className="px-4 py-2.5 font-medium">Kalshi YES</th>
                  <th className="px-4 py-2.5 font-medium">Polymarket YES</th>
                  <th className="px-4 py-2.5 font-medium">Manifold</th>
                  <th className="px-4 py-2.5 font-medium">Mid gap</th>
                  <th className="px-4 py-2.5 font-medium">Net arb edge</th>
                  <th className="px-4 py-2.5 font-medium">Seen</th>
                </tr>
              </thead>
              <tbody>
                {pairs.map((p) => (
                  <Fragment key={p.pair_id}>
                    <tr
                      onClick={() => setExpanded(expanded === p.pair_id ? null : p.pair_id)}
                      className="cursor-pointer border-t border-[var(--card-border)] hover:bg-[var(--table-head-bg)]"
                    >
                      <td className="max-w-[340px] px-4 py-3">
                        <div className="font-medium leading-snug">{p.kalshi_title}</div>
                        <div className="mt-0.5 leading-snug text-[var(--foreground-secondary)]">{p.poly_question}</div>
                        <div className="mt-1 font-mono text-[11px] text-[var(--foreground-secondary)]">
                          match {(p.match_score * 100).toFixed(0)}%
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 font-mono">{book(p.kalshi_yes_bid, p.kalshi_yes_ask)}</td>
                      <td className="whitespace-nowrap px-4 py-3 font-mono">{book(p.poly_yes_bid, p.poly_yes_ask)}</td>
                      <td className="whitespace-nowrap px-4 py-3 font-mono">
                        {p.manifold_prob === null ? "—" : `${(p.manifold_prob * 100).toFixed(0)}%`}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 font-mono">{cents(p.mid_gap, 2)}</td>
                      <td className="whitespace-nowrap px-4 py-3 font-mono">
                        <span style={{ color: (p.arb_edge ?? 0) > 0 ? "#4ade80" : undefined, fontWeight: (p.arb_edge ?? 0) > 0 ? 700 : 400 }}>
                          {signedCents(p.arb_edge)}
                        </span>
                        {p.arb_direction && (
                          <div className="mt-0.5 font-sans text-[11px] font-normal text-[var(--foreground-secondary)]">
                            {DIRECTION_LABELS[p.arb_direction] ?? p.arb_direction}
                          </div>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-[var(--foreground-secondary)]">
                        {timeAgo(p.scanned_at)}
                      </td>
                    </tr>
                    {expanded === p.pair_id && (
                      <tr className="border-t border-[var(--card-border)] bg-[var(--table-head-bg)]/40">
                        <td colSpan={7} className="p-0">
                          <HistoryPanel pairId={p.pair_id} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="mt-6 font-mono text-[12px] leading-relaxed text-[var(--foreground-secondary)]">
          Measurement only — nothing trades off this page. A positive edge is a momentary snapshot at
          executable prices, net of Kalshi&apos;s taker fee (Polymarket fee assumed 0). Thin or stale
          books — common in long-dated markets — can show gaps that vanish on the next scan; a gap that
          persists across many scans is the signal worth believing.
        </p>
      </main>
    </>
  );
}
