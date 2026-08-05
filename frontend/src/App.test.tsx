import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import App from "./App";
import type { RunRecord, RunsResponse, SectorsResponse } from "./api/client";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// Route the mocked fetch by endpoint: /api/runs/* returns the run records,
// /api/sectors/* returns the sector board (an empty board by default so the
// run-focused tests need not supply one).
function mockRuns(
  byMarket: Record<string, RunsResponse>,
  sectorsByMarket: Record<string, SectorsResponse> = {},
) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const market = url.split("/").pop()!.toUpperCase();
      const isSectors = url.includes("/api/sectors/");
      const body = isSectors
        ? (sectorsByMarket[market] ?? emptySectors(market))
        : byMarket[market];
      return { ok: true, json: async () => body } as Response;
    }),
  );
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
      },
      US: { market: "US", latest: null, runs: [], universe_size: null },
    });
    render(<App />);
    // The stale banner is shown...
    expect(await screen.findByRole("status")).toHaveTextContent(/quarantined|last good/i);
    // ...and the served session is still the last good one, dated (banner + as-of).
    expect(screen.getAllByText("2026-08-04").length).toBeGreaterThan(0);
  });

  it("shows no banner when the latest run published", async () => {
    mockRuns({
      IDX: {
        market: "IDX",
        latest: run("IDX", "2026-08-04"),
        runs: [run("IDX", "2026-08-04")],
        universe_size: 100,
      },
      US: { market: "US", latest: null, runs: [], universe_size: null },
    });
    render(<App />);
    expect(await screen.findByText("2026-08-04")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

function runs(market: string, session: string, universe_size = 100): RunsResponse {
  return { market, latest: run(market, session), runs: [run(market, session)], universe_size };
}

function empty(market: string): RunsResponse {
  return { market, latest: null, runs: [], universe_size: null };
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
