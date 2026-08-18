"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import BackfillCard from "@/components/settings/BackfillCard";
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
    <section className="rounded-xl border border-[var(--card-border)] bg-[var(--card-bg)] p-5">
      <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        {title}
      </h2>
      <p className="mb-4 text-xs text-neutral-500">{description}</p>
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
      <div className="sticky top-0 z-40 flex items-center justify-center gap-2 bg-[var(--paper-banner-bg)] px-4 py-2 text-center text-sm font-semibold text-[var(--paper-banner-fg)]">
        <span aria-hidden="true">🧪</span>
        PAPER TRADING — simulated money only. No real orders are ever placed.
      </div>
      <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6 lg:px-8">
        <header className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Settings</h1>
            <p className="text-sm text-neutral-500">
              Data pipeline status, source health, and wallet controls.
            </p>
          </div>
          <Link
            href="/"
            className="rounded-md border border-[var(--card-border)] px-3 py-1.5 text-sm text-neutral-500 hover:bg-[var(--table-head-bg)]"
          >
            ← Dashboard
          </Link>
        </header>

        <div className="space-y-6">
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
