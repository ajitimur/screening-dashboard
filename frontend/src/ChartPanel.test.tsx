import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import ChartPanel from "./ChartPanel";
import type { ChartResponse } from "./api/client";

// lightweight-charts drives a canvas jsdom cannot render, so mock it and record
// every series added with its data — that is what "candles render with the MA
// set" verifies at the porting seam (spec §7.6).
const { addedSeries } = vi.hoisted(() => ({
  addedSeries: [] as Array<{
    definition: unknown;
    options: Record<string, unknown>;
    data: unknown[];
    priceLines: Array<Record<string, unknown>>;
  }>,
}));

vi.mock("lightweight-charts", () => ({
  createChart: () => ({
    addSeries: (definition: unknown, options: Record<string, unknown> = {}) => {
      const rec = { definition, options, data: [] as unknown[], priceLines: [] as Array<Record<string, unknown>> };
      addedSeries.push(rec);
      return {
        setData: (d: unknown[]) => (rec.data = d),
        createPriceLine: (o: Record<string, unknown>) => rec.priceLines.push(o),
      };
    },
    priceScale: () => ({ applyOptions: () => {} }),
    timeScale: () => ({ fitContent: () => {} }),
    remove: () => {},
  }),
  CandlestickSeries: "Candlestick",
  LineSeries: "Line",
  HistogramSeries: "Histogram",
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  addedSeries.length = 0;
});

function chart(over: Partial<ChartResponse> = {}): ChartResponse {
  return {
    market: "US",
    symbol: "AAA",
    session: "2026-08-05",
    candles: [
      { session: "2026-08-01", open: 98, high: 99, low: 97, close: 98, volume: 1000 },
      { session: "2026-08-02", open: 98, high: 100, low: 98, close: 100, volume: 1200 },
    ],
    sma10: [{ session: "2026-08-02", value: 99 }],
    sma20: [{ session: "2026-08-02", value: 98.5 }],
    sma50: [{ session: "2026-08-02", value: 98 }],
    ema65: [{ session: "2026-08-02", value: 97.8 }],
    setup: null,
    facts: {
      base_len: 30,
      trigger: 100,
      dist_adr: 1.02,
      stopw_adr: 1.53,
      adr: 0.02,
      dollar_volume: 1_200_000,
      decile_ranks: { "1m": 0.95, "3m": 0.9 },
      sector: "Technology",
    },
    ...over,
  };
}

// A setup overlay: the base (from 08-01), the cluster inside it (from 08-02), the
// two rules (trigger 100 / stop 97), the envelope line and the eight-row breakdown.
// Hits sum to 2+2+1+1 = 6 points → 6/2 = 3.0 stars.
function setup(): NonNullable<ChartResponse["setup"]> {
  return {
    base_start: "2026-08-01",
    cluster_start: "2026-08-02",
    trigger: 100,
    stop: 97,
    envelope: [
      { session: "2026-08-01", value: 100.5 },
      { session: "2026-08-02", value: 100 },
    ],
    score: 3,
    breakdown: [
      { dimension: "Tightness", weight: 2, hit: true },
      { dimension: "Orderliness", weight: 2, hit: true },
      { dimension: "Prior move", weight: 1, hit: true },
      { dimension: "Base length", weight: 1, hit: false },
      { dimension: "MA support", weight: 1, hit: true },
      { dimension: "Volume", weight: 1, hit: false },
      { dimension: "Sector", weight: 1, hit: false },
      { dimension: "ADR", weight: 1, hit: false },
    ],
  };
}

function mockChart(data: ChartResponse) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, json: async () => data }) as Response),
  );
}

describe("the chart panel", () => {
  it("prompts to pick a candidate when nothing is selected", () => {
    render(<ChartPanel market="US" symbol={null} />);
    expect(screen.getByText(/select a candidate/i)).toBeInTheDocument();
  });

  it("draws candles plus the four MA lines of the daily set", async () => {
    mockChart(chart());
    render(<ChartPanel market="US" symbol="AAA" />);
    await screen.findByTestId("chart-canvas");
    await waitFor(() => expect(addedSeries.length).toBeGreaterThan(0));

    const candles = addedSeries.find((s) => s.definition === "Candlestick");
    expect(candles).toBeDefined();
    expect(candles!.data).toHaveLength(2); // one per candle

    // SMA 10/20/50 and the 65 EMA — four line series (spec §2/§5.1).
    const lines = addedSeries.filter((s) => s.definition === "Line");
    expect(lines).toHaveLength(4);

    // A volume histogram too — the ported baseline draws it (spec §7.6).
    expect(addedSeries.some((s) => s.definition === "Histogram")).toBe(true);
  });

  it("shows the facts block: base length, trigger, distance, stop, ADR, dollar volume, ranks, sector", async () => {
    mockChart(chart());
    render(<ChartPanel market="US" symbol="AAA" />);
    const facts = await screen.findByLabelText("facts");
    const text = facts.textContent ?? "";
    expect(text).toMatch(/Base length/i);
    expect(within(facts).getByText("30 bars")).toBeInTheDocument();
    expect(text).toMatch(/Trigger/i);
    expect(within(facts).getByText("100.00")).toBeInTheDocument();
    expect(text).toMatch(/Distance to trigger/i);
    expect(within(facts).getByText("1.02×")).toBeInTheDocument();
    expect(text).toMatch(/Stop width/i);
    expect(within(facts).getByText("1.53×")).toBeInTheDocument();
    expect(text).toMatch(/ADR/i);
    expect(within(facts).getByText("2.00%")).toBeInTheDocument();
    expect(text).toMatch(/Dollar volume/i);
    expect(text).toMatch(/Decile ranks/i);
    expect(within(facts).getByText(/1m 95/)).toBeInTheDocument();
    expect(within(facts).getByText("Technology")).toBeInTheDocument();
  });

  it("draws the setup overlay: base/cluster bands, the envelope, and the trigger/stop rules", async () => {
    mockChart(chart({ setup: setup() }));
    render(<ChartPanel market="US" symbol="AAA" />);
    await screen.findByTestId("chart-canvas");
    await waitFor(() => expect(addedSeries.length).toBeGreaterThan(0));

    // The four MA lines plus the envelope drawn as a fifth line series (spec §3.2:
    // a line the candles pierce, not a corrected trendline).
    const lines = addedSeries.filter((s) => s.definition === "Line");
    expect(lines).toHaveLength(5);

    // Trigger and stop as horizontal rules on the candle series (spec §7).
    const candles = addedSeries.find((s) => s.definition === "Candlestick")!;
    const prices = (candles.priceLines.map((p) => p.price) as number[]).sort((a, b) => a - b);
    expect(prices).toEqual([97, 100]);

    // Base and cluster shaded as band series, plus the volume histogram — three
    // histograms in all.
    const histos = addedSeries.filter((s) => s.definition === "Histogram");
    expect(histos.length).toBe(3);

    // The base's volume bars are distinguished (each base bar carries its own
    // colour); expansion is never drawn — nothing beyond the base is tinted.
    const volume = histos.find((h) => h.options.priceScaleId === "volume")!;
    expect((volume.data as Array<{ color?: string }>).some((d) => d.color !== undefined)).toBe(true);
  });

  it("reconstructs the star score arithmetically in the eight-row breakdown", async () => {
    mockChart(chart({ setup: setup() }));
    render(<ChartPanel market="US" symbol="AAA" />);
    const breakdown = await screen.findByLabelText("score breakdown");
    const rows = within(breakdown).getAllByRole("row");
    // Eight dimensions (a header row may or may not be present, so filter by text).
    for (const dim of [
      "Tightness", "Orderliness", "Prior move", "Base length",
      "MA support", "Volume", "Sector", "ADR",
    ]) {
      expect(within(breakdown).getByText(dim)).toBeInTheDocument();
    }
    expect(rows.length).toBeGreaterThanOrEqual(8);
    // The arithmetic: 6 of 10 points → 3 stars.
    expect(breakdown.textContent).toMatch(/6\s*\/\s*10/);
    expect(breakdown.textContent).toMatch(/3/);
  });

  it("draws no overlay and no breakdown for a name with no base tonight", async () => {
    mockChart(chart({ setup: null }));
    render(<ChartPanel market="US" symbol="AAA" />);
    await screen.findByTestId("chart-canvas");
    await waitFor(() => expect(addedSeries.length).toBeGreaterThan(0));
    // Only the four MA lines — no envelope; only the volume histogram — no bands.
    expect(addedSeries.filter((s) => s.definition === "Line")).toHaveLength(4);
    expect(addedSeries.filter((s) => s.definition === "Histogram")).toHaveLength(1);
    expect(screen.queryByLabelText("score breakdown")).not.toBeInTheDocument();
  });

  it("still draws, without a facts block, for a name with no base tonight", async () => {
    mockChart(chart({ facts: null }));
    render(<ChartPanel market="US" symbol="BBB" />);
    await screen.findByTestId("chart-canvas");
    expect(screen.queryByLabelText("facts")).not.toBeInTheDocument();
    expect(screen.getByText(/no base tonight/i)).toBeInTheDocument();
  });

  it("refetches when the selected symbol changes", async () => {
    const fetchMock = vi.fn(async (url: string) => ({
      ok: true,
      json: async () => chart({ symbol: url.endsWith("BBB") ? "BBB" : "AAA" }),
    })) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetchMock);

    const { rerender } = render(<ChartPanel market="US" symbol="AAA" />);
    await screen.findByRole("heading", { name: "AAA" });
    rerender(<ChartPanel market="US" symbol="BBB" />);
    await screen.findByRole("heading", { name: "BBB" });
  });
});
