import type { TradeDiagnosis } from "@/lib/api";
import TradeSourceBadge from "@/components/TradeSourceBadge";

const CATEGORY_STYLES: Record<TradeDiagnosis["category"], string> = {
  bad_luck: "border-[var(--card-border)] bg-[var(--table-head-bg)] text-[var(--foreground-tertiary)]",
  systematic_bias: "border-[#8a5a1f] bg-[#3a2a12] text-[#f0b866]",
  data_bug: "border-[#7a2a2a] bg-[#3a1414] text-[#f28b8b]",
  other: "border-[var(--card-border)] bg-[var(--table-head-bg)] text-[var(--foreground-tertiary)]",
};

const CATEGORY_LABELS: Record<TradeDiagnosis["category"], string> = {
  bad_luck: "Bad luck",
  systematic_bias: "Systematic bias",
  data_bug: "Data bug",
  other: "Other",
};

function CategoryBadge({ category }: { category: TradeDiagnosis["category"] }) {
  return (
    <span
      className={
        "inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.06em] " +
        CATEGORY_STYLES[category]
      }
    >
      {CATEGORY_LABELS[category]}
    </span>
  );
}

function ConfidenceDots({ confidence }: { confidence: TradeDiagnosis["confidence"] }) {
  const level = { low: 1, medium: 2, high: 3 }[confidence];
  return (
    <span className="inline-flex items-center gap-1" title={`${confidence} confidence`}>
      {[1, 2, 3].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 rounded-full"
          style={{
            background: i <= level ? "var(--foreground-secondary)" : "var(--card-border)",
          }}
        />
      ))}
    </span>
  );
}

export default function DiagnosisCard({ diagnosis }: { diagnosis: TradeDiagnosis }) {
  const pnl = diagnosis.pnl ?? 0;
  const won = pnl >= 0;

  return (
    <div className="rounded border border-[var(--card-border)] bg-[var(--card-bg)] p-4">
      <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs font-semibold text-[var(--foreground)]">
            {diagnosis.target_date}
          </span>
          <TradeSourceBadge isBot={diagnosis.is_bot_trade} />
          <span className="font-mono text-[11px] text-[var(--foreground-secondary)]">
            {diagnosis.side.toUpperCase()} @ {diagnosis.price}
          </span>
        </div>
        <div className="flex items-center gap-2.5">
          <span
            className="font-mono text-xs font-semibold"
            style={{ color: won ? "var(--positive)" : "var(--negative)" }}
          >
            {won ? "+" : ""}
            {pnl.toFixed(2)}
          </span>
          <CategoryBadge category={diagnosis.category} />
          <ConfidenceDots confidence={diagnosis.confidence} />
        </div>
      </div>
      <p className="text-[13px] leading-relaxed text-[var(--foreground-secondary)]">
        {diagnosis.summary}
      </p>
    </div>
  );
}
