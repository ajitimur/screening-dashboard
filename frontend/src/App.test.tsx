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
