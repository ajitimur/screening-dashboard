"""Render round 3's decks, exactly as PREREGISTRATION_R3.md specifies. Seed 3.

Three decks, 224 cards, every one rendered BARE — candles and §2's moving averages, no base, no
cluster, no trigger, no stop. Round 2 drew deck A with overlays and deck D without, and that is the
axis its unexplained +0.69-star gap sits on. One rendering, one poolable population.

  A3  120  US, the split's own accepted population, stratified on the round-3 provisional score
  C3   52  IDX, 26 partial limit-lock vs 26 clean — per-market calibration and D13's probe
  D3   40  20 split rejects vs 20 detections — ticket 11's unowned obligation
  +12  repeats drawn from A3 and hidden inside C3 and D3, for the test-retest ceiling

Writes deck3_A.html / deck3_C.html / deck3_D.html, deck3_manifest.csv and deck3_key.json.
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

SEED = 3
DECILE = 0.90
MOVE_FLOOR = 25.0
N_A, N_C_ARM, N_D_ARM, N_REPEAT = 120, 26, 20, 12
BANDS = [(0, 1.5), (1.5, 2.5), (2.5, 3.5), (3.5, 4.5), (4.5, 5.01)]


def band_of(stars):
    for i, (lo, hi) in enumerate(BANDS):
        if lo <= stars < hi:
            return i
    return len(BANDS) - 1


def frames(market):
    f = "universe_us.pkl" if market == "US" else "universe_idx.pkl"
    return {s: S.clean(d) for s, d in pd.read_pickle(os.path.join(CACHE, f)).items()}


def provisional(d, end, symbol, market, rk, sectors):
    """The round-3 provisional score — used only to stratify, never reported as a result."""
    sig = signals_at(d, end)
    if sig is None or not sig["split_ok"]:
        return None
    pm = R.prior_move_pct(rk, symbol, str(end)) if False else None
    return sig


def collapsed_share(d, end, base_len):
    """Share of bars inside the base with a literally zero range — IDX limit days (09 D13)."""
    high = d["High"].to_numpy(float)
    low = d["Low"].to_numpy(float)
    s = end - base_len + 1
    rngs = high[s:end + 1] / np.maximum(low[s:end + 1], 1e-12) - 1.0
    return float((rngs < 1e-9).mean())


def population(market, rk, sectors, fr):
    """Every split-accepted, decile-gated, move-floored detection, scored provisionally."""
    sp = pd.read_pickle(os.path.join(CACHE, "split.pkl"))
    sp = sp[(sp.market == market) & sp.tight & sp.line_ok & sp.caught_up
            & (sp.move_gain >= MOVE_FLOOR)].copy()
    sp["date"] = pd.to_datetime(sp.date).dt.strftime("%Y-%m-%d")
    rng = np.random.default_rng(SEED)
    sp = sp.iloc[rng.permutation(len(sp))]

    cap = 30 if market == "IDX" else 8   # IDX has only 76 names that ever pass; US has plenty
    rows, per_symbol = [], {}
    for _, r in sp.iterrows():
        if per_symbol.get(r.symbol, 0) >= cap:
            continue
        d = fr.get(r.symbol)
        if d is None:
            continue
        end = int(r.end)
        pm = R.prior_move_pct(rk, r.symbol, r.date) if market == "US" else None
        if market == "US" and (pm is None or pm < DECILE):
            continue
        sig = signals_at(d, end)
        if sig is None or not sig["split_ok"]:
            continue
        ss = R.sector_share_loo(rk, sectors, r.symbol, r.date) if market == "US" else None
        st = score3(sig, pm, ss, "boolean")["stars"]
        per_symbol[r.symbol] = per_symbol.get(r.symbol, 0) + 1
        rows.append({"symbol": r.symbol, "market": market, "date": r.date, "end": end,
                     "adr": float(r.adr), "stars": st, "band": band_of(st),
                     "base_len": sig["base_len"], "cluster_k": sig["cluster_k"],
                     "collapsed": collapsed_share(d, end, sig["base_len"])})
        if len(rows) >= (4000 if market == "US" else 2500):
            break
    return pd.DataFrame(rows)


def rejects(market, fr, n):
    """The split's own two rejection paths, decile-gating aside — bare cards, no geometry."""
    sp = pd.read_pickle(os.path.join(CACHE, "split.pkl"))
    sp = sp[(sp.market == market) & sp.has_base & (sp.move_gain >= MOVE_FLOOR)].copy()
    sp["date"] = pd.to_datetime(sp.date).dt.strftime("%Y-%m-%d")
    sp["reason"] = np.where(~sp.tight, "no_cluster",
                            np.where(~sp.line_ok, "line_not_drawable", "not_caught_up"))
    rng = np.random.default_rng(SEED + 1)
    out = []
    for reason in ("no_cluster", "line_not_drawable"):
        pool = sp[sp.reason == reason]
        pool = pool.iloc[rng.permutation(len(pool))]
        seen = set()
        for _, r in pool.iterrows():
            if r.symbol in seen or r.symbol not in fr:
                continue
            seen.add(r.symbol)
            out.append({"symbol": r.symbol, "market": market, "date": r.date, "end": int(r.end),
                        "adr": float(r.adr), "reason": reason})
            if len(seen) == n // 2:
                break
    return pd.DataFrame(out)


def stratify(pop, n, rng, max_per_symbol=2):
    """Equal cards per provisional band, then redistribute whatever the thin bands cannot supply.

    The pre-registration asks for 24 per band. Under the split's own population the bottom band
    (<=1.5 stars) is nearly empty — the detector's gates already remove most of what would score
    that low — so a strict quota would silently return a short deck. The shortfall is spread over
    the bands that can supply it and the actual mix is recorded in the manifest.
    """
    take, seen = [], {}
    bands = list(range(len(BANDS)))
    remaining = n

    def draw(b, want):
        got = 0
        sub = pop[pop.band == b]
        sub = sub.iloc[rng.permutation(len(sub))]
        for _, r in sub.iterrows():
            if got >= want:
                break
            if seen.get(r.symbol, 0) >= max_per_symbol:
                continue
            if any(t["symbol"] == r.symbol and t["end"] == r.end for t in take):
                continue
            seen[r.symbol] = seen.get(r.symbol, 0) + 1
            take.append(r.to_dict())
            got += 1
        return got

    for b in bands:
        remaining -= draw(b, n // len(bands))
    for _ in range(4):                      # top-up passes over whatever still has depth
        if remaining <= 0:
            break
        for b in sorted(bands, key=lambda x: -len(pop[pop.band == x])):
            if remaining <= 0:
                break
            remaining -= draw(b, remaining)
    return take


# --------------------------------------------------------------------------- rendering

QUESTION = "how good a continuation setup is this, tonight?"
DECK_JS_KEY = {"A": "wf15r3A", "C": "wf15r3C", "D": "wf15r3D"}


def render(deck, cards, fr, title, intro):
    html_cards, keys, meta = [], [], []
    for i, c in enumerate(cards):
        d = fr[c["market"]].get(c["symbol"])
        svg = chart17.svg(d, int(c["end"]), mode="bare",
                          title=f'{c["symbol"]}  {c["date"]}')
        btns = "".join(f'<button data-v="{v}" onclick="set({i},\'{v}\')">{v}</button>'
                       for v in "12345")
        html_cards.append(
            f'<div class="card" id="c{i}"><div class="hd"><span class="n">#{i+1}</span>'
            f'<span class="tag">ADR {c["adr"]*100:.1f}%</span></div>{svg}'
            f'<div class="grade"><span>{QUESTION}</span>{btns}</div></div>')
        keys.append("12345")
        meta.append({"deck": deck, "card": i, **{k: v for k, v in c.items()
                                                 if k not in ("stars", "band")},
                     "provisional": c.get("stars"), "band": c.get("band")})

    js = (JS.replace("%N%", str(len(html_cards)))
            .replace("%KEYS%", json.dumps(keys))
            .replace("wf17deck", DECK_JS_KEY[deck]))
    html = [
        f"<style>{CSS}</style>",
        f"<header><h1>{title}</h1><p class=\"sub\">{intro}</p>"
        '<p class="keys"><kbd>1</kbd>&ndash;<kbd>5</kbd> answer and advance &middot; '
        '<kbd>j</kbd>/<kbd>k</kbd> move &middot; grades save in the browser, and <b>export</b> at '
        'the bottom emits the string to paste back</p></header>',
        "<main>", *html_cards, "</main>",
        '<div id="bar"><span>answered <b id="cnt">0</b></span>'
        '<button onclick="exp()">export</button><textarea id="out" readonly></textarea></div>',
        f"<script>{js}</script>",
    ]
    path = os.path.join(HERE, f"deck3_{deck}.html")
    with open(path, "w") as f:
        f.write("".join(html))
    print(f"  wrote {os.path.basename(path)}  ({len(html_cards)} cards)")
    return meta


def main():
    rk, _, _ = R.load_or_build()
    sectors = pd.read_pickle(os.path.join(CACHE, "sectors_us.pkl"))
    fr = {"US": frames("US"), "IDX": frames("IDX")}
    rng = np.random.default_rng(SEED)

    print("sampling the US population...", flush=True)
    pop_us = population("US", rk, sectors, fr["US"])
    print(f"  {len(pop_us)} scored US detections; band mix "
          f"{pop_us.band.value_counts().sort_index().to_dict()}")

    a_cards = stratify(pop_us, N_A, rng)
    rng.shuffle(a_cards)
    print(f"  deck A3: {len(a_cards)} cards, band mix "
          f"{pd.Series([c['band'] for c in a_cards]).value_counts().sort_index().to_dict()}")

    print("sampling the IDX population...", flush=True)
    pop_idx = population("IDX", rk, sectors, fr["IDX"])
    print(f"  {len(pop_idx)} scored IDX detections")
    # D13's partial-lock probe: check the population still exists before spending a deck on it.
    partial = pop_idx[(pop_idx.collapsed > 0) & (pop_idx.collapsed <= 0.20)]
    clean = pop_idx[pop_idx.collapsed == 0]
    share = len(partial) / max(len(pop_idx), 1)
    print(f"  partially limit-locked bases: {len(partial)} of {len(pop_idx)} ({share:.1%}); "
          f"clean {len(clean)}")
    if share < 0.10:
        print("  -> D13's probe is not runnable: the population it was sized for has gone.")
        print("     Deck C becomes IDX calibration, carrying every locked card that exists.")
        n_lock = min(len(partial), 12)               # descriptive subgroup, not a powered arm
        locked = stratify(partial, n_lock, rng)
        have = {(c["symbol"], c["end"]) for c in locked}
        rest = clean[~clean.apply(lambda r: (r.symbol, r.end) in have, axis=1)]
        c_cards = locked + stratify(rest, 2 * N_C_ARM - n_lock, rng)
        for c in c_cards:
            c["tag"] = "idx_locked" if c["collapsed"] > 0 else "idx_clean"
    else:
        c_cards = ([{**c, "tag": "idx_locked"} for c in stratify(partial, N_C_ARM, rng)]
                   + [{**c, "tag": "idx_clean"} for c in stratify(clean, N_C_ARM, rng)])

    print("sampling rejects...", flush=True)
    rej = rejects("US", fr["US"], N_D_ARM)
    used = {(c["symbol"], c["end"]) for c in a_cards}
    spare = pop_us[~pop_us.apply(lambda r: (r.symbol, r.end) in used, axis=1)]
    det = stratify(spare, N_D_ARM, rng)
    d_cards = ([{**r, "tag": f"reject:{r['reason']}", "stars": None, "band": None}
                for r in rej.to_dict("records")]
               + [{**c, "tag": "detection"} for c in det])

    # repeats: 12 A3 cards, re-shown inside C3 and D3 under a fresh id
    reps = [dict(a_cards[i]) for i in rng.choice(len(a_cards), N_REPEAT, replace=False)]
    for r in reps:
        r["tag"] = "repeat"
    c_cards += reps[:6]
    d_cards += reps[6:]
    rng.shuffle(c_cards)
    rng.shuffle(d_cards)

    print("rendering...", flush=True)
    meta = []
    meta += render("A", a_cards, fr, "Round 3 — the core deck",
                   "120 charts, plain candles and §2's moving averages. No base, no cluster, no "
                   "trigger, no stop &mdash; nothing on a card tells you what the machine did. "
                   "<b>1</b> = not a setup, <b>5</b> = exactly the continuation setup you want. "
                   "This deck fits the rubric's four remaining free numbers, so it is the one that "
                   "must be finished.")
    meta += render("C", c_cards, fr, "Round 3 — IDX",
                   "52 IDX charts plus a few carried over, rendered identically. This is the first "
                   "time any IDX card has been graded on this map, so it answers two things at "
                   "once: whether IDX needs its own thresholds, and whether partially limit-locked "
                   "bases flatter the score the way ticket 09 suspected.")
    meta += render("D", d_cards, fr, "Round 3 — what the detector threw away",
                   "40 charts, and a different question. Some of these the detector <b>rejected</b>. "
                   "Grade them the same way &mdash; <b>is there a setup here you would want to see "
                   "tonight?</b> If the rejects grade as well as the detections, the detector is "
                   "discarding setups you want.")

    m = pd.DataFrame(meta)
    m.to_csv(os.path.join(HERE, "deck3_manifest.csv"), index=False)
    with open(os.path.join(HERE, "deck3_key.json"), "w") as f:
        json.dump(meta, f, indent=1, default=str)
    print(f"\ntotal {len(m)} cards")
    print(m.groupby("deck").size().to_string())
    print(m.groupby(["deck", "tag"]).size().to_string() if "tag" in m else "")


if __name__ == "__main__":
    main()
