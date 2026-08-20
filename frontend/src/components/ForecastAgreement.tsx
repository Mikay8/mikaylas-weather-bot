"use client";

import { useEffect, useState } from "react";
import { fetchForecastAgreement, type ForecastAgreement } from "@/lib/api";

const SOURCE_LABELS: Record<string, string> = {
  OPEN_METEO: "Open-Meteo",
  ECMWF: "ECMWF",
};

export default function ForecastAgreementBanner() {
  const [agreement, setAgreement] = useState<ForecastAgreement | null>(null);

  useEffect(() => {
    const load = () => fetchForecastAgreement().then(setAgreement).catch(() => {});
    load();
    const interval = setInterval(load, 300_000);
    return () => clearInterval(interval);
  }, []);

  if (!agreement || !agreement.disagrees) return null;

  return (
    <div className="mb-5 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-sm border border-[var(--no-border)] bg-[var(--no-bg)] px-3.5 py-2.5 font-mono text-xs text-[var(--no-fg)]">
      <span className="font-medium">
        ⚠ Forecast sources disagree by up to {agreement.spread}°F for {agreement.target_date}
      </span>
      <span>NWS: {agreement.nws_predicted_high}°F</span>
      {Object.entries(agreement.sources).map(([source, data]) => (
        <span key={source}>
          {SOURCE_LABELS[source] ?? source}: {data.predicted_high}°F
        </span>
      ))}
      <span className="text-[var(--foreground-secondary)]">
        The bot skips trades on this date until sources agree — unusually uncertain forecast.
      </span>
    </div>
  );
}
