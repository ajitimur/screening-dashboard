// PROTOTYPE — throwaway. Shared derivations the three Sectors variants read.
//
// Question: what should the Sectors list look like so a trader can read sector
// leadership and rotation at a glance, without reconstructing the arithmetic?
// Four variants on the existing Sectors tab, switchable via `?variant=`:
//   current · A briefing lanes · B annotated ledger · C rotation map

import type {
  IndustryStrength,
  SectorStrength,
  SectorsResponse,
} from "../api/client";

// A sector with no edge has one tenth of its members in the top decile.
export const BASELINE = 0.1;
// "Leading" = clearly above baseline; "established" = the 6m share was.
const LEAD = 0.16;
const ESTABLISHED = 0.18;
const FADE_GAP = 0.04;

export type RotationState = "Emerging" | "Leading" | "Fading" | "Quiet" | "Thin";

export const STATE_ORDER: RotationState[] = [
  "Emerging",
  "Leading",
  "Fading",
  "Quiet",
  "Thin",
];

export const STATE_HINT: Record<RotationState, string> = {
  Emerging:
    "Leaders are new: high this week, low six months ago. Money is rotating in.",
  Leading: "Leaders now and six months ago. A persistent leader.",
  Fading:
    "Led six months ago, fewer leaders this week. Money is rotating out.",
  Quiet: "Near the one-in-ten baseline at every lookback. Nothing to trade.",
  Thin: "Fewer than two names in the top decile this week. No information.",
};

export function rotationState(s: SectorStrength): RotationState {
  if (!s.rotation_eligible) return "Thin";
  const now = Math.max(s.shares["1w"], s.shares["1m"]);
  const then = s.shares["6m"];
  const leadingNow = now >= LEAD;
  const established = then >= ESTABLISHED;
  if (leadingNow && !established) return "Emerging";
  if (established && s.shares["1w"] < then - FADE_GAP) return "Fading";
  if (leadingNow && established) return "Leading";
  return "Quiet";
}

// Multiple of the baseline: 0.30 share → 3.0×.
export function multiple(share: number): string {
  return `${(share / BASELINE).toFixed(1)}×`;
}

// Confidence as a 0..1 intensity from the decile count behind a share.
export function confidence(k: number): number {
  if (k < 2) return 0.3;
  if (k < 4) return 0.6;
  return 1;
}

// Industries that lead, grouped by parent sector, for the "broad or narrow?" read.
export function leadingIndustriesBySector(
  industries: IndustryStrength[],
): Map<string, { leading: IndustryStrength[]; total: number }> {
  const out = new Map<string, { leading: IndustryStrength[]; total: number }>();
  for (const i of industries) {
    const slot = out.get(i.sector) ?? { leading: [], total: 0 };
    slot.total += 1;
    if (i.shares["1w"] >= LEAD || i.shares["1m"] >= LEAD) slot.leading.push(i);
    out.set(i.sector, slot);
  }
  for (const slot of out.values())
    slot.leading.sort((a, b) => b.shape_differential - a.shape_differential);
  return out;
}

// The one sentence a trader wants before the open.
export function summarise(data: SectorsResponse): string {
  const by = (st: RotationState) =>
    data.sectors.filter((s) => rotationState(s) === st).map((s) => s.sector);
  const list = (xs: string[]) =>
    xs.length <= 2
      ? xs.join(" and ")
      : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`;
  const parts: string[] = [];
  const emerging = by("Emerging");
  const leading = by("Leading");
  const fading = by("Fading");
  if (emerging.length)
    parts.push(
      `${list(emerging)} ${emerging.length === 1 ? "is" : "are"} gaining leaders`,
    );
  if (leading.length)
    parts.push(
      `${list(leading)} ${leading.length === 1 ? "keeps" : "keep"} leading`,
    );
  if (fading.length)
    parts.push(`${list(fading)} ${fading.length === 1 ? "is" : "are"} fading`);
  if (!parts.length) return "No sector stands out from the baseline tonight.";
  return parts.join(". ") + ".";
}

// The sector colour tokens the sheet already carries (index.css @theme).
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

export function pct(share: number): string {
  return `${Math.round(share * 100)}%`;
}
export function signedPp(value: number): string {
  const p = Math.round(value * 100);
  return `${p > 0 ? "+" : ""}${p}pp`;
}

export const LOOKBACKS = [
  { key: "1w", label: "1W" },
  { key: "1m", label: "1M" },
  { key: "3m", label: "3M" },
  { key: "6m", label: "6M" },
  { key: "12m", label: "12M" },
] as const;
