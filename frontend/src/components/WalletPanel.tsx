"use client";

import type { Wallet } from "@/lib/api";

function fmtUsd(v: number): string {
  return v.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

export default function WalletPanel({ wallet }: { wallet: Wallet }) {
  const pnl = wallet.balance - wallet.starting_balance;
  const pnlPositive = pnl >= 0;

  return (
    <div className="space-y-5">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">
          Paper balance
        </p>
        <p className="text-3xl font-semibold tabular-nums">{fmtUsd(wallet.balance)}</p>
        <p
          className={`text-sm font-medium tabular-nums ${
            pnlPositive ? "text-[var(--positive)]" : "text-[var(--negative)]"
          }`}
        >
          {pnlPositive ? "+" : ""}
          {fmtUsd(pnl)} since start ({fmtUsd(wallet.starting_balance)})
        </p>
      </div>

      {wallet.open_trades.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-500">
            Open positions ({wallet.open_trades.length})
          </p>
          <ul className="space-y-1.5">
            {wallet.open_trades.map((t) => (
              <li
                key={t.id}
                className="flex items-center justify-between rounded-md bg-[var(--table-head-bg)] px-3 py-2 text-sm"
              >
                <div>
                  <span className="font-medium">{t.contract_id}</span>
                  <span className="ml-2 text-xs text-neutral-500">
                    {t.side.toUpperCase()} @ {Math.round(t.price * 100)}¢
                  </span>
                </div>
                <span className="tabular-nums text-neutral-500">{fmtUsd(t.size)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {wallet.settled_trades.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-500">
            History ({wallet.settled_trades.length})
          </p>
          <ul className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
            {wallet.settled_trades.map((t) => (
              <li
                key={t.id}
                className="flex items-center justify-between rounded-md bg-[var(--table-head-bg)] px-3 py-2 text-sm"
              >
                <div>
                  <span className="font-medium">{t.contract_id}</span>
                  <span className="ml-2 text-xs text-neutral-500">
                    {t.side.toUpperCase()} @ {Math.round(t.price * 100)}¢
                  </span>
                </div>
                <span
                  className={`tabular-nums font-medium ${
                    (t.pnl ?? 0) >= 0 ? "text-[var(--positive)]" : "text-[var(--negative)]"
                  }`}
                >
                  {(t.pnl ?? 0) >= 0 ? "+" : ""}
                  {fmtUsd(t.pnl ?? 0)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {wallet.open_trades.length === 0 && wallet.settled_trades.length === 0 && (
        <p className="text-sm text-neutral-500">No paper trades yet — place a bet below.</p>
      )}
    </div>
  );
}
