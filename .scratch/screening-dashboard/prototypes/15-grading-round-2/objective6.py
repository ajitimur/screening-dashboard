"""Round 6 — the fitting objective (ticket 21). Everything here is fixed by PREREGISTRATION_R6.md.

    python objective6.py              the pre-registered run, in order (sections 1-7)
    python objective6.py --selftest   pins the fast search to rubric3.score3, then runs on synthetic

Why this file exists at all: `rubric3.fit` minimises mean absolute error over the grid, and mae is a
*level* statistic while the app sorts. This module is the same exhaustive search over the same
`rubric3.GRIDS` with the objective made pluggable, plus the stability reporting R6 section 4 makes
mandatory. The rubric itself is not touched -- `_fast_predictor` is asserted equal to `score3` on
every population before any number below is computed.
"""

import json
import os
import sys
from itertools import product

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
CACHE = os.path.join(P09, "cache")
sys.path.insert(0, P09)

import rubric3 as RB                                    # noqa: E402
from rubric3 import GRIDS, T3, score3                   # noqa: E402
import analyse3 as A3                                   # noqa: E402

CARDS_PKL = os.path.join(CACHE, "r6_cards.pkl")

# --- the pre-registered constants, R6 sections 2, 4, 5, 6, 7
SEEDS = (11, 12, 13, 14, 15)     # 5 fold assignments x 5 folds = 25 fits
FOLDS = 5
MARGIN = 0.030                   # S2: a challenger must beat mae by this to replace it
MAE_GUARDRAIL = 0.15             # S2: level guardrail, in stars
POOL_TOL = 0.020                 # S3: pooling adopted if within this of the deck-only fit
STABLE_SHARE = 0.60              # S4
STABLE_STEPS = 2                 # S4
LAMBDAS = (0.0, 0.001, 0.003, 0.010)   # S5
LAMBDA_GAIN = 0.010              # S5
ORD_GAIN = 0.030                 # S6
PARTIAL_FLOOR = 0.15             # S7


# --------------------------------------------------------------------------- populations

def load_cards():
    """Every graded card with signals attached. Cached: attaching costs ~2 minutes."""
    if os.path.exists(CARDS_PKL):
        return pd.read_pickle(CARDS_PKL)
    grades = {d: open(os.path.join(HERE, f"grades3_{d}.txt")).read().strip()
              for d in ("A", "C", "D", "E")}
    df = A3.attach_signals(A3.load_cards(grades))
    df.to_pickle(CARDS_PKL)
    return df


def populations(df):
    """The three graded populations, as R6 defines them."""
    return {
        "A3": df[(df.deck == "A") & df.split_ok],
        "E3": df[(df.deck == "E") & df.split_ok & (df.tag == "confirm")],
        "C3": df[(df.deck == "C") & df.split_ok & (df.market == "IDX") & (df.tag != "repeat")],
    }


def rows_of(df, deck_label=None):
    out = []
    for _, r in df.iterrows():
        out.append({"sig": r.to_dict(), "prior_move": r.prior_move,
                    "sector_share": r.sector_share, "eye": float(r.eye),
                    "deck": deck_label or r.deck})
    return out


# --------------------------------------------------------------------------- the fast search

class Fast:
    """Boolean-mode `score3` over a fixed row set, with every threshold's contribution precomputed.

    An exhaustive pass is 86,400 grid points; recomputing the per-dimension points at each one is
    what made the incumbent search slow enough that ticket 20 could only afford one fold assignment.
    Precomputing them makes 25 assignments affordable, which is what R6 section 4 needs.
    """

    def __init__(self, rows, drop=()):
        self.rows = rows
        self.drop = tuple(drop)
        n = len(rows)
        k = np.full(n, np.nan); o = np.full(n, np.nan)
        du = np.full(n, np.nan); L = np.full(n, np.nan)
        fixed_total = np.zeros(n); fixed_max = np.zeros(n)
        for i, r in enumerate(rows):
            sig = r["sig"]
            for arr, key in ((k, "cluster_k"), (o, "orderliness"), (du, "dryup"), (L, "L_true")):
                v = RB._num(sig.get(key))
                arr[i] = np.nan if v is None else v
            # NB: score3 treats a *NaN* prior_move / sector_share as a scored zero (NaN >= x is
            # False) while still counting its weight, whereas rubric3._vector_predictor drops it
            # from both. The two therefore disagree on IDX cards, which carry neither. score3 is
            # the rubric of record and produced every published prediction, so it is what is
            # matched here. See ROUND6_OUTPUT / OBJECTIVE_FINDINGS F0.
            pm, ss = r["prior_move"], r["sector_share"]
            if pm is not None:
                fixed_total[i] += 1.0 if pm >= RB.FIXED["prior_move"] else 0.0
                fixed_max[i] += 1
            rising = sig.get("sma20_rising")
            fixed_total[i] += 0.5 if rising is None else (1.0 if rising else 0.0)
            fixed_max[i] += 1
            if ss is not None:
                fixed_total[i] += 1.0 if ss >= RB.FIXED["sector_share"] else 0.0
                fixed_max[i] += 1
            a = RB._num(sig.get("adr"))
            if a is not None:
                fixed_total[i] += 1.0 if a >= RB.FIXED["adr"] else 0.0
                fixed_max[i] += 1

        hasL = np.isfinite(L)
        self.w_t = 0.0 if "tightness" in self.drop else 2.0
        self.w_o = 0.0 if "orderliness" in self.drop else 2.0
        self.w_v = 0.0 if "volume" in self.drop else 1.0
        self.w_l = 0.0 if "base_length" in self.drop else 1.0
        self.scale = 5.0 / (fixed_max + self.w_t + self.w_o + self.w_v + self.w_l * hasL)
        self.base = fixed_total

        # per-threshold-value point vectors
        self.keys = [key for key in ("cluster_k", "ord_lo", "ord_hi", "len_ok", "dryup")
                     if not ("orderliness" in self.drop and key in ("ord_lo", "ord_hi"))]
        self.PT = {v: np.where(np.isfinite(k), (k >= v).astype(float), 0.5) for v in GRIDS["cluster_k"]}
        self.PO = {(lo, hi): np.where(np.isfinite(o), ((o >= lo) & (o <= hi)).astype(float), 0.5)
                   for lo in GRIDS["ord_lo"] for hi in GRIDS["ord_hi"] if hi > lo}
        self.PV = {v: np.where(np.isfinite(du), (du <= v).astype(float), 0.5) for v in GRIDS["dryup"]}
        self.PL = {v: np.where(hasL, (L <= v).astype(float), 0.0) for v in GRIDS["len_ok"]}
        self.eye = np.array([r["eye"] for r in rows], float)
        self.deck = np.array([r.get("deck", "?") for r in rows])

    def predict(self, T):
        total = self.base + self.w_v * self.PV[T["dryup"]] + self.w_l * self.PL[T["len_ok"]]
        if self.w_t:
            total = total + self.w_t * self.PT[T["cluster_k"]]
        if self.w_o:
            total = total + self.w_o * self.PO[(T["ord_lo"], T["ord_hi"])]
        return total * self.scale

    def combos(self):
        grids = {"cluster_k": GRIDS["cluster_k"], "len_ok": GRIDS["len_ok"], "dryup": GRIDS["dryup"]}
        if "orderliness" in self.drop:
            for c in product(*(grids[k] for k in ("cluster_k", "len_ok", "dryup"))):
                yield {**T3, "cluster_k": c[0], "len_ok": c[1], "dryup": c[2]}
        else:
            for lo, hi in self.PO:
                for c in product(*(grids[k] for k in ("cluster_k", "len_ok", "dryup"))):
                    yield {**T3, "ord_lo": lo, "ord_hi": hi,
                           "cluster_k": c[0], "len_ok": c[1], "dryup": c[2]}


def assert_matches_score3(rows, drop=()):
    f = Fast(rows, drop=drop)
    for T in (T3, {**T3, "cluster_k": 6, "ord_lo": 0.15, "ord_hi": 0.45, "dryup": 1.2, "len_ok": 8}):
        got = f.predict(T)
        want = np.array([score3(r["sig"], r["prior_move"], r["sector_share"], "boolean", T,
                                drop=drop)["stars"] for r in rows])
        assert np.allclose(got, want, atol=1e-9), f"fast predictor diverged from score3 {drop}"


# --------------------------------------------------------------------------- the objectives

def _avg_rank(x):
    """Average ranks, so the discrete rubric's many ties are handled the way Spearman requires."""
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x), float)
    sx = x[order]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and sx[j + 1] == sx[i]:
            j += 1
        ranks[order[i:j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    return ranks


def spearman(pred, eye):
    if np.std(pred) == 0:
        return 0.0
    rp, re = _avg_rank(pred), _avg_rank(eye)
    if np.std(rp) == 0 or np.std(re) == 0:
        return 0.0
    return float(np.corrcoef(rp, re)[0, 1])


class Objective:
    """Pluggable loss over a `Fast` row set. Deck-aware: R6 section 2 ranks within deck."""

    def __init__(self, kind, fast, lam=0.0):
        self.kind, self.fast, self.lam = kind, fast, lam
        self.groups = [np.where(fast.deck == d)[0] for d in np.unique(fast.deck)]
        self.pairs = []
        for g in self.groups:
            e = fast.eye[g]
            I, J = np.triu_indices(len(g), 1)
            keep = np.abs(e[I] - e[J]) >= 1.0      # S1: pairs the eye can tell apart
            I, J = I[keep], J[keep]
            hi = np.where(e[I] > e[J], g[I], g[J])
            lo = np.where(e[I] > e[J], g[J], g[I])
            self.pairs.append((hi, lo))
        self.hi = np.concatenate([p[0] for p in self.pairs]) if self.pairs else np.array([], int)
        self.lo = np.concatenate([p[1] for p in self.pairs]) if self.pairs else np.array([], int)
        self.steps = _step_index()

    def _penalty(self, T):
        if not self.lam:
            return 0.0
        return self.lam * sum(abs(self.steps[k][T[k]] - self.steps[k][T3[k]]) for k in self.steps
                              if k in T)

    def loss(self, pred, T):
        if self.kind == "mae":
            base = float(np.abs(pred - self.fast.eye).mean())
        elif self.kind == "spearman":
            vals, ns = [], []
            for g in self.groups:
                vals.append(spearman(pred[g], self.fast.eye[g])); ns.append(len(g))
            base = 1.0 - float(np.average(vals, weights=ns))
        elif self.kind == "cindex":
            if len(self.hi) == 0:
                return 1.0
            d = pred[self.hi] - pred[self.lo]
            base = 1.0 - float((d > 0).mean() + 0.5 * (d == 0).mean())
        else:
            raise ValueError(self.kind)
        return base + self._penalty(T)


def _step_index():
    return {k: {v: i for i, v in enumerate(vals)} for k, vals in GRIDS.items()}


def fit(rows, kind, drop=(), lam=0.0, fast=None):
    """Exhaustive over the same grid rubric3.fit uses; ties break toward the incumbent T3."""
    f = fast or Fast(rows, drop=drop)
    obj = Objective(kind, f, lam=lam)
    best_T, best = dict(T3), obj.loss(f.predict(T3), T3)
    for T in f.combos():
        lv = obj.loss(f.predict(T), T)
        if lv < best - 1e-12:
            best, best_T = lv, T
    return best_T, best


# --------------------------------------------------------------------------- the protocol

def cv(rows, kind, drop=(), lam=0.0, seeds=SEEDS, eval_on=None):
    """5 folds x len(seeds) assignments. Returns per-assignment out-of-fold stats and every fit.

    `eval_on`: indices to score (R6 section 3 fits on a pool and scores on E3 only).
    """
    f = Fast(rows, drop=drop)
    eye = f.eye
    out, picked = [], []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        idx = rng.permutation(len(rows))
        pred = np.zeros(len(rows))
        for fold in range(FOLDS):
            te = idx[fold::FOLDS]
            tr = np.setdiff1d(np.arange(len(rows)), te)
            sub = Fast([rows[i] for i in tr], drop=drop)
            T, _ = fit(None, kind, drop=drop, lam=lam, fast=sub)
            picked.append(T)
            pred[te] = f.predict(T)[te]
        m = np.array(eval_on) if eval_on is not None else np.arange(len(rows))
        decks = f.deck[m]
        vals, ns = [], []
        for d in np.unique(decks):
            g = m[decks == d]
            vals.append(spearman(pred[g], eye[g])); ns.append(len(g))
        out.append({"rho": float(np.average(vals, weights=ns)),
                    "mae": float(np.abs(pred[m] - eye[m]).mean()),
                    "within1": float((np.abs(pred[m] - eye[m]) <= 1).mean()),
                    "r": float(np.corrcoef(pred[m], eye[m])[0, 1]) if np.std(pred[m]) else np.nan})
    return {"rho": float(np.median([o["rho"] for o in out])),
            "rho_lo": float(np.min([o["rho"] for o in out])),
            "rho_hi": float(np.max([o["rho"] for o in out])),
            "mae": float(np.median([o["mae"] for o in out])),
            "within1": float(np.median([o["within1"] for o in out])),
            "r": float(np.median([o["r"] for o in out])),
            "fits": picked, "per_seed": out}


def stability(picked, keys=("cluster_k", "ord_lo", "ord_hi", "len_ok", "dryup")):
    """R6 section 4: modal value, modal share, spread in grid steps, and the stable/unstable call."""
    steps = _step_index()
    rep = {}
    for key in keys:
        vals = [T[key] for T in picked if key in T]
        if not vals:
            continue
        uniq, counts = np.unique(np.array(vals, float), return_counts=True)
        mode = uniq[counts.argmax()]
        share = float(counts.max() / len(vals))
        gi = [steps[key][v] for v in vals if v in steps[key]]
        spread = (max(gi) - min(gi)) if gi else 0
        rep[key] = {"mode": float(mode), "share": share, "spread": int(spread),
                    "min": float(min(vals)), "max": float(max(vals)),
                    "stable": bool(share >= STABLE_SHARE and spread <= STABLE_STEPS)}
    return rep


def partial_spearman(x, y, z):
    """R6 section 7: Spearman partial, controlling z, on rank residuals."""
    m = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    if m.sum() < 20:
        return np.nan
    rx, ry, rz = _avg_rank(x[m]), _avg_rank(y[m]), _avg_rank(z[m])
    ex = rx - np.polyval(np.polyfit(rz, rx, 1), rz)
    ey = ry - np.polyval(np.polyfit(rz, ry, 1), rz)
    return float(np.corrcoef(ex, ey)[0, 1]) if ex.std() and ey.std() else np.nan


# --------------------------------------------------------------------------- the run

def show_stability(rep, indent="    "):
    for key, s in rep.items():
        flag = "stable" if s["stable"] else "UNSTABLE"
        print(f"{indent}{key:10s} mode {s['mode']:<6g} share {s['share']:.0%}  "
              f"range {s['min']:g}-{s['max']:g} ({s['spread']} steps)  {flag}")


def main():
    df = load_cards()
    pops = populations(df)
    print("populations: " + "  ".join(f"{k} n={len(v)}" for k, v in pops.items()))

    rows = {k: rows_of(v, k) for k, v in pops.items()}
    for k, rs in rows.items():
        assert_matches_score3(rs)
        assert_matches_score3(rs, drop=("orderliness",))
    print("fast predictor pinned to score3 on every population (kept and orderliness-dropped)\n")

    results = {}

    # ---- S1/S2: the three objectives on E3, the population ticket 20's decision was made on
    print("=== 1-2. the objectives, fitted and scored on E3 (R6 S2 primary criterion)")
    print(f"  {'objective':10s} {'median rho':>11s} {'range':>16s} {'mae':>6s} {'within1':>8s} {'pearson r':>10s}")
    for kind in ("mae", "spearman", "cindex"):
        res = cv(rows["E3"], kind)
        results[kind] = res
        print(f"  {kind:10s} {res['rho']:+11.3f} {res['rho_lo']:+7.3f}..{res['rho_hi']:+.3f} "
              f"{res['mae']:6.2f} {res['within1']:8.0%} {res['r']:+10.3f}")

    base = results["mae"]
    ranked = sorted(("spearman", "cindex"), key=lambda k: (-results[k]["rho"], k != "cindex"))
    challenger = ranked[0]
    gain = results[challenger]["rho"] - base["rho"]
    mae_cost = results[challenger]["mae"] - base["mae"]
    print(f"\n  best challenger: {challenger}  gain {gain:+.3f} rho (needs >= {MARGIN:+.3f})  "
          f"mae cost {mae_cost:+.2f} (guardrail {MAE_GUARDRAIL})")
    if gain >= MARGIN and mae_cost <= MAE_GUARDRAIL:
        winner = challenger
        print(f"  -> {winner.upper()} REPLACES mae as the fitting objective.")
    elif gain >= MARGIN:
        winner = "mae"
        print(f"  -> {challenger} wins on rank but BREAKS THE LEVEL GUARDRAIL. mae stands.")
    else:
        winner = "mae"
        print(f"  -> no challenger clears the margin. MAE STANDS, and the objective is not the culprit.")

    # ---- S4: stability of every objective, reported whichever won
    print("\n=== 4. threshold stability across the 25 fits (R6 S4)")
    for kind in ("mae", "spearman", "cindex"):
        print(f"  {kind}:")
        show_stability(stability(results[kind]["fits"]))

    # ---- S3: poolability
    print("\n=== 3. poolability under the winning objective (R6 S3)")
    e3_only = results[winner]["rho"]
    for label, parts in (("A3+E3", ("A3", "E3")), ("A3+E3+C3", ("A3", "E3", "C3"))):
        pooled_rows = [r for p in parts for r in rows[p]]
        e_idx = [i for i, r in enumerate(pooled_rows) if r["deck"] == "E3"]
        res = cv(pooled_rows, winner, eval_on=e_idx)
        delta = res["rho"] - e3_only
        verdict = "POOL" if delta >= -POOL_TOL else "do not pool"
        print(f"  {label:9s} n={len(pooled_rows):3d}  rho on E3 {res['rho']:+.3f}  "
              f"vs E3-only {e3_only:+.3f}  delta {delta:+.3f}  -> {verdict}")
        results[f"pool_{label}"] = res
        if delta >= -POOL_TOL:
            print("    stability of the pooled fit:")
            show_stability(stability(res["fits"]))

    # ---- S5: regularisation
    print("\n=== 5. regularisation toward the incumbent (R6 S5)")
    lam_res = {}
    for lam in LAMBDAS:
        res = cv(rows["E3"], winner, lam=lam)
        lam_res[lam] = res
        print(f"  lambda {lam:<6g} rho {res['rho']:+.3f}  mae {res['mae']:.2f}")
    best_lam = max(LAMBDAS, key=lambda l: lam_res[l]["rho"])
    lam_gain = lam_res[best_lam]["rho"] - lam_res[0.0]["rho"]
    if best_lam and lam_gain >= LAMBDA_GAIN:
        print(f"  -> lambda = {best_lam} ADOPTED (gain {lam_gain:+.3f} >= {LAMBDA_GAIN})")
    else:
        best_lam = 0.0
        print(f"  -> lambda = 0. Shrinkage was not needed (best gain {lam_gain:+.3f}).")

    # ---- S6: the orderliness verdict, re-run
    print("\n=== 6. orderliness, re-decided under the winning objective (R6 S6)")
    keep = cv(rows["E3"], winner, lam=best_lam)
    drop = cv(rows["E3"], winner, drop=("orderliness",), lam=best_lam)
    d = keep["rho"] - drop["rho"]
    st = stability(keep["fits"], keys=("ord_lo", "ord_hi"))
    stable = all(s["stable"] for s in st.values())
    print(f"  keep the band  rho {keep['rho']:+.3f}  mae {keep['mae']:.2f}")
    print(f"  drop it, x2 redistributed  rho {drop['rho']:+.3f}  mae {drop['mae']:.2f}")
    print(f"  keeping is worth {d:+.3f} rho (needs >= {ORD_GAIN:+.3f}); band stable: {stable}")
    show_stability(st)
    if d >= ORD_GAIN and stable:
        print("  -> ORDERLINESS IS RESTORED. Ticket 20's drop was an artefact of the objective.")
    elif d >= ORD_GAIN:
        print("  -> REAL BUT UNFITTABLE: the dimension carries signal the rubric cannot spend.")
        print("     It goes to the trader as a question about form, not a threshold.")
    else:
        print("  -> ticket 20's drop STANDS. The objective was not the culprit.")

    # ---- S7: the retired dimensions
    print("\n=== 7. the retired dimensions, re-measured (R6 S7)")
    cands = ["ma_dist_adr", "narrow_cluster", "narrowing_ratio", "sqrt_shortfall",
             "base_height_adr", "cluster_churn", "density"]
    pooled = pd.concat([pops["A3"], pops["E3"]], ignore_index=True)
    pooled["density"] = pooled.cluster_k / pooled.cluster_range_adr
    a3 = pooled[pooled.deck == "A"]; e3 = pooled[pooled.deck == "E"]
    print(f"  {'dimension':18s} {'pooled':>8s} {'A3':>8s} {'E3':>8s}   verdict")
    flagged = []
    for c in cands:
        if c not in pooled.columns:
            print(f"  {c:18s} (absent)")
            continue
        def pr(frame):
            return partial_spearman(frame[c].to_numpy(float), frame.eye.to_numpy(float),
                                    frame.base_len.to_numpy(float))
        p, pa, pe = pr(pooled), pr(a3), pr(e3)
        agree = np.isfinite(pa) and np.isfinite(pe) and (np.sign(pa) == np.sign(pe))
        flag = np.isfinite(p) and p >= PARTIAL_FLOOR and agree
        if flag:
            flagged.append(c)
        print(f"  {c:18s} {p:+8.3f} {pa:+8.3f} {pe:+8.3f}   "
              f"{'FLAGGED for reinstatement' if flag else 'correctly retired'}")
    # the two incumbents, for scale
    for c, label in (("cluster_k", "cluster_k (incumbent)"), ("orderliness", "orderliness (incumbent)")):
        p = partial_spearman(pooled[c].to_numpy(float), pooled.eye.to_numpy(float),
                             pooled.base_len.to_numpy(float))
        print(f"  {label:18s} {p:+8.3f}   (context, not a candidate)")
    print(f"\n  flagged: {flagged or 'none'} -> a new ticket if non-empty; R6 S7 forbids adopting here.")

    # ---- the published thresholds, under whatever won
    print("\n=== published thresholds (winner, on the adopted population)")
    pool_label = "A3+E3+C3" if results.get("pool_A3+E3+C3", {}).get("rho", -9) >= e3_only - POOL_TOL \
        else ("A3+E3" if results.get("pool_A3+E3", {}).get("rho", -9) >= e3_only - POOL_TOL else "E3")
    parts = {"E3": ("E3",), "A3+E3": ("A3", "E3"), "A3+E3+C3": ("A3", "E3", "C3")}[pool_label]
    final_rows = [r for p in parts for r in rows[p]]
    T_final, loss = fit(final_rows, winner, lam=best_lam)
    print(f"  objective {winner}  lambda {best_lam}  population {pool_label} (n={len(final_rows)})")
    print(f"  {T_final}   in-sample loss {loss:.4f}")
    print("  fold stability of this fit:")
    show_stability(stability(cv(final_rows, winner, lam=best_lam)["fits"]))
    json.dump({"objective": winner, "lambda": best_lam, "population": pool_label,
               "thresholds": {k: float(v) for k, v in T_final.items()}},
              open(os.path.join(HERE, "r6_result.json"), "w"), indent=2)
    print("\n  written: r6_result.json")


def selftest():
    """Pins the fast search to score3 and runs the protocol on synthetic grades."""
    rng = np.random.default_rng(6)
    df = load_cards().copy()
    df["eye"] = rng.integers(1, 6, len(df))
    pops = populations(df)
    rs = rows_of(pops["E3"], "E3")
    assert_matches_score3(rs)
    assert_matches_score3(rs, drop=("orderliness",))
    # The fast fit must agree with rubric3's own exhaustive search under mae. Compared on the rows
    # where the two predictors provably agree -- complete prior_move and sector_share -- since
    # rubric3._vector_predictor and score3 disagree on the rest (F0), and this assertion is about
    # the SEARCH, not that disagreement.
    rs = [r for r in rs if np.isfinite(r["prior_move"]) and np.isfinite(r["sector_share"])]
    f_T, _ = fit(rs, "mae")
    r_T, _ = RB.fit(rs, "boolean")
    pf = np.abs(Fast(rs).predict(f_T) - np.array([r["eye"] for r in rs])).mean()
    pr = np.abs(Fast(rs).predict(r_T) - np.array([r["eye"] for r in rs])).mean()
    assert abs(pf - pr) < 1e-9, f"fast mae fit {f_T} ({pf}) != rubric3 fit {r_T} ({pr})"
    print(f"selftest OK: fast search reaches rubric3.fit's optimum under mae (mae {pf:.4f})")
    for kind in ("spearman", "cindex"):
        T, lv = fit(rs, kind)
        print(f"  {kind}: loss {lv:.4f}  T {T}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        selftest()
    else:
        main()
