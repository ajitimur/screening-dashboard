import type { components } from "./schema";

// The response types the frontend consumes are the generated OpenAPI ones.
// Referencing the fields here (e.g. `latest.session`) is what makes a renamed
// backend field a typecheck failure rather than a runtime `undefined`.
export type RunsResponse = components["schemas"]["RunsResponse"];
export type RunRecord = components["schemas"]["RunRecord"];
export type RunTriggerResponse = components["schemas"]["RunTriggerResponse"];
// The leaderboards read (spec §4.4). *Leaders* names the endpoint because
// *Board* names the composite home screen — hence `Board.tsx` reading
// `fetchLeaders`, which is otherwise a surprise.
export type LeadersResponse = components["schemas"]["LeadersResponse"];
export type Leader = components["schemas"]["Leader"];
export type LeaderRow = components["schemas"]["LeaderRow"];
export type SectorsResponse = components["schemas"]["SectorsResponse"];
export type SectorStrength = components["schemas"]["SectorStrength"];
export type IndustryStrength = components["schemas"]["IndustryStrength"];
export type SectorDetailResponse = components["schemas"]["SectorDetailResponse"];
export type SectorMember = components["schemas"]["SectorMember"];
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

export async function fetchLeaders(market: string): Promise<LeadersResponse> {
  const resp = await fetch(`/api/leaders/${market}`);
  if (!resp.ok) throw new Error(`GET /api/leaders/${market} → ${resp.status}`);
  return (await resp.json()) as LeadersResponse;
}

export async function fetchSectors(market: string): Promise<SectorsResponse> {
  const resp = await fetch(`/api/sectors/${market}`);
  if (!resp.ok) throw new Error(`GET /api/sectors/${market} → ${resp.status}`);
  return (await resp.json()) as SectorsResponse;
}

// The sector drill-down (spec §4.5 / §5.5). The sector name needs URL-encoding —
// GECS labels carry spaces (`Consumer Cyclical`) — spec'd explicitly rather than
// left to whoever implements. The member rows carry per-lookback returns,
// percentile-in-universe and per-name decile, so the client's lookback switch
// re-renders without a refetch.
export async function fetchSectorDetail(
  market: string,
  sector: string,
): Promise<SectorDetailResponse> {
  const resp = await fetch(`/api/sectors/${market}/${encodeURIComponent(sector)}`);
  if (!resp.ok)
    throw new Error(`GET /api/sectors/${market}/${sector} → ${resp.status}`);
  return (await resp.json()) as SectorDetailResponse;
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

// `bars` caps the window the read returns (spec §6.4 / ticket #77): the mini
// charts ask for 60 so a thumbnail never ships a full price history, and the
// sheet asks for the same 60 so a mini already on screen makes the open a cache
// hit (the shared-cache point of §6.4). Omitted → the backend's default window.
export async function fetchChart(
  market: string,
  symbol: string,
  bars?: number | null,
): Promise<ChartResponse> {
  const query = bars == null ? "" : `?bars=${bars}`;
  const resp = await fetch(`/api/chart/${market}/${symbol}${query}`);
  if (!resp.ok) throw new Error(`GET /api/chart/${market}/${symbol} → ${resp.status}`);
  return (await resp.json()) as ChartResponse;
}
