"use client";

import { useState } from "react";
import type { MarketSnapshot, Recommendation } from "@/lib/api";
import { placeBet } from "@/lib/api";

function bracketLabel(m: MarketSnapshot): string {
  if (m.kalshi_label) return m.kalshi_label;
  if (m.strike_type === "greater") return `> ${m.bracket_low}°F`;
  if (m.strike_type === "less") return `< ${m.bracket_high}°F`;
  return `${m.bracket_low}–${m.bracket_high}°F`;
}

function fmtCents(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return `${Math.round(v * 100)}¢`;
}

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

export default function MarketsTable({
  markets,
  recommendations,
  onBetPlaced,
}: {
  markets: MarketSnapshot[];
  recommendations: Recommendation[];
  onBetPlaced: () => void;
}) {
  const [betTarget, setBetTarget] = useState<{ contract: MarketSnapshot; side: "yes" | "no" } | null>(
    null
  );
  const [amount, setAmount] = useState("25");
  const [placing, setPlacing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recByContract = new Map(recommendations.map((r) => [r.contract_id, r]));
  const rows = [...markets].sort((a, b) => (a.bracket_low ?? -999) - (b.bracket_low ?? -999));

  async function submitBet() {
    if (!betTarget) return;
    const amt = parseFloat(amount);
    if (!amt || amt <= 0) {
      setError("Enter a valid amount");
      return;
    }
    setPlacing(true);
    setError(null);
    try {
      await placeBet(betTarget.contract.contract_id, betTarget.side, amt);
      setBetTarget(null);
      setAmount("25");
      onBetPlaced();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to place bet");
    } finally {
      setPlacing(false);
    }
  }

  return (
    <div>
      <div className="overflow-x-auto rounded border border-[var(--card-border)]">
        <table className="w-full min-w-[820px] text-sm">
          <thead>
            <tr className="border-b border-[var(--card-border)] bg-[var(--table-head-bg)] text-left text-[var(--foreground-tertiary)]">
              <th className="px-3 py-2 font-mono text-[11px] font-medium uppercase tracking-[0.08em]">
                Bracket
              </th>
              <th className="px-3 py-2 font-mono text-[11px] font-medium uppercase tracking-[0.08em]">
                Yes bid/ask
              </th>
              <th className="px-3 py-2 font-mono text-[11px] font-medium uppercase tracking-[0.08em]">
                Market prob
              </th>
              <th className="px-3 py-2 font-mono text-[11px] font-medium uppercase tracking-[0.08em]">
                Model prob
              </th>
              <th className="px-3 py-2 font-mono text-[11px] font-medium uppercase tracking-[0.08em]">
                Fee-adj. edge
              </th>
              <th className="px-3 py-2 font-mono text-[11px] font-medium uppercase tracking-[0.08em]">
                Signal
              </th>
              <th className="px-3 py-2 font-mono text-[11px] font-medium uppercase tracking-[0.08em]">
                Volume
              </th>
              <th className="px-3 py-2 text-right font-mono text-[11px] font-medium uppercase tracking-[0.08em]">
                Bet
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => {
              const rec = recByContract.get(m.contract_id);
              return (
                <tr key={m.contract_id} className="border-b border-[var(--row-border)] last:border-0">
                  <td className="px-3 py-2 font-medium">{bracketLabel(m)}</td>
                  <td className="px-3 py-2 font-mono tabular-nums">
                    {fmtCents(m.yes_bid)} / {fmtCents(m.yes_ask)}
                  </td>
                  <td className="px-3 py-2 font-mono tabular-nums">
                    {m.implied_prob !== null ? pct(m.implied_prob) : "—"}
                  </td>
                  <td className="px-3 py-2 font-mono tabular-nums text-[var(--foreground-secondary)]">
                    {rec ? pct(rec.model_prob) : "—"}
                  </td>
                  <td
                    className="px-3 py-2 font-mono tabular-nums"
                    style={{
                      color:
                        rec?.fee_adjusted_edge !== undefined &&
                        rec?.fee_adjusted_edge !== null &&
                        rec.fee_adjusted_edge > 0
                          ? "var(--positive)"
                          : "var(--foreground-secondary)",
                    }}
                  >
                    {rec?.fee_adjusted_edge !== undefined && rec?.fee_adjusted_edge !== null
                      ? pct(rec.fee_adjusted_edge)
                      : "—"}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2">
                    {rec?.recommend ? (
                      <span
                        className={
                          "inline-flex items-center whitespace-nowrap rounded-full border px-2.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.06em] " +
                          (rec.side === "yes"
                            ? "border-[var(--yes-border)] bg-[var(--yes-bg)] text-[var(--yes-fg)]"
                            : "border-[var(--no-border)] bg-[var(--no-bg)] text-[var(--no-fg)]")
                        }
                      >
                        Buy {rec.side}
                      </span>
                    ) : (
                      <span className="text-xs text-[var(--foreground-tertiary)]">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 font-mono tabular-nums text-[var(--foreground-secondary)]">
                    {m.volume?.toLocaleString() ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="inline-flex gap-1.5">
                      <button
                        onClick={() => setBetTarget({ contract: m, side: "yes" })}
                        className="rounded-sm border border-[var(--yes-border)] bg-[var(--yes-bg)] px-2.5 py-1 font-mono text-xs font-medium text-[var(--yes-fg)] hover:opacity-80"
                      >
                        Yes
                      </button>
                      <button
                        onClick={() => setBetTarget({ contract: m, side: "no" })}
                        className="rounded-sm border border-[var(--no-border)] bg-[var(--no-bg)] px-2.5 py-1 font-mono text-xs font-medium text-[var(--no-fg)] hover:opacity-80"
                      >
                        No
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {betTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-sm rounded border border-[var(--card-border)] bg-[var(--card-bg)] p-5 shadow-xl">
            <h4 className="mb-1 text-base font-semibold">
              Simulated bet: {betTarget.side.toUpperCase()} on {bracketLabel(betTarget.contract)}
            </h4>
            <p className="mb-3 font-mono text-xs text-[var(--foreground-tertiary)]">
              {betTarget.contract.contract_id}
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
                onClick={() => setBetTarget(null)}
                className="rounded-sm px-3 py-1.5 text-sm text-[var(--foreground-secondary)] hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                onClick={submitBet}
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
