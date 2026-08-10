import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
} from "lightweight-charts";
import type { ChartResponse } from "./api/client";

// ── The charting seam (spec §6) ──────────────────────────────────────────────
//
// The repo's ONE integration of `lightweight-charts`, ported from v1's chart
// panel rather than rewritten — the exact seam the tests assert at. Every
// surface that draws a chart (the sheet, the mini charts, v1's dying panel)
// renders through this one component, so the library is integrated once and the
// series/overlay contract is defined once. Assert at this seam only: the data
// handed to each series and the price lines requested — never pixels (spec §6).

// The daily MA set drawn as line series — SMA 10/20/50 and the one exponential,
// the 65 EMA (spec §2 / §5.1). `key` indexes the four MaPoint arrays the chart
// bundle carries; the colours only need to be distinct.
export const MA_LINES = [
  { key: "sma10", label: "SMA 10", color: "#2962ff" },
  { key: "sma20", label: "SMA 20", color: "#ff6d00" },
  { key: "sma50", label: "SMA 50", color: "#2e7d32" },
  { key: "ema65", label: "EMA 65", color: "#8e24aa" },
] as const;

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
 * The lightweight-charts canvas. Ported from q-scanner-v2's `renderChart.ts`
 * (spec §7.6): candles, the SMA set and a volume histogram, drawn against the
 * FastAPI payload. The 65 EMA is one of the additions that port did not have.
 *
 * When a setup is present the chart carries the overlay (ticket 41): the base and
 * cluster shaded as full-height band series *behind* the candles, the envelope as
 * a line the candles pierce, the trigger and stop as horizontal rules, and the
 * base's volume bars tinted so the dry-up is visible.
 *
 * The canvas is `aria-hidden` (spec §8.9): it is opaque, the adjacent text
 * already carries the data, and a generated "candlestick chart of…" label would
 * lie by implying the chart is summarisable. `height` lets the sheet draw it tall
 * and a mini chart draw it as a thumbnail off the *same* seam.
 */
export function Chart({ data, height = 360 }: { data: ChartResponse; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (el === null) return;
    const chart = createChart(el, { autoSize: true, height });
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
  }, [data, height]);

  return <div className="chart-canvas" data-testid="chart-canvas" aria-hidden="true" ref={ref} />;
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
