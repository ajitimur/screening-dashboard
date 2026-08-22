# screening-dashboard

Qullamaggie EOD screening dashboard for IDX and US. Design is normative in
[`.scratch/screening-dashboard/v1-spec.md`](.scratch/screening-dashboard/v1-spec.md).

This is the **walking skeleton** (ticket 27): the DuckDB store, the run record,
the read API and the two market tabs — the disciplines every later ticket
depends on, in place.

## Evidence and plans

Measured studies live in [`references/`](references/) and accepted decisions in
[`docs/adr/`](docs/adr/). Read
[`docs/out-of-sample-backtest-plan.md`](docs/out-of-sample-backtest-plan.md) before running,
extending or interpreting the 2012-onward US/IDX backtest — it fixes the run contract, the
point-in-time rules, the survivorship bound and the anchors a run reproduces before its
figures are read.

## Layout

```
backend/     Python package — DuckDB store, the run pipeline slice, FastAPI app
frontend/    Vite + React + TS — the IDX/US tab shell
data/        screener.duckdb (created on first run), digests/
```

## Setup

```bash
python3 -m venv .venv                       # then bootstrap pip if absent
.venv/bin/pip install -r backend/requirements.txt
npm --prefix frontend install
```

## One command, one URL

```bash
npm start        # builds the frontend, then FastAPI serves it at http://127.0.0.1:8000
```

FastAPI serves the built frontend, so it is one process on one URL. The DuckDB
file is created under `data/` on first run.

## The type-generation loop

The frontend's response types are generated from the API's OpenAPI schema, and
committed (`frontend/src/api/schema.d.ts`). After changing a Pydantic response
model, regenerate and typecheck — a renamed field becomes a typecheck failure
rather than a runtime `undefined`:

```bash
npm run gen:types
npm run typecheck
```

## Tests

Two seams (both required by ticket 27):

- **Seam 1** — `backend/tests/test_store_seam.py`: seeds a fixture store, runs
  something, asserts on rows (and pins append-only + quarantine).
- **Seam 2** — `backend/tests/test_api_seam.py`: hits an endpoint via
  `TestClient` against a fixture store and asserts on the payload.

```bash
npm test         # backend pytest + frontend vitest
npm run typecheck
```

(`PYTHON=... npm test` overrides the interpreter; defaults to `.venv/bin/python`.)
