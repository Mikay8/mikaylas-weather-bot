"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { logout } from "@/app/actions";
import ApiLogsCard from "@/components/settings/ApiLogsCard";
import BackfillCard from "@/components/settings/BackfillCard";
import BotControlCard from "@/components/settings/BotControlCard";
import CronStatusCard from "@/components/settings/CronStatusCard";
import DataCoverageCard from "@/components/settings/DataCoverageCard";
import SourceHealthCard from "@/components/settings/SourceHealthCard";
import WalletResetCard from "@/components/settings/WalletResetCard";
import {
  fetchCronStatus,
  fetchDataCoverage,
  fetchSourceHealth,
  type CronStatus,
  type DataCoverage,
  type SourceHealth,
} from "@/lib/api";

function SettingsSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="min-w-0 rounded border border-[var(--card-border)] bg-[var(--card-bg)] p-4 sm:p-6">
      <h2 className="mb-1 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--foreground-tertiary)]">
        {title}
      </h2>
      <p className="mb-4 text-xs text-[var(--foreground-secondary)]">{description}</p>
      {children}
    </section>
  );
}

export default function SettingsPage() {
  const [cronStatus, setCronStatus] = useState<CronStatus | null>(null);
  const [health, setHealth] = useState<SourceHealth | null>(null);
  const [coverage, setCoverage] = useState<DataCoverage | null>(null);

  const loadCron = useCallback(() => {
    fetchCronStatus().then(setCronStatus).catch(() => {});
  }, []);

  const loadCoverage = useCallback(() => {
    fetchDataCoverage().then(setCoverage).catch(() => {});
  }, []);

  useEffect(() => {
    loadCron();
    loadCoverage();
    fetchSourceHealth().then(setHealth).catch(() => {});
  }, [loadCron, loadCoverage]);

  return (
    <>
      <div className="sticky top-0 z-40 flex items-center justify-center gap-2.5 border-b border-[var(--paper-banner-border)] bg-[var(--paper-banner-bg)] px-4 py-2.5 text-center sm:px-7">
        <span
          className="inline-block h-[7px] w-[7px] shrink-0 rounded-full bg-[var(--accent-forecast)]"
          style={{ boxShadow: "0 0 8px var(--accent-forecast)" }}
        />
        <span className="font-mono text-[11px] font-semibold tracking-[0.08em] text-[var(--paper-banner-fg)] sm:text-xs sm:tracking-[0.12em]">
          SIMULATED / PAPER TRADING — no real orders are ever placed
        </span>
      </div>
      <main className="mx-auto min-w-0 w-full max-w-[1360px] px-4 pb-16 pt-8 sm:px-7">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4 sm:gap-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight sm:text-[26px]">Settings</h1>
            <p className="mt-1.5 font-mono text-[13px] text-[var(--foreground-secondary)]">
              Data pipeline status, source health, and wallet controls.
            </p>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <div className="flex overflow-hidden rounded border border-[var(--card-border)]">
              <Link
                href="/"
                className="px-3 py-[9px] font-sans text-[13px] font-semibold text-[var(--foreground-secondary)] no-underline hover:bg-[var(--table-head-bg)] hover:text-[var(--foreground)] sm:px-[18px]"
              >
                Dashboard
              </Link>
              <span className="border-l border-[var(--card-border)] bg-[#1a2028] px-3 py-[9px] font-sans text-[13px] font-semibold sm:px-[18px]">
                Settings
              </span>
            </div>
            <form action={logout}>
              <button
                type="submit"
                className="rounded border border-[var(--card-border)] px-3 py-1.5 font-sans text-xs font-medium text-[var(--foreground-secondary)] hover:bg-[var(--table-head-bg)] hover:text-[var(--foreground)]"
              >
                Log out
              </button>
            </form>
          </div>
        </header>

        <div className="space-y-5">
          <SettingsSection
            title="Auto-trading bot"
            description="When enabled, automatically places a paper trade whenever a market's fee-adjusted edge clears your threshold — no manual review. Off by default."
          >
            <BotControlCard />
          </SettingsSection>

          <SettingsSection
            title="Cron jobs"
            description="Scheduled pulls running on Railway. 'Run now' triggers an immediate pull outside the schedule."
          >
            <CronStatusCard cronStatus={cronStatus} onRefresh={loadCron} />
          </SettingsSection>

          <SettingsSection
            title="Data source health"
            description="Live reachability check against NWS and Kalshi's public APIs."
          >
            <SourceHealthCard health={health} />
          </SettingsSection>

          <SettingsSection
            title="API logs"
            description="Every outbound request to NWS, IEM Mesonet, Open-Meteo/ECMWF, and Kalshi in the last 24 hours, with request/response detail. Click a row to expand."
          >
            <ApiLogsCard />
          </SettingsSection>

          <SettingsSection
            title="Data coverage"
            description="What's currently stored, by table."
          >
            <DataCoverageCard coverage={coverage} />
          </SettingsSection>

          <SettingsSection
            title="Historical backfill"
            description="Fill in past forecasts and settlements for backtesting."
          >
            <BackfillCard onDone={loadCoverage} />
          </SettingsSection>

          <SettingsSection
            title="Paper wallet"
            description="Reset your simulated balance and trade history."
          >
            <WalletResetCard />
          </SettingsSection>
        </div>
      </main>
    </>
  );
}
