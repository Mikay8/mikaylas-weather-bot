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
      cronSchedule: "0 12 * * *", // once/day, after NWS publishes the morning CLI report
      restartPolicyType: "NEVER",
    },
    env: sharedEnv,
  });

  return project("mikaylas-weather-bot", {
    resources: [Postgres, postgresVolume, forecastCron, marketCron, settlementCron],
  });
});
