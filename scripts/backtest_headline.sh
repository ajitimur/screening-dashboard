#!/usr/bin/env bash
#
# The headline figure, and its bound — one command (PRD #182 Phase 7, issue #200).
#
# Phase 7 is done when "a reader who has seen none of this can reproduce the
# headline figure from the committed command, and can state its bound without
# reading the code". This is that command.
#
# Usage:
#   bash scripts/backtest_headline.sh                      # from the committed payloads
#   bash scripts/backtest_headline.sh --from-store PATH    # recomputed from the bar store
#
# Two paths, and they are deliberately not the same claim:
#
#   The default reads the recorded payloads under references/ and re-evaluates the
#   contract's own criteria over them. What it checks is that the committed result
#   and the write-up's prose still agree — it does not touch a bar, and it says so
#   on its first line. This is the path a reader can run today: `data/*.duckdb` is
#   1.1GB of bars and 446MB of denominator, and `.gitignore` keeps both out of the
#   repository, so there is nothing here to read them from.
#
#   `--from-store` recomputes the headline from a built store: the pre-registered
#   metric, Phase 2's bound attached to it, the sweep whose count rides beside the
#   verdict, and then the verdict itself. That is the reproduction proper, and it
#   needs the store built first (`python -m backtest.crawl`, then
#   `python -m backtest.full_run`) — roughly two hours of paced fetching before it
#   can run at all.
#
# Either way the last thing printed is the same page: both markets, both windows,
# each figure beside its pessimistic twin, and the verdict in the words the
# contract fixed before the run.
set -euo pipefail

cd "$(dirname "$0")/.."

REPO="$PWD"
REFERENCES=references
METRIC="$REPO/$REFERENCES/backtest_primary_metric.json"
SWEEP="$REPO/$REFERENCES/backtest_sweep.json"
SURVIVORSHIP="$REPO/$REFERENCES/backtest_survivorship.json"

# Absolute, because every step below runs from backend/ so that `backtest` and
# `screener` import the way pyproject's pythonpath expects.
PYTHON="${PYTHON:-$PWD/backend/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

STORE=""
if [[ "${1:-}" == "--from-store" ]]; then
  STORE="${2:-}"
  if [[ -z "$STORE" ]]; then
    echo "error: --from-store needs the path to a built bar store." >&2
    exit 2
  fi
  if [[ ! -f "$STORE" ]]; then
    # A missing store is refused rather than quietly falling back to the recorded
    # payloads, which would print the right numbers under the wrong claim.
    echo "error: no bar store at $STORE." >&2
    echo "Build it first: python -m backtest.crawl && python -m backtest.full_run" >&2
    exit 2
  fi
  # Absolute from here on: every step runs from backend/, so a path the caller
  # gave relative to the repository root would resolve one directory too deep.
  STORE="$(cd "$(dirname "$STORE")" && pwd)/$(basename "$STORE")"
elif [[ -n "${1:-}" ]]; then
  echo "usage: bash scripts/backtest_headline.sh [--from-store PATH]" >&2
  exit 2
fi

if [[ -n "$STORE" ]]; then
  WORK="$(mktemp -d)"
  trap 'rm -rf "$WORK"' EXIT
  echo "Recomputing the headline from the bars at $STORE."
  echo "The recorded payloads under $REFERENCES/ are read for nothing here;"
  echo "run without --from-store to re-read them instead."
  echo

  # The order is the contract's, not a convenience: the sweep refuses to run until
  # a pre-registered headline has been recorded, and the verdict refuses a metric
  # with no bound attached. Each step's output is the next step's required input.
  ( cd backend && "$PYTHON" -m backtest.metric \
      --store "$STORE" --out-json "$WORK/metric.json" ) > /dev/null
  ( cd backend && "$PYTHON" -m backtest.survivorship \
      --store "$STORE" \
      --metric-json "$WORK/metric.json" \
      --out-json "$WORK/survivorship.json" \
      --out-metric-json "$WORK/metric_bounded.json" ) > /dev/null
  ( cd backend && "$PYTHON" -m backtest.sweep \
      --store "$STORE" \
      --recorded "$WORK/metric.json" \
      --out-json "$WORK/sweep.json" ) > /dev/null

  METRIC="$WORK/metric_bounded.json"
  SWEEP="$WORK/sweep.json"
  SURVIVORSHIP="$WORK/survivorship.json"
else
  echo "Read back from the recorded payloads committed under $REFERENCES/:"
  echo "  $METRIC"
  echo "  $SURVIVORSHIP"
  echo "  $SWEEP"
  echo "No bar is read on this path — it checks that the committed result and the"
  echo "write-up still agree. To recompute the figure from the bars themselves,"
  echo "build the store and pass --from-store data/backtest.duckdb."
  echo
fi

cd backend
exec "$PYTHON" -m backtest.verdict \
  --metric-json "$METRIC" \
  --sweep-json "$SWEEP" \
  --survivorship-json "$SURVIVORSHIP"
