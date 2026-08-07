import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import SectorTable from "./SectorTable";
import type { SectorStrength, SectorsResponse } from "./api/client";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const LOOKBACKS = ["1w", "1m", "3m", "6m", "12m"];
const SECTORS = [
  "Basic Materials", "Communication Services", "Consumer Cyclical",
  "Consumer Defensive", "Energy", "Financial Services", "Healthcare",
  "Industrials", "Real Estate", "Technology", "Utilities",
];

function sector(name: string, over: Partial<SectorStrength> = {}): SectorStrength {
  return {
    sector: name,
    members: 0,
    shares: Object.fromEntries(LOOKBACKS.map((lb) => [lb, 0])),
    decile_counts: Object.fromEntries(LOOKBACKS.map((lb) => [lb, 0])),
    shape_differential: 0,
    temporal_delta: null,
    rotation_eligible: false,
    delta_low_confidence: true,
    ...over,
  };
}

function board(over: Partial<SectorsResponse> = {}): SectorsResponse {
  return {
    market: "IDX",
    session: "2026-08-04",
    taxonomy: "GECS",
    sectors: SECTORS.map((s) => sector(s)),
    industries: [],
    ...over,
  };
}

function mockSectors(data: SectorsResponse) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, json: async () => data }) as Response),
  );
}

describe("the sector board", () => {
  it("renders all 11 sectors even at 0% on every lookback", async () => {
    mockSectors(board());
    render(<SectorTable market="IDX" />);
    for (const s of SECTORS) {
      expect(await screen.findByRole("rowheader", { name: s })).toBeInTheDocument();
    }
  });

  it("carries k/n on every sector row", async () => {
    mockSectors(
      board({
        sectors: [
          sector("Energy", {
            members: 9,
            shares: { ...zero(), "1w": 2 / 9 },
            decile_counts: { ...zero(), "1w": 2 },
            rotation_eligible: true,
          }),
          ...SECTORS.filter((s) => s !== "Energy").map((s) => sector(s)),
        ],
      }),
    );
    render(<SectorTable market="IDX" />);
    const energy = (await screen.findByRole("rowheader", { name: "Energy" }))
      .closest("tr")!;
    expect(within(energy).getByText("2/9")).toBeInTheDocument();
  });

  it("sorts a sub-two-member sector into the ineligible group below the leaders", async () => {
    // Utilities has the largest shape differential but rests on ONE name, so it
    // must never top the board; Technology (two names) leads.
    mockSectors(
      board({
        sectors: [
          sector("Utilities", {
            members: 10, shape_differential: 1.0, rotation_eligible: false,
            decile_counts: { ...zero(), "1w": 1 },
          }),
          sector("Technology", {
            members: 14, shape_differential: 0.4, rotation_eligible: true,
            decile_counts: { ...zero(), "1w": 2 },
          }),
          ...SECTORS.filter((s) => !["Utilities", "Technology"].includes(s))
            .map((s) => sector(s)),
        ],
      }),
    );
    render(<SectorTable market="IDX" />);
    await screen.findByRole("rowheader", { name: "Technology" });
    const rowNames = screen
      .getAllByRole("rowheader")
      .map((el) => el.textContent);
    expect(rowNames.indexOf("Technology")).toBeLessThan(rowNames.indexOf("Utilities"));
    const utilRow = screen.getByRole("rowheader", { name: "Utilities" }).closest("tr")!;
    expect(utilRow.className).toContain("rotation-ineligible");
  });

  it("greys and marks the Δ20d cell when it rests on fewer than two names", async () => {
    mockSectors(
      board({
        sectors: [
          sector("Energy", {
            members: 5, temporal_delta: 0.2, delta_low_confidence: true,
            rotation_eligible: true,
          }),
          ...SECTORS.filter((s) => s !== "Energy").map((s) => sector(s)),
        ],
      }),
    );
    render(<SectorTable market="IDX" />);
    const energy = (await screen.findByRole("rowheader", { name: "Energy" }))
      .closest("tr")!;
    const deltaCell = energy.querySelector(".temporal")!;
    expect(deltaCell.className).toContain("low-confidence");
    expect(within(energy).getByTitle(/fewer than two/i)).toBeInTheDocument();
  });

  it("makes both rotation columns sortable, shape the default", async () => {
    mockSectors(
      board({
        sectors: [
          sector("Energy", {
            members: 4, rotation_eligible: true,
            shape_differential: 0.1, temporal_delta: 0.5,
          }),
          sector("Technology", {
            members: 4, rotation_eligible: true,
            shape_differential: 0.4, temporal_delta: -0.2,
          }),
          ...SECTORS.filter((s) => !["Energy", "Technology"].includes(s))
            .map((s) => sector(s)),
        ],
      }),
    );
    render(<SectorTable market="IDX" />);
    await screen.findByRole("rowheader", { name: "Technology" });
    // Default sort is the shape differential: Technology (0.4) above Energy (0.1).
    let names = screen.getAllByRole("rowheader").map((e) => e.textContent);
    expect(names.indexOf("Technology")).toBeLessThan(names.indexOf("Energy"));
    // Sort by Δ20d: Energy (+0.5) rises above Technology (−0.2).
    act(() => screen.getByRole("button", { name: /Δ20d/ }).click());
    await waitFor(() => {
      names = screen.getAllByRole("rowheader").map((e) => e.textContent);
      expect(names.indexOf("Energy")).toBeLessThan(names.indexOf("Technology"));
    });
  });

  it("ranks only industries with 10 or more members", async () => {
    mockSectors(
      board({
        industries: [
          {
            industry: "Biotechnology",
            sector: "Healthcare",
            members: 10,
            shares: { ...zero(), "1w": 0.3 },
            decile_counts: { ...zero(), "1w": 3 },
            shape_differential: 0.3,
          },
        ],
      }),
    );
    render(<SectorTable market="IDX" />);
    expect(await screen.findByRole("rowheader", { name: "Biotechnology" })).toBeInTheDocument();
  });

  it("carries the pullback note only under CHOPPY or HOSTILE", async () => {
    mockSectors(board());
    const { rerender } = render(<SectorTable market="IDX" regime="FRIENDLY" />);
    await screen.findByRole("rowheader", { name: "Energy" });
    expect(screen.queryByRole("note")).not.toBeInTheDocument();

    rerender(<SectorTable market="IDX" regime="HOSTILE" />);
    await waitFor(() =>
      expect(screen.getByRole("note")).toHaveTextContent(/relative strength through a decline/i),
    );
  });
});

function zero(): Record<string, number> {
  return Object.fromEntries(LOOKBACKS.map((lb) => [lb, 0]));
}
