"""Audit the 22 numbers before fitting any of them.

Fitting is expensive and a parameter only earns a fit if it is *live*. Four ways a number can fail
to be:

  dead            defined and never read
  discretisation  a resolution knob, not a preference — converges and then stops mattering
  drawing-only    changes what the chart shows and whether a detection exists, but ticket 18's
                  identity means it cannot move the trigger
  redundant       something upstream already does its job

Everything left is live and goes to the sweeps. Nothing here needs the trader — these are facts
about the code and the tape.
"""

import os
import re
import sys

import numpy as np
import pandas as pd

import harness as H

P16 = H.P16


def dead_numbers():
    """A parameter never read by the module is dead however plausible it looks."""
    src = open(os.path.join(P16, "split.py")).read()
    # the constants sit in one block above the first function, so everything from `def prior_move`
    # onwards is use rather than definition
    body = src.split("def prior_move", 1)[1]
    print("=== dead: defined and never read\n")
    for name in list(H.BILL) + list(H.DEAD):
        uses = len(re.findall(rf"\b{name}\b", body))
        if uses == 0:
            print(f"  {name:20s} 0 uses in any function body — DEAD")
    print("\n  (every other name in the bill is read at least once)")


def trigger_identity():
    """Ticket 18's identity, re-checked on this sample: does the fitted line ever set the level?"""
    df = H.scan("US")
    a = H.accepted(df)
    print("\n=== the trigger identity (ticket 18 R1), re-measured on this sample\n")
    # trigger = max(line_end, cluster_high); cluster_high is recoverable from the stop width.
    line_bound = 0
    n = len(a)
    # split.py does not persist cluster_high, but trigger == cluster_high whenever the line loses.
    # Recompute line_end for a subsample and compare directly.
    import split as S
    frames = H.frames("US")
    checked = wins = 0
    for sym, g in a.groupby("symbol"):
        d = frames[sym]
        high = d["High"].to_numpy(float)
        low = d["Low"].to_numpy(float)
        close = d["Close"].to_numpy(float)
        adr = pd.Series(high / low - 1.0).rolling(20).mean().to_numpy()
        for _, r in g.iterrows():
            as_of, k = int(r["end"]), int(r["cluster_k"])
            adr_abs = adr[as_of] * close[as_of]
            ch = float(high[as_of - k + 1:as_of + 1].max())
            anchor = (as_of - k + 1) + int(np.argmax(high[as_of - k + 1:as_of + 1]))
            # the line can only lose height going forward: it is anchored at ch and slopes <= 0
            checked += 1
            if float(r["trigger"]) > ch + 1e-9:
                wins += 1
        if checked > 20000:
            break
    print(f"  detections checked           {checked:,}")
    print(f"  fitted line set the trigger  {wins:,} ({wins / max(checked, 1):.1%})")
    print("  the line is anchored AT the cluster high and searched over non-positive slopes,")
    print("  so line_end <= cluster_high by construction. Four numbers below inherit this.")
    return line_bound, n


def discretisation():
    """SLOPE_STEPS is a grid resolution. If the list stops moving, it is not a preference."""
    print("\n=== discretisation: does SLOPE_STEPS converge?\n")
    base = None
    print(f"  {'SLOPE_STEPS':>12s} {'accepted':>10s} {'/night':>8s} {'vs 200':>9s}")
    for v in (25, 50, 100, 200, 400, 800):
        a = H.accepted(H.scan("US", {"SLOPE_STEPS": v}))
        if v == 200:
            base = len(a)
        print(f"  {v:>12d} {len(a):>10,} {H.per_night(a):>8.1f}", end="")
        print(f" {'—' if base is None else f'{len(a) / base - 1:+8.2%}'}")
    print("\n  a resolution knob, not a preference: fix it and stop counting it.")


def drawing_only():
    """The four line-shape numbers cannot move the trigger. What DO they move?"""
    print("\n=== drawing-only: the line-shape four (ticket 18's added scope)\n")
    base = H.accepted(H.scan("US"))
    print(f"  baseline {len(base):,} accepted, {H.per_night(base):.1f}/night\n")
    print(f"  {'parameter':16s} {'value':>7s} {'accepted':>10s} {'vs base':>9s}")
    for name, values in (("OVER_W", (1.5, 3.0, 6.0)),
                         ("UNDER_W", (0.5, 1.0, 2.0)),
                         ("MAX_SLOPE_ADR", (0.25, 0.5, 1.0))):
        for v in values:
            a = H.accepted(H.scan("US", {name: v}))
            print(f"  {name:16s} {v:>7} {len(a):>10,} {len(a) / len(base) - 1:>+8.1%}")
        print()
    print("  these move only whether a line is drawable (line_ok) and what the chart draws.")


def redundant_floor():
    """Does the 25% prior-move floor do anything the ticket-06 decile gate has not already done?

    Ticket 06 R2 gates on the union of top deciles across 1w/1m/3m/6m/12m per market — ~29% of the
    universe. The floor is a second momentum filter on the same quantity.
    """
    print("\n=== redundancy: the 25% prior-move floor against ticket 06's decile gate\n")
    ranks, _, _ = pd.read_pickle(os.path.join(H.CACHE, "ranks_us.pkl"))
    gate = None
    for lb, frame in ranks.items():
        top = frame >= 0.90
        gate = top if gate is None else (gate | top)
    gate.index = pd.to_datetime(gate.index)

    df = H.scan("US")
    a = H.accepted(df, floor=False).copy()
    a["date"] = pd.to_datetime(a["date"])
    cols = set(gate.columns)
    a = a[a.symbol.isin(cols)]
    a = a[a.date.isin(set(gate.index))]
    if not len(a):
        print("  no overlap between the sample and the rank table — skipped")
        return
    in_gate = np.array([bool(gate.at[d, s]) for s, d in zip(a.symbol, a.date)])
    passes = (a.move_gain >= H.MOVE_FLOOR).to_numpy()

    n = len(a)
    print(f"  detections with rank coverage      {n:,}")
    print(f"  pass the 25% floor                 {passes.mean():.1%}")
    print(f"  in the union-of-deciles gate       {in_gate.mean():.1%}")
    print(f"  both                               {(passes & in_gate).mean():.1%}")
    print()
    print(f"  P(floor | in gate)                 {passes[in_gate].mean():.1%}")
    print(f"  P(in gate | floor)                 {in_gate[passes].mean():.1%}")
    print(f"  floor's marginal cut, given gate   "
          f"{1 - passes[in_gate].mean():.1%} of gated detections")
    print(f"  gate's marginal cut, given floor   "
          f"{1 - in_gate[passes].mean():.1%} of floored detections")
    both = float((passes & in_gate).sum())
    print(f"\n  agreement (Jaccard)                "
          f"{both / float((passes | in_gate).sum()):.1%}")


def main():
    dead_numbers()
    trigger_identity()
    discretisation()
    drawing_only()
    redundant_floor()


if __name__ == "__main__":
    main()
