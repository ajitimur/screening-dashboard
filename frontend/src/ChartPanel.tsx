import { useEffect, useState } from "react";
import { Chart } from "./Chart";
import {
  fetchChart,
  type ChartFacts,
  type ChartResponse,
  type SetupOverlay,
} from "./api/client";

// The five lookbacks in order, for the decile-ranks fact (spec §4.3).
const LOOKBACKS = ["1w", "1m", "3m", "6m", "12m"] as const;

/**
 * The chart panel (spec §5.1 / ticket 40): click a candidate row, see its chart.
 * One interaction — the panel swaps and nothing else navigates (spec §5.3).
 *
 * Renders the symbol's evidence bundle in a single call: **candles** (unadjusted,
 * the price the trigger and stop live in), the **daily MA set** (SMA 10/20/50 and
 * the 65 EMA) as line series, a **volume** histogram, and the **facts block** —
 * the numbers the row deliberately left off, read here where the trade is decided.
 *
 * When the name has a base tonight the chart stops being a price chart and becomes
 * *evidence for the score* (ticket 41): the **base is shaded with the cluster
 * shaded inside it**, the **envelope** is drawn as a line series the candles pierce
 * (spec §3.2 — not "corrected" to a clean trendline), the **trigger and stop**
 * render as horizontal rules, and the **base's volume bars are distinguished** so
 * the dry-up dimension is visible. The eight-row §4.7 **breakdown** sits adjacent,
 * reconstructing the star score arithmetically.
 */
export default function ChartPanel({
  market,
  symbol,
}: {
  market: string;
  symbol: string | null;
}) {
  const [data, setData] = useState<ChartResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (symbol === null) {
      setData(null);
      setError(null);
      return;
    }
    let live = true;
    setData(null);
    setError(null);
    fetchChart(market, symbol)
      .then((d) => live && setData(d))
      .catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [market, symbol]);

  if (symbol === null)
    return (
      <section aria-label="chart panel" className="chart-panel empty">
        <p className="chart-empty">Select a candidate to see its chart.</p>
      </section>
    );
  if (error)
    return (
      <section aria-label="chart panel" className="chart-panel">
        <p role="alert" className="chart-error">
          Could not load {symbol}: {error}
        </p>
      </section>
    );
  if (!data)
    return (
      <section aria-label="chart panel" className="chart-panel">
        <p>Loading {symbol}…</p>
      </section>
    );

  return (
    <section aria-label={`${symbol} chart`} className="chart-panel">
      <h2>{symbol}</h2>
      <Chart data={data} />
      {data.setup && <Breakdown setup={data.setup} />}
      <FactsBlock facts={data.facts} />
    </section>
  );
}

/**
 * The eight-row §4.7 score breakdown, adjacent to the chart (spec §5.1 / ticket
 * 41): each dimension, its weight, whether it scored, and the `n/10 → stars`
 * arithmetic — because the score is the sort key and a sort key you cannot audit
 * at a glance is one you will not trust.
 */
function Breakdown({ setup }: { setup: SetupOverlay }) {
  const points = setup.breakdown.reduce((sum, d) => sum + (d.hit ? d.weight : 0), 0);
  return (
    <table aria-label="score breakdown" className="breakdown">
      <thead>
        <tr>
          <th scope="col">Dimension</th>
          <th scope="col">Weight</th>
          <th scope="col">Scored</th>
        </tr>
      </thead>
      <tbody>
        {setup.breakdown.map((d) => (
          <tr key={d.dimension} className={d.hit ? "hit" : "miss"}>
            <td>{d.dimension}</td>
            <td>×{d.weight}</td>
            <td>{d.hit ? "✓" : "—"}</td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <td colSpan={2}>{points} / 10 points</td>
          <td>→ {setup.score}★</td>
        </tr>
      </tfoot>
    </table>
  );
}

/**
 * The facts block (spec §5.1): base length, trigger, distance, stop in ADR, ADR,
 * dollar volume, the five decile ranks and sector. Absent when the name has no
 * base tonight — the chart still draws, but there is nothing to describe.
 */
function FactsBlock({ facts }: { facts: ChartFacts | null }) {
  if (facts === null)
    return (
      <p className="facts-empty">No base tonight — nothing to describe.</p>
    );
  return (
    <dl aria-label="facts" className="facts">
      <div>
        <dt>Base length</dt>
        <dd>{facts.base_len} bars</dd>
      </div>
      <div>
        <dt>Trigger</dt>
        <dd>{facts.trigger.toFixed(2)}</dd>
      </div>
      <div>
        <dt>Distance to trigger</dt>
        <dd>{facts.dist_adr.toFixed(2)}×</dd>
      </div>
      <div>
        <dt>Stop width ÷ ADR</dt>
        <dd>{facts.stopw_adr.toFixed(2)}×</dd>
      </div>
      <div>
        <dt>ADR</dt>
        <dd>{(facts.adr * 100).toFixed(2)}%</dd>
      </div>
      <div>
        <dt>Dollar volume</dt>
        <dd>{facts.dollar_volume === null ? "—" : formatDollarVolume(facts.dollar_volume)}</dd>
      </div>
      <div>
        <dt>Decile ranks</dt>
        <dd>{formatRanks(facts.decile_ranks)}</dd>
      </div>
      <div>
        <dt>Sector</dt>
        <dd>{facts.sector ?? "—"}</dd>
      </div>
    </dl>
  );
}

// Compact dollar volume, e.g. "$1.2M" — the §4.1 median-20d liquidity number.
function formatDollarVolume(value: number): string {
  return `$${new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value)}`;
}

// The five decile ranks as percentiles, in lookback order, e.g. "1m 95 · 3m 90".
// A lookback the name is not ranked in (a recent listing) is simply omitted.
function formatRanks(ranks: Record<string, number>): string {
  const parts = LOOKBACKS.filter((lb) => lb in ranks).map(
    (lb) => `${lb} ${Math.round(ranks[lb] * 100)}`,
  );
  return parts.length === 0 ? "—" : parts.join(" · ");
}
