import type { components } from "./schema";

// The response types the frontend consumes are the generated OpenAPI ones.
// Referencing the fields here (e.g. `latest.session`) is what makes a renamed
// backend field a typecheck failure rather than a runtime `undefined`.
export type RunsResponse = components["schemas"]["RunsResponse"];
export type RunRecord = components["schemas"]["RunRecord"];
export type BoardsResponse = components["schemas"]["BoardsResponse"];
export type Board = components["schemas"]["Board"];
export type BoardRow = components["schemas"]["BoardRow"];
export type SectorsResponse = components["schemas"]["SectorsResponse"];
export type SectorStrength = components["schemas"]["SectorStrength"];
export type IndustryStrength = components["schemas"]["IndustryStrength"];
export type RegimeResponse = components["schemas"]["RegimeResponse"];

export async function fetchRuns(market: string): Promise<RunsResponse> {
  const resp = await fetch(`/api/runs/${market}`);
  if (!resp.ok) throw new Error(`GET /api/runs/${market} → ${resp.status}`);
  return (await resp.json()) as RunsResponse;
}

export async function fetchBoards(market: string): Promise<BoardsResponse> {
  const resp = await fetch(`/api/boards/${market}`);
  if (!resp.ok) throw new Error(`GET /api/boards/${market} → ${resp.status}`);
  return (await resp.json()) as BoardsResponse;
}

export async function fetchSectors(market: string): Promise<SectorsResponse> {
  const resp = await fetch(`/api/sectors/${market}`);
  if (!resp.ok) throw new Error(`GET /api/sectors/${market} → ${resp.status}`);
  return (await resp.json()) as SectorsResponse;
}

export async function fetchRegime(market: string): Promise<RegimeResponse> {
  const resp = await fetch(`/api/regime/${market}`);
  if (!resp.ok) throw new Error(`GET /api/regime/${market} → ${resp.status}`);
  return (await resp.json()) as RegimeResponse;
}
