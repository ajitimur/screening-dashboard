import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import App from "./App";
import {
  industryStrength,
  regimeResponse,
  sectorDetailResponse,
  sectorMember,
  sectorStrength,
  sectorsResponse,
  stubFetch,
  type ApiRoutes,
} from "./api/fixtures";

// The chart canvas jsdom cannot draw; stub the library so the sheet mounts (the
// detail page renders a ChartSheet on ticker click).
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

beforeEach(() => {
  window.history.replaceState(null, "", "/?tab=sectors");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// Render the app already on the Sectors tab, waiting for the first band to paint.
async function renderSectors(routes: ApiRoutes = {}) {
  stubFetch(vi, routes);
  render(<App />);
  await screen.findByRole("heading", { level: 2, name: "Sectors" });
}

describe("Sectors — the two stacked bands (spec §5.4)", () => {
  it("renders both finished bands: the decile board and the market-wide industry board", async () => {
    await renderSectors({
      sectors: (m) =>
        sectorsResponse({
          market: m,
          industries: [industryStrength({ industry: "Semiconductors", sector: "Technology" })],
        }),
    });

    // Band 1 — the decile-share model, named for behaviour with a measure subtitle.
    expect(
      await screen.findByRole("region", { name: /where the leaders are clustered/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/share of the top momentum decile/i)).toBeInTheDocument();
    // Band 2 — the industry leadership board, market-wide.
    const industry = screen.getByRole("region", { name: /industry leadership/i });
    expect(within(industry).getByText("Semiconductors")).toBeInTheDocument();
  });

  it("keeps ineligible (thin) sectors visible, grouped below, and still clickable", async () => {
    await renderSectors({
      sectors: (m) =>
        sectorsResponse({
          market: m,
          sectors: [
            sectorStrength({ sector: "Technology", rotation_eligible: true, shape_differential: 0.4 }),
            // A thin, rotation-ineligible sector: it must stay visible and open.
            sectorStrength({ sector: "Utilities", rotation_eligible: false, shape_differential: 1.0 }),
          ],
        }),
    });

    const util = await screen.findByRole("button", { name: "Utilities" });
    const tech = screen.getByRole("button", { name: "Technology" });
    // Ineligible sinks below the eligible leaders despite the larger differential.
    const names = screen.getAllByRole("button", { name: /Technology|Utilities/ }).map((b) => b.textContent);
    expect(names.indexOf("Technology")).toBeLessThan(names.indexOf("Utilities"));
    // ...and it is a real, enabled <button>.
    expect(util).toBeEnabled();
    expect(tech).toBeEnabled();
  });

  it("carries the pullback note only on the decile band and only under a weaker regime", async () => {
    const routes: ApiRoutes = {
      regime: (m) => regimeResponse({ market: m, state: "FRIENDLY" }),
    };
    await renderSectors(routes);
    await screen.findByRole("region", { name: /where the leaders are clustered/i });
    expect(screen.queryByRole("note")).not.toBeInTheDocument();

    cleanup();
    await renderSectors({ regime: (m) => regimeResponse({ market: m, state: "HOSTILE" }) });
    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent(/relative strength through a decline/i);
    // The note sits inside the decile band, not the industry band.
    expect(within(screen.getByRole("region", { name: /where the leaders are clustered/i })).getByRole("note")).toBe(note);
  });
});

describe("Sectors — click-through into detail (spec §5.4/§5.5)", () => {
  it("drills a decile row into that sector and moves focus to the detail heading", async () => {
    await renderSectors({
      sectors: (m) => sectorsResponse({ market: m, sectors: [sectorStrength({ sector: "Energy" })] }),
      sectorDetail: (m, s) => sectorDetailResponse({ market: m, sector: s, members: [sectorMember({ symbol: "XOM" })] }),
    });

    act(() => screen.getByRole("button", { name: "Energy" }).click());

    const heading = await screen.findByRole("heading", { level: 2, name: "Energy" });
    await waitFor(() => expect(heading).toHaveFocus());
    expect(window.location.search).toBe("?tab=sectors&sector=Energy");
  });

  it("drills an industry row into its PARENT sector", async () => {
    await renderSectors({
      sectors: (m) =>
        sectorsResponse({
          market: m,
          industries: [industryStrength({ industry: "Biotechnology", sector: "Healthcare" })],
        }),
      sectorDetail: (m, s) => sectorDetailResponse({ market: m, sector: s }),
    });

    act(() => screen.getByRole("button", { name: "Biotechnology" }).click());

    await screen.findByRole("heading", { level: 2, name: "Healthcare" });
    expect(window.location.search).toBe("?tab=sectors&sector=Healthcare");
  });
});

describe("Sectors — the two back-doors (spec §5.5/§8.6)", () => {
  it("breadcrumb-back returns to the list and restores focus to the drilled row", async () => {
    window.history.replaceState(null, "", "/?tab=sectors");
    await renderSectors({
      sectors: (m) => sectorsResponse({ market: m, sectors: [sectorStrength({ sector: "Energy" })] }),
    });

    act(() => screen.getByRole("button", { name: "Energy" }).click());
    await screen.findByRole("heading", { level: 2, name: "Energy" });

    act(() => screen.getByRole("button", { name: "Sectors" }).click());

    // Back to the list, and the drilled row is refocused (a long list to re-find).
    const row = await screen.findByRole("button", { name: "Energy" });
    await waitFor(() => expect(row).toHaveFocus());
    expect(window.location.search).toBe("?tab=sectors");
  });

  it("clicking the lit Sectors tab returns to the list", async () => {
    window.history.replaceState(null, "", "/?tab=sectors&sector=Energy");
    stubFetch(vi);
    render(<App />);
    // We start on the detail (the Sectors tab is lit).
    await screen.findByRole("heading", { level: 2, name: "Energy" });
    expect(screen.getByRole("tab", { name: "Sectors" })).toHaveAttribute("aria-selected", "true");

    act(() => screen.getByRole("tab", { name: "Sectors" }).click());

    await screen.findByRole("heading", { level: 2, name: "Sectors" });
    expect(window.location.search).toBe("?tab=sectors");
  });
});

describe("Sector detail — the member table (spec §5.5)", () => {
  const detailRoutes: ApiRoutes = {
    sectorDetail: (m, s) =>
      sectorDetailResponse({
        market: m,
        sector: s,
        members: [
          sectorMember({
            symbol: "AAA",
            returns: { "1w": 0.1, "1m": 0.2, "3m": 0.05 },
            pctile_universe: { "1w": 0.9, "1m": 0.95, "3m": 0.6 },
            top_decile: { "1w": true, "1m": true, "3m": false },
          }),
        ],
      }),
  };

  async function openDetail(routes: ApiRoutes = detailRoutes) {
    window.history.replaceState(null, "", "/?tab=sectors&sector=Technology");
    stubFetch(vi, routes);
    render(<App />);
    await screen.findByRole("heading", { level: 2, name: "Technology" });
  }

  it("shows rank, ticker, the selected-lookback return, and a population-named percentile", async () => {
    await openDetail();
    const table = await screen.findByRole("table");
    // The population is named explicitly in the column head (spec §5.5).
    expect(within(table).getByRole("columnheader", { name: /percentile \(universe\)/i })).toBeInTheDocument();
    // Default lookback is 1m: return +20%, percentile 95, rank 1.
    const row = within(table).getByRole("button", { name: "AAA" }).closest("tr")!;
    expect(within(row).getByText("+20%")).toBeInTheDocument();
    expect(within(row).getByText("95")).toBeInTheDocument();
    expect(within(row).getByText("1")).toBeInTheDocument();
  });

  it("defaults the lookback to 1m and re-renders the decile badge on switch", async () => {
    await openDetail();
    const row = () => screen.getByRole("button", { name: "AAA" }).closest("tr")!;
    // 1m is top-decile → the badge is present.
    expect(within(row()).getByText(/top decile/i)).toBeInTheDocument();

    // Switch to 3M, where the name is NOT top-decile: the badge re-renders away.
    act(() => screen.getByRole("radio", { name: "3M" }).click());
    await waitFor(() => expect(within(row()).queryByText(/top decile/i)).not.toBeInTheDocument());
    // ...and the return follows the switch too (3m = +5%).
    expect(within(row()).getByText("+5%")).toBeInTheDocument();
  });

  it("has no ADR% or dollar-volume columns (dropped, not reserved)", async () => {
    await openDetail();
    const table = await screen.findByRole("table");
    expect(within(table).queryByRole("columnheader", { name: /ADR/i })).not.toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: /volume/i })).not.toBeInTheDocument();
  });

  it("the top-decile toggle filters to top-decile names for the selected lookback", async () => {
    await openDetail({
      sectorDetail: (m, s) =>
        sectorDetailResponse({
          market: m,
          sector: s,
          members: [
            sectorMember({ symbol: "TOP", returns: { "1m": 0.3 }, pctile_universe: { "1m": 0.99 }, top_decile: { "1m": true } }),
            sectorMember({ symbol: "MID", returns: { "1m": 0.1 }, pctile_universe: { "1m": 0.5 }, top_decile: { "1m": false } }),
          ],
        }),
    });
    expect(await screen.findByRole("button", { name: "MID" })).toBeInTheDocument();

    act(() => screen.getByRole("button", { name: /top decile only/i }).click());

    await waitFor(() => expect(screen.queryByRole("button", { name: "MID" })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "TOP" })).toBeInTheDocument();
  });

  it("opens the chart sheet when a ticker is clicked", async () => {
    await openDetail();
    act(() => screen.getByRole("button", { name: "AAA" }).click());
    // The sheet is portalled with the symbol as its heading (spec §6).
    expect(await screen.findByRole("heading", { level: 2, name: "AAA" })).toBeInTheDocument();
  });
});

describe("Sectors — accessibility (spec §8)", () => {
  it("the list has no axe violations", async () => {
    await renderSectors({
      sectors: (m) =>
        sectorsResponse({ market: m, industries: [industryStrength()] }),
    });
    await screen.findByRole("region", { name: /where the leaders are clustered/i });
    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("the detail page has no axe violations", async () => {
    window.history.replaceState(null, "", "/?tab=sectors&sector=Technology");
    stubFetch(vi, {
      sectorDetail: (m, s) => sectorDetailResponse({ market: m, sector: s, members: [sectorMember()] }),
    });
    render(<App />);
    await screen.findByRole("table");
    expect(await axe(document.body)).toHaveNoViolations();
  });
});
