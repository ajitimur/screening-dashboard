import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import Boards from "./Boards";
import type { BoardsResponse } from "./api/client";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function row(
  symbol: string,
  raw_return: number,
  opts: Partial<{ breadth: number; is_new: boolean; surge: boolean; adr: number | null }> = {},
) {
  return {
    symbol,
    raw_return,
    breadth: opts.breadth ?? 1,
    is_new: opts.is_new ?? false,
    surge: opts.surge ?? false,
    adr: opts.adr ?? 0.05,
    // Phase-1 leaders fields (spec §4.4); v1 renders neither yet.
    sector: null,
    dollar_volume: null,
  };
}

function mockBoards(body: BoardsResponse) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, json: async () => body }) as Response),
  );
}

const FIVE = ["1w", "1m", "3m", "6m", "12m"] as const;

function fullBoards(): BoardsResponse {
  return {
    market: "US",
    session: "2026-08-04",
    boards: FIVE.map((lookback) => ({
      lookback,
      rows: [
        row("WIN", 0.42, { breadth: 3, is_new: true, surge: lookback === "1w" }),
        row("MEG", 0.10, { breadth: 1, adr: 0.02 }),
      ],
    })),
  };
}

describe("the boards tab", () => {
  it("renders five boards, one per lookback", async () => {
    mockBoards(fullBoards());
    render(<Boards market="US" />);
    for (const lb of FIVE) {
      expect(await screen.findByRole("table", { name: new RegExp(lb) })).toBeInTheDocument();
    }
  });

  it("shows an empty state when no run has published", async () => {
    mockBoards({ market: "US", session: null, boards: [] });
    render(<Boards market="US" />);
    expect(await screen.findByText(/No run yet/)).toBeInTheDocument();
  });

  it("carries the k/5 badge and the NEW marker on a row", async () => {
    mockBoards(fullBoards());
    render(<Boards market="US" />);
    const board = await screen.findByRole("table", { name: /1m/ });
    const win = within(board).getByRole("row", { name: /WIN/ });
    expect(within(win).getByText("3/5")).toBeInTheDocument();
    expect(within(win).getByText("NEW")).toBeInTheDocument();
  });

  it("flags the ≥30%/5d surge only on the 1w board", async () => {
    mockBoards(fullBoards());
    render(<Boards market="US" />);
    const oneW = await screen.findByRole("table", { name: /1w/ });
    expect(within(oneW).getByText(/↑30%/)).toBeInTheDocument();
    const threeM = screen.getByRole("table", { name: /3m/ });
    expect(within(threeM).queryByText(/↑30%/)).not.toBeInTheDocument();
  });

  it("has an ADR toggle that defaults off and hides sub-4% names when on", async () => {
    mockBoards(fullBoards());
    render(<Boards market="US" />);
    const toggle = await screen.findByRole("checkbox", { name: /ADR/i });
    expect(toggle).not.toBeChecked(); // defaults off — nothing hidden

    // Off: the sub-4% ADR name (MEG, 0.02) is visible.
    const board = screen.getByRole("table", { name: /1m/ });
    expect(within(board).getByRole("row", { name: /MEG/ })).toBeInTheDocument();

    act(() => toggle.click());
    await waitFor(() =>
      expect(within(screen.getByRole("table", { name: /1m/ })).queryByRole("row", { name: /MEG/ })).toBeNull(),
    );
    // The 5% ADR name stays.
    expect(within(screen.getByRole("table", { name: /1m/ })).getByRole("row", { name: /WIN/ })).toBeInTheDocument();
  });
});
