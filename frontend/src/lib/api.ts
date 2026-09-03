const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

// Set on the read-only demo deployment (see frontend/README.md) — build-time
// flag that hides trade/settings UI. The API also enforces this itself
// (see block_demo_mutations in weatherbot/api/main.py) so this flag is a UX
// nicety, not the actual security boundary.
export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

export type ForecastVsActual = {
  target_date: string;
  predicted_high: number | null;
  open_meteo_predicted_high: number | null;
  actual_high: number | null;
};

export type ForecastPull = {
  id: number;
  station: string;
  forecast_time: string;
  target_date: string;
  predicted_high: number | null;
  model_source: string;
};

export type MarketSnapshot = {
  contract_id: string;
  timestamp: string;
  target_date: string | null;
  bracket_low: number | null;
  bracket_high: number | null;
  strike_type: "greater" | "less" | "between" | null;
  kalshi_label: string | null;
  close_time: string | null;
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
  strike_type?: "greater" | "less" | "between" | null;
  fee?: number | null;
  status?: string | null;
  pnl?: number | null;
  is_bot_trade?: boolean;
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

export function fetchForecasts(limit = 90) {
  return getJSON<ForecastPull[]>(`/api/forecasts?limit=${limit}`);
}

export function fetchMarkets() {
  return getJSON<MarketSnapshot[]>("/api/markets");
}

export function fetchWallet() {
  return getJSON<Wallet>("/api/wallet");
}

export type Recommendation = {
  contract_id: string;
  target_date: string;
  bracket_low: number | null;
  bracket_high: number | null;
  strike_type: "greater" | "less" | "between";
  kalshi_label: string | null;
  predicted_high: number;
  forecast_time: string;
  forecast_stale: boolean;
  model_prob: number;
  market_prob: number;
  side: "yes" | "no";
  edge: number;
  fee_adjusted_edge: number | null;
  recommend: boolean;
  volume: number | null;
  open_interest: number | null;
};

export function fetchRecommendations() {
  return getJSON<Recommendation[]>("/api/recommendations");
}

export type DataStatus = {
  last_forecast_pull: string | null;
  last_market_pull: string | null;
  last_settlement_date: string | null;
  server_time: string;
};

export function fetchStatus() {
  return getJSON<DataStatus>("/api/status");
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

export async function resetWallet(startingBalance = 1000) {
  const res = await fetch(`${API_URL}/api/wallet/reset?starting_balance=${startingBalance}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to reset wallet");
  return res.json();
}

export type TableCoverage = {
  earliest: string | null;
  latest: string | null;
  row_count: number;
  size_bytes: number;
  est_cost_usd_month: number;
};

export type DataCoverage = {
  forecasts: TableCoverage;
  market_snapshots: TableCoverage;
  settlements: TableCoverage;
  trades: TableCoverage;
  api_call_logs: TableCoverage;
};

export function fetchDataCoverage() {
  return getJSON<DataCoverage>("/api/settings/data-coverage");
}

export type SourceHealthEntry = {
  reachable: boolean;
  status_code?: number;
  latency_ms?: number;
  error?: string;
};

export type SourceHealth = {
  nws: SourceHealthEntry;
  kalshi: SourceHealthEntry;
};

export function fetchSourceHealth() {
  return getJSON<SourceHealth>("/api/settings/source-health");
}

export type ApiLogEntry = {
  id: number;
  source: "nws" | "iem" | "ecmwf" | "open_meteo" | "kalshi";
  method: string;
  url: string;
  request_body: string | null;
  status_code: number | null;
  response_body: string | null;
  error: string | null;
  latency_ms: number | null;
  created_at: string;
};

export function fetchApiLogs(source?: string) {
  const query = source ? `?source=${encodeURIComponent(source)}` : "";
  return getJSON<ApiLogEntry[]>(`/api/settings/api-logs${query}`);
}

export type CronEntry = {
  name: string;
  schedule: string;
  schedule_label: string;
  last_run_status?: string;
  last_run_at?: string | null;
  error?: string;
};

export type CronStatus = Record<"forecast" | "market" | "settlement", CronEntry>;

export function fetchCronStatus() {
  return getJSON<CronStatus>("/api/settings/cron-status");
}

export async function triggerCronJob(key: string) {
  const res = await fetch(`${API_URL}/api/settings/cron-trigger/${key}`, { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || "Failed to trigger cron job");
  }
  return res.json();
}

export async function backfillSettlements(limit = 14) {
  const res = await fetch(`${API_URL}/api/settings/backfill-settlements?limit=${limit}`, {
    method: "POST",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || "Backfill failed");
  }
  return res.json();
}

export type BotSettings = {
  enabled: boolean;
  bet_amount: number;
  edge_threshold: number;
  skip_if_position_exists: boolean;
  updated_at: string;
};

export function fetchBotSettings() {
  return getJSON<BotSettings>("/api/bot/settings");
}

export async function updateBotSettings(patch: Partial<BotSettings>) {
  const res = await fetch(`${API_URL}/api/bot/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || "Failed to update bot settings");
  }
  return res.json() as Promise<BotSettings>;
}

export async function runBotCycle() {
  const res = await fetch(`${API_URL}/api/bot/run`, { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || "Failed to run bot cycle");
  }
  return res.json();
}

export async function backfillHistorical(days = 365) {
  const res = await fetch(`${API_URL}/api/settings/backfill-historical?days=${days}`, {
    method: "POST",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || "Historical backfill failed");
  }
  return res.json();
}

export async function backfillKalshiMarkets() {
  const res = await fetch(`${API_URL}/api/settings/backfill-kalshi-markets`, { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || "Kalshi market backfill failed");
  }
  return res.json();
}

export type HourlyPoint = {
  timestamp: string;
  temperature: number;
  condition: string | null;
};

export type HourlyWeather = {
  current: HourlyPoint | null;
  past: HourlyPoint[];
  future: HourlyPoint[];
};

// NWS's live observation occasionally comes back with a null temperature
// (sensor QC failure, often during heavy rain/fog) even though the station
// itself is fine and past data is good - fall back to the latest past
// reading rather than losing "now" entirely. Shared so the Today header
// and the hourly strip never disagree about what "current" means.
export function effectiveCurrent(data: HourlyWeather | null | undefined): HourlyPoint | null {
  if (!data) return null;
  return data.current ?? data.past[data.past.length - 1] ?? null;
}

export function fetchHourlyWeather() {
  return getJSON<HourlyWeather>("/api/weather/hourly");
}

export type ForecastAgreement = {
  target_date: string;
  nws_predicted_high: number;
  sources: Record<string, { predicted_high: number; spread: number }>;
  spread: number;
  disagrees: boolean;
};

// 404s until NWS and at least one secondary source have reported for
// tomorrow (e.g. right after a fresh deploy, before crons have run once) -
// not an error.
export async function fetchForecastAgreement(): Promise<ForecastAgreement | null> {
  const res = await fetch(`${API_URL}/api/forecast-agreement`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to fetch forecast agreement: ${res.status}`);
  return res.json();
}
