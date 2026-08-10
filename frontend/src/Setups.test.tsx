import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import Setups from "./Setups";
import { _clearChartCache } from "./chartCache";
import { candidate, candidatesResponse, stubFetch } from "./api/fixtures";
import type { components } from "./api/schema";

type Candidate = components["schemas"]["Candidate"];

// The charting seam mock (spec §6): the sheet and minis mount, we assert markup,
// never pixels.
vi.mock("lightweight-charts", () => ({
  createChart: () => ({
    addSeries: () => ({ setData: () => {}, createPriceLine: () => {} }),
    priceScale: () => ({ applyOptions: () => {} }),
    timeScale: () => ({ fitContent: () => {} }),
    remove: () => {},
  }),
  CandlestickSeries: "Candlestick",
  LineSeries: "Line",
  HistogramSeries: "Histogram",
}));

// jsdom has no IntersectionObserver; a no-op stub keeps the minis inert (they
// never scroll into view here) so the card renders its frame without a chart
// read — Setups' own markup is what these tests assert.
class NoopIO {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal("IntersectionObserver", NoopIO as unknown as typeof IntersectionObserver);
  _clearChartCache();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// A market's detected population, built off the typed fixture.
function candidatesRoute(candidates: Candidate[]) {
  return { candidates: (m: string) => candidatesResponse({ market: m, candidates }) };
}

describe("Setups — the card grid (spec §5.2)", () => {
  it("renders a card grid of articles — never a table", async () => {
    stubFetch(vi, candidatesRoute([candidate({ symbol: "AAA" }), candidate({ symbol: "BBB" })]));
    render(<Setups market="IDX" />);

    // Exactly the detected population as <article> cards…
    const cards = await screen.findAllByRole("article");
    expect(cards).toHaveLength(2);
    // …and NEVER a table (the whole point of this screen over Leaders).
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("renders exactly the detected population with no verdict or sort control", async () => {
    stubFetch(vi, candidatesRoute([candidate({ symbol: "AAA" }), candidate({ symbol: "BBB" })]));
    render(<Setups market="IDX" />);
    await screen.findAllByRole("article");

    // No verdict axis (an "All" unioning forming with detected is P2) and no
    // sort control — the star score IS the order (spec §5.2).
    expect(screen.queryByRole("combobox", { name: /verdict/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /sort/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/forming/i)).not.toBeInTheDocument();
  });

  it("names each card by its ticker and lists its stats as a description list", async () => {
    stubFetch(
      vi,
      candidatesRoute([
        candidate({
          symbol: "AAA",
          score: 4.5,
          new_tonight: true,
          sector: "Technology",
          trigger_price: 123.45,
          stop_price: 118.2,
          dist_adr: 1.28,
          stopw_adr: 1.53,
        }),
      ]),
    );
    render(<Setups market="IDX" />);

    const card = await screen.findByRole("article", { name: /AAA/ });
    // Header: ticker (a button — the keyboard door), stars, NEW, sector.
    expect(within(card).getByRole("button", { name: "AAA" })).toBeInTheDocument();
    expect(within(card).getByText("4.5★")).toBeInTheDocument();
    expect(within(card).getByText("NEW")).toBeInTheDocument();
    expect(within(card).getByText("Technology")).toBeInTheDocument();
    // The three stats are a description list, not sibling spans.
    expect(card.querySelector("dl")).toBeInTheDocument();
    expect(within(card).getByText("Trigger")).toBeInTheDocument();
    expect(within(card).getByText("123.45")).toBeInTheDocument();
    expect(within(card).getByText("118.20")).toBeInTheDocument();
    expect(within(card).getByText("1.28×")).toBeInTheDocument();
    // The mini chart frame and the labelled stop-width bar.
    expect(card.querySelector(".mini-chart")).toBeInTheDocument();
    expect(within(card).getByText(/stop 1\.53×ADR/)).toBeInTheDocument();
  });

  it("orders cards by stars descending, then stop-width ascending — no sort control", async () => {
    stubFetch(
      vi,
      candidatesRoute([
        candidate({ symbol: "LOW", score: 3.5, stopw_adr: 1.0 }),
        candidate({ symbol: "TIE_WIDE", score: 4.0, stopw_adr: 2.0 }),
        candidate({ symbol: "TIE_TIGHT", score: 4.0, stopw_adr: 1.0 }),
      ]),
    );
    render(<Setups market="IDX" />);

    const cards = await screen.findAllByRole("article");
    const order = cards.map((c) => c.getAttribute("aria-labelledby"));
    // 4.0 tight before 4.0 wide (tie-break), both before the 3.5.
    expect(order).toEqual(["setup-TIE_TIGHT", "setup-TIE_WIDE", "setup-LOW"]);
  });
});

describe("Setups — the two controls (spec §5.2 / §5.6)", () => {
  it("ticker search filters the population", async () => {
    stubFetch(vi, candidatesRoute([candidate({ symbol: "AAPL" }), candidate({ symbol: "MSFT" })]));
    render(<Setups market="IDX" />);
    await screen.findAllByRole("article");

    fireEvent.change(screen.getByRole("searchbox", { name: /ticker/i }), {
      target: { value: "aap" },
    });

    expect(screen.getByRole("article", { name: /AAPL/ })).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: /MSFT/ })).not.toBeInTheDocument();
    // The header count follows the filter (true filtered total).
    expect(screen.getByText(/1 setup ·/)).toBeInTheDocument();
  });

  it("the sector filter cuts to the chosen sector", async () => {
    stubFetch(
      vi,
      candidatesRoute([
        candidate({ symbol: "TEC", sector: "Technology" }),
        candidate({ symbol: "NRG", sector: "Energy" }),
      ]),
    );
    render(<Setups market="IDX" />);
    await screen.findAllByRole("article");

    fireEvent.change(screen.getByRole("combobox", { name: /sector/i }), {
      target: { value: "Energy" },
    });

    expect(screen.getByRole("article", { name: /NRG/ })).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: /TEC/ })).not.toBeInTheDocument();
  });

  it("a carried sector arrives as a dismissible chip that filters and clears", async () => {
    const onClearCarried = vi.fn();
    stubFetch(
      vi,
      candidatesRoute([
        candidate({ symbol: "TEC", sector: "Technology" }),
        candidate({ symbol: "NRG", sector: "Energy" }),
      ]),
    );
    render(<Setups market="IDX" carriedSector="Energy" onClearCarried={onClearCarried} />);

    // The carried filter is applied and shown as a chip, not the plain select.
    expect(await screen.findByText(/Sector: Energy/)).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /sector/i })).not.toBeInTheDocument();
    expect(screen.getByRole("article", { name: /NRG/ })).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: /TEC/ })).not.toBeInTheDocument();

    // Dismissing it clears the filter and tells the parent.
    act(() => screen.getByRole("button", { name: /clear sector filter/i }).click());
    expect(onClearCarried).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("article", { name: /TEC/ })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /sector/i })).toBeInTheDocument();
  });
});

describe("Setups — the render cap (spec §5.2)", () => {
  it("caps at 60 cards with a `show N more`, and the header keeps the true total", async () => {
    const many = Array.from({ length: 65 }, (_, i) =>
      candidate({ symbol: `S${String(i).padStart(3, "0")}`, score: 5 - i * 0.01 }),
    );
    stubFetch(vi, candidatesRoute(many));
    render(<Setups market="IDX" />);

    // 60 rendered…
    await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(60));
    // …but the header reports the TRUE filtered total of 65, not the 60 shown.
    expect(screen.getByText(/65 setups ·/)).toBeInTheDocument();

    // The button appends the next batch and names the remainder honestly.
    act(() => screen.getByRole("button", { name: /show 5 more/i }).click());
    expect(screen.getAllByRole("article")).toHaveLength(65);
    expect(screen.queryByRole("button", { name: /show .* more/i })).not.toBeInTheDocument();
  });
});

describe("Setups — the sheet and the reflow (spec §5.2 / §6)", () => {
  it("opening a card reflows the grid to two columns and outlines the clicked card", async () => {
    stubFetch(vi, candidatesRoute([candidate({ symbol: "AAA" }), candidate({ symbol: "BBB" })]));
    const { container } = render(<Setups market="IDX" />);
    await screen.findAllByRole("article");

    const grid = container.querySelector(".setups-grid")!;
    expect(grid).not.toHaveAttribute("data-sheet-open");

    act(() => screen.getByRole("button", { name: "AAA" }).click());

    // The sheet is open (portalled to <body>)…
    expect(await screen.findByRole("heading", { name: "AAA" })).toBeInTheDocument();
    // …the grid reflows to two columns…
    expect(grid).toHaveAttribute("data-sheet-open", "true");
    // …and the clicked card stays mounted with its active outline so it survives
    // the reflow.
    expect(screen.getByRole("article", { name: /AAA/ })).toHaveAttribute("data-active", "true");
    expect(screen.getByRole("article", { name: /BBB/ })).not.toHaveAttribute("data-active");
  });
});

describe("Setups — empties and a11y", () => {
  it("a thin night states the fact with no special copy and never apologises", async () => {
    stubFetch(vi, candidatesRoute([]));
    render(<Setups market="IDX" />);

    // The header count is the whole explanation (spec §5.2): 0 setups, and a
    // plain night-empty fact — not an error, not an apology.
    expect(await screen.findByText(/0 setups ·/)).toBeInTheDocument();
    const empty = screen.getByText(/cleared every gate/i);
    expect(empty.textContent).not.toMatch(/sorry|apolog|error|failed|unavailable/i);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders with no axe violations", async () => {
    stubFetch(
      vi,
      candidatesRoute([
        candidate({ symbol: "AAA", new_tonight: true }),
        candidate({ symbol: "BBB", sector: "Energy" }),
      ]),
    );
    render(
      <main>
        <Setups market="IDX" />
      </main>,
    );
    await screen.findAllByRole("article");

    const results = await axe(document.body, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results).toHaveNoViolations();
  });
});
