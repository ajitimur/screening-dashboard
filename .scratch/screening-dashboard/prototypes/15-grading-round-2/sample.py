"""Draw the four decks exactly as PREREGISTRATION.md §2 specifies. Seed 15, nothing adaptive.

Writes cache/picks_r2.pkl — a list of card specs. Rendering is build_deck2.py's job; keeping the
sampling in its own file means the deck can be re-rendered without re-drawing the sample.
"""

import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
sys.path.insert(0, P09)
CACHE = os.path.join(P09, "cache")

SEED = 15
BANDS = [(0, 1.5, "≤1.5★"), (1.5, 2.5, "2★"), (2.5, 3.5, "3★"), (3.5, 4.5, "4★"), (4.5, 5.01, "5★")]
DECK_A = 120               # the pre-registered size; split evenly over the bands that exist
PROBE_ARM = 26
FN_PER_REASON = 10
N_REPEATS = 12
MAX_PER_SYMBOL = 2


def band_of(x):
    for lo, hi, lab in BANDS:
        if lo <= x < hi:
            return lab
    return BANDS[-1][2]


def take(df, n, rng, seen, max_per_symbol=MAX_PER_SYMBOL):
    """Sample n rows, honouring a per-symbol cap across the whole draw."""
    out = []
    for _, r in df.sample(frac=1.0, random_state=rng.integers(1 << 30)).iterrows():
        if seen.get(r.symbol, 0) >= max_per_symbol:
            continue
        seen[r.symbol] = seen.get(r.symbol, 0) + 1
        out.append(r)
        if len(out) == n:
            break
    return out


def draw_matched(arm_a, arm_b, n, rng, seen, add, deck, market, tag_a, tag_b):
    """Draw n from each arm, matching arm B's star-band mix to arm A's.

    Largest-remainder allocation, then a top-up pass, so each arm lands on exactly n even when a
    band runs dry — the probes are powered for a 1-star difference and lose that power quickly if
    the arms come in short.
    """
    mix = arm_a.band.value_counts(normalize=True) * n
    alloc = {lab: int(np.floor(v)) for lab, v in mix.items()}
    for lab in sorted(mix.index, key=lambda l: -(mix[l] - np.floor(mix[l])))[: n - sum(alloc.values())]:
        alloc[lab] += 1
    for src, tag in ((arm_a, tag_a), (arm_b, tag_b)):
        got = 0
        for lab, k in alloc.items():
            rows = take(src[src.band == lab], k, rng, seen)
            for r in rows:
                add(r, deck, market, tag)
            got += len(rows)
        if got < n:  # band ran dry — top up from the arm as a whole
            for r in take(src, n - got, rng, seen, max_per_symbol=3):
                add(r, deck, market, tag)


def main():
    rng = np.random.default_rng(SEED)
    us = pd.read_pickle(os.path.join(CACHE, "pool_us.pkl"))
    idx = pd.read_pickle(os.path.join(CACHE, "pool_idx.pkl"))
    rej = pd.read_pickle(os.path.join(CACHE, "rejects_us.pkl"))

    us["risk_pct"] = (us.trigger - us.base_low) / us.trigger
    idx["risk_pct"] = (idx.trigger - idx.base_low) / idx.trigger
    gated = us[(us.prior_move >= 0.90) & (us.risk_pct >= 0.005)].copy()
    gated["band"] = gated.stars2.map(band_of)
    idx = idx[idx.risk_pct >= 0.005].copy()
    idx["band"] = idx.stars2.map(band_of)

    picks, seen = [], {}

    def add(r, deck, market, tag, repeat_of=None):
        picks.append({"symbol": r["symbol"], "row": r, "deck": deck, "market": market,
                      "tag": tag, "repeat_of": repeat_of})

    # ---- deck A: DECK_A cards, split evenly over the bands that are actually populated.
    # Under the round-2 rubric nothing gated scores below 1.5*, because ticket 09's "unmeasurable
    # scores neutral, not zero" lifted the floor. An empty band is not a reason to grade a smaller
    # deck, so the allocation is recomputed over the bands that exist, and short bands are topped
    # up from the largest one. Decided here, before any card was graded.
    live = [lab for _, _, lab in BANDS if len(gated[gated.band == lab])]
    per = DECK_A // len(live)
    for lab in live:
        g = gated[gated.band == lab]
        got = take(g, per, rng, seen)
        for r in got:
            add(r, "A", "US", f"core · {lab}")
        if len(got) < per:
            print(f"  band {lab}: only {len(got)} of {per} available")
    short = DECK_A - len(picks)
    if short > 0:
        biggest = max(live, key=lambda l: len(gated[gated.band == l]))
        for r in take(gated[gated.band == biggest], short, rng, seen, max_per_symbol=3):
            add(r, "A", "US", f"core · {biggest}")
    n_a = len(picks)

    # ---- deck B: trigger already breached vs comfortably above, band-matched
    breached = gated[gated.trig_vs_close <= 0]
    above = gated[gated.trig_vs_close >= 0.02]
    draw_matched(breached, above, PROBE_ARM, rng, seen, add, "B", "US",
                 "trigger already breached", "trigger ≥ 2% above close")

    # ---- deck C: IDX partial lock vs clean, band-matched
    part = idx[(idx.zero_rng_in_base > 0) & (idx.zero_rng_in_base <= 0.20)]
    cleanb = idx[idx.zero_rng_in_base == 0]
    draw_matched(part, cleanb, PROBE_ARM, rng, seen, add, "C", "IDX",
                 "IDX · partial limit-lock", "IDX · no collapsed bars")

    # ---- deck D: rejects vs detections, overlays off for every card
    for reason in ("no_window", "stop_too_wide"):
        g = rej[rej.reason == reason]
        if not len(g):
            print(f"  !! no rejects of type {reason}")
            continue
        for r in take(g, FN_PER_REASON, rng, seen):
            add(r, "D", "US", f"reject · {reason}")
    for r in take(gated, 2 * FN_PER_REASON, rng, seen):
        add(r, "D", "US", "detection")

    # ---- repeats: 12 deck-A cards re-shown later
    a_cards = [p for p in picks if p["deck"] == "A"]
    rep_idx = rng.choice(len(a_cards), size=N_REPEATS, replace=False)
    for j, k in enumerate(rep_idx):
        src = a_cards[int(k)]
        target = "BC"[j % 2]   # never deck D: it asks a different question, so an
                              # A/D pair would not measure the same instrument twice
        picks.append({**src, "deck": target, "tag": src["tag"], "repeat_of": int(k)})

    pd.to_pickle(picks, os.path.join(CACHE, "picks_r2.pkl"))
    df = pd.DataFrame([{"deck": p["deck"], "tag": p["tag"], "repeat": p["repeat_of"] is not None}
                       for p in picks])
    print(f"deck A core cards: {n_a}")
    print(df.groupby(["deck", "tag"]).size().to_string())
    print("\ntotal cards:", len(picks), " repeats:", int(df.repeat.sum()))


if __name__ == "__main__":
    main()
