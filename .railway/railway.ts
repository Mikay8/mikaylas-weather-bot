import { defineRailway, github, postgres, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const Postgres = postgres("Postgres", { region: "sfo" });
  const postgresVolume = volume("postgres-volume", {
    alerts: { usage: { "100": {}, "80": {}, "95": {} } },
    allowOnlineResize: true,
    region: "sfo",
    sizeMB: 5000,
  });

  const repo = { source: github("Mikay8/mikaylas-weather-bot", { branch: "main" }) };
  const sharedEnv = {
    DATABASE_URL: Postgres.env.DATABASE_URL,
    NWS_USER_AGENT_CONTACT: "mikayla.hill8@gmail.com",
    // weatherbot lives under src/, and no pyproject.toml installs it as a
    // package (local dev works around this the same way) — without this,
    // `python3 -m weatherbot...` fails with ModuleNotFoundError on every run.
    PYTHONPATH: "src",
  };

  const forecastCron = service("forecast-cron", {
    ...repo,
    build: { buildCommand: "pip install -r requirements.txt" },
    deploy: {
      startCommand: "python3 -m weatherbot.ingest.nws_forecast",
      cronSchedule: "0 6,11,17,22 * * *", // 4x/day, aligned with NWS forecast update cadence
      restartPolicyType: "NEVER",
    },
    env: sharedEnv,
  });

  const marketCron = service("market-cron", {
    ...repo,
    build: { buildCommand: "pip install -r requirements.txt" },
    deploy: {
      startCommand: "python3 -m weatherbot.ingest.kalshi_market",
      cronSchedule: "0 * * * *", // hourly
      restartPolicyType: "NEVER",
    },
    env: sharedEnv,
  });

  const settlementCron = service("settlement-cron", {
    ...repo,
    build: { buildCommand: "pip install -r requirements.txt" },
    deploy: {
      startCommand: "python3 -m weatherbot.ingest.nws_settlement",
      // NWS's daily CLI report (containing the prior day's final actual high)
      // consistently publishes 06:17-06:33 UTC — checked live issuance times
      // across two weeks of history. Run a few minutes after the latest
      // observed publish time instead of the old noon-UTC guess.
      cronSchedule: "40 6 * * *",
      restartPolicyType: "NEVER",
    },
    env: sharedEnv,
  });

  const botCron = service("bot-cron", {
    ...repo,
    build: { buildCommand: "pip install -r requirements.txt" },
    deploy: {
      startCommand: "python3 -m weatherbot.api.bot",
      // 10 min after market-cron's hourly pull so it always evaluates
      // against a fresh snapshot, never data up to an hour stale. No-ops
      // immediately if the bot is disabled in bot_settings (off by default).
      cronSchedule: "10 * * * *",
      restartPolicyType: "NEVER",
    },
    env: sharedEnv,
  });

  const api = service("api", {
    ...repo,
    build: { buildCommand: "pip install -r requirements.txt" },
    deploy: {
      // Fixed PORT (not Railway's auto-injected one) so it always matches
      // networking.serviceDomains below.
      startCommand: "uvicorn weatherbot.api.main:app --host 0.0.0.0 --port 8000",
      restartPolicyType: "ON_FAILURE",
    },
    networking: { serviceDomains: { api: { port: 8000 } } },
    env: {
      ...sharedEnv,
      // Restricts CORS to just the deployed frontend (see main.py) instead
      // of the local-dev allow_origins=["*"] default.
      WEB_PUBLIC_URL: "https://${{web.RAILWAY_PUBLIC_DOMAIN}}",
    },
  });

  const web = service("web", {
    // Scoped to frontend/ so Railpack detects Node from package.json
    // instead of Python from the repo-root requirements.txt (which left
    // npm missing from the build image entirely).
    source: github("Mikay8/mikaylas-weather-bot", { branch: "main", rootDirectory: "frontend" }),
    build: { buildCommand: "npm ci && npm run build" },
    deploy: {
      startCommand: "npx next start --port 3000",
      restartPolicyType: "ON_FAILURE",
    },
    networking: { serviceDomains: { web: { port: 3000 } } },
    env: {
      // Next.js inlines NEXT_PUBLIC_* at build time, not runtime, so this
      // must resolve before `npm run build` runs. Railway resolves
      // ${{service.OUTPUT}} template refs before the build step.
      NEXT_PUBLIC_API_URL: "https://${{api.RAILWAY_PUBLIC_DOMAIN}}",
    },
  });

  return project("mikaylas-weather-bot", {
    resources: [
      Postgres,
      postgresVolume,
      forecastCron,
      marketCron,
      settlementCron,
      botCron,
      api,
      web,
    ],
  });
});
