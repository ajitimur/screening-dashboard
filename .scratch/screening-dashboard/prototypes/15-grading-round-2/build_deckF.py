"""Render deck F, exactly as PREREGISTRATION_DECK_F.md specifies. Seed 25.

105 cards, every one bare — candles and §2's moving averages, nothing else. Three arms drawn from
one gated population differing in exactly one bit, plus 6 repeats:

  33  detections            tight & line_ok & caught_up
  33  line_not_drawable     tight & ~line_ok & caught_up      <- the primary question
  33  not_caught_up         tight & line_ok & ~caught_up      <- secondary, descriptive
   6  repeats from A3       for the ceiling, disjoint from the 24 already used

Every arm is US, move_gain >= 25%, prior_move >= 0.90 (D15), drawn at RANDOM — no stratification,
because the statistic is a mean-grade difference. Deck D3 stratified one arm and not the other,
and gated one arm and not the other; §1 of the pre-registration measures what that cost.

Writes deckF.html, deckF_manifest.csv and deckF_key.json.
"""

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
P16 = os.path.abspath(os.path.join(HERE, "..", "16-trendline-fit"))
P17 = os.path.abspath(os.path.join(HERE, "..", "17-base-cluster"))
for p in (P09, P16, P17):
    sys.path.insert(0, p)
CACHE = os.path.join(P09, "cache")

import chart17                              # noqa: E402
import ranks as R                           # noqa: E402
import split as S                           # noqa: E402
from build_deck17 import CSS, JS            # noqa: E402
from rubric3 import score3                  # noqa: E402
from split_signals import signals_at        # noqa: E402

SEED = 25
DECILE = 0.90
MOVE_FLOOR = 25.0
N_ARM = 33
N_REPEAT = 6
MAX_PER_SYMBOL = 2

ARMS = {
    "detection":         lambda d: d.tight & d.line_ok & d.caught_up,
    "line_not_drawable": lambda d: d.tight & ~d.line_ok & d.caught_up,
    "not_caught_up":     lambda d: d.tight & d.line_ok & ~d.caught_up,
}


def frames():
    return {s: S.clean(d)
            for s, d in pd.read_pickle(os.path.join(CACHE, "universe_us.pkl")).items()}


def seen_before():
    """Every (symbol, end) any deck has already shown the eye."""
    out = set()
    for name in ("deck3_manifest.csv", "deckE_manifest.csv"):
        p = os.path.join(HERE, name)
        if os.path.exists(p):
            m = pd.read_csv(p)
            out |= {(r.symbol, int(r.end)) for _, r in m.iterrows()}
    return out


def draw(pool, rk, fr, n, tag, used, rng):
    """Random draw from an arm's population, decile-gated one row at a time.

    The gate is a per-row lookup, so gating the whole pool up front would cost hundreds of
    thousands of calls to find 33 cards. Shuffling first and gating lazily is the same sample.
    """
    pool = pool.iloc[rng.permutation(len(pool))]
    per_symbol, take, checked = {}, [], 0
    for _, r in pool.iterrows():
        if len(take) >= n:
            break
        key = (r.symbol, int(r.end))
        if key in used or per_symbol.get(r.symbol, 0) >= MAX_PER_SYMBOL:
            continue
        if r.symbol not in fr:
            continue
        checked += 1
        pm = R.prior_move_pct(rk, r.symbol, r.date)
        if pm is None or pm < DECILE:
            continue
        sig = signals_at(fr[r.symbol], int(r.end))
        if sig is None:
            continue
        used.add(key)
        per_symbol[r.symbol] = per_symbol.get(r.symbol, 0) + 1
        take.append({"symbol": r.symbol, "market": "US", "date": r.date, "end": int(r.end),
                     "adr": float(r.adr), "tag": tag, "base_len": int(sig["base_len"]),
                     "cluster_k": int(sig["cluster_k"]) if sig.get("cluster_k") else None,
                     "touch_zones": (None if pd.isna(r.get("touch_zones", np.nan))
                                     else int(r.touch_zones)),
                     "overshoot_adr": (None if pd.isna(r.get("overshoot_adr", np.nan))
                                       else float(r.overshoot_adr))})
    print(f"  {tag:20s} {len(take):3d} cards  (from {checked:,} decile checks, "
          f"pool {len(pool):,})")
    return take


def repeats(rng, n):
    """Deck-A3 cards not yet re-shown, so deck F's pairs are disjoint from the existing 24."""
    m = pd.read_csv(os.path.join(HERE, "deck3_manifest.csv"))
    a3 = m[m.deck == "A"]
    already = set()
    for name in ("deck3_manifest.csv", "deckE_manifest.csv"):
        p = os.path.join(HERE, name)
        if os.path.exists(p):
            mm = pd.read_csv(p)
            if "tag" in mm:
                already |= {(r.symbol, int(r.end))
                            for _, r in mm[mm.tag == "repeat"].iterrows()}
    avail = a3[~a3.apply(lambda r: (r.symbol, int(r.end)) in already, axis=1)]
    print(f"  repeats: {len(avail)} A3 cards never re-shown; taking {n} "
          f"({len(already)} pairs already exist)")
    pick = avail.iloc[rng.permutation(len(avail))[:n]]
    return [{"symbol": r.symbol, "market": "US", "date": r.date, "end": int(r.end),
             "adr": float(r.adr), "tag": "repeat", "base_len": None, "cluster_k": None,
             "touch_zones": None, "overshoot_adr": None} for _, r in pick.iterrows()]


QUESTION = "is there a setup here you would want to see tonight?"

INTRO = (
    "105 charts, plain candles and §2's moving averages &mdash; no base, no cluster, no trigger, "
    "no stop. Some of these the detector <b>rejected</b>, and nothing on a card says which. Grade "
    "them all the same way: <b>1</b> = not a setup, <b>5</b> = exactly the continuation setup you "
    "want. Every card here cleared the same prior-move and top-decile gates, so the only thing "
    "that differs between them is which of the detector's tests they passed. If the rejects grade "
    "as well as the detections, the detector is discarding setups you want."
)


def render(cards, fr):
    html_cards, keys, meta = [], [], []
    for i, c in enumerate(cards):
        svg = chart17.svg(fr[c["symbol"]], int(c["end"]), mode="bare",
                          title=f'{c["symbol"]}  {c["date"]}')
        btns = "".join(f'<button data-v="{v}" onclick="set({i},\'{v}\')">{v}</button>'
                       for v in "12345")
        html_cards.append(
            f'<div class="card" id="c{i}"><div class="hd"><span class="n">#{i+1}</span>'
            f'<span class="tag">ADR {c["adr"]*100:.1f}%</span></div>{svg}'
            f'<div class="grade"><span>{QUESTION}</span>{btns}</div></div>')
        keys.append("12345")
        meta.append({"deck": "F", "card": i, **c})

    js = (JS.replace("%N%", str(len(html_cards)))
            .replace("%KEYS%", json.dumps(keys))
            .replace("wf17deck", "wf25deckF"))
    html = [
        f"<style>{CSS}</style>",
        '<header><h1>Deck F &mdash; the line_not_drawable path</h1>'
        f'<p class="sub">{INTRO}</p>'
        '<p class="keys"><kbd>1</kbd>&ndash;<kbd>5</kbd> answer and advance &middot; '
        '<kbd>j</kbd>/<kbd>k</kbd> move &middot; grades save in the browser, and <b>export</b> at '
        'the bottom emits the string to paste back</p></header>',
        "<main>", *html_cards, "</main>",
        '<div id="bar"><span>answered <b id="cnt">0</b></span>'
        '<button onclick="exp()">export</button><textarea id="out" readonly></textarea></div>',
        f"<script>{js}</script>",
    ]
    path = os.path.join(HERE, "deckF.html")
    with open(path, "w") as f:
        f.write("".join(html))
    print(f"\nwrote {os.path.basename(path)}  ({len(html_cards)} cards)")
    return meta


def main():
    rk, _, _ = R.load_or_build()
    fr = frames()
    rng = np.random.default_rng(SEED)

    sp = pd.read_pickle(os.path.join(CACHE, "split.pkl"))
    sp = sp[(sp.market == "US") & sp.has_base & (sp.move_gain >= MOVE_FLOOR)].copy()
    sp["date"] = pd.to_datetime(sp.date).dt.strftime("%Y-%m-%d")

    used = seen_before()
    print(f"excluding {len(used):,} (symbol, end) pairs the eye has already seen\n")

    cards = []
    for tag, mask in ARMS.items():
        cards += draw(sp[mask(sp)], rk, fr, N_ARM, tag, used, rng)
    cards += repeats(rng, N_REPEAT)

    rng.shuffle(cards)
    meta = render(cards, fr)

    m = pd.DataFrame(meta)
    m.to_csv(os.path.join(HERE, "deckF_manifest.csv"), index=False)
    with open(os.path.join(HERE, "deckF_key.json"), "w") as f:
        json.dump(meta, f, indent=1, default=str)

    print("\narm mix:")
    print(m.tag.value_counts().to_string())
    print("\ncovariates by arm (base_len / cluster_k medians):")
    print(m.groupby("tag")[["base_len", "cluster_k", "adr"]].median().round(3).to_string())


if __name__ == "__main__":
    main()
