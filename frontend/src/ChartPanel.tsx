import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
} from "lightweight-charts";
import { fetchChart, type ChartFacts, type ChartResponse } from "./api/client";

// The daily MA set drawn as line series — SMA 10/20/50 and the one exponential,
// the 65 EMA (spec §2 / §5.1). `key` indexes the four MaPoint arrays the chart
// bundle carries; the colours only need to be distinct.
const MA_LINES = [
  { key: "sma10", label: "SMA 10", color: "#2962ff" },
  { key: "sma20", label: "SMA 20", color: "#ff6d00" },
  { key: "sma50", label: "SMA 50", color: "#2e7d32" },
  { key: "ema65", label: "EMA 65", color: "#8e24aa" },
] as const;

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
 * The base/cluster shading, the envelope and the trigger/stop rules — the §3.5
 * breakdown too — are the fuller chart of ticket 41, which this ticket unblocks.
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
      <FactsBlock facts={data.facts} />
    </section>
  );
}

/**
 * The lightweight-charts canvas. Ported from q-scanner-v2's `renderChart.ts`
 * (spec §7.6): candles, the SMA set and a volume histogram, drawn against the
 * FastAPI payload. The 65 EMA is one of the additions that port did not have.
 */
function Chart({ data }: { data: ChartResponse }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (el === null) return;
    const chart = createChart(el, { autoSize: true, height: 360 });

    // Candles — the unadjusted OHLC series (spec §3.5).
    const candles = chart.addSeries(CandlestickSeries, {});
    candles.setData(
      data.candles.map((c) => ({
        time: c.session,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    );

    // The daily MA set as line series (spec §5.1).
    for (const line of MA_LINES) {
      const series = chart.addSeries(LineSeries, {
        color: line.color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      series.setData(data[line.key].map((p) => ({ time: p.session, value: p.value })));
    }

    // Volume on its own overlay scale, pinned to the bottom (spec §5.1). Base
    // bars are not yet distinguished — that is ticket 41.
    const volume = chart.addSeries(HistogramSeries, {
      priceScaleId: "volume",
      priceFormat: { type: "volume" },
    });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    volume.setData(data.candles.map((c) => ({ time: c.session, value: c.volume })));

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [data]);

  return <div className="chart-canvas" data-testid="chart-canvas" ref={ref} />;
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
