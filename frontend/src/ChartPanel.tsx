import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
} from "lightweight-charts";
import {
  fetchChart,
  type ChartFacts,
  type ChartResponse,
  type SetupOverlay,
} from "./api/client";

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

// The setup overlay's colours (spec §5.1 / ticket 41). The cluster band sits on
// top of the base band, so the two translucent fills stack to a darker shade
// where they overlap — the cluster reads as the tight end of the base. The
// envelope is a plain line the candles pierce; the trigger/stop are the two rules.
const BASE_FILL = "rgba(41, 98, 255, 0.07)";
const CLUSTER_FILL = "rgba(41, 98, 255, 0.13)";
const ENVELOPE_COLOR = "#455a64";
const VOLUME_BASE_COLOR = "rgba(41, 98, 255, 0.55)";
const VOLUME_COLOR = "rgba(120, 123, 134, 0.5)";
const TRIGGER_COLOR = "#2e7d32";
const STOP_COLOR = "#c62828";

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
 * The lightweight-charts canvas. Ported from q-scanner-v2's `renderChart.ts`
 * (spec §7.6): candles, the SMA set and a volume histogram, drawn against the
 * FastAPI payload. The 65 EMA is one of the additions that port did not have.
 *
 * When a setup is present the chart carries the overlay (ticket 41): the base and
 * cluster shaded as full-height band series *behind* the candles, the envelope as
 * a line the candles pierce, the trigger and stop as horizontal rules, and the
 * base's volume bars tinted so the dry-up is visible.
 */
function Chart({ data }: { data: ChartResponse }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (el === null) return;
    const chart = createChart(el, { autoSize: true, height: 360 });
    const setup = data.setup;

    // The base/cluster shading is drawn *first* so it sits behind the candles. Each
    // is a histogram of full-height columns (value 1, base 0) on its own hidden
    // price scale, one column per session in the region — the cluster's darker fill
    // stacks on the base's inside the tight window (spec §5.1: cluster inside base).
    if (setup) {
      band(chart, "base-band", BASE_FILL, data.candles, setup.base_start);
      band(chart, "cluster-band", CLUSTER_FILL, data.candles, setup.cluster_start);
    }

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

    // Trigger and stop as horizontal rules read against the candles (spec §7). Two
    // real order levels — the cluster high and the cluster low.
    if (setup) {
      candles.createPriceLine({ price: setup.trigger, color: TRIGGER_COLOR, lineWidth: 1, title: "trigger" });
      candles.createPriceLine({ price: setup.stop, color: STOP_COLOR, lineWidth: 1, title: "stop" });
    }

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

    // The envelope as a line series (spec §3.2): candles pierce it in both
    // directions and that is the correct picture — it must not be "fixed" to a
    // clean trendline that sits above every high.
    if (setup) {
      const envelope = chart.addSeries(LineSeries, {
        color: ENVELOPE_COLOR,
        lineWidth: 1,
        lineStyle: 2, // dashed — a fit, not a price
        priceLineVisible: false,
        lastValueVisible: false,
      });
      envelope.setData(setup.envelope.map((p) => ({ time: p.session, value: p.value })));
    }

    // Volume on its own overlay scale, pinned to the bottom (spec §5.1). The base's
    // bars are tinted so the dry-up dimension is visible; expansion is never drawn —
    // it exists only at the break, so a name still in its base has nothing to show.
    const volume = chart.addSeries(HistogramSeries, {
      priceScaleId: "volume",
      priceFormat: { type: "volume" },
    });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    volume.setData(
      data.candles.map((c) => ({
        time: c.session,
        value: c.volume,
        color: setup && c.session >= setup.base_start ? VOLUME_BASE_COLOR : VOLUME_COLOR,
      })),
    );

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [data]);

  return <div className="chart-canvas" data-testid="chart-canvas" ref={ref} />;
}

// A full-height shaded band over every candle on or after `from`, on its own
// hidden price scale (value 1 over base 0 → the columns fill the pane). Used for
// the base and the cluster; the cluster's fill stacks on the base's where they
// overlap (spec §5.1).
function band(
  chart: ReturnType<typeof createChart>,
  scaleId: string,
  color: string,
  candles: ChartResponse["candles"],
  from: string,
) {
  const series = chart.addSeries(HistogramSeries, {
    priceScaleId: scaleId,
    color,
    priceLineVisible: false,
    lastValueVisible: false,
  });
  chart.priceScale(scaleId).applyOptions({ scaleMargins: { top: 0, bottom: 0 } });
  series.setData(
    candles.filter((c) => c.session >= from).map((c) => ({ time: c.session, value: 1 })),
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
