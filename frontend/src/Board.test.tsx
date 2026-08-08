import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import Board from "./Board";
import {
  candidate,
  candidatesResponse,
  leader,
  leaderRow,
  leadersResponse,
  sectorStrength,
  sectorsResponse,
  stubFetch,
  type ApiRoutes,
} from "./api/fixtures";

// The chart sheet imports the chart library through Chart.tsx; jsdom cannot draw
// a canvas, so stub it — the sheet opening is what these tests exercise, not the
// candles.
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
  vi.unstubAllGlobals();
});

const noop = () => {};

// Five detected names ≥3.5★ plus one below the bar, deliberately out of order so
// the sort (stars desc, stopw_adr asc) and the ≥3.5 cut and the cap at 4 are all
// exercised at once. Expected hero cut: AAA(5.0), DDD(4.0), EEE(3.5/0.3),
// BBB(3.5/0.5) — CCC(3.5/2.0) drops on the cap, FFF(3.0) on the bar.
function heroCandidates(): ApiRoutes {
  return {
    candidates: (m) =>
      candidatesResponse({
        market: m,
        candidates: [
          candidate({ symbol: "AAA", score: 5.0, stopw_adr: 1.0, new_tonight: true }),
          candidate({ symbol: "BBB", score: 3.5, stopw_adr: 0.5 }),
          candidate({ symbol: "CCC", score: 3.5, stopw_adr: 2.0 }),
          candidate({ symbol: "DDD", score: 4.0, stopw_adr: 1.5 }),
          candidate({ symbol: "EEE", score: 3.5, stopw_adr: 0.3 }),
          candidate({ symbol: "FFF", score: 3.0, stopw_adr: 0.1 }),
        ],
      }),
  };
}

// A leaders payload with a 1-month board — the only lookback the strip reads —
// carrying a hero (AAA, included, no dedup) and a non-hero.
function leadersRoutes(): ApiRoutes {
  return {
    leaders: (m) =>
      leadersResponse({
        market: m,
        boards: [
          leader({
            lookback: "1m",
            rows: [
              leaderRow({ symbol: "AAA", raw_return: 0.42, breadth: 4, sector: "Technology" }),
              leaderRow({ symbol: "ZZZ", raw_return: 0.31, breadth: 2, sector: "Energy" }),
            ],
          }),
        ],
      }),
  };
}

// Five sectors with mixed signs, all inside the top-5, so a negative bar renders.
function rotationRoutes(): ApiRoutes {
  return {
    sectors: (m) =>
      sectorsResponse({
        market: m,
        sectors: [
          sectorStrength({ sector: "Technology", shape_differential: 0.3 }),
          sectorStrength({ sector: "Energy", shape_differential: 0.2 }),
          sectorStrength({ sector: "Healthcare", shape_differential: 0.1 }),
          sectorStrength({ sector: "Utilities", shape_differential: 0.0 }),
          sectorStrength({ sector: "Industrials", shape_differential: -0.1 }),
        ],
      }),
  };
}

function renderBoard(
  extra: Partial<{
    universeSize: number | null;
    navigate: (patch: { tab?: string; sector?: string | null }) => void;
    market: string;
    routes: ApiRoutes;
  }> = {},
) {
  stubFetch(vi, { ...heroCandidates(), ...leadersRoutes(), ...rotationRoutes(), ...extra.routes });
  // `null` is a real value the caller may pass (universe size unknown), distinct
  // from "not supplied" — so `??` would wrongly swallow it into the default.
  const universeSize = "universeSize" in extra ? (extra.universeSize ?? null) : 4812;
  return render(
    <Board
      market={extra.market ?? "IDX"}
      universeSize={universeSize}
      navigate={extra.navigate ?? noop}
    />,
  );
}

// ── The hero cut (spec §5.1) ─────────────────────────────────────────────────

describe("Board — the hero cut", () => {
  it("is the ≥3.5★ subset of detected, capped at 4, sorted stars desc then stopw asc", async () => {
    renderBoard();
    // Wait for the hero panel to paint.
    await screen.findByRole("article", { name: "AAA" });

    const cards = screen.getAllByRole("article");
    expect(cards.map((c) => c.getAttribute("aria-label"))).toEqual(["AAA", "DDD", "EEE", "BBB"]);
    // CCC dropped by the cap of 4; FFF dropped by the ≥3.5 bar.
    expect(screen.queryByRole("article", { name: "CCC" })).not.toBeInTheDocument();
    expect(screen.queryByRole("article", { name: "FFF" })).not.toBeInTheDocument();
  });

  it("renders a two-card night as two cards and no filler — no placeholder slots", async () => {
    renderBoard({
      routes: {
        candidates: (m) =>
          candidatesResponse({
            market: m,
            candidates: [
              candidate({ symbol: "AAA", score: 4.0 }),
              candidate({ symbol: "BBB", score: 3.5 }),
              candidate({ symbol: "LOW", score: 2.0 }),
            ],
          }),
      },
    });
    await screen.findByRole("article", { name: "AAA" });

    expect(screen.getAllByRole("article")).toHaveLength(2);
    // No "empty slot" / "more slots" placeholder copy anywhere.
    expect(screen.queryByText(/more slot/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/nothing else cleared/i)).not.toBeInTheDocument();
  });

  it("states a quiet night as a fact, without placeholder slots, when nothing clears the bar", async () => {
    renderBoard({
      routes: {
        candidates: (m) =>
          candidatesResponse({
            market: m,
            candidates: [candidate({ symbol: "LOW", score: 2.5 })],
          }),
      },
    });
    // Funnel still paints (the detected count is the night's fact).
    expect(await screen.findByText(/1 detected/)).toBeInTheDocument();
    expect(screen.queryAllByRole("article")).toHaveLength(0);
    expect(screen.getByText(/cleared the ≥3\.5★ bar/i)).toBeInTheDocument();
  });
});

// ── The funnel (spec §5.1) ───────────────────────────────────────────────────

describe("Board — the universe funnel", () => {
  it("renders as one line under the hero header: listed · detected", async () => {
    renderBoard({ universeSize: 4812 });
    await screen.findByRole("article", { name: "AAA" });
    // listed from the run's universe_size, detected from the candidate count.
    expect(screen.getByText(/4,812 listed · 6 detected/)).toBeInTheDocument();
  });

  it("shows detected alone when the universe size is unknown", async () => {
    renderBoard({ universeSize: null });
    await screen.findByRole("article", { name: "AAA" });
    expect(screen.getByText(/6 detected/)).toBeInTheDocument();
    expect(screen.queryByText(/listed/)).not.toBeInTheDocument();
  });
});

// ── NEW as a badge, never a panel (spec §5.1) ────────────────────────────────

describe("Board — NEW is a badge, never a panel", () => {
  it("shows NEW on the card whose name is new tonight, and has no 'New tonight' panel", async () => {
    renderBoard();
    const aaa = await screen.findByRole("article", { name: "AAA" });
    expect(within(aaa).getByText("NEW")).toBeInTheDocument();
    // A non-new card carries no badge.
    const bbb = screen.getByRole("article", { name: "BBB" });
    expect(within(bbb).queryByText("NEW")).not.toBeInTheDocument();
    // No standalone "New tonight" rail panel exists.
    expect(screen.queryByRole("heading", { name: /new tonight/i })).not.toBeInTheDocument();
  });
});

// ── The leaders strip (spec §5.1) ────────────────────────────────────────────

describe("Board — the leaders strip", () => {
  it("is 1-month, columns ticker · sector · 1M · breadth, heroes included", async () => {
    renderBoard();
    const strip = await screen.findByRole("table");
    // Heroes included, no dedup: AAA (a hero) sits in the strip too.
    expect(within(strip).getByRole("button", { name: "AAA" })).toBeInTheDocument();
    expect(within(strip).getByRole("button", { name: "ZZZ" })).toBeInTheDocument();
    // The 1M return and k/5 breadth columns.
    expect(within(strip).getByText("+42.0%")).toBeInTheDocument();
    expect(within(strip).getByText("4/5")).toBeInTheDocument();
  });

  it("states the fact when no 1-month board is ranked yet", async () => {
    renderBoard({
      routes: { leaders: (m) => leadersResponse({ market: m, boards: [leader({ lookback: "1w" })] }) },
    });
    await screen.findByRole("article", { name: "AAA" });
    expect(screen.getByText(/no 1-month leaders/i)).toBeInTheDocument();
  });
});

// ── The rotation rail (spec §5.1/§8.4) ───────────────────────────────────────

describe("Board — the rotation rail", () => {
  it("renders the top-5 sectors as diverging bars with sign legible in text", async () => {
    renderBoard();
    await screen.findByRole("heading", { name: "Where money is rotating" });
    // Sign is carried in the value text, not in hue alone.
    expect(screen.getByText("+30pp")).toBeInTheDocument();
    expect(screen.getByText("−10pp")).toBeInTheDocument(); // −10pp, U+2212
  });

  it("clicks a sector bar through to that sector's detail", async () => {
    const navigate = vi.fn();
    renderBoard({ navigate });
    const bar = await screen.findByRole("button", { name: /Energy/ });
    act(() => bar.click());
    expect(navigate).toHaveBeenCalledWith({ tab: "sectors", sector: "Energy" });
  });
});

// ── The cross-screen jumps (spec §5.6) ───────────────────────────────────────

describe("Board — the cross-screen jumps", () => {
  it("jumps to Setups on 'view charts →' and Leaders on 'See all →'", async () => {
    const navigate = vi.fn();
    renderBoard({ navigate });
    await screen.findByRole("article", { name: "AAA" });

    act(() => screen.getByRole("button", { name: /view charts/i }).click());
    expect(navigate).toHaveBeenCalledWith({ tab: "setups" });

    act(() => screen.getByRole("button", { name: /see all/i }).click());
    expect(navigate).toHaveBeenCalledWith({ tab: "leaders" });
  });
});

// ── The chart sheet and the rail collapse (spec §5.1/§6) ─────────────────────

describe("Board — opening the sheet collapses the rail", () => {
  it("collapses the rail while the sheet is open and keeps the hero grid", async () => {
    renderBoard();
    // AAA appears as both a hero card and a strip row (heroes included), so scope
    // the click to the hero card's ticker button.
    const aaa = await screen.findByRole("article", { name: "AAA" });
    const ticker = within(aaa).getByRole("button", { name: "AAA" });
    // The rail is present before the open.
    expect(screen.getByRole("heading", { name: "Where money is rotating" })).toBeInTheDocument();

    act(() => ticker.click());

    // The sheet opens (its heading is the symbol) and the rail collapses.
    await screen.findByRole("heading", { name: "AAA", level: 2 });
    expect(
      screen.queryByRole("heading", { name: "Where money is rotating" }),
    ).not.toBeInTheDocument();
    // The hero grid keeps its cards (its columns) — it did not reflow away.
    expect(screen.getByRole("article", { name: "AAA" })).toBeInTheDocument();
  });

  it("toggles the sheet closed on a re-click of the same ticker", async () => {
    renderBoard();
    const aaa = await screen.findByRole("article", { name: "AAA" });
    const ticker = within(aaa).getByRole("button", { name: "AAA" });

    act(() => ticker.click());
    await screen.findByRole("heading", { name: "AAA", level: 2 });

    act(() => within(aaa).getByRole("button", { name: "AAA" }).click());
    // Rail is back; the sheet is gone.
    await screen.findByRole("heading", { name: "Where money is rotating" });
  });

  it("closes the sheet on a market switch (the entity-state reset, spec §3.4)", async () => {
    const { rerender } = renderBoard({ market: "IDX" });
    const aaa = await screen.findByRole("article", { name: "AAA" });
    const ticker = within(aaa).getByRole("button", { name: "AAA" });
    act(() => ticker.click());
    await screen.findByRole("heading", { name: "AAA", level: 2 });

    rerender(<Board market="US" universeSize={4812} navigate={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Where money is rotating" })).toBeInTheDocument(),
    );
  });
});

// ── Accessibility (spec §8) ──────────────────────────────────────────────────

describe("Board — accessibility", () => {
  it("renders with no axe violations", async () => {
    const { container } = renderBoard();
    await screen.findByRole("article", { name: "AAA" });
    const results = await axe(container, { rules: { "color-contrast": { enabled: false } } });
    expect(results).toHaveNoViolations();
  });
});
