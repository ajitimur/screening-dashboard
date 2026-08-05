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
    score: null,
    dist_adr: 1.0,
    stopw_adr: 1.3,
    affordable: false,
    industry: "Semiconductors",
    breadth: 1,
    ...over,
  };
}

function list(over: Partial<CandidatesResponse> = {}): CandidatesResponse {
  return {
    market: "US",
    session: "2026-08-05",
    ordered_by: "ticker",
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

  it("states the order is by ticker and the score sort is not yet live", async () => {
    mockCandidates(list({ ordered_by: "ticker" }));
    render(<CandidateList market="US" />);
    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent(/ticker/i);
    expect(note).toHaveTextContent(/score.*not.*(yet|live)|not yet live/i);
  });

  it("shows the star score as a placeholder until the rubric lands", async () => {
    mockCandidates(list({ candidates: [candidate("AAA", { score: null })] }));
    render(<CandidateList market="US" />);
    const row = await screen.findByRole("row", { name: /AAA/ });
    // No fabricated number — the score cell is an explicit placeholder.
    expect(within(row).getByText("—")).toBeInTheDocument();
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
