import { defineRailway, github, postgres, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  // Everything was actually running in sfo (US West) despite no explicit
  // intent to be there. Moved to us-east4 — closer to NWS/Kalshi (both
  // US-East-hosted) and to the user.
  const REGION = "us-east4";

  const Postgres = postgres("Postgres", { region: REGION });
  const postgresVolume = volume("postgres-volume", {
    alerts: { usage: { "100": {}, "80": {}, "95": {} } },
    allowOnlineResize: true,
    // Still "us-east4-eqdc4a" live, not the bare "us-east4" region above —
    // reconciling that requires an explicit volume migration (potential
    // downtime), so it's deliberately left as its own follow-up rather than
    // folded into this apply. See the region comment above for the intent.
    region: "us-east4-eqdc4a",
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

  // Actual usage checked via Railway's 24h metrics before picking these:
  // every service was sitting at <1.5% CPU and well under 500MB. These
  // caps still give headroom above observed peaks — this is a single-user
  // paper-trading dashboard, not a service that needs to scale.
  const CRON_LIMITS = { containers: { cpu: 0.5, memoryBytes: 512 * 1024 * 1024 } };
  const API_LIMITS = {
    // Highest observed of the bunch (~460MB, ~1.2% CPU) — it's the one
    // holding pandas/numpy/scipy/statsmodels/scikit-learn resident.
    containers: { cpu: 1, memoryBytes: 1024 * 1024 * 1024 },
  };
  const WEB_LIMITS = { containers: { cpu: 0.5, memoryBytes: 512 * 1024 * 1024 } };

  const forecastCron = service("forecast-cron", {
    ...repo,
    build: { buildCommand: "pip install -r requirements.txt" },
    deploy: {
      startCommand: "python3 -m weatherbot.ingest.nws_forecast",
      // 7x/day: the original 4 aligned with NWS forecast update cadence,
      // plus 10:00 UTC (6 AM Eastern, fixed year-round - no DST handling)
      // added so bot-cron trades on a forecast pulled minutes earlier
      // instead of one up to 4h stale from the 6:00 UTC run, plus 8:00 and
      // 9:00 UTC (4/5 AM Eastern) added alongside bot-cron's matching
      // earlier runs - see the bot-cron comment for why those exist. Without
      // these, an 8:10/9:10 UTC bot-cron run would just re-evaluate the
      // stale 6:00 UTC forecast a second and third time instead of getting
      // genuinely fresh data to retry against.
      cronSchedule: "0 6,8,9,10,11,17,22 * * *",
      restartPolicyType: "NEVER",
      region: REGION,
      limitOverride: CRON_LIMITS,
    },
    env: sharedEnv,
  });

  const openMeteoCron = service("open-meteo-cron", {
    ...repo,
    build: { buildCommand: "pip install -r requirements.txt" },
    deploy: {
      startCommand: "python3 -m weatherbot.ingest.open_meteo_forecast",
      // Same cadence as forecast-cron so a same-cycle NWS/Open-Meteo
      // comparison is never comparing a fresh pull against a stale one.
      cronSchedule: "0 6,8,9,10,11,17,22 * * *",
      restartPolicyType: "NEVER",
      region: REGION,
      limitOverride: CRON_LIMITS,
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
      region: REGION,
      limitOverride: CRON_LIMITS,
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
      region: REGION,
      limitOverride: CRON_LIMITS,
    },
    env: sharedEnv,
  });

  const botCron = service("bot-cron", {
    ...repo,
    build: { buildCommand: "pip install -r requirements.txt" },
    deploy: {
      startCommand: "python3 -m weatherbot.api.bot",
      // 8:10, 9:10, 10:10 UTC (4, 5, 6 AM Eastern, fixed year-round - no DST
      // handling). The 10:10 run is the original - see the historical note
      // below. The two earlier runs are a deliberate second (and third)
      // chance at the same trading day: if forecast_agreement.py's
      // disagreement gate blocks the 10:10 run on a bad/outlier pull from
      // one source (happened 2026-09-03 - NWS returned 74F against
      // Open-Meteo/ECMWF both ~84F, self-corrected within the hour),
      // skip_if_position_exists means an earlier successful run just makes
      // the later ones no-ops rather than double-betting - see bot.py.
      // NOTE: as of 2026-09-03 this trades on less accurate data than the
      // 10:10 run - a by-hour MAE/bias breakdown of NWS/Open-Meteo/ECMWF/
      // ENSEMBLE history found the 06:00 UTC (2 AM Eastern) pull is
      // consistently the WORST-performing slot of the day, not the best,
      // and 17:00/22:00 UTC (1 PM/6 PM Eastern) the best - there's no
      // pre-dawn forecast pull in this pipeline more accurate than the
      // ones already in forecast-cron's 6,10,11,17,22 UTC schedule. Kept
      // anyway as extra chances to dodge a repeat of the outlier-data
      // failure above, not because early-morning data is better.
      //
      // Original 10:10 UTC run: 10 min buffer after the 10:00 UTC
      // forecast/ensemble/market pulls above - determined to be the most
      // accurate time to predict that day's high. No-ops immediately if
      // the bot is disabled in bot_settings (off by default).
      cronSchedule: "10 8,9,10 * * *",
      restartPolicyType: "NEVER",
      region: REGION,
      limitOverride: CRON_LIMITS,
    },
    env: {
      ...sharedEnv,
      // Trade notification emails (see notify.py) — scoped to bot-cron only
      // since it's the only service that places trades. RESEND_API_KEY is a
      // secret; NOTIFY_EMAIL_TO isn't but travels with it since both are
      // only meaningful together.
      RESEND_API_KEY: preserve(),
      NOTIFY_EMAIL_TO: preserve(),
    },
  });

  const analystCron = service("analyst-cron", {
    ...repo,
    build: { buildCommand: "pip install -r requirements.txt" },
    deploy: {
      // Runs after settlement-cron (06:40 UTC) resolves the prior day's
      // paper trades against real settlements, so there's something new to
      // diagnose. trade_analyst.py logs a per-trade diagnosis note;
      // calibration_proposer.py only opens a PR (against develop, never
      // auto-merged) once a repeated systematic_bias pattern clears
      // MIN_SYSTEMATIC_BIAS_HITS AND the proposed fix backtests better -
      // most nights this is a no-op. See weatherbot/analysis/.
      startCommand:
        "python3 -m weatherbot.analysis.trade_analyst && " +
        "python3 -m weatherbot.analysis.calibration_proposer",
      cronSchedule: "0 7 * * *",
      restartPolicyType: "NEVER",
      region: REGION,
      limitOverride: CRON_LIMITS,
    },
    env: {
      ...sharedEnv,
      // Scoped to analyst-cron only - the one service that calls Claude or
      // pushes branches/opens PRs. Same preserve() pattern as bot-cron's
      // RESEND_API_KEY. GITHUB_API_KEY should be a fine-grained PAT scoped
      // to just this repo (Contents + Pull requests: read/write) - not a
      // classic token with full account-wide repo scope.
      ANTHROPIC_API_KEY: preserve(),
      GITHUB_API_KEY: preserve(),
    },
  });

  const api = service("api", {
    ...repo,
    build: { buildCommand: "pip install -r requirements.txt" },
    deploy: {
      // Fixed PORT (not Railway's auto-injected one) so it always matches
      // networking.serviceDomains below.
      startCommand: "uvicorn weatherbot.api.main:app --host 0.0.0.0 --port 8000",
      restartPolicyType: "ON_FAILURE",
      region: REGION,
      limitOverride: API_LIMITS,
    },
    networking: { serviceDomains: { api: { port: 8000 } } },
    env: {
      ...sharedEnv,
      // Restricts CORS to just the deployed frontends + mikayladhill.com
      // (see main.py) instead of the local-dev allow_origins=["*"] default.
      // main.py splits this on commas.
      WEB_PUBLIC_URL: "https://${{web.RAILWAY_PUBLIC_DOMAIN}},https://www.mikayladhill.com",
      // Origin the block_demo_mutations middleware in main.py rejects
      // trade/settings POSTs from — see web-demo below. Kept separate from
      // WEB_PUBLIC_URL (which is CORS allow-list, additive) so this stays a
      // single unambiguous value to compare request Origin against.
      DEMO_PUBLIC_URL: "https://${{web-demo.RAILWAY_PUBLIC_DOMAIN}}",
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
      region: REGION,
      limitOverride: WEB_LIMITS,
    },
    networking: { serviceDomains: { web: { port: 3000 } } },
    env: {
      // Next.js inlines NEXT_PUBLIC_* at build time, not runtime, so this
      // must resolve before `npm run build` runs. Railway resolves
      // ${{service.OUTPUT}} template refs before the build step.
      NEXT_PUBLIC_API_URL: "https://${{api.RAILWAY_PUBLIC_DOMAIN}}",
      // Password + session gate (see proxy.ts) — this is the real
      // dashboard, not the public demo, so it stays behind a login.
      SITE_PASSWORD: preserve(),
      SESSION_SECRET: preserve(),
    },
  });

  // Read-only public demo of the same dashboard: same backend/data, but the
  // UI hides every trade/settings control (NEXT_PUBLIC_DEMO_MODE) and the
  // API backs that up by rejecting mutating requests whose Origin matches
  // this service's domain (see block_demo_mutations in main.py). No
  // password — this one's meant to be shared freely.
  const webDemo = service("web-demo", {
    source: github("Mikay8/mikaylas-weather-bot", { branch: "main", rootDirectory: "frontend" }),
    build: { buildCommand: "npm ci && npm run build" },
    deploy: {
      startCommand: "npx next start --port 3000",
      restartPolicyType: "ON_FAILURE",
      region: REGION,
      limitOverride: WEB_LIMITS,
    },
    networking: { serviceDomains: { web: { port: 3000 } } },
    env: {
      NEXT_PUBLIC_API_URL: "https://${{api.RAILWAY_PUBLIC_DOMAIN}}",
      NEXT_PUBLIC_DEMO_MODE: "true",
      // No SITE_PASSWORD/SESSION_SECRET — proxy.ts skips the login gate
      // entirely when NEXT_PUBLIC_DEMO_MODE is set.
    },
  });

  return project("mikaylas-weather-bot", {
    resources: [
      Postgres,
      postgresVolume,
      forecastCron,
      openMeteoCron,
      marketCron,
      settlementCron,
      botCron,
      analystCron,
      api,
      web,
      webDemo,
    ],
  });
});
