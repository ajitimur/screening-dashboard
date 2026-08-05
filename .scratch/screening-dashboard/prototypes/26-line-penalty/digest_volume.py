"""Ticket 26 — what demoting `line_ok` does to ticket 18's digest volume.

Ticket 26 lists the digest as a knock-on "to check rather than assume". Ticket 18's consecutive-bar
scan is cached, so this is a re-run of its own classifier with one bit changed: detection is
`tight & caught_up` with and without `& line_ok`. Everything else — the `close_today >
trigger_yesterday` rule, the contiguity requirement, the taxonomy — is ticket 18's code path.

Ticket 18's caveat carries: D15's decile gate is NOT applied here, so every rows-per-night figure is
an upper bound. The RATIO between the two gate sets is the answer; the levels are ticket 18's.

Usage: digest_volume.py
"""

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P18 = os.path.abspath(os.path.join(HERE, "..", "18-digest-rule"))
DAILY = None
for root in (P18, os.path.abspath(os.path.join(
        HERE, "..", "..", "..", "..", "..", "wf-18-digest-rule", ".scratch",
        "screening-dashboard", "prototypes", "18-digest-rule"))):
    p = os.path.join(root, "out", "daily.pkl")
    if os.path.exists(p):
        DAILY = p
        break

MOVE_FLOOR = 25.0


def classify(df, require_line_ok):
    """Ticket 18's crossings.classify, with the line test as a switch."""
    df = df.copy()
    det = (df.tight.fillna(False).astype(bool)
           & df.caught_up.fillna(False).astype(bool)
           & (df.move_gain >= MOVE_FLOOR))
    if require_line_ok:
        det &= df.line_ok.fillna(False).astype(bool)
    df["detected"] = det
    df.loc[~df.detected, "trigger"] = np.nan
    df = df.sort_values(["market", "symbol", "end"]).reset_index(drop=True)
    g = df.groupby(["market", "symbol"], sort=False)

    df["trig_y"] = g.trigger.shift(1)
    df["close_y"] = g.close.shift(1)
    df["det_y"] = g.detected.shift(1).fillna(False).astype(bool)
    df["contig"] = df.end - g.end.shift(1) == 1

    watching_y = df.det_y & df.contig & (df.close_y <= df.trig_y)
    df["t1"] = df.detected & watching_y & (df.close > df.trig_y)
    return df


def main():
    if DAILY is None:
        raise SystemExit("ticket 18's out/daily.pkl not found — run its crossings.py first")
    raw = pd.read_pickle(DAILY)
    print(f"loaded {len(raw):,} scanned bar-nights from {DAILY}\n")

    out = {}
    for label, req in (("as specified (line_ok gates)", True),
                       ("line_ok demoted", False)):
        c = classify(raw, req)
        out[label] = c
        print(f"=== {label}")
        for mkt in ("US", "IDX"):
            d = c[c.market == mkt]
            nights = d.date.nunique()
            names = d.symbol.nunique()
            det = int(d.detected.sum())
            t1 = int(d.t1.sum())
            print(f"  {mkt}: {det:,} detections, {t1:,} digest rows over {nights} nights "
                  f"/ {names} names  ->  {t1 / nights:.2f} rows per night (ungated)")
        print()

    print("=== the ratio, which is what transfers to ticket 18's decile-gated 7.0 US rows/night")
    a, b = out["as specified (line_ok gates)"], out["line_ok demoted"]
    for mkt in ("US", "IDX"):
        da, db = a[a.market == mkt], b[b.market == mkt]
        t1a, t1b = int(da.t1.sum()), int(db.t1.sum())
        deta, detb = int(da.detected.sum()), int(db.detected.sum())
        print(f"  {mkt}: detections x{detb / deta:.2f}, digest rows x{t1b / t1a:.2f}")
    print("\n  NOTE: those ratios are UNGATED. The decile gate cuts the marginal population much"
          "\n  harder than the accepted one (ticket 25: +98% ungated becomes +59% gated), so the"
          "\n  transfer has to use the gated growth and the measured relative break rate.")
    for mkt, rows_now, growth in (("US", 7.0, 0.59), ("IDX", 0.9, 0.59)):
        db = b[b.market == mkt]
        det = db[db.detected]
        acc = det[det.line_ok.fillna(False).astype(bool)]
        mar = det[~det.line_ok.fillna(False).astype(bool)]
        rel = mar.t1.mean() / acc.t1.mean()
        print(f"  {mkt}: marginal names break at {rel:.2f}x the accepted rate, and the gated list"
              f" grows {growth:+.0%}"
              f"  ->  {rows_now:.1f} -> {rows_now * (1 + growth * rel):.1f} rows/night")

    print("\n=== do the marginal names break at a different rate than the accepted ones?")
    for mkt in ("US", "IDX"):
        db = b[b.market == mkt]
        det = db[db.detected]
        for lab, m in (("accepted", det.line_ok.fillna(False).astype(bool)),
                       ("marginal", ~det.line_ok.fillna(False).astype(bool))):
            d = det[m]
            print(f"  {mkt} {lab:9s}: {len(d):,} detections, {int(d.t1.sum()):,} breaks "
                  f"({d.t1.mean():.2%} of detection-nights)")


if __name__ == "__main__":
    main()
