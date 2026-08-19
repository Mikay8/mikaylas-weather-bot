"use client";

import type { Wallet } from "@/lib/api";
import TradeSourceBadge from "@/components/TradeSourceBadge";

function fmtUsd(v: number): string {
  return v.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

export default function WalletPanel({ wallet }: { wallet: Wallet }) {
  const pnl = wallet.balance - wallet.starting_balance;
  const pnlPositive = pnl >= 0;

  return (
    <div className="space-y-5">
      <div>
        <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--foreground-tertiary)]">
          Paper balance
        </p>
        <p className="font-mono text-3xl font-semibold tabular-nums">{fmtUsd(wallet.balance)}</p>
        <p
          className={`font-mono text-sm font-medium tabular-nums ${
            pnlPositive ? "text-[var(--positive)]" : "text-[var(--negative)]"
          }`}
        >
          {pnlPositive ? "+" : ""}
          {fmtUsd(pnl)} since start ({fmtUsd(wallet.starting_balance)})
        </p>
      </div>

      {wallet.open_trades.length > 0 && (
        <div>
          <p className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--foreground-tertiary)]">
            Open positions ({wallet.open_trades.length})
          </p>
          <ul className="space-y-1.5">
            {wallet.open_trades.map((t) => (
              <li
                key={t.id}
                className="flex items-center justify-between rounded-sm border border-[var(--card-border)] bg-[var(--table-head-bg)] px-3 py-2 text-sm"
              >
                <div className="flex items-center gap-2">
                  <TradeSourceBadge isBot={t.is_bot_trade} />
                  <span className="font-medium">{t.contract_id}</span>
                  <span className="font-mono text-xs text-[var(--foreground-secondary)]">
                    {t.side.toUpperCase()} @ {Math.round(t.price * 100)}¢
                  </span>
                </div>
                <span className="font-mono tabular-nums text-[var(--foreground-secondary)]">
                  {fmtUsd(t.size)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {wallet.open_trades.length === 0 && (
        <p className="text-sm text-[var(--foreground-secondary)]">
          No open positions. See Trade History below for past results.
        </p>
      )}
    </div>
  );
}
