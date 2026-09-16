import { describe, expect, it } from "vitest";
import { industryStrength, sectorStrength } from "./api/fixtures";
import {
  leadingIndustriesBySector,
  orderByRotation,
  rotationState,
  sectorColor,
  summarise,
} from "./rotation";

// Shares at the five lookbacks, in order 1w 1m 3m 6m 12m.
function sector(name: string, shares: [number, number, number, number, number], extra = {}) {
  const [w1, m1, m3, m6, m12] = shares;
  return sectorStrength({
    sector: name,
    shares: { "1w": w1, "1m": m1, "3m": m3, "6m": m6, "12m": m12 },
    shape_differential: w1 - m6,
    ...extra,
  });
}

describe("rotationState — the four reads off decile share", () => {
  it("Emerging: leaders now, none six months ago (Energy, US, 2026-09-15)", () => {
    expect(rotationState(sector("Energy", [0.28, 0.41, 0.2, 0.11, 0.24]))).toBe("Emerging");
  });

  it("Leading: leaders now and six months ago (Technology, US)", () => {
    expect(rotationState(sector("Technology", [0.2, 0.11, 0.19, 0.2, 0.15]))).toBe("Leading");
  });

  it("Fading: led six months ago, this week's share has drained (Healthcare, US)", () => {
    expect(rotationState(sector("Healthcare", [0.15, 0.16, 0.25, 0.22, 0.26]))).toBe("Fading");
  });

  it("Fading wins over Leading when the 1m share still clears the bar", () => {
    // 1m = 0.20 would read as leading now; the 1w share under the 6m share says
    // the leadership is leaving, and that is the read that matters before the open.
    expect(rotationState(sector("X", [0.1, 0.2, 0.2, 0.2, 0.2]))).toBe("Fading");
  });

  it("Quiet: near baseline everywhere", () => {
    expect(rotationState(sector("Industrials", [0.04, 0.03, 0.03, 0.06, 0.04]))).toBe("Quiet");
  });

  it("Thin: the backend's k≥2 guard overrides every share", () => {
    expect(
      rotationState(sector("Utilities", [0.5, 0.5, 0.5, 0.0, 0.5], { rotation_eligible: false })),
    ).toBe("Thin");
  });
});

describe("orderByRotation", () => {
  it("orders by state, then by shape differential, with thin sectors last", () => {
    const ordered = orderByRotation([
      sector("Quiet", [0.05, 0.05, 0.05, 0.05, 0.05]),
      sector("Thin", [0.9, 0.9, 0.9, 0.0, 0.9], { rotation_eligible: false }),
      sector("Fading", [0.1, 0.1, 0.2, 0.3, 0.3]),
      sector("Emerging-small", [0.17, 0.1, 0.1, 0.05, 0.05]),
      sector("Emerging-big", [0.3, 0.3, 0.1, 0.05, 0.05]),
      sector("Leading", [0.25, 0.25, 0.25, 0.25, 0.25]),
    ]).map((s) => s.sector);
    expect(ordered).toEqual([
      "Emerging-big",
      "Emerging-small",
      "Leading",
      "Fading",
      "Quiet",
      "Thin",
    ]);
  });
});

describe("summarise — the sentence before the open", () => {
  it("names the informative states in reading order", () => {
    const sectors = [
      sector("Energy", [0.28, 0.41, 0.2, 0.11, 0.24]),
      sector("Communication Services", [0.17, 0.1, 0.04, 0.09, 0.08]),
      sector("Technology", [0.2, 0.11, 0.19, 0.2, 0.15]),
      sector("Healthcare", [0.15, 0.16, 0.25, 0.22, 0.26]),
      sector("Industrials", [0.04, 0.03, 0.03, 0.06, 0.04]),
    ];
    expect(summarise({ sectors })).toBe(
      "Energy and Communication Services are gaining leaders. Technology keeps leading. Healthcare is fading.",
    );
  });

  it("joins three or more with commas", () => {
    const sectors = [
      sector("A", [0.3, 0.3, 0.1, 0.05, 0.05]),
      sector("B", [0.3, 0.3, 0.1, 0.05, 0.05]),
      sector("C", [0.3, 0.3, 0.1, 0.05, 0.05]),
    ];
    expect(summarise({ sectors })).toBe("A, B and C are gaining leaders.");
  });

  it("says so when nothing stands out", () => {
    expect(summarise({ sectors: [sector("Q", [0.05, 0.05, 0.05, 0.05, 0.05])] })).toBe(
      "No sector stands out from the baseline tonight.",
    );
  });
});

describe("leadingIndustriesBySector", () => {
  it("keeps only industries that clear the lead bar, grouped under their sector", () => {
    const grouped = leadingIndustriesBySector([
      industryStrength({ industry: "E&P", sector: "Energy", shares: { "1w": 0.57, "1m": 0.5 }, shape_differential: 0.5 }),
      industryStrength({ industry: "Midstream", sector: "Energy", shares: { "1w": 0.33, "1m": 0.3 }, shape_differential: 0.1 }),
      industryStrength({ industry: "Coal", sector: "Energy", shares: { "1w": 0.0, "1m": 0.05 }, shape_differential: -0.05 }),
      industryStrength({ industry: "Biotech", sector: "Healthcare", shares: { "1w": 0.04, "1m": 0.2 }, shape_differential: 0 }),
    ]);
    expect(grouped.get("Energy")?.map((i) => i.industry)).toEqual(["E&P", "Midstream"]);
    // A 1m share alone clears the bar too.
    expect(grouped.get("Healthcare")?.map((i) => i.industry)).toEqual(["Biotech"]);
  });
});

describe("sectorColor", () => {
  it("maps a GECS label onto the sheet's sector token", () => {
    expect(sectorColor("Consumer Cyclical")).toBe("var(--color-sector-consumer-cyclical)");
  });
  it("falls back to the faint fill for a sector without a token", () => {
    expect(sectorColor("Real Estate")).toBe("var(--color-fill-faint)");
  });
});
