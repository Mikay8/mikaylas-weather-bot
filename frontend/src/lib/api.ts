const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export type ForecastVsActual = {
  target_date: string;
  predicted_high: number | null;
  actual_high: number | null;
};

export type MarketSnapshot = {
  contract_id: string;
  timestamp: string;
  target_date: string | null;
  bracket_low: number | null;
  bracket_high: number | null;
  strike_type: "greater" | "less" | "between" | null;
  yes_bid: number | null;
  yes_ask: number | null;
  implied_prob: number | null;
  volume: number | null;
  open_interest: number | null;
};

export type Trade = {
  id: number;
  contract_id: string;
  timestamp: string;
  side: "yes" | "no";
  price: number;
  size: number;
  target_date: string | null;
  bracket_low?: number | null;
  bracket_high?: number | null;
  strike_type?: string | null;
  fee?: number | null;
  status?: string | null;
  pnl?: number | null;
};

export type Wallet = {
  balance: number;
  starting_balance: number;
  updated_at: string;
  realized_pnl: number;
  open_trades: Trade[];
  settled_trades: Trade[];
};

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

export function fetchForecastVsActual(limit = 90) {
  return getJSON<ForecastVsActual[]>(`/api/forecast-vs-actual?limit=${limit}`);
}

export function fetchMarkets() {
  return getJSON<MarketSnapshot[]>("/api/markets");
}

export function fetchWallet() {
  return getJSON<Wallet>("/api/wallet");
}

export async function placeBet(contract_id: string, side: "yes" | "no", amount: number) {
  const res = await fetch(`${API_URL}/api/wallet/bet`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contract_id, side, amount }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || "Failed to place bet");
  }
  return res.json();
}

export async function resolveTrades() {
  const res = await fetch(`${API_URL}/api/wallet/resolve`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to resolve trades");
  return res.json();
}
