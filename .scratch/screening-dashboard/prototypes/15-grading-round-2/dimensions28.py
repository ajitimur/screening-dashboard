"""Ticket 28 — do the retired dimensions come back? Everything here is fixed by
PREREGISTRATION_R7.md, which was committed before this file was run.

    python dimensions28.py             the pre-registered run, in order (sections 1-5)
    python dimensions28.py --selftest  pins the extended predictor to rubric3.score3

Ticket 21 showed `mae` cannot identify a dimension the eye is demonstrably using, which makes its
verdicts on the six already-dropped dimensions suspect. Ticket 27 then adopted `cindex` and fixed
the pool at 432 cards. This module re-screens the six under the corrected rule (|rho|, not rho) and
fits the survivors under the adopted objective.

The one structural claim it rests on is eye-free: the six candidates are not six independent
dimensions but two families, each shadowing an incumbent, established from their mutual correlation
alone (R7 section 2). So the live question is almost entirely "is this a better representation of a
dimension the rubric already has" -- a swap -- rather than "is this something new".
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
sys.path.insert(0, HERE)
sys.path.insert(0, P09)

import rubric3 as RB                                   # noqa: E402
from rubric3 import GRIDS, T3, score3                  # noqa: E402
import analyse3 as A3                                  # noqa: E402
import objective6 as O6                                # noqa: E402
from objective6 import spearman, _avg_rank             # noqa: E402

CARDS_PKL = os.path.join(CACHE, "t28_cards.pkl")
RESULT_JSON = os.path.join(HERE, "r7_result.json")

# --- the pre-registered constants, R7 sections 2, 3, 5
SEEDS = (11, 12, 13, 14, 15)      # 5 fold assignments x 5 folds = 25 fits
FOLDS = 5
SCREEN_FLOOR = 0.15               # S2 stage 1, now read as |rho|
BAR_SWAP = 0.030                  # S3
BAR_ADD = 0.050                   # S3
STABLE_SHARE = 0.60               # S3, inherited from R6 S4
STABLE_STEPS = 2                  # S3
FROZEN = {"len_ok": 14, "dryup": 0.95}   # S5, held by ticket 27

# S2 stage 2 -- families, fixed from the eye-free correlation matrix.
FAMILY = {
    "cluster_churn": "packing", "density": "packing", "narrow_cluster": "packing",
    "narrowing_ratio": "shape", "base_height_adr": "shape", "ma_dist_adr": "shape",
    "sqrt_shortfall": "shape",
}
INCUMBENT_OF = {"packing": "cluster_k", "shape": "orderliness"}
SEAT_OF = {"packing": "tightness", "shape": "orderliness"}
CANDIDATES = ["cluster_churn", "density", "narrowing_ratio", "ma_dist_adr",
              "base_height_adr", "sqrt_shortfall", "narrow_cluster", "dryup"]


# --------------------------------------------------------------------------- populations

def load_cards():
    """The 432-card pool, deck F included. Cached: attaching signals costs a couple of minutes."""
    if os.path.exists(CARDS_PKL):
        return pd.read_pickle(CARDS_PKL)
    grades = {d: open(os.path.join(HERE, f"grades3_{d}.txt")).read().strip()
              for d in ("A", "C", "D", "E", "F")}
    df = A3.attach_signals(A3.load_cards(grades))
    df.to_pickle(CARDS_PKL)
    return df


def populations(df):
    """R7 section 1. Deck F joins on `tight & caught_up`, not `split_ok`: tickets 25 and 26
    demoted `line_ok` to a sort tiebreak, so its rejects are on the nightly list and the rubric
    that sorts that list has to be fitted on them."""
    return {
        "A3": df[(df.deck == "A") & df.split_ok],
        "E3": df[(df.deck == "E") & df.split_ok & (df.tag == "confirm")],
        "C3": df[(df.deck == "C") & df.split_ok & (df.market == "IDX") & (df.tag != "repeat")],
        "F3": df[(df.deck == "F") & df.tag.isin(["detection", "line_not_drawable"])
                 & df.tight & df.caught_up],
    }


def derived(df):
    """`density` is the one candidate not already in the signal vector."""
    out = df.copy()
    out["density"] = out.cluster_k / out.cluster_range_adr
    return out


def rows_of(df, label):
    return [{"sig": r.to_dict(), "prior_move": r.prior_move, "sector_share": r.sector_share,
             "eye": float(r.eye), "deck": label} for _, r in df.iterrows()]


# --------------------------------------------------------------------------- the predictor

def decile_grid(values):
    """R7 section 5: the 9 deciles of the candidate's own distribution over the 432 pool."""
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    g = [float(np.quantile(v, q)) for q in np.arange(0.1, 0.91, 0.1)]
    # collapse duplicates a lumpy distribution can produce, keeping order
    out = []
    for x in g:
        if not out or x > out[-1]:
            out.append(x)
    return out


class Fast28:
    """`objective6.Fast`, extended with one candidate dimension in a named role.

    role is one of:
      None       the baseline rubric, and then this is `objective6.Fast` exactly
      "swap"     the candidate replaces its incumbent in that incumbent's x2 seat
      "add"      the candidate joins at x1, and the /2 denominator grows by one

    The baseline path is asserted equal to `rubric3.score3` before any number is computed
    (R7 section 6): the pool contains IDX cards, which are exactly the cards that expose the
    fast-path/score3 NaN disagreement.
    """

    def __init__(self, rows, cand=None, role=None, direction=+1, cgrid=None, seat=None):
        self.rows, self.cand, self.role = rows, cand, role
        self.direction, self.seat = direction, seat
        n = len(rows)
        k = np.full(n, np.nan); o = np.full(n, np.nan)
        du = np.full(n, np.nan); L = np.full(n, np.nan); c = np.full(n, np.nan)
        fixed_total = np.zeros(n); fixed_max = np.zeros(n)
        for i, r in enumerate(rows):
            sig = r["sig"]
            for arr, key in ((k, "cluster_k"), (o, "orderliness"), (du, "dryup"), (L, "L_true")):
                v = RB._num(sig.get(key))
                arr[i] = np.nan if v is None else v
            if cand is not None:
                v = RB._num(sig.get(cand))
                c[i] = np.nan if v is None else v
            # score3 is the rubric of record; see objective6.Fast for why this arithmetic and not
            # rubric3._vector_predictor's.
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
        self.w_t, self.w_o, self.w_v, self.w_l = 2.0, 2.0, 1.0, 1.0
        self.w_c = 1.0 if role == "add" else 0.0
        # a swap leaves the denominator alone (R7 S4); an addition grows it by one
        self.scale = 5.0 / (fixed_max + self.w_t + self.w_o + self.w_v
                            + self.w_c + self.w_l * hasL)
        self.base = fixed_total

        self.PT = {v: np.where(np.isfinite(k), (k >= v).astype(float), 0.5)
                   for v in GRIDS["cluster_k"]}
        self.PO = {(lo, hi): np.where(np.isfinite(o), ((o >= lo) & (o <= hi)).astype(float), 0.5)
                   for lo in GRIDS["ord_lo"] for hi in GRIDS["ord_hi"] if hi > lo}
        self.PV = {v: np.where(np.isfinite(du), (du <= v).astype(float), 0.5)
                   for v in GRIDS["dryup"]}
        self.PL = {v: np.where(hasL, (L <= v).astype(float), 0.0) for v in GRIDS["len_ok"]}
        self.cgrid = list(cgrid or [])
        self.PC = {v: np.where(np.isfinite(c),
                               ((c >= v) if direction > 0 else (c <= v)).astype(float), 0.5)
                   for v in self.cgrid}
        self.eye = np.array([r["eye"] for r in rows], float)
        self.deck = np.array([r.get("deck", "?") for r in rows])

    # -- the seat wiring, R7 section 5
    def _tight_pts(self, T):
        if self.role == "swap" and self.seat == "tightness":
            return self.PC[T["cand"]]
        return self.PT[T["cluster_k"]]

    def _order_pts(self, T):
        if self.role == "swap" and self.seat == "orderliness":
            return self.PC[T["cand"]]
        return self.PO[(T["ord_lo"], T["ord_hi"])]

    def predict(self, T):
        total = (self.base
                 + self.w_t * self._tight_pts(T)
                 + self.w_o * self._order_pts(T)
                 + self.w_v * self.PV[T["dryup"]]
                 + self.w_l * self.PL[T["len_ok"]])
        if self.w_c:
            total = total + self.w_c * self.PC[T["cand"]]
        return total * self.scale

    def combos(self):
        """`len_ok` and `dryup` are frozen by ticket 27, so neither is searched."""
        fixed = {**T3, **FROZEN}
        ks = GRIDS["cluster_k"]
        ords = list(self.PO)
        if self.role == "swap" and self.seat == "tightness":
            for cv, (lo, hi) in product(self.cgrid, ords):
                yield {**fixed, "cand": cv, "ord_lo": lo, "ord_hi": hi}
        elif self.role == "swap" and self.seat == "orderliness":
            for cv, kk in product(self.cgrid, ks):
                yield {**fixed, "cand": cv, "cluster_k": kk}
        elif self.role == "add":
            for cv, kk, (lo, hi) in product(self.cgrid, ks, ords):
                yield {**fixed, "cand": cv, "cluster_k": kk, "ord_lo": lo, "ord_hi": hi}
        else:
            for kk, (lo, hi) in product(ks, ords):
                yield {**fixed, "cluster_k": kk, "ord_lo": lo, "ord_hi": hi}

    def free_keys(self):
        if self.role == "swap" and self.seat == "tightness":
            return ("cand", "ord_lo", "ord_hi")
        if self.role == "swap" and self.seat == "orderliness":
            return ("cand", "cluster_k")
        if self.role == "add":
            return ("cand", "cluster_k", "ord_lo", "ord_hi")
        return ("cluster_k", "ord_lo", "ord_hi")


def assert_baseline_matches_score3(rows):
    """R7 section 6. The baseline arm must be `score3`, exactly, on every card in the pool."""
    f = Fast28(rows)
    for T in ({**T3, **FROZEN},
              {**T3, **FROZEN, "cluster_k": 6, "ord_lo": 0.15, "ord_hi": 0.45}):
        got = f.predict(T)
        want = np.array([score3(r["sig"], r["prior_move"], r["sector_share"], "boolean", T)
                         ["stars"] for r in rows])
        assert np.allclose(got, want, atol=1e-9), "Fast28 baseline diverged from score3"


# --------------------------------------------------------------------------- the protocol

def cindex_loss(pred, fast, pairs):
    hi, lo = pairs
    if len(hi) == 0:
        return 1.0
    d = pred[hi] - pred[lo]
    return 1.0 - float((d > 0).mean() + 0.5 * (d == 0).mean())


def make_pairs(fast):
    """R6 section 1's rule, unchanged: rank within deck, on pairs the eye can tell apart."""
    His, Los = [], []
    for d in np.unique(fast.deck):
        g = np.where(fast.deck == d)[0]
        e = fast.eye[g]
        I, J = np.triu_indices(len(g), 1)
        keep = np.abs(e[I] - e[J]) >= 1.0
        I, J = I[keep], J[keep]
        His.append(np.where(e[I] > e[J], g[I], g[J]))
        Los.append(np.where(e[I] > e[J], g[J], g[I]))
    return (np.concatenate(His) if His else np.array([], int),
            np.concatenate(Los) if Los else np.array([], int))


def fit(fast):
    """Exhaustive over the pre-registered grid; ties break toward the incumbent (R7 S3)."""
    pairs = make_pairs(fast)
    best_T, best = None, np.inf
    for T in fast.combos():
        lv = cindex_loss(fast.predict(T), fast, pairs)
        if lv < best - 1e-12:
            best, best_T = lv, T
    return best_T, best


def cv(rows, **kw):
    """5 folds x 5 assignments, deck-weighted out-of-fold rho. The protocol objective6.cv runs."""
    full = Fast28(rows, **kw)
    out, picked = [], []
    for seed in SEEDS:
        rng = np.random.default_rng(seed)
        idx = rng.permutation(len(rows))
        pred = np.zeros(len(rows))
        for fold in range(FOLDS):
            te = idx[fold::FOLDS]
            tr = np.setdiff1d(np.arange(len(rows)), te)
            sub = Fast28([rows[i] for i in tr], **kw)
            T, _ = fit(sub)
            picked.append(T)
            pred[te] = full.predict(T)[te]
        vals, ns = [], []
        for d in np.unique(full.deck):
            g = np.where(full.deck == d)[0]
            vals.append(spearman(pred[g], full.eye[g])); ns.append(len(g))
        out.append({"rho": float(np.average(vals, weights=ns)),
                    "mae": float(np.abs(pred - full.eye).mean()),
                    "within1": float((np.abs(pred - full.eye) <= 1).mean())})
    return {"rho": float(np.median([o["rho"] for o in out])),
            "rho_lo": float(np.min([o["rho"] for o in out])),
            "rho_hi": float(np.max([o["rho"] for o in out])),
            "mae": float(np.median([o["mae"] for o in out])),
            "within1": float(np.median([o["within1"] for o in out])),
            "fits": picked, "per_seed": out, "keys": full.free_keys()}


def stability(picked, keys, cgrid=None):
    """R7 section 3 / R6 section 4: modal value, modal share, spread in grid steps."""
    steps = {k: {v: i for i, v in enumerate(vals)} for k, vals in GRIDS.items()}
    if cgrid:
        steps["cand"] = {v: i for i, v in enumerate(cgrid)}
    rep = {}
    for key in keys:
        vals = [T[key] for T in picked if key in T]
        if not vals:
            continue
        uniq, counts = np.unique(np.array(vals, float), return_counts=True)
        share = float(counts.max() / len(vals))
        gi = [steps[key][v] for v in vals if key in steps and v in steps[key]]
        spread = (max(gi) - min(gi)) if gi else 0
        rep[key] = {"mode": float(uniq[counts.argmax()]), "share": share, "spread": int(spread),
                    "min": float(min(vals)), "max": float(max(vals)),
                    "stable": bool(share >= STABLE_SHARE and spread <= STABLE_STEPS)}
    return rep


def show_stability(rep, indent="      "):
    for key, s in rep.items():
        print(f"{indent}{key:9s} mode {s['mode']:<7g} share {s['share']:.0%}  "
              f"range {s['min']:g}-{s['max']:g} ({s['spread']} steps)  "
              f"{'stable' if s['stable'] else 'UNSTABLE'}")


def partial(frame, c, controls):
    """Spearman partial of candidate against the eye, controlling `controls`, on rank residuals."""
    cols = [c, "eye"] + list(controls)
    d = frame[cols].astype(float)
    d = d[np.isfinite(d).all(axis=1)]
    if len(d) < 20:
        return np.nan
    R = {k: _avg_rank(d[k].to_numpy(float)) for k in cols}
    Z = np.column_stack([np.ones(len(d))] + [R[k] for k in controls])
    def resid(y):
        beta, *_ = np.linalg.lstsq(Z, y, rcond=None)
        return y - Z @ beta
    ex, ey = resid(R[c]), resid(R["eye"])
    return float(np.corrcoef(ex, ey)[0, 1]) if ex.std() and ey.std() else np.nan


# --------------------------------------------------------------------------- the run

def main():
    df = derived(load_cards())
    P = populations(df)
    pool = pd.concat(P.values(), ignore_index=True)
    print("=" * 78)
    print("Ticket 28 — the retired dimensions, under PREREGISTRATION_R7.md")
    print("=" * 78)
    print("populations: " + "  ".join(f"{k} n={len(v)}" for k, v in P.items())
          + f"   pool n={len(pool)}")

    rows = [r for k, v in P.items() for r in rows_of(v, k)]
    assert_baseline_matches_score3(rows)
    print("baseline predictor pinned to score3 on all 432 cards (R7 S6)\n")

    # ---- S2: the screen
    print("=== 1. the screen (R7 S2): |rho| >= 0.15, controlling base_len, signs agreeing")
    print(f"  {'candidate':18s} {'|rho| 432':>10s} {'A3':>7s} {'E3':>7s} {'C3':>7s} {'F3':>7s} "
          f"{'family':>8s}  verdict")
    screened = {}
    for c in CANDIDATES:
        p = partial(pool, c, ["base_len"])
        per = [partial(derived(P[k]), c, ["base_len"]) for k in ("A3", "E3", "C3", "F3")]
        agree = all(np.isfinite(v) for v in per) and len({np.sign(v) for v in per}) == 1
        ok = np.isfinite(p) and abs(p) >= SCREEN_FLOOR and agree
        screened[c] = {"rho": p, "per_deck": per, "agree": agree, "pass": ok,
                       "family": FAMILY.get(c)}
        why = "passes" if ok else ("fails floor" if abs(p) < SCREEN_FLOOR else "signs disagree")
        if not ok and abs(p) < SCREEN_FLOOR and not agree:
            why = "fails floor + signs"
        print(f"  {c:18s} {p:+10.3f} " + " ".join(f"{v:+7.3f}" for v in per)
              + f" {str(FAMILY.get(c)):>8s}  {why}")
    for c in ("cluster_k", "orderliness"):
        print(f"  {c + ' (incumbent)':18s} {partial(pool, c, ['base_len']):+10.3f}")

    # ---- S2 stage 3: one seat per family
    print("\n=== 2. one seat per family (R7 S2 stage 3)")
    carried = {}
    for fam in ("packing", "shape"):
        members = [c for c in CANDIDATES if screened[c]["family"] == fam and screened[c]["pass"]]
        if not members:
            print(f"  {fam:8s} nothing passes the screen")
            continue
        best = max(members, key=lambda c: abs(screened[c]["rho"]))
        carried[fam] = best
        others = [f"{c} {screened[c]['rho']:+.3f}" for c in members if c != best]
        print(f"  {fam:8s} carries {best} ({screened[best]['rho']:+.3f})"
              + (f"; screened out as same-family: {', '.join(others)}" if others else ""))

    # ---- reported, not decisive: how much of each candidate is new
    print("\n=== 3. how much of each candidate is new (R7 S2, diagnostic only)")
    print(f"  {'candidate':18s} {'ctrl len':>9s} {'+ incumbents':>13s}")
    for c in CANDIDATES:
        if not np.isfinite(screened[c]["rho"]):
            continue
        ctrl = ["base_len", "cluster_k", "orderliness"]
        ctrl = [x for x in ctrl if x != c]
        print(f"  {c:18s} {screened[c]['rho']:+9.3f} {partial(pool, c, ctrl):+13.3f}")

    # ---- S5: the fits
    print("\n=== 4. the fits (R7 S5), objective cindex, len_ok=14 and dryup=0.95 frozen")
    base = cv(rows)
    print(f"\n  BASELINE (incumbent rubric)   rho {base['rho']:+.3f} "
          f"[{base['rho_lo']:+.3f}..{base['rho_hi']:+.3f}]  mae {base['mae']:.2f}  "
          f"within1 {base['within1']:.0%}")
    show_stability(stability(base["fits"], base["keys"]))

    results = {"baseline": {k: base[k] for k in ("rho", "rho_lo", "rho_hi", "mae", "within1")}}
    adopted = []
    for fam, c in carried.items():
        grid = decile_grid(pool[c])
        direction = 1 if screened[c]["rho"] > 0 else -1
        seat = SEAT_OF[fam]
        for role, bar in (("swap", BAR_SWAP), ("add", BAR_ADD)):
            kw = dict(cand=c, role=role, direction=direction, cgrid=grid, seat=seat)
            res = cv(rows, **kw)
            gain = res["rho"] - base["rho"]
            st = stability(res["fits"], res["keys"], cgrid=grid)
            stable = st["cand"]["stable"]
            verdict = "ADOPTED" if (gain >= bar and stable) else "rejected"
            label = (f"{role.upper()} {c} -> {seat} seat" if role == "swap"
                     else f"ADD {c} at x1")
            print(f"\n  {label}   rho {res['rho']:+.3f} "
                  f"[{res['rho_lo']:+.3f}..{res['rho_hi']:+.3f}]  mae {res['mae']:.2f}  "
                  f"within1 {res['within1']:.0%}")
            print(f"      gain {gain:+.3f} (bar {bar:+.3f})  candidate stable: {stable}"
                  f"   -> {verdict}")
            show_stability(st)
            results[f"{role}:{c}"] = {"rho": res["rho"], "gain": gain, "bar": bar,
                                      "stable": stable, "verdict": verdict,
                                      "mode": st["cand"]["mode"], "grid": grid,
                                      "direction": direction, "seat": seat}
            if verdict == "ADOPTED":
                adopted.append((role, c, seat, gain))

    # ---- the verdict
    print("\n=== 5. the pre-registered verdict (R7 S3, S8)\n")
    if not adopted:
        print("  NOTHING CLEARS. Every retired dimension stays retired, and the incumbent")
        print("  rubric is the right shape (R7 S10). The |rho| fix and the enlarged pool were")
        print("  applied as pre-registered; the gains are simply not there.")
    else:
        for role, c, seat, gain in adopted:
            print(f"  {role.upper()} {c} into the {seat} seat, +{gain:.3f} rho — ADOPTED (R7 S8).")
    json.dump({"pool": int(len(pool)), "carried": carried, "adopted": adopted,
               "results": results}, open(RESULT_JSON, "w"), indent=2, default=float)
    print(f"\n  written: {os.path.basename(RESULT_JSON)}")


def selftest():
    df = derived(load_cards())
    P = populations(df)
    rows = [r for k, v in P.items() for r in rows_of(v, k)]
    assert_baseline_matches_score3(rows)
    # the baseline arm must also equal objective6.Fast, the predictor every published number used
    f28, f6 = Fast28(rows), O6.Fast(rows)
    T = {**T3, **FROZEN}
    assert np.allclose(f28.predict(T), f6.predict(T), atol=1e-9), "Fast28 != objective6.Fast"
    # a swap must leave the denominator alone; an addition must grow it by exactly one
    g = decile_grid(df.cluster_churn)
    sw = Fast28(rows, cand="cluster_churn", role="swap", cgrid=g, seat="tightness")
    ad = Fast28(rows, cand="cluster_churn", role="add", cgrid=g, seat="tightness")
    assert np.allclose(sw.scale, f28.scale), "swap moved the /2 denominator"
    # scale is 5/denominator, so the denominator is 5/scale
    assert np.allclose(5 / ad.scale - 5 / f28.scale, 1.0), "addition did not grow it by one"
    # a swap at a threshold below the whole grid awards the point to everyone, so the seat is
    # full — which must equal a saturated incumbent seat, the point being that only the *test*
    # in the seat changed and not the seat's weight or the arithmetic around it
    sentinel = min(g) - 1e9
    sw2 = Fast28(rows, cand="cluster_churn", role="swap", cgrid=[sentinel], seat="tightness")
    sat = Fast28(rows)
    sat.PT[sentinel] = np.ones(len(rows))
    assert np.allclose(sw2.predict({**T, "cand": sentinel}),
                       sat.predict({**T, "cluster_k": sentinel})), \
        "swap seat wiring disagrees with a saturated incumbent seat"
    print("selftest OK: baseline == score3 == objective6.Fast; seat and denominator wiring sound")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        selftest()
    else:
        main()
