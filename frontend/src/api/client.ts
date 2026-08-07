import type { components } from "./schema";

// The response types the frontend consumes are the generated OpenAPI ones.
// Referencing the fields here (e.g. `latest.session`) is what makes a renamed
// backend field a typecheck failure rather than a runtime `undefined`.
export type RunsResponse = components["schemas"]["RunsResponse"];
export type RunRecord = components["schemas"]["RunRecord"];
export type RunTriggerResponse = components["schemas"]["RunTriggerResponse"];
// `Boards` renamed to `Leaders` on the backend (spec §4.4 / §10.2); `/api/boards`
// is kept as an alias so v1 keeps working until it dies in the integration
// commit. These aliases hold the v1 names against the renamed schemas so the v1
// screen compiles unchanged over the aliased endpoint.
export type BoardsResponse = components["schemas"]["LeadersResponse"];
export type Board = components["schemas"]["Leader"];
export type BoardRow = components["schemas"]["LeaderRow"];
export type SectorsResponse = components["schemas"]["SectorsResponse"];
export type SectorStrength = components["schemas"]["SectorStrength"];
export type IndustryStrength = components["schemas"]["IndustryStrength"];
export type RegimeResponse = components["schemas"]["RegimeResponse"];
export type CandidatesResponse = components["schemas"]["CandidatesResponse"];
export type Candidate = components["schemas"]["Candidate"];
export type ChartResponse = components["schemas"]["ChartResponse"];
export type Candle = components["schemas"]["Candle"];
export type MaPoint = components["schemas"]["MaPoint"];
export type ChartFacts = components["schemas"]["ChartFacts"];
export type SetupOverlay = components["schemas"]["SetupOverlay"];
export type ScoreRow = components["schemas"]["ScoreRow"];

export async function fetchRuns(market: string): Promise<RunsResponse> {
  const resp = await fetch(`/api/runs/${market}`);
  if (!resp.ok) throw new Error(`GET /api/runs/${market} → ${resp.status}`);
  return (await resp.json()) as RunsResponse;
}

// Run-on-open (spec §7.3): opening a tab whose last final session is missing
// kicks a run. Single-flight on the backend, so a duplicate open is a no-op.
export async function triggerRun(market: string): Promise<RunTriggerResponse> {
  const resp = await fetch(`/api/runs/${market}`, { method: "POST" });
  if (!resp.ok) throw new Error(`POST /api/runs/${market} → ${resp.status}`);
  return (await resp.json()) as RunTriggerResponse;
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

export async function fetchCandidates(market: string): Promise<CandidatesResponse> {
  const resp = await fetch(`/api/candidates/${market}`);
  if (!resp.ok) throw new Error(`GET /api/candidates/${market} → ${resp.status}`);
  return (await resp.json()) as CandidatesResponse;
}

export async function fetchChart(market: string, symbol: string): Promise<ChartResponse> {
  const resp = await fetch(`/api/chart/${market}/${symbol}`);
  if (!resp.ok) throw new Error(`GET /api/chart/${market}/${symbol} → ${resp.status}`);
  return (await resp.json()) as ChartResponse;
}
