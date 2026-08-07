import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import CandidateList from "./CandidateList";
import type { Candidate, CandidatesResponse } from "./api/client";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function candidate(symbol: string, over: Partial<Candidate> = {}): Candidate {
  return {
    symbol,
    score: 3.5,
    breakdown: [],
    dist_adr: 1.0,
    stopw_adr: 1.3,
    affordable: false,
    industry: "Semiconductors",
    breadth: 1,
    // The chart-facts fold (spec §4.3): folded onto the row so a Setups card
    // renders without a per-symbol chart fetch.
    trigger_price: 100.0,
    stop_price: 97.0,
    close: 98.0,
    sector: "Technology",
    adr: 0.02,
    dollar_volume: 1_000_000,
    decile_ranks: {},
    new_tonight: false,
    verdict: null,
    ...over,
  };
}

function list(over: Partial<CandidatesResponse> = {}): CandidatesResponse {
  return {
    market: "US",
    session: "2026-08-05",
    ordered_by: "score",
    candidates: [candidate("AAA")],
    ...over,
  };
}

function mockCandidates(data: CandidatesResponse) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, json: async () => data }) as Response),
  );
}

describe("the candidate list", () => {
  it("renders the five columns of the workbench list", async () => {
    mockCandidates(list());
    render(<CandidateList market="US" />);
    const table = await screen.findByRole("table", { name: /US candidates/i });
    const headers = within(table)
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    // Ticker, star score, distance to trigger, stop width in ADR, industry, k/5.
    expect(headers.join("|")).toMatch(/Ticker/i);
    expect(headers.join("|")).toMatch(/score/i);
    expect(headers.join("|")).toMatch(/trigger/i);
    expect(headers.join("|")).toMatch(/stop/i);
    expect(headers.join("|")).toMatch(/industry/i);
    expect(headers.join("|")).toMatch(/5/);
  });

  it("states the list is sorted by star score, highest first", async () => {
    mockCandidates(list({ ordered_by: "score" }));
    render(<CandidateList market="US" />);
    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent(/score/i);
    expect(note).toHaveTextContent(/highest|descending|first/i);
  });

  it("renders the star score to one decimal — the sort key", async () => {
    mockCandidates(list({ candidates: [candidate("AAA", { score: 4.5 })] }));
    render(<CandidateList market="US" />);
    const row = await screen.findByRole("row", { name: /AAA/ });
    expect(within(row).getByText("4.5")).toBeInTheDocument();
  });

  it("renders candidates in the server's order and marks no line_ok failure", async () => {
    // The server already sorted by score with the silent line_ok tiebreak; the
    // component preserves that order and adds no marker of its own.
    mockCandidates(
      list({
        candidates: [
          candidate("TOP", { score: 5.0 }),
          candidate("MID", { score: 3.0 }),
        ],
      }),
    );
    render(<CandidateList market="US" />);
    const table = await screen.findByRole("table", { name: /US candidates/i });
    const rows = within(table).getAllByRole("row").slice(1); // drop the header
    expect(rows.map((r) => within(r).getByRole("rowheader").textContent)).toEqual([
      "TOP",
      "MID",
    ]);
  });

  it("highlights the sub-1×ADR affordable minority and filters nothing", async () => {
    mockCandidates(
      list({
        candidates: [
          candidate("TIGHT", { stopw_adr: 0.51, affordable: true }),
          candidate("WIDE", { stopw_adr: 2.55, affordable: false }),
        ],
      }),
    );
    render(<CandidateList market="US" />);
    // Both rows render — the stop column never filters.
    const tight = await screen.findByRole("row", { name: /TIGHT/ });
    const wide = await screen.findByRole("row", { name: /WIDE/ });
    // The affordable one is marked; the wide majority is not.
    expect(within(tight).getByText(/0.5/)).toHaveClass("affordable");
    expect(within(wide).getByText(/2.5/)).not.toHaveClass("affordable");
  });

  it("renders the k/5 breadth badge and the industry tag", async () => {
    mockCandidates(
      list({ candidates: [candidate("AAA", { breadth: 3, industry: "Biotech" })] }),
    );
    render(<CandidateList market="US" />);
    const row = await screen.findByRole("row", { name: /AAA/ });
    expect(within(row).getByText("3/5")).toBeInTheDocument();
    expect(within(row).getByText("Biotech")).toBeInTheDocument();
  });

  it("shows an explicit empty state when no run has published", async () => {
    mockCandidates(list({ session: null, candidates: [] }));
    render(<CandidateList market="US" />);
    expect(await screen.findByText(/no candidates/i)).toBeInTheDocument();
  });

  it("selects a row's ticker on click, so the chart panel can swap", async () => {
    mockCandidates(list({ candidates: [candidate("AAA"), candidate("BBB")] }));
    const onSelect = vi.fn();
    render(<CandidateList market="US" onSelect={onSelect} selected={null} />);
    const ticker = await screen.findByRole("button", { name: "BBB" });
    ticker.click();
    expect(onSelect).toHaveBeenCalledWith("BBB");
  });

  it("marks the selected row", async () => {
    mockCandidates(list({ candidates: [candidate("AAA"), candidate("BBB")] }));
    render(<CandidateList market="US" selected="BBB" />);
    const row = await screen.findByRole("row", { name: /BBB/ });
    expect(row).toHaveAttribute("aria-selected", "true");
  });
});
