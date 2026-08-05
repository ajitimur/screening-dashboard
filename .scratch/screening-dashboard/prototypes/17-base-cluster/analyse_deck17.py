"""Score deck 17 against the arms it was built from.

Section 1 is the population question: three arms of 20, blind, no overlay that could identify one.
The comparison that decides the ticket is **split-only against 08-only** — the names each detector
adds that the other refuses. `shared` is the control: if the eye cannot separate the arms at all,
the deck has failed rather than answered, and shared should sit between them.

Section 2 is the geometry question, blind A/B with the side randomised per card.

Significance is by permutation (20,000 draws) rather than a t-test, because n=20 per arm and the
grades are ordinal — the same standard ticket 15's pre-registration used.
"""

import os
import sys
import json
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P16 = os.path.abspath(os.path.join(HERE, "..", "16-trendline-fit"))
sys.path.insert(0, P16)
CACHE = os.path.join(HERE, "cache")
OUT = os.path.join(HERE, "out")

import split as S            # noqa: E402
import build_deck17 as B     # noqa: E402

SEED = 17


def perm_diff(a, b, n=20000, seed=SEED):
    """Two-sided permutation p for a difference in means."""
    obs = np.mean(a) - np.mean(b)
    pool = np.concatenate([a, b])
    rng = np.random.default_rng(seed)
    k = len(a)
    hits = sum(abs(np.mean(p[:k]) - np.mean(p[k:])) >= abs(obs)
               for p in (rng.permutation(pool) for _ in range(n)))
    return obs, hits / n


def binom_p(k, n, seed=SEED):
    """Two-sided p that k of n votes went one way under a fair coin."""
    rng = np.random.default_rng(seed)
    draws = rng.binomial(n, 0.5, 40000)
    return float(np.mean(np.abs(draws - n / 2) >= abs(k - n / 2)))


def main(grades):
    man = pd.DataFrame(json.load(open(os.path.join(HERE, "deck17_key.json"))))
    g = list(grades.strip())
    if len(g) != len(man):
        raise SystemExit(f"expected {len(man)} grades, got {len(g)}")
    man["answer"] = g

    pop = man[man.section == "population"].copy()
    geo = man[man.section == "geometry"].copy()

    ungraded = (pop.answer == "-").sum() + (geo.answer == "-").sum()
    print(f"=== deck 17: {len(man)} cards, {ungraded} left blank")

    # ---------------------------------------------------------------- section 1
    pop = pop[pop.answer != "-"].copy()
    pop["eye"] = pop.answer.astype(int)
    print(f"\n--- section 1, the population question ({len(pop)} graded)")
    print(f"  {'arm':12s} {'n':>4s} {'mean':>7s} {'median':>7s} {'>=4':>7s} {'<=2':>7s}")
    stats = {}
    for arm in ("shared", "08 only", "split only"):
        s = pop[pop.arm == arm].eye.to_numpy(float)
        stats[arm] = s
        print(f"  {arm:12s} {len(s):>4d} {s.mean():>7.2f} {np.median(s):>7.1f} "
              f"{(s >= 4).mean():>7.1%} {(s <= 2).mean():>7.1%}")

    print("\n  the comparison the ticket turns on:")
    d, p = perm_diff(stats["split only"], stats["08 only"])
    print(f"    split-only minus 08-only: {d:+.2f} stars   permutation p = {p:.3f}")
    d2, p2 = perm_diff(stats["shared"], stats["08 only"])
    print(f"    shared    minus 08-only: {d2:+.2f} stars   permutation p = {p2:.3f}")
    d3, p3 = perm_diff(stats["shared"], stats["split only"])
    print(f"    shared    minus split-only: {d3:+.2f} stars   permutation p = {p3:.3f}")
    print(f"\n    a null result here is not a non-answer: the split costs 22 parameters and")
    print(f"    ticket 15's rubric, so 'the added names are no better' decides the ticket.")

    # ---------------------------------------------------------------- section 2
    geo = geo[geo.answer != "-"].copy()
    print(f"\n--- section 2, the geometry question ({len(geo)} graded)")
    geo["chose"] = [r.A if r.answer == "a" else (r.B if r.answer == "b" else "neither")
                    for _, r in geo.iterrows()]
    vc = geo.chose.value_counts()
    for k in ("t08", "split", "neither"):
        print(f"  {k:9s} {int(vc.get(k, 0)):>3d}")
    t, s = int(vc.get("t08", 0)), int(vc.get("split", 0))
    if t + s:
        print(f"  excluding 'neither': split {s}/{t+s}  binomial p = {binom_p(s, t + s):.3f}")
    print(f"  median base drawn: 08 {geo.t08_L.median():.0f} bars, split {geo.split_L.median():.0f}")

    # ------------------------------------------------- fresh check on F3 / cluster_k
    frames = {s_: S.clean(d)
              for s_, d in pd.read_pickle(os.path.join(CACHE, "universe_us.pkl")).items()}
    rows = []
    for _, r in pop.iterrows():
        d = frames.get(r.symbol)
        if d is None:
            continue
        gs = B.geom_split(d, int(r.end))
        g8 = B.geom_t08(d, int(r.end))
        rows.append({"eye": r.eye, "arm": r.arm,
                     "split_base_len": gs["L"] if gs else np.nan,
                     "cluster_k": (int(r.end) - int(gs["cluster_start"]) + 1) if gs else np.nan,
                     "t08_L": g8["L"] if g8 else np.nan})
    F = pd.DataFrame(rows)

    def corr(x, y):
        m = np.isfinite(x) & np.isfinite(y)
        return (np.corrcoef(x[m], y[m])[0, 1], int(m.sum())) if m.sum() > 5 else (np.nan, 0)

    print("\n--- out-of-sample check on the ticket-09 length finding (fresh grades)")
    for lab, col in (("split base length", "split_base_len"), ("08 primary window", "t08_L"),
                     ("cluster length k", "cluster_k")):
        r, n = corr(F[col].to_numpy(float), F.eye.to_numpy(float))
        print(f"  eye vs {lab:20s} r = {r:+.3f}  (n={n}, |r|>{1.96/np.sqrt(max(n-2,1)):.3f} for p<.05)")

    F.to_pickle(os.path.join(OUT, "deck17_grades.pkl"))
    pop.to_csv(os.path.join(OUT, "deck17_population.csv"), index=False)
    geo.to_csv(os.path.join(OUT, "deck17_geometry.csv"), index=False)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else open(os.path.join(HERE, "grades17.txt")).read())
