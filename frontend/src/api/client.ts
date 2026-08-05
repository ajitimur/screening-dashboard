import type { components } from "./schema";

// The response types the frontend consumes are the generated OpenAPI ones.
// Referencing the fields here (e.g. `latest.session`) is what makes a renamed
// backend field a typecheck failure rather than a runtime `undefined`.
export type RunsResponse = components["schemas"]["RunsResponse"];
export type RunRecord = components["schemas"]["RunRecord"];

export async function fetchRuns(market: string): Promise<RunsResponse> {
  const resp = await fetch(`/api/runs/${market}`);
  if (!resp.ok) throw new Error(`GET /api/runs/${market} → ${resp.status}`);
  return (await resp.json()) as RunsResponse;
}
