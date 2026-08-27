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

# Both paths read the verdict off `backtest.verdict`, which imports the package,
# which imports duckdb. That is worth one clear sentence rather than a traceback:
# the reader who runs this has cloned a repository, not installed a tool, and the
# failure they are about to hit is a missing environment rather than a missing
# figure. Checked before anything is printed, so the two do not interleave.
require_environment() {
  if "$PYTHON" -c 'import duckdb' 2>/dev/null; then
    return
  fi
  echo "error: $PYTHON cannot import duckdb, so the backtest package will not load." >&2
  echo "This command needs the project's Python environment (no bar store, but the" >&2
  echo "same dependencies). Set it up with:" >&2
  echo "    python3 -m venv backend/.venv" >&2
  echo "    backend/.venv/bin/pip install -r backend/requirements.txt" >&2
  echo "Or point PYTHON at an interpreter that already has them:" >&2
  echo "    PYTHON=/path/to/python bash scripts/backtest_headline.sh" >&2
  exit 3
}

usage() {
  echo "usage: bash scripts/backtest_headline.sh [--from-store PATH]"
  echo
  echo "  (no arguments)      print the headline and its bound from the payloads"
  echo "                      committed under references/; reads no bars"
  echo "  --from-store PATH   recompute it from a built bar store instead"
}

STORE=""
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
elif [[ "${1:-}" == "--from-store" ]]; then
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
  usage >&2
  exit 2
fi

# After the argument parsing, so --help answers without an environment at all.
require_environment

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

# Not `exec`: that replaces the shell image, so bash would never run the EXIT
# trap and every --from-store run would leave its temp directory behind.
cd backend
"$PYTHON" -m backtest.verdict \
  --metric-json "$METRIC" \
  --sweep-json "$SWEEP" \
  --survivorship-json "$SURVIVORSHIP"
