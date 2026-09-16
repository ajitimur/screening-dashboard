// PROTOTYPE — throwaway. The five-lookback share sparkline with the 10%
// baseline tick. Cells rest on fewer names render lighter (confidence as
// intensity, not a dagger).

import { BASELINE, LOOKBACKS, confidence, pct } from "./state";

const MAX = 0.6; // a 60% share fills the bar

export function ShareBars({
  shares,
  counts,
  color,
  height = 28,
}: {
  shares: Record<string, number>;
  counts: Record<string, number>;
  color: string;
  height?: number;
}) {
  return (
    <span className="proto-bars" style={{ height }} aria-hidden="true">
      {LOOKBACKS.map(({ key, label }) => {
        const v = Math.min(shares[key] ?? 0, MAX);
        return (
          <span
            key={key}
            className="proto-bar"
            title={`${label}: ${pct(shares[key] ?? 0)} (${counts[key] ?? 0} names)`}
          >
            <span
              className="proto-bar-fill"
              style={{
                height: `${(v / MAX) * 100}%`,
                background: color,
                opacity: confidence(counts[key] ?? 0),
              }}
            />
            <span className="proto-bar-label">{label}</span>
          </span>
        );
      })}
      <span
        className="proto-baseline"
        style={{ bottom: `calc(${(BASELINE / MAX) * 100}% + 0.8rem)` }}
      />
    </span>
  );
}
