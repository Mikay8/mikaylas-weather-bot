"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Trade } from "@/lib/api";

function fmtUsd(v: number): string {
  return v.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

function bracketLabel(t: Trade): string {
  if (t.strike_type === "greater") return `> ${t.bracket_low}°F`;
  if (t.strike_type === "less") return `< ${t.bracket_high}°F`;
  if (t.bracket_low != null && t.bracket_high != null) return `${t.bracket_low}–${t.bracket_high}°F`;
  return t.contract_id;
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function TradeHistory({
  trades,
  startingBalance,
}: {
  trades: Trade[];
  startingBalance: number;
}) {
  const chronological = useMemo(
    () => [...trades].sort((a, b) => a.timestamp.localeCompare(b.timestamp)),
    [trades]
  );

  const chartData = useMemo(() => {
    let running = startingBalance;
    return chronological.map((t) => {
      running += t.pnl ?? 0;
      return { date: fmtDate(t.timestamp), balance: running };
    });
  }, [chronological, startingBalance]);

  const displayRows = useMemo(() => [...trades], [trades]);

  if (trades.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-sm text-[var(--foreground-secondary)]">
        No settled trades yet — history appears here once a paper bet resolves.
      </div>
    );
  }

  return (
    <div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData} margin={{ top: 8, right: 16, left: -16, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
          <XAxis dataKey="date" tick={{ fontSize: 12, fill: "var(--chart-axis)" }} />
          <YAxis
            tick={{ fontSize: 12, fill: "var(--chart-axis)" }}
            domain={["dataMin - 10", "dataMax + 10"]}
            tickFormatter={(v: number) => `$${Math.round(v)}`}
          />
          <Tooltip
            contentStyle={{
              background: "var(--table-head-bg)",
              border: "1px solid var(--card-border)",
              borderRadius: 3,
              fontSize: 13,
              fontFamily: "var(--font-geist-mono)",
            }}
            labelStyle={{ color: "var(--foreground-secondary)" }}
            formatter={(v) => [fmtUsd(Number(v)), "Balance"]}
          />
          <Line
            type="monotone"
            dataKey="balance"
            stroke="var(--accent-forecast)"
            strokeWidth={2}
            dot={{ r: 2.5 }}
          />
        </LineChart>
      </ResponsiveContainer>

      <div className="mt-5 overflow-x-auto rounded border border-[var(--card-border)]">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b border-[var(--card-border)] bg-[var(--table-head-bg)] text-left text-[var(--foreground-tertiary)]">
              <th className="px-3 py-2 font-mono text-[11px] font-medium uppercase tracking-[0.08em]">
                Date
              </th>
              <th className="px-3 py-2 font-mono text-[11px] font-medium uppercase tracking-[0.08em]">
                Bracket
              </th>
              <th className="px-3 py-2 font-mono text-[11px] font-medium uppercase tracking-[0.08em]">
                Side
              </th>
              <th className="px-3 py-2 font-mono text-[11px] font-medium uppercase tracking-[0.08em]">
                Price
              </th>
              <th className="px-3 py-2 font-mono text-[11px] font-medium uppercase tracking-[0.08em]">
                Size
              </th>
              <th className="px-3 py-2 font-mono text-[11px] font-medium uppercase tracking-[0.08em]">
                Fee
              </th>
              <th className="px-3 py-2 font-mono text-[11px] font-medium uppercase tracking-[0.08em]">
                Result
              </th>
              <th className="px-3 py-2 text-right font-mono text-[11px] font-medium uppercase tracking-[0.08em]">
                P&amp;L
              </th>
            </tr>
          </thead>
          <tbody>
            {displayRows.map((t) => (
              <tr key={t.id} className="border-b border-[var(--row-border)] last:border-0">
                <td className="px-3 py-2 font-mono text-xs text-[var(--foreground-secondary)]">
                  {fmtDate(t.timestamp)}
                </td>
                <td className="px-3 py-2 font-medium">{bracketLabel(t)}</td>
                <td className="px-3 py-2">
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
                </td>
                <td className="px-3 py-2 font-mono tabular-nums">{Math.round(t.price * 100)}¢</td>
                <td className="px-3 py-2 font-mono tabular-nums text-[var(--foreground-secondary)]">
                  {fmtUsd(t.size)}
                </td>
                <td className="px-3 py-2 font-mono tabular-nums text-[var(--foreground-secondary)]">
                  {t.fee != null ? fmtUsd(t.fee) : "—"}
                </td>
                <td className="px-3 py-2">
                  <span
                    className={`font-mono text-xs font-semibold uppercase tracking-[0.06em] ${
                      t.status === "settled_win" ? "text-[var(--positive)]" : "text-[var(--negative)]"
                    }`}
                  >
                    {t.status === "settled_win" ? "Won" : "Lost"}
                  </span>
                </td>
                <td
                  className={`px-3 py-2 text-right font-mono tabular-nums font-medium ${
                    (t.pnl ?? 0) >= 0 ? "text-[var(--positive)]" : "text-[var(--negative)]"
                  }`}
                >
                  {(t.pnl ?? 0) >= 0 ? "+" : ""}
                  {fmtUsd(t.pnl ?? 0)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
