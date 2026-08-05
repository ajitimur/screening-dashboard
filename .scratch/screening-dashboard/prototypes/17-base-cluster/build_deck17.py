"""Render deck 17 — the eye question ticket 16 could not ask.

Two sections, because the ticket has two eye questions and they need different instruments.

**Section 1, the population question (blind, 1-5).** The measurement says the two detectors produce
same-sized nightly lists that share about a quarter of their names, and that the split's accept/
reject is uncorrelated with the trader's existing 120 grades. What that cannot say is whether the
names the split adds are *better*. So: 60 cards, 20 from each arm —

    shared      both detectors surface it
    08 only     ticket 08's list has it, the split refuses it
    split only  the split surfaces it, ticket 08 never does

drawn as **bare candles with the MA set and no overlay at all**. Any drawn base would label the
arm (08's is 3 bars, the split's is 15), so the card cannot show one. The question is the one the
list actually asks: is this a continuation setup you want to look at tonight?

**Section 2, the geometry question (blind A/B).** On 15 names *both* detectors fire on, the same
bars are drawn twice at identical scale: 08's primary window with its OLS line, trigger and
base-low stop, against the split's base + cluster with its envelope, clamped trigger and cluster-low
stop. Which drawing describes the setup? This is ticket 16's unasked question, now asked over bases
long enough for a line to mean something.

Every arm is gated as it would be on a real night: D15's decile gate (top decile in any of
1m/3m/6m) on both, plus the split's own >=25% prior-move floor on its arm. US only — the rank
table is US only, and mixing markets would confound the population question with IDX's thinner
tape.

Run: overlap.py -> build_deck17.py -> (grade) -> analyse_deck17.py
"""

import os
import sys
import json
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P16 = os.path.abspath(os.path.join(HERE, "..", "16-trendline-fit"))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
sys.path.insert(0, P16)
sys.path.insert(0, P09)
CACHE = os.path.join(HERE, "cache")
OUT = os.path.join(HERE, "out")

import chart17                       # noqa: E402
import envelope as E                 # noqa: E402
import ranks as R                    # noqa: E402
import split as S                    # noqa: E402

SEED = 17
N_POP = 20      # cards per arm in section 1
N_GEOM = 15     # cards in section 2
DECILE = 0.90   # D15


# --------------------------------------------------------------------- geometry

def geom_t08(d, end):
    """Ticket 08's reading of the bar: shortest valid end-anchored window, OLS upper, min() clamp."""
    high = d["High"].to_numpy(float)
    low = d["Low"].to_numpy(float)
    L = None
    for cand in range(3, 61):
        s = end - cand + 1
        if s < 0:
            break
        h, lo = high[s:end + 1], low[s:end + 1]
        x = np.arange(cand, dtype=float)
        if np.polyfit(x, h, 1)[0] <= 0 and np.polyfit(x, lo, 1)[0] >= 0:
            L = cand
            break
    if L is None:
        return None
    s = end - L + 1
    line_end, m = E.ols_upper(high, s, end)
    base_high = float(high[s:end + 1].max())
    base_low = float(low[s:end + 1].min())
    return {"base_start": s, "cluster_start": None, "L": L,
            "line_at_start": line_end - m * (L - 1), "line_at_end": line_end,
            "trigger": float(min(base_high, line_end)), "stop": base_low}


def geom_split(d, end):
    """q-scanner's reading: prior-move base, trailing cluster, anchored envelope, max() clamp."""
    high = d["High"].to_numpy(float)
    low = d["Low"].to_numpy(float)
    close = d["Close"].to_numpy(float)
    adr = pd.Series(high / low - 1.0).rolling(20).mean().to_numpy()
    a = adr[end]
    if np.isnan(a) or a <= 0:
        return None
    adr_abs = a * close[end]
    mv = S.prior_move(high, low, end)
    if mv is None:
        return None
    _, peak = mv
    base_start = peak
    if end - base_start + 1 > S.MAX_BASE_LEN:
        recent = end - S.MAX_BASE_LEN + 1
        base_start = recent + int(np.argmax(high[recent:end + 1]))
    if end - base_start + 1 < S.MIN_BASE_LEN:
        return None
    cl = S.find_cluster(high, low, end, adr_abs)
    if cl is None:
        return None
    k, ch, clow, _ = cl
    anchor = (end - k + 1) + int(np.argmax(high[end - k + 1:end + 1]))
    m, ok, _, _ = S.fit_line(high, adr_abs, anchor, base_start, end, k)
    line_end = float(high[anchor]) + m * (end - anchor)
    return {"base_start": base_start, "cluster_start": end - k + 1, "L": end - base_start + 1,
            "line_at_start": float(high[anchor]) + m * (base_start - anchor),
            "line_at_end": line_end,
            "trigger": float(max(line_end + m, ch)), "stop": float(clow), "line_ok": bool(ok)}


# ----------------------------------------------------------------------- sample

def arms():
    ov = pd.read_pickle(os.path.join(OUT, "overlap.pkl"))
    ov = ov[(ov.market == "US") & ov.sp_base_len.notna()].copy()
    rk, _, _ = R.load_or_build()

    both = ov[ov.t08_gated & ov.split_floor]
    only08 = ov[ov.t08_gated & ~ov.split_ok]
    onlysp = ov[ov.split_floor & ~ov.t08_gated]

    rng = np.random.default_rng(SEED)
    out = {}
    for name, pool, k in (("shared", both, N_POP), ("08 only", only08, N_POP),
                          ("split only", onlysp, N_POP)):
        # D15 on every arm, checked lazily because the rank lookup is per (symbol, date)
        take, seen = [], set()
        for i in rng.permutation(len(pool)):
            r = pool.iloc[int(i)]
            if r.symbol in seen:          # one card per name, or a hot name dominates an arm
                continue
            pm = R.prior_move_pct(rk, r.symbol, r.date)
            if pm is None or pm < DECILE:
                continue
            seen.add(r.symbol)
            take.append({**r.to_dict(), "arm": name, "prior_move": pm})
            if len(take) == k:
                break
        out[name] = take
        print(f"  {name:11s} pool {len(pool):>7,}  sampled {len(take)}")
    return out, both, rng


# ------------------------------------------------------------------------ page

CSS = """
:root{--bg:#0f1115;--fg:#e6e8ee;--mut:#8b93a7;--line:#252a35;--card:#161a22;--acc:#7aa2f7;
--up:#3fb950;--dn:#f85149;--stp:#f85149;--trg:#3fb950;}
@media (prefers-color-scheme:light){:root{--bg:#f7f8fa;--fg:#14161c;--mut:#5b6270;--line:#dfe3ea;
--card:#fff;--up:#1a7f37;--dn:#cf222e;--trg:#1a7f37;}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;padding-bottom:72px}
header{padding:28px 24px 8px;max-width:1080px;margin:0 auto}
h1{font-size:22px;margin:0 0 6px}h2{font-size:17px;margin:36px 0 4px}
.sub{color:var(--mut);max-width:78ch}
.keys{color:var(--mut);font-size:12px;margin-top:10px}
.keys kbd{background:var(--card);border:1px solid var(--line);border-radius:4px;padding:1px 6px;
font:12px ui-monospace,monospace;color:var(--fg)}
main{max-width:1080px;margin:0 auto;padding:16px 24px 40px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:20px 0;
overflow:hidden;scroll-margin-top:12px}
.card.here{border-color:var(--acc)}.card.done .hd{opacity:.75}
.hd{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;
border-bottom:1px solid var(--line)}
.n{font-weight:600}.tag{color:var(--mut);font-size:12px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:0}
.pair>div{border-right:1px solid var(--line)}.pair>div:last-child{border-right:0}
.pl{padding:6px 12px;font-weight:700;color:var(--acc);font-size:13px}
svg .bg{fill:transparent}svg .grid{stroke:var(--line);stroke-width:1}
svg .axis,svg .lbl{fill:var(--mut);font-size:10px}
svg .title{fill:var(--fg);font-size:12px;font-weight:600}
svg .wick,svg .body{stroke-width:1}
svg .up{stroke:var(--up);fill:var(--up)}svg .dn{stroke:var(--dn);fill:var(--dn)}
svg .ma10{fill:none;stroke:#7aa2f7;stroke-width:1.2}
svg .ma20{fill:none;stroke:#bb9af7;stroke-width:1.4}
svg .ma50{fill:none;stroke:#8b93a7;stroke-width:1.2;stroke-dasharray:4 3}
svg .ema65{fill:none;stroke:#e0af68;stroke-width:1;stroke-dasharray:2 4}
svg .fit{stroke:#e3b341;stroke-width:1.6;fill:none}
svg .trig{stroke:var(--trg);stroke-width:1.2;stroke-dasharray:5 3}
svg .stop{stroke:var(--stp);stroke-width:1.2;stroke-dasharray:3 3}
svg .trigl{fill:var(--trg)}svg .stopl{fill:var(--stp)}
svg .baseband{fill:#7aa2f7;opacity:.10}svg .clusterband{fill:#e3b341;opacity:.12}
.grade{display:flex;gap:8px;align-items:center;padding:12px 16px;border-top:1px solid var(--line);
flex-wrap:wrap}.grade span{color:var(--mut);margin-right:4px}
button{background:transparent;color:var(--fg);border:1px solid var(--line);border-radius:6px;
padding:6px 12px;cursor:pointer;font:inherit}
button:hover{border-color:var(--acc)}
button.sel{background:var(--acc);border-color:var(--acc);color:#0f1115}
#bar{position:fixed;bottom:0;left:0;right:0;background:var(--card);border-top:1px solid var(--line);
padding:10px 24px;font-size:13px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
#bar b{color:var(--acc)}
#out{width:100%;max-width:100%;height:74px;background:var(--bg);color:var(--fg);
border:1px solid var(--line);border-radius:6px;padding:8px;font:12px ui-monospace,monospace;
display:none}#out.on{display:block}
"""

JS = """
const N=%N%, KEYS=%KEYS%, KEY='wf17deck';
function load(){try{return JSON.parse(localStorage.getItem(KEY)||'{}');}catch(e){return {};}}
function save(v){try{localStorage.setItem(KEY,JSON.stringify(v));}catch(e){}}
let G=load(), cur=0;
function paint(){
  for(let i=0;i<N;i++){
    const c=document.getElementById('c'+i);
    c.classList.toggle('here',i===cur);
    c.classList.toggle('done',G[i]!==undefined);
    c.querySelectorAll('button[data-v]').forEach(b=>b.classList.toggle('sel',G[i]===b.dataset.v));
  }
  document.getElementById('cnt').textContent=Object.keys(G).length+' / '+N;
}
function set(i,v){ if(G[i]===v) delete G[i]; else G[i]=v; save(G); paint();
  if(G[i]!==undefined&&i<N-1){cur=i+1;document.getElementById('c'+cur).scrollIntoView({block:'center',behavior:'smooth'});}
  paint();
}
document.addEventListener('keydown',e=>{
  const k=e.key.toLowerCase();
  if((KEYS[cur]||'').includes(k)){set(cur,k);e.preventDefault();}
  else if(k==='j'&&cur<N-1){cur++;document.getElementById('c'+cur).scrollIntoView({block:'center'});paint();}
  else if(k==='k'&&cur>0){cur--;document.getElementById('c'+cur).scrollIntoView({block:'center'});paint();}
});
function exp(){const o=document.getElementById('out');o.classList.add('on');
  o.value=Array.from({length:N},(_,i)=>G[i]||'-').join('');o.select();}
"""


def build():
    picks, both_pool, rng = arms()
    frames = {s: S.clean(d)
              for s, d in pd.read_pickle(os.path.join(CACHE, "universe_us.pkl")).items()}

    pop = [p for arm in picks.values() for p in arm]
    rng.shuffle(pop)

    cards, meta, keys = [], [], []

    # ---- section 1: bare charts, graded 1-5
    for r in pop:
        d = frames.get(r["symbol"])
        if d is None:
            continue
        end = int(r["end"])
        n = len(cards)
        s = chart17.svg(d, end, mode="bare",
                        title=f'{r["symbol"]}  {r["date"]}')
        btns = "".join(f'<button data-v="{v}" onclick="set({n},\'{v}\')">{v}</button>'
                       for v in "12345")
        cards.append(
            f'<div class="card" id="c{n}"><div class="hd"><span class="n">#{n+1}</span>'
            f'<span class="tag">ADR {r["adr"]*100:.1f}%</span></div>{s}'
            f'<div class="grade"><span>how good a continuation setup is this, tonight?</span>'
            f'{btns}</div></div>')
        keys.append("12345")
        meta.append({"card": n, "section": "population", "arm": r["arm"], "symbol": r["symbol"],
                     "date": r["date"], "end": end, "prior_move": float(r["prior_move"]),
                     "adr": float(r["adr"])})

    # ---- section 2: the same bars drawn both ways, blind A/B
    geo, seen = [], set()
    for i in rng.permutation(len(both_pool)):
        r = both_pool.iloc[int(i)]
        if r.symbol in seen:
            continue
        d = frames.get(r.symbol)
        if d is None:
            continue
        end = int(r["end"])
        g8, gs = geom_t08(d, end), geom_split(d, end)
        if not g8 or not gs or not gs.get("line_ok"):
            continue
        seen.add(r.symbol)
        geo.append((r, end, d, g8, gs))
        if len(geo) == N_GEOM:
            break

    sec2_start = len(cards)
    for r, end, d, g8, gs in geo:
        n = len(cards)
        ylo, yhi = chart17.common_scale(d, end)
        order = ["t08", "split"]
        if rng.random() < 0.5:
            order = order[::-1]
        panes = []
        for tag, which in zip("AB", order):
            g = g8 if which == "t08" else gs
            panes.append(f'<div><div class="pl">{tag}</div>' +
                         chart17.svg(d, end, mode=which, geom=g, ylo=ylo, yhi=yhi) + "</div>")
        btns = "".join(f'<button data-v="{v}" onclick="set({n},\'{v}\')">{lbl}</button>'
                       for v, lbl in (("a", "A"), ("b", "B"), ("n", "neither")))
        cards.append(
            f'<div class="card" id="c{n}"><div class="hd"><span class="n">#{n+1}</span>'
            f'<span class="tag">{r.symbol} &middot; {r.date} &middot; ADR {r.adr*100:.1f}%</span>'
            f'</div><div class="pair">{"".join(panes)}</div>'
            f'<div class="grade"><span>which drawing describes the setup you would trade?</span>'
            f'{btns}</div></div>')
        keys.append("abn")
        meta.append({"card": n, "section": "geometry", "symbol": r.symbol, "date": r.date,
                     "end": end, "A": order[0], "B": order[1],
                     "t08_L": int(g8["L"]), "split_L": int(gs["L"])})

    pd.DataFrame(meta).to_csv(os.path.join(HERE, "deck17_manifest.csv"), index=False)
    with open(os.path.join(HERE, "deck17_key.json"), "w") as f:
        json.dump(meta, f, indent=1)

    html = [
        f"<style>{CSS}</style>",
        '<header><h1>Ticket 17 — is the base/cluster split the detector you want?</h1>',
        f'<p class="sub">Two questions, {len(cards)} cards. Grade top to bottom; nothing on a card '
        'says which detector it came from.</p>',
        f'<h2>1 &mdash; the names ({sec2_start} cards)</h2>'
        '<p class="sub">Plain candles, §2\'s moving averages, no drawn base and no trigger &mdash; '
        'a drawn base would tell you which detector picked the card. Grade each one the way you '
        'graded round 2: <b>1</b> = not a setup, <b>5</b> = exactly the continuation setup you want. '
        'You are answering: <i>would I want this name on tonight\'s list?</i></p>'
        f'<h2>2 &mdash; the drawings ({len(cards)-sec2_start} cards)</h2>'
        '<p class="sub">The same bars drawn twice, at the same scale, by the two detectors. '
        'Shaded blue is the base; shaded gold, where present, is the tight cluster inside it. The '
        'gold line is that detector\'s upper boundary, green dashed its trigger, red dashed its '
        'stop. <b>Which side is which is randomised per card.</b> Pick the drawing that describes '
        'the setup you would actually trade &mdash; <b>neither</b> is a real answer.</p>'
        '<p class="keys"><kbd>1</kbd>&ndash;<kbd>5</kbd> or <kbd>a</kbd>/<kbd>b</kbd>/<kbd>n</kbd> '
        'answer and advance &middot; <kbd>j</kbd>/<kbd>k</kbd> move &middot; grades are saved in the '
        'browser, and <b>export</b> at the bottom emits the string to paste back</p></header>',
        "<main>", *cards, "</main>",
        '<div id="bar"><span>answered <b id="cnt">0</b></span>'
        '<button onclick="exp()">export</button>'
        '<textarea id="out" readonly></textarea></div>',
        f"<script>{JS.replace('%N%', str(len(cards))).replace('%KEYS%', json.dumps(keys))}</script>",
    ]
    p = os.path.join(HERE, "deck17.html")
    with open(p, "w") as f:
        f.write("".join(html))
    m = pd.DataFrame(meta)
    print(f"\nwrote {p}  ({len(cards)} cards)")
    print(m.groupby("section").size().to_string())
    print(m[m.section == "population"].arm.value_counts().to_string())


if __name__ == "__main__":
    build()
