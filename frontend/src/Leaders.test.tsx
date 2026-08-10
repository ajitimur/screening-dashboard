import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import Leaders from "./Leaders";
import { _clearChartCache } from "./chartCache";
import { leader, leaderRow, leadersResponse } from "./api/fixtures";
import { stubFetch, type ApiRoutes } from "./api/fixtures";
import type { LeadersResponse } from "./api/client";

// The charting seam is mocked — the grid renders MiniCharts and the sheet a Chart;
// jsdom has no canvas. Record series, never pixels (spec §6).
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

// jsdom has no IntersectionObserver; the grid's minis observe, so a no-op stub is
// enough (these tests never assert a mini painted, only that the cards render).
class NoopIO {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal("IntersectionObserver", NoopIO as unknown as typeof IntersectionObserver);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  _clearChartCache();
});

const lr = (symbol: string, over: Partial<ReturnType<typeof leaderRow>> = {}) =>
  leaderRow({ symbol, ...over });
const board = (lookback: string, rows: ReturnType<typeof leaderRow>[]) =>
  leader({ lookback, rows });

// A market's leaderboards: 1w and 1m carry distinct row sets so a lookback switch
// is observable; the other three carry one row each. `surge` is left at the
// fixture default of `true` on every row precisely so a passing suite proves the
// screen never renders it.
function body(market = "IDX"): LeadersResponse {
  return leadersResponse({
    market,
    session: "2026-08-04",
    boards: [
      board("1w", [
        lr("WIN", { raw_return: 0.42, breadth: 3, is_new: true, adr: 0.05, sector: "Technology", dollar_volume: 5_000_000 }),
        lr("MEG", { raw_return: 0.6, breadth: 1, is_new: false, adr: 0.02, sector: "Energy", dollar_volume: 1_000_000 }),
        lr("LOW", { raw_return: 0.1, breadth: 5, is_new: false, adr: 0.08, sector: "Healthcare", dollar_volume: 9_000_000 }),
      ]),
      board("1m", [
        lr("WIN", { raw_return: 0.3, breadth: 2, is_new: false, adr: 0.05, sector: "Technology", dollar_volume: 5_000_000 }),
        lr("ALT", { raw_return: 0.55, breadth: 4, is_new: true, adr: 0.06, sector: "Industrials", dollar_volume: 3_000_000 }),
      ]),
      board("3m", [lr("C3", { raw_return: 0.2 })]),
      board("6m", [lr("C6", { raw_return: 0.2 })]),
      board("12m", [lr("C12", { raw_return: 0.2 })]),
    ],
  });
}

function renderLeaders(routes: ApiRoutes = { leaders: (m) => body(m) }, market = "IDX") {
  stubFetch(vi, routes);
  return render(<Leaders market={market} />);
}

describe("the Leaders screen", () => {
  it("renders ONE table — v1's five-up is retired (spec §5.3)", async () => {
    renderLeaders();
    await screen.findByRole("table");
    expect(screen.getAllByRole("table")).toHaveLength(1);
  });

  it("defaults to return descending, with aria-sort on the return header (spec §5.3)", async () => {
    renderLeaders();
    const table = await screen.findByRole("table");
    // MEG (0.02 ADR) is hidden by the default-ON toggle; WIN (0.42) leads LOW (0.10).
    const rows = within(table).getAllByRole("row").slice(1); // drop the header row
    expect(within(rows[0]).getByRole("button", { name: "WIN" })).toBeInTheDocument();
    expect(within(rows[1]).getByRole("button", { name: "LOW" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /Return/ })).toHaveAttribute("aria-sort", "descending");
  });

  it("sorts by k/5 when its header button is pressed — one shared sort (spec §5.3)", async () => {
    renderLeaders();
    const table = await screen.findByRole("table");
    act(() => within(table).getByRole("button", { name: /k\/5/ }).click());

    await waitFor(() => {
      const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
      // breadth desc: LOW (5) now leads WIN (3).
      expect(within(rows[0]).getByRole("button", { name: "LOW" })).toBeInTheDocument();
    });
    expect(screen.getByRole("columnheader", { name: /k\/5/ })).toHaveAttribute("aria-sort", "descending");
    // The prior key relinquishes its sort — only one column is active at a time.
    expect(screen.getByRole("columnheader", { name: /Return/ })).toHaveAttribute("aria-sort", "none");
  });

  it("exposes return, k/5, ADR and $vol as sortable headers, and nothing else (spec §5.3)", async () => {
    renderLeaders();
    await screen.findByRole("table");
    for (const name of [/Return/, /k\/5/, /ADR/, /\$ Vol/]) {
      expect(within(screen.getByRole("columnheader", { name })).getByRole("button")).toBeInTheDocument();
    }
    // No tier band column and no cutoff strip in phase 1 (spec §5.3).
    expect(screen.queryByRole("columnheader", { name: /tier|band|cutoff/i })).not.toBeInTheDocument();
  });

  it("switches the row set when the lookback control changes (spec §5.3)", async () => {
    renderLeaders();
    await screen.findByRole("button", { name: "WIN" });
    // 1w carries LOW; 1m carries ALT and not LOW.
    expect(screen.getByRole("button", { name: "LOW" })).toBeInTheDocument();

    act(() => screen.getByRole("radio", { name: "1M" }).click());

    expect(await screen.findByRole("button", { name: "ALT" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "LOW" })).not.toBeInTheDocument();
  });

  it("scopes NEW to the active lookback and names it apart from newly-detected (spec §2.4/§5.3)", async () => {
    renderLeaders();
    const table = await screen.findByRole("table");
    const win = within(table).getByRole("row", { name: /WIN/ });
    const badge = within(win).getByText("NEW");
    // Named distinctly: a ranking move, not the newly-detected sense on Setups.
    expect(badge).toHaveAttribute("title", expect.stringMatching(/ranking move/i));

    // On the 1m board WIN is not new — the badge is scoped to the lookback.
    act(() => screen.getByRole("radio", { name: "1M" }).click());
    await screen.findByRole("button", { name: "ALT" });
    const winRow = within(screen.getByRole("table")).getByRole("row", { name: /WIN/ });
    expect(within(winRow).queryByText("NEW")).not.toBeInTheDocument();
  });

  it("never renders the surge flag, even though the row carries it (spec §5.3)", async () => {
    renderLeaders();
    await screen.findByRole("table");
    expect(screen.queryByText(/↑30/)).not.toBeInTheDocument();
    expect(screen.queryByText(/surge/i)).not.toBeInTheDocument();
  });

  it("defaults the hide-sub-4%-ADR toggle ON (spec §5.3)", async () => {
    renderLeaders();
    const toggle = await screen.findByRole("checkbox", { name: /ADR/i });
    expect(toggle).toBeChecked();
    // MEG (0.02 ADR) is hidden at the default.
    expect(screen.queryByRole("button", { name: "MEG" })).not.toBeInTheDocument();
    act(() => toggle.click());
    expect(await screen.findByRole("button", { name: "MEG" })).toBeInTheDocument();
  });

  it("a zero-row table reads as filter-inflicted, with the toggle chip and a clear action (spec §7.4)", async () => {
    // Every 1w name is sub-4% ADR, so the default-ON toggle empties the table the
    // user never touched.
    const allSub4: LeadersResponse = leadersResponse({
      market: "IDX",
      session: "2026-08-04",
      boards: [
        board("1w", [lr("AAA", { adr: 0.01, raw_return: 0.2 }), lr("BBB", { adr: 0.03, raw_return: 0.1 })]),
        board("1m", [lr("C1", { raw_return: 0.2 })]),
        board("3m", [lr("C3", { raw_return: 0.2 })]),
        board("6m", [lr("C6", { raw_return: 0.2 })]),
        board("12m", [lr("C12", { raw_return: 0.2 })]),
      ],
    });
    renderLeaders({ leaders: () => allSub4 });

    // Not an error, not a night state: a filter-inflicted empty carrying its chip.
    expect(await screen.findByText("ADR ≥ 4%")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    const clear = screen.getByRole("button", { name: /clear filter/i });
    act(() => clear.click());
    // Clearing recovers the rows.
    expect(await screen.findByRole("button", { name: "AAA" })).toBeInTheDocument();
  });

  it("counts AFTER filtering in the trailing summary (spec §5.3)", async () => {
    renderLeaders();
    await screen.findByRole("table");
    // Two visible (MEG hidden), ranked by return.
    expect(screen.getByText(/2 names · ranked by return/)).toBeInTheDocument();

    // Narrow to WIN by ticker search: the tally drops to one, live.
    const search = screen.getByRole("searchbox", { name: /ticker/i });
    fireEvent.change(search, { target: { value: "WIN" } });
    expect(await screen.findByText(/1 name · ranked by return/)).toBeInTheDocument();
  });

  it("the table/grid toggle is a radiogroup sharing the same rows (spec §5.3)", async () => {
    renderLeaders();
    await screen.findByRole("table");
    expect(screen.getByRole("radiogroup", { name: "View" })).toBeInTheDocument();

    act(() => screen.getByRole("radio", { name: "Grid" }).click());

    // The table is gone; the grid shows the SAME filtered rows (MEG still hidden).
    await waitFor(() => expect(screen.queryByRole("table")).not.toBeInTheDocument());
    const grid = screen.getByRole("list", { name: /leaders grid/i });
    expect(within(grid).getByRole("button", { name: "WIN" })).toBeInTheDocument();
    expect(within(grid).getByRole("button", { name: "LOW" })).toBeInTheDocument();
    expect(within(grid).queryByRole("button", { name: "MEG" })).not.toBeInTheDocument();
  });

  it("opens the chart sheet from a ticker button (spec §6.1)", async () => {
    renderLeaders();
    const win = await screen.findByRole("button", { name: "WIN" });
    act(() => win.click());
    // The sheet's heading names the opened symbol.
    expect(await screen.findByRole("heading", { level: 2, name: "WIN" })).toBeInTheDocument();
  });

  it("a genuinely empty board is a night state, not a filter one (spec §7.4)", async () => {
    const empty: LeadersResponse = leadersResponse({
      market: "IDX",
      session: "2026-08-04",
      boards: [
        board("1w", []),
        board("1m", [lr("C1")]),
        board("3m", [lr("C3")]),
        board("6m", [lr("C6")]),
        board("12m", [lr("C12")]),
      ],
    });
    renderLeaders({ leaders: () => empty });
    expect(await screen.findByText(/No leaders for IDX tonight/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /clear filter/i })).not.toBeInTheDocument();
  });

  it("resets the open sheet on a market switch (entity state, spec §3.4)", async () => {
    const { rerender } = renderLeaders();
    const win = await screen.findByRole("button", { name: "WIN" });
    act(() => win.click());
    await screen.findByRole("heading", { level: 2, name: "WIN" });

    rerender(<Leaders market="US" />);
    await waitFor(() => expect(screen.queryByRole("heading", { level: 2, name: "WIN" })).not.toBeInTheDocument());
  });

  it("renders with no axe violations (spec §8.10)", async () => {
    // In the app the screen sits inside the shell's <main> landmark; mirror that
    // here so axe's `region` rule sees the content contained, as it always is.
    stubFetch(vi, { leaders: (m) => body(m) });
    render(
      <main>
        <Leaders market="IDX" />
      </main>,
    );
    await screen.findByRole("table");
    const results = await axe(document.body, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results).toHaveNoViolations();
  });
});
