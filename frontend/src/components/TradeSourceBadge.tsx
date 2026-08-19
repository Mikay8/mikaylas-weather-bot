export default function TradeSourceBadge({
  isBot,
  variant = "light",
}: {
  isBot?: boolean;
  variant?: "light" | "dark";
}) {
  const youClasses =
    variant === "dark"
      ? "border-white/25 bg-white/10 text-white/70"
      : "border-[var(--card-border)] bg-[var(--table-head-bg)] text-[var(--foreground-tertiary)]";

  return (
    <span
      className={
        "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.06em] " +
        (isBot ? "border-[#6b5fd8] bg-[#241f45] text-[#b3a8f5]" : youClasses)
      }
    >
      {isBot ? (
        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" aria-hidden>
          <rect x="5" y="9" width="14" height="10" rx="2" stroke="currentColor" strokeWidth="2" />
          <path d="M12 9V5M9 5h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          <circle cx="9.5" cy="14" r="1.2" fill="currentColor" />
          <circle cx="14.5" cy="14" r="1.2" fill="currentColor" />
        </svg>
      ) : null}
      {isBot ? "Bot" : "You"}
    </span>
  );
}
