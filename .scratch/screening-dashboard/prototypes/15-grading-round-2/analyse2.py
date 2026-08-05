"""Run the pre-registered analysis over the round-2 grades.

Usage:  analyse2.py grades.txt          # one exported line per deck, as pasted back from the deck
        analyse2.py "A A001:4 A002:2 …"

Every number this prints is specified in PREREGISTRATION.md. Nothing here chooses a rule; it only
executes the ones fixed before grading.
"""

import os
import re
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
sys.path.insert(0, P09)
CACHE = os.path.join(P09, "cache")

from rubric2 import score2, fit, T2, DIMS2  # noqa: E402

BANDS = [(0, 1.5, "≤1.5★"), (1.5, 2.5, "2★"), (2.5, 3.5, "3★"), (3.5, 4.5, "4★"), (4.5, 5.01, "5★")]


def parse(text):
    out = {}
    for m in re.finditer(r"\b([ABCD]\d{3}):([1-5])\b", text):
        out[m.group(1)] = int(m.group(2))
    return out


def rows_for(cids, manifest, picks):
    rows = []
    for cid, eye in cids.items():
        mrec = manifest[manifest.cid == cid]
        if not len(mrec):
            continue
        mrec = mrec.iloc[0]
        p = picks[int(mrec["pick"])]
        r = p["row"]
        sig = dict(r)
        sig["contraction"] = r.get("contraction2")
        sig["churn"] = r.get("churn2")
        sig["L_eff"] = r.get("L_eff")
        sig["L_true"] = r.get("L_longest")
        pm = r.get("prior_move") if p["market"] == "US" else None
        ss = r.get("sector_share") if p["market"] == "US" else None
        pm = None if (pm is None or (isinstance(pm, float) and np.isnan(pm))) else float(pm)
        ss = None if (ss is None or (isinstance(ss, float) and np.isnan(ss))) else float(ss)
        rows.append({"cid": cid, "deck": mrec["deck"], "tag": mrec["tag"], "market": p["market"],
                     "symbol": p["symbol"], "eye": eye, "sig": sig, "prior_move": pm,
                     "sector_share": ss, "repeat_of": mrec["repeat_of"],
                     "L_true": r.get("L_longest"), "trig_vs_close": r.get("trig_vs_close"),
                     "zero_rng": r.get("zero_rng_in_base")})
    return rows


def stars(rows, T, mode):
    return np.array([score2(r["sig"], r["prior_move"], r["sector_share"], mode, T)["stars"] for r in rows])


def report(rows, T, mode, label):
    s = stars(rows, T, mode)
    e = np.array([r["eye"] for r in rows], float)
    err = s - e
    r_ = np.corrcoef(s, e)[0, 1] if len(s) > 2 and s.std() > 0 else np.nan
    print(f"{label:28s} r={r_:+.3f}  mean|err|={np.abs(err).mean():.2f}  "
          f"within1={100*(np.abs(err)<=1).mean():.0f}%  bias={err.mean():+.2f}  n={len(s)}")
    return r_, err


def cv_fit(rows, mode, folds=5, seed=15):
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(rows))
    oof = np.zeros(len(rows))
    Ts = []
    for f in range(folds):
        te = idx[f::folds]
        tr = np.setdiff1d(idx, te)
        T, _ = fit([rows[i] for i in tr], mode=mode)
        Ts.append(T)
        for i in te:
            oof[i] = score2(rows[i]["sig"], rows[i]["prior_move"], rows[i]["sector_share"], mode, T)["stars"]
    return oof, Ts


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg is None:
        print(__doc__)
        return
    text = open(arg).read() if os.path.exists(arg) else arg
    grades = parse(text)
    manifest = pd.read_pickle(os.path.join(CACHE, "manifest_r2.pkl"))
    picks = pd.read_pickle(os.path.join(CACHE, "picks_r2.pkl"))
    rows = rows_for(grades, manifest, picks)
    print(f"parsed {len(grades)} grades, matched {len(rows)} cards\n")

    df = pd.DataFrame([{k: r[k] for k in ("cid", "deck", "tag", "market", "symbol", "eye",
                                          "repeat_of", "L_true", "trig_vs_close", "zero_rng")}
                       for r in rows])

    # ---------- test-retest ceiling (the repeats)
    # A repeat is the SAME card rendered twice under two ids, so pair on what the card actually
    # shows — symbol and date — not on the pick index, which differs between the two entries.
    if df.repeat_of.notna().any():
        # Deck D is excluded: it asks a different question with the overlays off, so a
        # deck-A/deck-D pair measures two instruments, not one grader twice.
        key_of = {r["cid"]: (r["symbol"], str(manifest[manifest.cid == r["cid"]].iloc[0]["date"]))
                  for r in rows if r["deck"] != "D"}
        eye_of = {r["cid"]: r["eye"] for r in rows}
        seen = {}
        for cid, key in key_of.items():
            seen.setdefault(key, []).append(cid)
        pairs = [(eye_of[c[0]], eye_of[c[1]]) for c in seen.values() if len(c) == 2]
        if len(pairs) >= 3:
            a, b = zip(*pairs)
            tr = np.corrcoef(a, b)[0, 1]
            print(f"=== test-retest on {len(pairs)} repeated cards: r={tr:+.3f}, "
                  f"mean|Δ|={np.mean(np.abs(np.array(a)-np.array(b))):.2f}★  "
                  f"(this is the ceiling any rubric can reach)\n")

    core = [r for r in rows if r["deck"] == "A" and pd.isna(r["repeat_of"])]
    if len(core) >= 20:
        print("=== deck A: incumbent thresholds (ticket 09's provisional numbers) ===")
        report(core, T2, "boolean", "incumbent boolean")
        report(core, T2, "continuous", "incumbent continuous")

        print("\n=== fitted, in-sample (upper bound, not the answer) ===")
        Tb, _ = fit(core, "boolean")
        Tc, _ = fit(core, "continuous")
        report(core, Tb, "boolean", "fitted boolean (in-sample)")
        report(core, Tc, "continuous", "fitted continuous (in-sample)")
        print("  boolean thresholds:", {k: round(v, 3) for k, v in Tb.items()})
        print("  continuous thresholds:", {k: round(v, 3) for k, v in Tc.items()})

        print("\n=== fitted, 5-fold out-of-fold (the honest number) ===")
        e = np.array([r["eye"] for r in core], float)
        out = {}
        for mode in ("boolean", "continuous"):
            oof, Ts = cv_fit(core, mode)
            err = oof - e
            r_ = np.corrcoef(oof, e)[0, 1]
            out[mode] = {"r": r_, "mae": np.abs(err).mean(), "w1": (np.abs(err) <= 1).mean()}
            print(f"{mode:12s} oof r={r_:+.3f}  mean|err|={np.abs(err).mean():.2f}  "
                  f"within1={100*(np.abs(err)<=1).mean():.0f}%")
            spread = pd.DataFrame(Ts).agg(["min", "median", "max"])
            print("   fold-to-fold threshold spread:\n" + spread.to_string())

        # pre-registered tie-break
        b, c = out["boolean"], out["continuous"]
        win = "continuous" if (c["mae"] <= b["mae"] - 0.10 and c["w1"] > b["w1"]) else "boolean"
        print(f"\n  --> pre-registered rule picks: {win.upper()}")

        # 4-star threshold
        oof, _ = cv_fit(core, win)
        print("\n=== where should the trade threshold sit? (out-of-fold) ===")
        for cut in (3.0, 3.5, 4.0, 4.5):
            pred, act = oof >= cut, e >= 4
            tp = int((pred & act).sum())
            prec = tp / max(int(pred.sum()), 1)
            rec = tp / max(int(act.sum()), 1)
            print(f"  machine ≥{cut}★ vs eye ≥4★: n={int(pred.sum()):3d} precision={prec:.2f} recall={rec:.2f}")

        # per-market
        print("\n=== per-market residuals under the pooled fit ===")
        Tw, _ = fit(core, win)
        allrows = [r for r in rows if pd.isna(r["repeat_of"])]
        for mkt in ("US", "IDX"):
            sub = [r for r in allrows if r["market"] == mkt]
            if len(sub) >= 10:
                report(sub, Tw, win, f"pooled fit on {mkt}")

    # ---------- probes
    for deck, split, label in [
        ("B", lambda r: "breached" if r["trig_vs_close"] <= 0 else "above", "trigger probe"),
        ("C", lambda r: "partial-lock" if (r["zero_rng"] or 0) > 0 else "clean", "IDX lock probe"),
        ("D", lambda r: "reject" if str(r["tag"]).startswith("reject") else "detection", "false-negative probe"),
    ]:
        sub = [r for r in rows if r["deck"] == deck and pd.isna(r["repeat_of"])]
        if len(sub) < 10:
            continue
        print(f"\n=== deck {deck}: {label} ===")
        g = {}
        for r in sub:
            g.setdefault(split(r), []).append(r["eye"])
        keys = sorted(g)
        for k in keys:
            v = np.array(g[k], float)
            print(f"  {k:14s} n={len(v):3d} mean={v.mean():.2f}★ sd={v.std(ddof=1):.2f} "
                  f"≥4★={100*(v>=4).mean():.0f}%")
        if len(keys) == 2:
            a, b = np.array(g[keys[0]], float), np.array(g[keys[1]], float)
            d = a.mean() - b.mean()
            se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
            print(f"  difference {d:+.2f}★  SE={se:.2f}  t={d/se:+.2f}  "
                  f"{'SEPARATES' if abs(d/se) > 1.96 else 'no 1-star effect detected'}")


if __name__ == "__main__":
    main()
