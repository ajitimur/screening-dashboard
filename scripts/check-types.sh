#!/usr/bin/env bash
#
# Contract-drift check (spec §4.9, issue #74).
#
# Regenerate the API types from the backend response models, then fail if the
# working tree moved — a `models.py` edit that was never propagated to
# `openapi.json` / `schema.d.ts` is caught here rather than later, at a frontend
# type error. Runnable by hand and by a future CI job; wiring CI is out of scope.
#
# Usage: npm run gen:types:check   (or: bash scripts/check-types.sh)
set -euo pipefail

cd "$(dirname "$0")/.."

GENERATED=(frontend/src/api/openapi.json frontend/src/api/schema.d.ts)

# If the generated artefacts are already dirty, there is nothing this check can
# prove — a pre-existing edit would masquerade as (or mask) real drift. Refuse
# rather than report a result that is not about regeneration.
if ! git diff --quiet -- "${GENERATED[@]}"; then
  echo "error: ${GENERATED[*]} already have uncommitted changes." >&2
  echo "Commit or stash them before running the drift check." >&2
  exit 2
fi

npm run gen:types

if ! git diff --quiet -- "${GENERATED[@]}"; then
  echo >&2
  echo "error: generated API types are out of date." >&2
  echo "A response model changed but the committed contract was not regenerated." >&2
  git --no-pager diff --stat -- "${GENERATED[@]}" >&2
  echo "Fix: run 'npm run gen:types' and commit the result." >&2
  exit 1
fi

echo "API types are up to date — no contract drift."
