"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { logout } from "@/app/actions";
import CalibrationProposalCard from "@/components/analytics/CalibrationProposalCard";
import DiagnosisCard from "@/components/analytics/DiagnosisCard";
import {
  DEMO_MODE,
  fetchAnalyticsSummary,
  fetchCalibrationProposals,
  fetchDiagnoses,
  type AnalyticsSummary,
  type CalibrationProposal,
  type TradeDiagnosis,
} from "@/lib/api";

const CATEGORY_ORDER: TradeDiagnosis["category"][] = [
  "systematic_bias",
  "data_bug",
  "bad_luck",
  "other",
];
const CATEGORY_LABELS: Record<TradeDiagnosis["category"], string> = {
  bad_luck: "Bad luck",
  systematic_bias: "Systematic bias",
  data_bug: "Data bug",
  other: "Other",
};

export default function AnalyticsPage() {
  const [diagnoses, setDiagnoses] = useState<TradeDiagnosis[]>([]);
  const [proposals, setProposals] = useState<CalibrationProposal[]>([]);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<TradeDiagnosis["category"] | "all">("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchDiagnoses(), fetchCalibrationProposals(), fetchAnalyticsSummary()])
      .then(([d, p, s]) => {
        setDiagnoses(d);
        setProposals(p);
        setSummary(s);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load analytics"))
      .finally(() => setLoading(false));
  }, []);

  const displayedDiagnoses =
    categoryFilter === "all" ? diagnoses : diagnoses.filter((d) => d.category === categoryFilter);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-[var(--foreground-secondary)]">
        Loading…
      </div>
    );
  }

  return (
    <>
      <div className="sticky top-0 z-40 flex items-center justify-center gap-2.5 border-b border-[var(--paper-banner-border)] bg-[var(--paper-banner-bg)] px-4 py-2.5 text-center sm:px-7">
        <span
          className="inline-block h-[7px] w-[7px] shrink-0 rounded-full bg-[var(--accent-forecast)]"
          style={{ boxShadow: "0 0 8px var(--accent-forecast)" }}
        />
        <span className="font-mono text-[11px] font-semibold tracking-[0.08em] text-[var(--paper-banner-fg)] sm:text-xs sm:tracking-[0.12em]">
          {DEMO_MODE
            ? "DEMO — VIEW ONLY — trading and settings are disabled"
            : "SIMULATED / PAPER TRADING — no real orders are ever placed"}
        </span>
      </div>

      <main className="mx-auto min-w-0 w-full max-w-[1360px] px-4 pb-16 pt-8 sm:px-7">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4 sm:gap-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight sm:text-[26px]">Analytics</h1>
            <p className="mt-1.5 font-mono text-[13px] text-[var(--foreground-secondary)]">
              Nightly Claude post-mortem on every settled trade, and any calibration changes it proposed.
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
                Analytics
              </span>
              {!DEMO_MODE && (
                <Link
                  href="/settings"
                  className="border-l border-[var(--card-border)] px-3 py-[9px] font-sans text-[13px] font-semibold text-[var(--foreground-secondary)] no-underline hover:bg-[var(--table-head-bg)] hover:text-[var(--foreground)] sm:px-[18px]"
                >
                  Settings
                </Link>
              )}
            </div>
            {!DEMO_MODE && (
              <form action={logout}>
                <button
                  type="submit"
                  className="rounded border border-[var(--card-border)] px-3 py-1.5 font-sans text-xs font-medium text-[var(--foreground-secondary)] hover:bg-[var(--table-head-bg)] hover:text-[var(--foreground)]"
                >
                  Log out
                </button>
              </form>
            )}
          </div>
        </header>

        {error && (
          <div className="mb-5 rounded border border-[var(--negative)] bg-[var(--card-bg)] p-4 text-sm text-[var(--negative)]">
            Failed to reach the API: {error}
          </div>
        )}

        <div className="mb-5 rounded border border-[var(--card-border)] bg-[var(--card-bg)] p-6">
          <h2 className="mb-[18px] text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--foreground-tertiary)]">
            Calibration proposals
          </h2>
          <p className="mb-4 text-xs text-[var(--foreground-secondary)]">
            Opened only when several settled trades independently point to the same systematic bias
            AND the proposed fix backtests better out-of-sample. Every PR targets{" "}
            <code className="rounded bg-[var(--table-head-bg)] px-1 py-0.5">develop</code>, not{" "}
            <code className="rounded bg-[var(--table-head-bg)] px-1 py-0.5">main</code>, and is never
            auto-merged — review the backtest numbers before merging.
          </p>
          {proposals.length === 0 ? (
            <p className="text-sm text-[var(--foreground-secondary)]">
              No calibration proposal runs yet.
            </p>
          ) : (
            <div className="space-y-3">
              {proposals.slice(0, 5).map((p) => (
                <CalibrationProposalCard key={p.id} proposal={p} />
              ))}
            </div>
          )}
        </div>

        <div className="rounded border border-[var(--card-border)] bg-[var(--card-bg)] p-6">
          <div className="mb-[18px] flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--foreground-tertiary)]">
              Trade diagnoses
            </h2>
            <div className="flex flex-wrap gap-1.5">
              <button
                onClick={() => setCategoryFilter("all")}
                className="rounded-sm border px-2.5 py-1 font-mono text-[11px] font-semibold"
                style={{
                  borderColor: "var(--card-border)",
                  background: categoryFilter === "all" ? "#1a2028" : "transparent",
                  color:
                    categoryFilter === "all" ? "var(--foreground)" : "var(--foreground-secondary)",
                }}
              >
                All ({diagnoses.length})
              </button>
              {CATEGORY_ORDER.map((cat) => {
                const count = diagnoses.filter((d) => d.category === cat).length;
                if (count === 0) return null;
                return (
                  <button
                    key={cat}
                    onClick={() => setCategoryFilter(cat)}
                    className="rounded-sm border px-2.5 py-1 font-mono text-[11px] font-semibold"
                    style={{
                      borderColor: "var(--card-border)",
                      background: categoryFilter === cat ? "#1a2028" : "transparent",
                      color:
                        categoryFilter === cat ? "var(--foreground)" : "var(--foreground-secondary)",
                    }}
                  >
                    {CATEGORY_LABELS[cat]} ({count})
                  </button>
                );
              })}
            </div>
          </div>

          {summary && (
            <p className="mb-4 text-xs text-[var(--foreground-secondary)]">
              Last 30 days:{" "}
              {Object.entries(summary.by_category_30d)
                .map(([cat, n]) => `${n} ${CATEGORY_LABELS[cat as TradeDiagnosis["category"]] ?? cat}`)
                .join(", ") || "no diagnoses yet"}
              {" · "}
              {summary.total_prs_opened} PR{summary.total_prs_opened === 1 ? "" : "s"} opened all-time.
            </p>
          )}

          {displayedDiagnoses.length === 0 ? (
            <p className="text-sm text-[var(--foreground-secondary)]">
              No diagnoses {categoryFilter === "all" ? "yet" : `in "${CATEGORY_LABELS[categoryFilter]}"`} —
              the analyst runs nightly after settlement-cron.
            </p>
          ) : (
            <div className="space-y-3">
              {displayedDiagnoses.map((d) => (
                <DiagnosisCard key={d.id} diagnosis={d} />
              ))}
            </div>
          )}
        </div>
      </main>
    </>
  );
}
