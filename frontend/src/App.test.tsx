import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import App from "./App";
import type {
  CandidatesResponse,
  ChartResponse,
  RegimeResponse,
  RunRecord,
  RunsResponse,
  SectorsResponse,
} from "./api/client";

// The chart panel drives a canvas jsdom cannot render; stub the library so the
// workbench-level interaction test can mount it (its data is asserted in
// ChartPanel.test.tsx). Harmless for the tests that never select a row.
vi.mock("lightweight-charts", () => ({
  createChart: () => ({
    addSeries: () => ({ setData: () => {} }),
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
});

function noRegime(market: string): RegimeResponse {
  return { market, session: null, state: null, posture: null, breadth: null };
}

function emptyCandidates(market: string): CandidatesResponse {
  return { market, session: null, ordered_by: "score", candidates: [] };
}

// Route the mocked fetch by endpoint: /api/runs/* returns the run records,
// /api/sectors/* returns the sector board, /api/regime/* the regime banner and
// /api/candidates/* the candidate list — each empty/off by default so the
// run-focused tests need not supply any of them.
function mockApi(
  runsByMarket: Record<string, RunsResponse>,
  regimeByMarket: Record<string, RegimeResponse> = {},
  sectorsByMarket: Record<string, SectorsResponse> = {},
) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const market = url.split("/").pop()!.toUpperCase();
      const body = url.includes("/api/sectors/")
        ? (sectorsByMarket[market] ?? emptySectors(market))
        : url.includes("/api/candidates/")
          ? emptyCandidates(market)
          : url.includes("/regime/")
            ? (regimeByMarket[market] ?? noRegime(market))
            : runsByMarket[market];
      return { ok: true, json: async () => body } as Response;
    }),
  );
}

// Most tests do not care about the regime banner; default it off (session null).
function mockRuns(byMarket: Record<string, RunsResponse>) {
  mockApi(byMarket);
}

describe("the two market tabs", () => {
  it("renders the last run's as-of session date", async () => {
    mockRuns({
      IDX: runs("IDX", "2026-08-04"),
      US: empty("US"),
    });
    render(<App />);
    expect(await screen.findByText("2026-08-04")).toBeInTheDocument();
  });

  it("shows an explicit empty state when no run exists", async () => {
    mockRuns({ IDX: empty("IDX"), US: empty("US") });
    render(<App />);
    expect(await screen.findByText(/No run yet for IDX/)).toBeInTheDocument();
  });

  it("shows tonight's universe size", async () => {
    mockRuns({ IDX: runs("IDX", "2026-08-04", 288), US: empty("US") });
    render(<App />);
    expect(await screen.findByText("288")).toBeInTheDocument();
  });

  it("switches the as-of date when the US tab is selected", async () => {
    mockRuns({
      IDX: runs("IDX", "2026-08-04"),
      US: runs("US", "2026-08-05"),
    });
    render(<App />);
    expect(await screen.findByText("2026-08-04")).toBeInTheDocument();

    act(() => screen.getByRole("button", { name: "US" }).click());
    await waitFor(() => expect(screen.getByText("2026-08-05")).toBeInTheDocument());
  });

  it("banners a quarantined latest run while serving the last good session", async () => {
    // Newest run (08-05) quarantined; last published (08-04) keeps serving.
    mockRuns({
      IDX: {
        market: "IDX",
        latest: run("IDX", "2026-08-04"),
        runs: [quarantined("IDX", "2026-08-05"), run("IDX", "2026-08-04")],
        universe_size: 100,
        run_due: false,
        running: false,
      },
      US: { market: "US", latest: null, runs: [], universe_size: null, run_due: false, running: false },
    });
    render(<App />);
    // The stale banner is shown...
    expect(await screen.findByRole("status")).toHaveTextContent(/quarantined|last good/i);
    // ...and the served session is still the last good one, dated (banner + as-of).
    expect(screen.getAllByText("2026-08-04").length).toBeGreaterThan(0);
  });

  it("switches to the Boards screen and renders a board", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const market = url.split("/").pop()!.toUpperCase();
        if (url.includes("/api/boards/")) {
          return {
            ok: true,
            json: async () => ({
              market,
              session: "2026-08-04",
              boards: [
                {
                  lookback: "1w",
                  rows: [{ symbol: "WIN", raw_return: 0.42, breadth: 3, is_new: true, surge: true, adr: 0.05 }],
                },
              ],
            }),
          } as Response;
        }
        if (url.includes("/api/sectors/")) {
          return { ok: true, json: async () => emptySectors(market) } as Response;
        }
        if (url.includes("/api/candidates/")) {
          return { ok: true, json: async () => emptyCandidates(market) } as Response;
        }
        return { ok: true, json: async () => runs(market, "2026-08-04") } as Response;
      }),
    );
    render(<App />);
    await screen.findByText("2026-08-04"); // workbench first

    act(() => screen.getByRole("button", { name: "Boards" }).click());
    expect(await screen.findByRole("table", { name: /1w/ })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /ADR/i })).not.toBeChecked();
  });

  it("shows the regime banner: state, sizing posture in words, breadth and as-of date", async () => {
    mockApi(
      { IDX: runs("IDX", "2026-08-04"), US: empty("US") },
      {
        IDX: {
          market: "IDX",
          session: "2026-08-04",
          state: "FRIENDLY",
          posture: "full size",
          breadth: 0.5,
        },
      },
    );
    render(<App />);
    const banner = await screen.findByLabelText(/IDX regime/i);
    expect(banner).toHaveTextContent(/FRIENDLY/);
    expect(banner).toHaveTextContent(/full size/); // words, not a number
    expect(banner).toHaveTextContent(/50%/); // breadth, displayed
    expect(banner).toHaveTextContent("2026-08-04"); // the as-of session date
  });

  it("shows a hostile regime with the sit-out posture", async () => {
    mockApi(
      { IDX: runs("IDX", "2026-08-04"), US: empty("US") },
      {
        IDX: {
          market: "IDX",
          session: "2026-08-04",
          state: "HOSTILE",
          posture: "sit out",
          breadth: 0.1,
        },
      },
    );
    render(<App />);
    const banner = await screen.findByLabelText(/IDX regime/i);
    expect(banner).toHaveTextContent(/HOSTILE/);
    expect(banner).toHaveTextContent(/sit out/);
  });

  it("shows an undefined regime as warming up, with no posture", async () => {
    mockApi(
      { IDX: runs("IDX", "2026-08-04"), US: empty("US") },
      {
        IDX: {
          market: "IDX",
          session: "2026-08-04",
          state: null,
          posture: null,
          breadth: null,
        },
      },
    );
    render(<App />);
    const banner = await screen.findByLabelText(/IDX regime/i);
    expect(banner).toHaveTextContent(/undefined|warming up/i);
    expect(banner).not.toHaveTextContent(/full size|reduced|sit out/);
  });

  it("shows no regime banner before any run has published", async () => {
    mockApi({ IDX: empty("IDX"), US: empty("US") });
    render(<App />);
    await screen.findByText(/No run yet for IDX/);
    expect(screen.queryByLabelText(/IDX regime/i)).not.toBeInTheDocument();
  });

  it("swaps the chart panel when a candidate row is clicked, and nothing else navigates", async () => {
    const oneCandidate: CandidatesResponse = {
      market: "IDX",
      session: "2026-08-04",
      ordered_by: "score",
      candidates: [
        {
          symbol: "AAA",
          score: 3.5,
          breakdown: [],
          dist_adr: 1.0,
          stopw_adr: 1.3,
          affordable: false,
          industry: "Semiconductors",
          breadth: 2,
        },
      ],
    };
    const chartOf = (symbol: string): ChartResponse => ({
      market: "IDX",
      symbol,
      session: "2026-08-04",
      candles: [{ session: "2026-08-04", open: 1, high: 2, low: 0.5, close: 1.5, volume: 100 }],
      sma10: [],
      sma20: [],
      sma50: [],
      ema65: [],
      setup: null,
      facts: {
        base_len: 30,
        trigger: 100,
        dist_adr: 1.02,
        stopw_adr: 1.53,
        adr: 0.02,
        dollar_volume: 1_000_000,
        decile_ranks: { "1m": 0.95 },
        sector: "Technology",
      },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/api/candidates/"))
          return { ok: true, json: async () => oneCandidate } as Response;
        if (url.includes("/api/chart/")) {
          const symbol = url.split("/").pop()!;
          return { ok: true, json: async () => chartOf(symbol) } as Response;
        }
        if (url.includes("/api/sectors/")) {
          const market = url.split("/").pop()!.toUpperCase();
          return { ok: true, json: async () => emptySectors(market) } as Response;
        }
        if (url.includes("/regime/")) {
          const market = url.split("/").pop()!.toUpperCase();
          return { ok: true, json: async () => noRegime(market) } as Response;
        }
        const market = url.split("/").pop()!.toUpperCase();
        return { ok: true, json: async () => runs(market, "2026-08-04") } as Response;
      }),
    );
    render(<App />);
    // Before a click the panel prompts for a selection.
    expect(await screen.findByText(/select a candidate/i)).toBeInTheDocument();

    act(() => screen.getByRole("button", { name: "AAA" }).click());

    // The chart panel swapped to AAA...
    expect(await screen.findByRole("heading", { name: "AAA" })).toBeInTheDocument();
    expect(await screen.findByLabelText("facts")).toBeInTheDocument();
    // ...and nothing else navigated: still the IDX market, still the Workbench.
    expect(screen.getByRole("button", { name: "IDX" })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("button", { name: "Workbench" })).toHaveAttribute("aria-current", "true");
  });

  it("kicks a run on open when the last final session is missing, and shows progress", async () => {
    // Run-on-open (spec §7.3): the tab opens on a store whose last final session
    // is missing (run_due), POSTs to kick the run, shows a progress state while
    // it is in flight, then serves the now-complete session.
    vi.useFakeTimers();
    const okJson = (body: unknown) => ({ ok: true, json: async () => body }) as Response;
    const post = vi.fn();
    let getCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, opts?: RequestInit) => {
        if (url.includes("/api/runs/") && opts?.method === "POST") {
          post();
          return okJson({ market: "IDX", triggered: true, running: true });
        }
        if (url.includes("/api/runs/")) {
          getCount += 1;
          const base = { market: "IDX", runs: [], universe_size: 100 };
          if (getCount === 1)
            return okJson({ ...base, latest: run("IDX", "2026-08-04"), run_due: true, running: false });
          if (getCount === 2)
            return okJson({ ...base, latest: run("IDX", "2026-08-04"), run_due: true, running: true });
          return okJson({ ...base, latest: run("IDX", "2026-08-05"), run_due: false, running: false });
        }
        if (url.includes("/api/sectors/")) return okJson(emptySectors("IDX"));
        if (url.includes("/api/candidates/")) return okJson(emptyCandidates("IDX"));
        if (url.includes("/regime/")) return okJson(noRegime("IDX"));
        return okJson(emptySectors("IDX"));
      }),
    );
    try {
      render(<App />);
      // The first look kicks the run.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(post).toHaveBeenCalledTimes(1);
      // The next poll finds it in flight — the progress state shows.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect(screen.getByRole("status")).toHaveTextContent(/Running tonight's IDX/i);
      // The run lands: the fresh session is served and the progress state clears.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect(screen.getByText("2026-08-05")).toBeInTheDocument();
      expect(screen.queryByText(/Running tonight's IDX/i)).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows no banner when the latest run published", async () => {
    mockRuns({
      IDX: {
        market: "IDX",
        latest: run("IDX", "2026-08-04"),
        runs: [run("IDX", "2026-08-04")],
        universe_size: 100,
        run_due: false,
        running: false,
      },
      US: { market: "US", latest: null, runs: [], universe_size: null, run_due: false, running: false },
    });
    render(<App />);
    expect(await screen.findByText("2026-08-04")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

function runs(market: string, session: string, universe_size = 100): RunsResponse {
  return {
    market,
    latest: run(market, session),
    runs: [run(market, session)],
    universe_size,
    run_due: false,
    running: false,
  };
}

function empty(market: string): RunsResponse {
  return { market, latest: null, runs: [], universe_size: null, run_due: false, running: false };
}

function run(market: string, session: string): RunRecord {
  return {
    market,
    session,
    status: "published",
    symbols_enumerated: 100,
    symbols_resolved: 100,
    created_at: `${session}T22:00:00`,
  };
}

function quarantined(market: string, session: string): RunRecord {
  return { ...run(market, session), status: "quarantined", symbols_resolved: 50 };
}

const SECTORS = [
  "Basic Materials", "Communication Services", "Consumer Cyclical",
  "Consumer Defensive", "Energy", "Financial Services", "Healthcare",
  "Industrials", "Real Estate", "Technology", "Utilities",
];
const LOOKBACKS = ["1w", "1m", "3m", "6m", "12m"];

function emptySectors(market: string): SectorsResponse {
  return {
    market,
    session: null,
    sectors: SECTORS.map((sector) => ({
      sector,
      members: 0,
      shares: Object.fromEntries(LOOKBACKS.map((lb) => [lb, 0])),
      decile_counts: Object.fromEntries(LOOKBACKS.map((lb) => [lb, 0])),
      shape_differential: 0,
      temporal_delta: null,
      rotation_eligible: false,
      delta_low_confidence: true,
    })),
    industries: [],
  };
}
