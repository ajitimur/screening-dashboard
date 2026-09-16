import type { IndustryStrength, SectorStrength, SectorsResponse } from "./api/client";

// ── Reading rotation off decile share (spec §5.4) ────────────────────────────
//
// The Sectors payload carries, per sector, the share of its members in the
// universe's top momentum decile at five lookbacks. A trader reads three things
// off those five numbers: is the sector leading NOW, WAS it leading, and which
// way is that moving. This module names that read so the screen can show a
// state instead of asking the reader to redo the arithmetic every morning.
//
// A sector with no edge has one tenth of its members in the top decile, so 10%
// is the baseline every share is read against. The cut lines below were set by
// eye against the September 2026 US and IDX boards (the prototype on branch
// `worktree-prototype+sectors-ui` shows them against live data) — they are a
// reading convention, not a fitted model, and are meant to be revisited.

export const BASELINE = 0.1;

// A share at or above this reads as "leading" at that lookback.
const LEAD = 0.16;
// The 6m share at or above this reads as "was established".
const ESTABLISHED = 0.18;
// A 1w share this far under the 6m share reads as leadership draining out.
const FADE_GAP = 0.04;

export type RotationState = "Emerging" | "Leading" | "Fading" | "Quiet" | "Thin";

// The reading order: what is arriving, what persists, what is leaving, then
// the sectors with nothing to say. `Thin` is the k≥2 eligibility guard from the
// backend (S4/S8): fewer than two top-decile names this week is no information,
// so a thin sector always sorts below every eligible one.
export const STATE_ORDER: readonly RotationState[] = [
  "Emerging",
  "Leading",
  "Fading",
  "Quiet",
  "Thin",
];

export const STATE_HINT: Record<RotationState, string> = {
  Emerging: "Leaders are new: many this week, few six months ago. Money is rotating in.",
  Leading: "Leaders this week and six months ago. A persistent leader.",
  Fading: "Led six months ago, fewer leaders this week. Money is rotating out.",
  Quiet: "Near the one-in-ten baseline at every lookback. Nothing to trade.",
  Thin: "Fewer than two names in the top decile this week. No information.",
};

export function rotationState(s: SectorStrength): RotationState {
  if (!s.rotation_eligible) return "Thin";
  const now = Math.max(s.shares["1w"] ?? 0, s.shares["1m"] ?? 0);
  const then = s.shares["6m"] ?? 0;
  const leadingNow = now >= LEAD;
  const established = then >= ESTABLISHED;
  if (leadingNow && !established) return "Emerging";
  // Fading is checked before Leading: a sector can still clear the lead bar on
  // its 1m share while its 1w share is already draining under the 6m share.
  if (established && (s.shares["1w"] ?? 0) < then - FADE_GAP) return "Fading";
  if (leadingNow && established) return "Leading";
  return "Quiet";
}

// Sectors in reading order: by state, then by shape differential within a state.
export function orderByRotation(sectors: readonly SectorStrength[]): SectorStrength[] {
  return [...sectors].sort((a, b) => {
    const sa = STATE_ORDER.indexOf(rotationState(a));
    const sb = STATE_ORDER.indexOf(rotationState(b));
    if (sa !== sb) return sa - sb;
    return b.shape_differential - a.shape_differential;
  });
}

// An industry "leads" by the same bar a sector does. Grouped by parent sector so
// the screen can say whether a sector's lead is broad or one industry's.
export function leadingIndustriesBySector(
  industries: readonly IndustryStrength[],
): Map<string, IndustryStrength[]> {
  const out = new Map<string, IndustryStrength[]>();
  for (const i of industries) {
    if ((i.shares["1w"] ?? 0) < LEAD && (i.shares["1m"] ?? 0) < LEAD) continue;
    out.set(i.sector, [...(out.get(i.sector) ?? []), i]);
  }
  for (const xs of out.values()) xs.sort((a, b) => b.shape_differential - a.shape_differential);
  return out;
}

// The one sentence to read before the open. Names only the states that carry
// information; an all-quiet board says so plainly.
export function summarise(data: Pick<SectorsResponse, "sectors">): string {
  const by = (st: RotationState) =>
    data.sectors.filter((s) => rotationState(s) === st).map((s) => s.sector);
  const list = (xs: string[]) =>
    xs.length <= 2 ? xs.join(" and ") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`;
  const parts: string[] = [];
  const emerging = by("Emerging");
  const leading = by("Leading");
  const fading = by("Fading");
  if (emerging.length)
    parts.push(`${list(emerging)} ${emerging.length === 1 ? "is" : "are"} gaining leaders`);
  if (leading.length)
    parts.push(`${list(leading)} ${leading.length === 1 ? "keeps" : "keep"} leading`);
  if (fading.length) parts.push(`${list(fading)} ${fading.length === 1 ? "is" : "are"} fading`);
  if (!parts.length) return "No sector stands out from the baseline tonight.";
  return `${parts.join(". ")}.`;
}

// The sector colour scale the sheet carries as `--color-sector-*` (spec §3.2).
// Real Estate has no token on the scale and falls back to the faint fill.
const SECTOR_TOKEN: Record<string, string> = {
  Technology: "technology",
  "Financial Services": "financials",
  Industrials: "industrials",
  "Communication Services": "communication",
  "Consumer Cyclical": "consumer-cyclical",
  Healthcare: "healthcare",
  Utilities: "utilities",
  Energy: "energy",
  "Basic Materials": "materials",
  "Consumer Defensive": "defensive",
};

export function sectorColor(sector: string): string {
  const t = SECTOR_TOKEN[sector];
  return t ? `var(--color-sector-${t})` : "var(--color-fill-faint)";
}
