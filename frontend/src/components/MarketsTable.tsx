"use client";

import { useState } from "react";
import type { MarketSnapshot } from "@/lib/api";
import { placeBet } from "@/lib/api";

function bracketLabel(m: MarketSnapshot): string {
  if (m.strike_type === "greater") return `> ${m.bracket_low}°F`;
  if (m.strike_type === "less") return `< ${m.bracket_high}°F`;
  return `${m.bracket_low}–${m.bracket_high}°F`;
}

function fmtCents(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return `${Math.round(v * 100)}¢`;
}

export default function MarketsTable({
  markets,
  onBetPlaced,
}: {
  markets: MarketSnapshot[];
  onBetPlaced: () => void;
}) {
  const [betTarget, setBetTarget] = useState<{ contract: MarketSnapshot; side: "yes" | "no" } | null>(
    null
  );
  const [amount, setAmount] = useState("25");
  const [placing, setPlacing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const grouped = new Map<string, MarketSnapshot[]>();
  for (const m of markets) {
    const key = m.target_date ?? "unknown";
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push(m);
  }
  const dates = [...grouped.keys()].sort();

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
    <div className="space-y-6">
      {dates.map((date) => (
        <div key={date}>
          <h3 className="mb-2 text-sm font-medium text-neutral-500">{date}</h3>
          <div className="overflow-x-auto rounded-lg border border-[var(--card-border)]">
            <table className="w-full min-w-[520px] text-sm">
              <thead>
                <tr className="border-b border-[var(--card-border)] bg-[var(--table-head-bg)] text-left text-neutral-500">
                  <th className="px-3 py-2 font-medium">Bracket</th>
                  <th className="px-3 py-2 font-medium">Yes bid/ask</th>
                  <th className="px-3 py-2 font-medium">Implied prob</th>
                  <th className="px-3 py-2 font-medium">Volume</th>
                  <th className="px-3 py-2 font-medium text-right">Bet</th>
                </tr>
              </thead>
              <tbody>
                {grouped
                  .get(date)!
                  .sort((a, b) => (a.bracket_low ?? -999) - (b.bracket_low ?? -999))
                  .map((m) => (
                    <tr key={m.contract_id} className="border-b border-[var(--card-border)] last:border-0">
                      <td className="px-3 py-2 font-medium">{bracketLabel(m)}</td>
                      <td className="px-3 py-2 tabular-nums">
                        {fmtCents(m.yes_bid)} / {fmtCents(m.yes_ask)}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {m.implied_prob !== null ? `${Math.round(m.implied_prob * 100)}%` : "—"}
                      </td>
                      <td className="px-3 py-2 tabular-nums text-neutral-500">
                        {m.volume?.toLocaleString() ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <div className="inline-flex gap-1.5">
                          <button
                            onClick={() => setBetTarget({ contract: m, side: "yes" })}
                            className="rounded-md bg-[var(--yes-bg)] px-2.5 py-1 text-xs font-medium text-[var(--yes-fg)] hover:opacity-80"
                          >
                            Yes
                          </button>
                          <button
                            onClick={() => setBetTarget({ contract: m, side: "no" })}
                            className="rounded-md bg-[var(--no-bg)] px-2.5 py-1 text-xs font-medium text-[var(--no-fg)] hover:opacity-80"
                          >
                            No
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      {betTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-xl border border-[var(--card-border)] bg-[var(--card-bg)] p-5 shadow-xl">
            <h4 className="mb-1 text-base font-semibold">
              Bet {betTarget.side.toUpperCase()} on {bracketLabel(betTarget.contract)}
            </h4>
            <p className="mb-4 text-xs text-neutral-500">{betTarget.contract.contract_id}</p>
            <label className="mb-1 block text-xs font-medium text-neutral-500">
              Amount (paper $)
            </label>
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="mb-3 w-full rounded-md border border-[var(--card-border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-[var(--accent-forecast)]"
              min={1}
              step={1}
            />
            {error && <p className="mb-3 text-xs text-red-500">{error}</p>}
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setBetTarget(null)}
                className="rounded-md px-3 py-1.5 text-sm text-neutral-500 hover:bg-neutral-500/10"
              >
                Cancel
              </button>
              <button
                onClick={submitBet}
                disabled={placing}
                className="rounded-md bg-[var(--accent-forecast)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                {placing ? "Placing…" : "Place bet"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
