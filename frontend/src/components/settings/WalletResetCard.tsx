"use client";

import { useState } from "react";
import { resetWallet } from "@/lib/api";

export default function WalletResetCard() {
  const [amount, setAmount] = useState("1000");
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleReset() {
    const val = parseFloat(amount);
    if (!val || val <= 0) {
      setMessage("Enter a valid starting balance");
      return;
    }
    await resetWallet(val);
    setMessage(`Wallet reset to $${val.toLocaleString()}. All paper trade history cleared.`);
    setConfirming(false);
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-[var(--foreground-secondary)]">
        Clears all paper trades and resets the balance. This cannot be undone.
      </p>
      <div className="flex items-center gap-2">
        <input
          type="number"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          className="w-28 rounded-sm border border-[var(--card-border)] bg-[var(--input-bg)] px-2.5 py-1.5 text-sm outline-none focus:border-[var(--accent-forecast)]"
          min={1}
        />
        {!confirming ? (
          <button
            onClick={() => setConfirming(true)}
            className="rounded-sm border border-[var(--no-border)] bg-[var(--no-bg)] px-3 py-1.5 text-sm font-medium text-[var(--no-fg)]"
          >
            Reset wallet
          </button>
        ) : (
          <>
            <button
              onClick={handleReset}
              className="rounded-sm bg-[var(--negative)] px-3 py-1.5 text-sm font-medium text-white"
            >
              Confirm reset
            </button>
            <button
              onClick={() => setConfirming(false)}
              className="rounded-sm px-3 py-1.5 text-sm text-[var(--foreground-secondary)] hover:bg-white/5"
            >
              Cancel
            </button>
          </>
        )}
      </div>
      {message && <p className="text-xs text-[var(--foreground-secondary)]">{message}</p>}
    </div>
  );
}
