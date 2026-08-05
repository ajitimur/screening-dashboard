import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import App from "./App";
import type { RunRecord, RunsResponse } from "./api/client";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function mockRuns(byMarket: Record<string, RunsResponse>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const market = url.split("/").pop()!.toUpperCase();
      return { ok: true, json: async () => byMarket[market] } as Response;
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
        return { ok: true, json: async () => runs(market, "2026-08-04") } as Response;
      }),
    );
    render(<App />);
    await screen.findByText("2026-08-04"); // workbench first

    act(() => screen.getByRole("button", { name: "Boards" }).click());
    expect(await screen.findByRole("table", { name: /1w/ })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /ADR/i })).not.toBeChecked();
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
