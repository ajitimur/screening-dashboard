import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import MiniChart from "./MiniChart";
import { _clearChartCache } from "./chartCache";
import { chartResponse } from "./api/fixtures";

// The charting seam mock (spec §6) — record series data, never pixels.
const { addedSeries } = vi.hoisted(() => ({
  addedSeries: [] as Array<{ definition: unknown; data: unknown[] }>,
}));
vi.mock("lightweight-charts", () => ({
  createChart: () => ({
    addSeries: (definition: unknown) => {
      const rec = { definition, data: [] as unknown[] };
      addedSeries.push(rec);
      return { setData: (d: unknown[]) => (rec.data = d), createPriceLine: () => {} };
    },
    priceScale: () => ({ applyOptions: () => {} }),
    timeScale: () => ({ fitContent: () => {} }),
    remove: () => {},
  }),
  CandlestickSeries: "Candlestick",
  LineSeries: "Line",
  HistogramSeries: "Histogram",
}));

// jsdom has no IntersectionObserver; a controllable stub lets a test drive the
// "not until it scrolls into view" behaviour deterministically.
class MockIO {
  static instances: MockIO[] = [];
  elements: Element[] = [];
  constructor(
    public cb: IntersectionObserverCallback,
    public options?: IntersectionObserverInit,
  ) {
    MockIO.instances.push(this);
  }
  observe(el: Element) {
    this.elements.push(el);
  }
  unobserve() {}
  disconnect() {}
  enter() {
    // Wrap the state-triggering callback in act() so the visibility flip is
    // flushed inside React's batch, not flagged as an un-acted update.
    act(() => {
      this.cb(
        this.elements.map((target) => ({ isIntersecting: true, target }) as IntersectionObserverEntry),
        this as unknown as IntersectionObserver,
      );
    });
  }
}

beforeEach(() => {
  MockIO.instances = [];
  vi.stubGlobal("IntersectionObserver", MockIO as unknown as typeof IntersectionObserver);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  _clearChartCache();
  addedSeries.length = 0;
});

function stub() {
  const fetchMock = vi.fn(async () => ({ ok: true, json: async () => chartResponse() }) as Response) as unknown as typeof fetch;
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock as unknown as ReturnType<typeof vi.fn>;
}

describe("the mini chart", () => {
  it("does not read the chart until it scrolls into view", async () => {
    const fetchMock = stub();
    render(<MiniChart market="US" symbol="AAA" />);
    expect(fetchMock).not.toHaveBeenCalled(); // lazy: mounted, but off-screen
    expect(screen.queryByTestId("chart-canvas")).not.toBeInTheDocument();

    MockIO.instances[0].enter();
    await screen.findByTestId("chart-canvas");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("observes with the 200px rootMargin and reads the 60-bar window", async () => {
    const fetchMock = stub();
    render(<MiniChart market="US" symbol="AAA" />);
    expect(MockIO.instances[0].options?.rootMargin).toBe("200px");
    MockIO.instances[0].enter();
    await screen.findByTestId("chart-canvas");
    expect(fetchMock.mock.calls[0][0]).toContain("bars=60");
  });

  it("shares one read between two mini charts of the same name", async () => {
    const fetchMock = stub();
    render(
      <>
        <MiniChart market="US" symbol="AAA" />
        <MiniChart market="US" symbol="AAA" />
      </>,
    );
    MockIO.instances.forEach((io) => io.enter());
    await waitFor(() => expect(screen.getAllByTestId("chart-canvas")).toHaveLength(2));
    expect(fetchMock).toHaveBeenCalledTimes(1); // the shared cache (spec §6.4)
  });

  it("fails silently — no message, no notice, just an empty frame (spec §7.7)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 500 }) as Response));
    const { container } = render(<MiniChart market="US" symbol="AAA" />);
    MockIO.instances[0].enter();
    // Give the rejected read a tick to settle.
    await waitFor(() => expect(container.querySelector("[data-testid='chart-canvas']")).toBeNull());
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(container.textContent).toBe(""); // 60 cards → not 60 apologies
  });

  it("the canvas is aria-hidden — decorative, the card's numbers carry the data", async () => {
    stub();
    render(<MiniChart market="US" symbol="AAA" />);
    MockIO.instances[0].enter();
    const canvas = await screen.findByTestId("chart-canvas");
    expect(canvas).toHaveAttribute("aria-hidden", "true");
  });

  it("a click opens the sheet through onActivate", async () => {
    stub();
    const onActivate = vi.fn();
    const { container } = render(<MiniChart market="US" symbol="AAA" onActivate={onActivate} />);
    fireEvent.click(container.firstElementChild!);
    expect(onActivate).toHaveBeenCalledTimes(1);
  });
});
