"use client";

import { useEffect, useState } from "react";
import { fetchBotSettings, runBotCycle, updateBotSettings, type BotSettings } from "@/lib/api";

export default function BotControlCard() {
  const [settings, setSettings] = useState<BotSettings | null>(null);
  const [betAmountInput, setBetAmountInput] = useState("25");
  const [thresholdInput, setThresholdInput] = useState("3");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    fetchBotSettings().then((s) => {
      setSettings(s);
      setBetAmountInput(String(s.bet_amount));
      setThresholdInput(String(Math.round(s.edge_threshold * 100)));
    });
  }, []);

  async function toggleEnabled() {
    if (!settings) return;
    setSaving(true);
    try {
      const updated = await updateBotSettings({ enabled: !settings.enabled });
      setSettings(updated);
      setMessage(updated.enabled ? "Bot enabled — it will trade automatically." : "Bot disabled.");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Failed to update");
    } finally {
      setSaving(false);
    }
  }

  async function saveParams() {
    const betAmount = parseFloat(betAmountInput);
    const thresholdPct = parseFloat(thresholdInput);
    if (!betAmount || betAmount <= 0) {
      setMessage("Enter a valid bet amount");
      return;
    }
    if (Number.isNaN(thresholdPct) || thresholdPct < 0 || thresholdPct > 100) {
      setMessage("Enter a valid edge threshold (0-100%)");
      return;
    }
    setSaving(true);
    try {
      const updated = await updateBotSettings({
        bet_amount: betAmount,
        edge_threshold: thresholdPct / 100,
      });
      setSettings(updated);
      setMessage("Bot parameters saved.");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  async function toggleSkipRule() {
    if (!settings) return;
    setSaving(true);
    try {
      const updated = await updateBotSettings({
        skip_if_position_exists: !settings.skip_if_position_exists,
      });
      setSettings(updated);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Failed to update");
    } finally {
      setSaving(false);
    }
  }

  async function handleRunNow() {
    setRunning(true);
    setMessage(null);
    try {
      const result = await runBotCycle();
      if (result.skipped) {
        setMessage(`Bot did not run: ${result.skipped}`);
      } else {
        setMessage(
          `Checked markets: ${result.trades_placed} trade(s) placed, ${result.skipped?.length ?? 0} skipped.`
        );
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Failed to run bot");
    } finally {
      setRunning(false);
    }
  }

  if (!settings) {
    return <p className="text-sm text-[var(--foreground-secondary)]">Loading…</p>;
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between rounded border border-[var(--card-border)] bg-[var(--table-head-bg)] px-4 py-3">
        <div>
          <div className="text-sm font-medium">Auto-trading bot</div>
          <p className="mt-0.5 text-xs text-[var(--foreground-secondary)]">
            {settings.enabled
              ? "On — checks open markets every hour and places a paper trade when the edge clears your threshold."
              : "Off — no trades are placed automatically. Everything runs manually."}
          </p>
        </div>
        <button
          onClick={toggleEnabled}
          disabled={saving}
          role="switch"
          aria-checked={settings.enabled}
          className="relative h-7 w-12 shrink-0 rounded-full transition-colors disabled:opacity-50"
          style={{ background: settings.enabled ? "var(--positive)" : "var(--card-border)" }}
        >
          <span
            className="absolute top-1 h-5 w-5 rounded-full bg-white transition-transform"
            style={{ transform: settings.enabled ? "translateX(22px)" : "translateX(4px)" }}
          />
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-xs font-medium text-[var(--foreground-secondary)]">
            Bet amount (simulated $)
          </label>
          <input
            type="number"
            value={betAmountInput}
            onChange={(e) => setBetAmountInput(e.target.value)}
            className="w-full rounded-sm border border-[var(--card-border)] bg-[var(--input-bg)] px-3 py-2 text-sm outline-none focus:border-[var(--accent-forecast)]"
            min={1}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-[var(--foreground-secondary)]">
            Minimum fee-adjusted edge (%)
          </label>
          <input
            type="number"
            value={thresholdInput}
            onChange={(e) => setThresholdInput(e.target.value)}
            className="w-full rounded-sm border border-[var(--card-border)] bg-[var(--input-bg)] px-3 py-2 text-sm outline-none focus:border-[var(--accent-forecast)]"
            min={0}
            max={100}
          />
        </div>
      </div>

      <button
        onClick={saveParams}
        disabled={saving}
        className="rounded-sm bg-[var(--accent-forecast)] px-3 py-1.5 text-sm font-medium text-[#0b0e12] disabled:opacity-50"
      >
        Save parameters
      </button>

      <label className="flex items-center gap-2.5 text-sm">
        <input
          type="checkbox"
          checked={settings.skip_if_position_exists}
          onChange={toggleSkipRule}
          disabled={saving}
          className="h-4 w-4"
        />
        Skip a day if you (or the bot) already have an open position on it
      </label>

      <div className="flex items-center gap-3 border-t border-[var(--card-border)] pt-4">
        <button
          onClick={handleRunNow}
          disabled={running}
          className="rounded-sm border border-[var(--card-border)] bg-[var(--table-head-bg)] px-3 py-1.5 text-sm font-medium hover:bg-white/5 disabled:opacity-50"
        >
          {running ? "Running…" : "Run bot cycle now"}
        </button>
        <span className="text-xs text-[var(--foreground-tertiary)]">
          Manually trigger one evaluation pass — useful for testing without waiting for the schedule.
        </span>
      </div>

      {message && <p className="text-xs text-[var(--foreground-secondary)]">{message}</p>}
    </div>
  );
}
