"""Render deck E3 — the orderliness band's confirmation set. Seed 20.

PREREGISTRATION_R4.md fixes everything here; this file only executes it. Deck E3 is A3's deck
built again on the same population with the same renderer and the same question, with two
differences:

  1. every card A3, C3 or D3 already used is excluded, so the grades are fresh
  2. 194 cards instead of 120 — R3 section 2's row for the r = +0.20 bar the band must clear

Plus 12 repeats drawn from A3, disjoint from the 12 hidden in C3 and D3, so E3 measures the
test-retest ceiling on its own.

Writes deck3_E.html and deckE_manifest.csv. deck3_manifest.csv is NOT touched — A3's graded
string indexes against it.
"""

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from build_deck3 import (BANDS, CACHE, frames, population, render,   # noqa: E402
                         stratify, DECK_JS_KEY)
import ranks as R                                                    # noqa: E402

SEED = 20
N_E = 194          # R4 section 2 — R3 section 2's r = 0.20 row
N_REPEAT = 12      # R4 section 4


def already_used():
    """Every (symbol, end) any round-3 deck has shown. A card the eye has seen is not evidence."""
    man = pd.read_csv(os.path.join(HERE, "deck3_manifest.csv"))
    return {(str(r.symbol), int(r.end)) for _, r in man.iterrows()}


def a3_cards():
    """A3's cards, as the pool the 12 repeats are drawn from — minus the 12 already repeated."""
    man = pd.read_csv(os.path.join(HERE, "deck3_manifest.csv"))
    a = man[man.deck == "A"]
    spent = {(str(r.symbol), int(r.end)) for _, r in man[man.tag == "repeat"].iterrows()}
    out = []
    for _, r in a.iterrows():
        if (str(r.symbol), int(r.end)) in spent:
            continue
        d = r.to_dict()
        d["stars"] = d.pop("provisional", None)
        # the renderer spreads the card dict into the manifest row, so A3's own deck/card
        # labels have to come off or they overwrite E3's and the deck lengths stop matching
        d.pop("deck", None)
        d.pop("card", None)
        d.pop("tag", None)
        d.pop("reason", None)
        out.append(d)
    return out


def main():
    rk, _, _ = R.load_or_build()
    sectors = pd.read_pickle(os.path.join(CACHE, "sectors_us.pkl"))
    fr = {"US": frames("US")}
    rng = np.random.default_rng(SEED)

    print("sampling the US population...", flush=True)
    pop = population("US", rk, sectors, fr["US"])
    print(f"  {len(pop)} scored US detections; band mix "
          f"{pop.band.value_counts().sort_index().to_dict()}")

    used = already_used()
    fresh = pop[~pop.apply(lambda r: (str(r.symbol), int(r.end)) in used, axis=1)]
    print(f"  {len(pop) - len(fresh)} already shown in a round-3 deck; {len(fresh)} fresh")

    cards = stratify(fresh, N_E, rng)
    for c in cards:
        c["tag"] = "confirm"
    print(f"  deck E3: {len(cards)} fresh cards, band mix "
          f"{pd.Series([c['band'] for c in cards]).value_counts().sort_index().to_dict()}")
    if len(cards) < N_E:
        print(f"  NOTE: pool supplied {len(cards)} of {N_E}; the shortfall is reported, not hidden")

    pool = a3_cards()
    reps = [dict(pool[i]) for i in rng.choice(len(pool), N_REPEAT, replace=False)]
    for r in reps:
        r["tag"] = "repeat"
    print(f"  + {len(reps)} repeats drawn from A3 (disjoint from C3/D3's 12)")

    all_cards = cards + reps
    rng.shuffle(all_cards)

    print("rendering...", flush=True)
    DECK_JS_KEY["E"] = "wf15r3E"
    meta = render("E", all_cards, fr, "Round 3 — the confirmation deck",
                  f"{len(all_cards)} charts, rendered exactly as the core deck was: plain candles "
                  "and §2's moving averages, no base, no cluster, no trigger, no stop. Same "
                  "question, fresh names. This deck exists to test one thing &mdash; whether the "
                  "<b>orderliness band</b>, which was chosen after the core deck was graded, "
                  "survives on cards it was not fitted to. It is long because the bar it has to "
                  "clear is a correlation of +0.20, and that needs the cards. <b>Any prefix is a "
                  "valid sample</b>, so stopping early costs power, not honesty.")

    m = pd.DataFrame(meta)
    m.to_csv(os.path.join(HERE, "deckE_manifest.csv"), index=False)
    with open(os.path.join(HERE, "deckE_key.json"), "w") as f:
        json.dump(meta, f, indent=1, default=str)
    print(f"\ntotal {len(m)} cards")
    print(m.groupby("tag").size().to_string())


if __name__ == "__main__":
    main()
