import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import ChartSheet, { type SheetTarget } from "./ChartSheet";
import { _clearChartCache } from "./chartCache";
import { chartFacts, chartResponse, scoreRow, setupOverlay } from "./api/fixtures";
import type { ChartResponse } from "./api/client";

// Mock the charting library at its seam (spec §6): record every series added and
// its data — never pixels. Same shape the ChartPanel suite uses.
const { addedSeries } = vi.hoisted(() => ({
  addedSeries: [] as Array<{ definition: unknown; options: Record<string, unknown>; data: unknown[]; priceLines: Array<Record<string, unknown>> }>,
}));
vi.mock("lightweight-charts", () => ({
  createChart: () => ({
    addSeries: (definition: unknown, options: Record<string, unknown> = {}) => {
      const rec = { definition, options, data: [] as unknown[], priceLines: [] as Array<Record<string, unknown>> };
      addedSeries.push(rec);
      return { setData: (d: unknown[]) => (rec.data = d), createPriceLine: (o: Record<string, unknown>) => rec.priceLines.push(o) };
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
  _clearChartCache();
  addedSeries.length = 0;
});

const BREAKDOWN = [
  scoreRow({ dimension: "Tightness", weight: 2, hit: true }),
  scoreRow({ dimension: "Orderliness", weight: 2, hit: true }),
  scoreRow({ dimension: "Prior move", weight: 1, hit: true }),
  scoreRow({ dimension: "Base length", weight: 1, hit: false }),
  scoreRow({ dimension: "MA support", weight: 1, hit: true }),
  scoreRow({ dimension: "Volume", weight: 1, hit: false }),
  scoreRow({ dimension: "Sector", weight: 1, hit: false }),
  scoreRow({ dimension: "ADR", weight: 1, hit: false }),
];

function target(over: Partial<SheetTarget> = {}): SheetTarget {
  return {
    symbol: "AAA",
    market: "US",
    verdict: "watch",
    sector: "Technology",
    facts: chartFacts(),
    breakdown: BREAKDOWN,
    score: 3,
    ...over,
  };
}

// Serve the chart read, optionally deferred so a test can assert what paints
// *before* the candles land.
function stubChart(data: ChartResponse = chartResponse(), defer?: Promise<void>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      if (defer) await defer;
      return { ok: true, json: async () => data } as Response;
    }),
  );
}

function trigger() {
  // A real focusable trigger standing in for the ticker <button> on the page.
  const btn = document.createElement("button");
  btn.textContent = "AAA";
  document.body.appendChild(btn);
  btn.focus();
  return btn;
}

describe("the chart sheet", () => {
  it("renders nothing when closed (a null target)", () => {
    stubChart();
    const { container } = render(<ChartSheet target={null} onClose={() => {}} />);
    expect(container.firstChild).toBeNull();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens on a non-null target and moves focus to its heading", async () => {
    stubChart();
    trigger();
    render(<ChartSheet target={target()} onClose={() => {}} />);
    const heading = await screen.findByRole("heading", { name: "AAA" });
    await waitFor(() => expect(heading).toHaveFocus());
  });

  it("paints header, facts and the breakdown before the candles land", async () => {
    let release!: () => void;
    stubChart(chartResponse(), new Promise<void>((r) => (release = r)));
    render(<ChartSheet target={target()} onClose={() => {}} />);

    // The header, facts and eight-row breakdown are on screen with the canvas
    // still in flight (spec §6.3/§7.7: never blocked on the canvas).
    expect(screen.getByRole("heading", { name: "AAA" })).toBeInTheDocument();
    expect(screen.getByLabelText("facts")).toBeInTheDocument();
    expect(screen.getAllByText("Technology").length).toBeGreaterThan(0); // header + facts
    const breakdown = screen.getByLabelText("score breakdown");
    for (const dim of ["Tightness", "Orderliness", "Base length", "ADR"]) {
      expect(within(breakdown).getByText(dim)).toBeInTheDocument();
    }
    expect(breakdown.textContent).toMatch(/6\s*\/\s*10/); // 2+2+1+1 hits
    expect(screen.queryByTestId("chart-canvas")).not.toBeInTheDocument();

    release();
    await screen.findByTestId("chart-canvas");
  });

  it("asks for the 60-bar window so a mini already on screen shares the read", async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => chartResponse() }) as Response) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetchMock);
    render(<ChartSheet target={target()} onClose={() => {}} />);
    await screen.findByTestId("chart-canvas");
    expect((fetchMock as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0]).toContain("bars=60");
  });

  it("Esc closes and returns focus to the trigger", async () => {
    stubChart();
    const btn = trigger();
    const onClose = vi.fn();
    const { rerender } = render(<ChartSheet target={target()} onClose={onClose} />);
    await screen.findByRole("heading", { name: "AAA" });
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    rerender(<ChartSheet target={null} onClose={onClose} />); // parent honours the close
    expect(btn).toHaveFocus();
  });

  it("the × closes and returns focus to the trigger", async () => {
    stubChart();
    const btn = trigger();
    const onClose = vi.fn();
    const { rerender } = render(<ChartSheet target={target()} onClose={onClose} />);
    await screen.findByRole("heading", { name: "AAA" });
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
    rerender(<ChartSheet target={null} onClose={onClose} />);
    expect(btn).toHaveFocus();
  });

  it("a content swap re-runs the open behaviour, moving focus to the new heading", async () => {
    stubChart();
    const { rerender } = render(<ChartSheet target={target()} onClose={() => {}} />);
    await screen.findByRole("heading", { name: "AAA" });
    rerender(<ChartSheet target={target({ symbol: "BBB", breakdown: BREAKDOWN })} onClose={() => {}} />);
    const heading = await screen.findByRole("heading", { name: "BBB" });
    await waitFor(() => expect(heading).toHaveFocus());
  });

  it("an external close (market switch / tab change) tears down and fires no onClose", async () => {
    stubChart();
    const btn = trigger();
    btn.blur(); // focus is elsewhere — a navigation, not a user close
    const onClose = vi.fn();
    const { rerender } = render(<ChartSheet target={target()} onClose={onClose} />);
    await screen.findByRole("heading", { name: "AAA" });
    rerender(<ChartSheet target={null} onClose={onClose} />);
    expect(screen.queryByRole("heading", { name: "AAA" })).not.toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled(); // teardown, not a close (spec §8.8)
  });

  it("a failed chart read replaces only the canvas — the breakdown stays readable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 500 }) as Response));
    render(<ChartSheet target={target()} onClose={() => {}} />);
    await screen.findByText(/chart unavailable/i);
    expect(screen.queryByTestId("chart-canvas")).not.toBeInTheDocument();
    // The audit material survives a dead canvas (spec §7.7).
    expect(screen.getByLabelText("score breakdown")).toBeInTheDocument();
    expect(screen.getByLabelText("facts")).toBeInTheDocument();
  });

  it("draws the candles and the setup overlay through the shared seam", async () => {
    stubChart(chartResponse({ setup: setupOverlay({ envelope: [], breakdown: BREAKDOWN }), sma10: [], sma20: [], sma50: [], ema65: [] }));
    render(<ChartSheet target={target()} onClose={() => {}} />);
    await screen.findByTestId("chart-canvas");
    await waitFor(() => expect(addedSeries.length).toBeGreaterThan(0));
    expect(addedSeries.some((s) => s.definition === "Candlestick")).toBe(true);
    const candles = addedSeries.find((s) => s.definition === "Candlestick")!;
    expect((candles.priceLines.map((p) => p.price) as number[]).sort((a, b) => a - b)).toEqual([97, 100]);
  });

  it("a name with bars but no detection draws the chart plus one explicit no-base line", async () => {
    stubChart(chartResponse({ setup: null, facts: null }));
    // No row-supplied facts/breakdown either — a Leaders-style open of a name
    // that has no base tonight.
    render(<ChartSheet target={target({ facts: null, breakdown: null })} onClose={() => {}} />);
    await screen.findByTestId("chart-canvas");
    expect(screen.getByText(/no base tonight/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("score breakdown")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("facts")).not.toBeInTheDocument();
  });

  it("has no accessibility violations", async () => {
    stubChart();
    render(<ChartSheet target={target()} onClose={() => {}} />);
    await screen.findByTestId("chart-canvas");
    // The sheet is portalled to <body>, so axe the document, not the render root.
    expect(await axe(document.body)).toHaveNoViolations();
  });
});
