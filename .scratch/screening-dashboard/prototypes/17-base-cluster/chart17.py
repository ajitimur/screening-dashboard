"""Candles for the ticket-17 deck, in three modes.

  mode="bare"   candles + §2's MA set and nothing else. Used for the population question, where
                any overlay would leak which detector picked the card: 08's band is 3 bars and the
                split's is 15, so a drawn base is a label.
  mode="t08"    ticket 08's reading — the primary (shortest valid) window, its OLS upper line, the
                trigger as min(flat high, line), stop at the base low.
  mode="split"  q-scanner's reading — the base from the prior move's peak, the 3-7 bar trailing
                cluster shaded inside it, the anchored envelope, trigger as max(line, cluster high),
                stop at the cluster low.

The two geometry modes render at identical scale on the same bars so a side-by-side card compares
the drawings and not the framing.
"""

import numpy as np

W, H = 860, 400
PADL, PADR, PADT, PADB = 8, 62, 12, 22


def _frame(df, s, e):
    c = df["Close"]
    mas = ((c.rolling(10).mean(), "ma10"), (c.rolling(20).mean(), "ma20"),
           (c.rolling(50).mean(), "ma50"), (c.ewm(span=65, adjust=False).mean(), "ema65"))
    lo = float(df["Low"].iloc[s:e + 1].min())
    hi = float(df["High"].iloc[s:e + 1].max())
    for series, _ in mas:
        seg = series.iloc[s:e + 1].dropna()
        if len(seg):
            lo, hi = min(lo, float(seg.min())), max(hi, float(seg.max()))
    pad = (hi - lo) * 0.06 or 1.0
    return mas, lo - pad, hi + pad


def svg(df, end, lookback=110, mode="bare", geom=None, title="", ylo=None, yhi=None):
    """geom: dict for the overlay modes — see build_deck17.py for what each mode expects."""
    df = df.reset_index(drop=True)
    s = max(0, end - lookback + 1)
    e = end
    n = e - s + 1

    mas, lo, hi = _frame(df, s, e)
    if ylo is not None:
        lo, hi = ylo, yhi

    pw, ph = W - PADL - PADR, H - PADT - PADB
    X = lambda i: PADL + (i - s) / max(n - 1, 1) * pw            # noqa: E731
    Y = lambda p: PADT + (hi - p) / (hi - lo) * ph               # noqa: E731
    bw = max(1.6, pw / n * 0.62)

    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" class="chart">',
           f'<rect x="0" y="0" width="{W}" height="{H}" class="bg"/>']
    for k in range(5):
        p = lo + (hi - lo) * k / 4
        y = Y(p)
        out.append(f'<line x1="{PADL}" y1="{y:.1f}" x2="{W-PADR}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{W-PADR+6}" y="{y+3.5:.1f}" class="axis">{p:.2f}</text>')

    for series, cls in mas:
        pts = [f"{X(i):.1f},{Y(float(series.iloc[i])):.1f}" for i in range(s, e + 1)
               if not np.isnan(series.iloc[i])]
        if len(pts) > 1:
            out.append(f'<polyline points="{" ".join(pts)}" class="{cls}"/>')

    if mode != "bare" and geom:
        bs = int(geom["base_start"])
        out.append(f'<rect x="{X(bs)-bw:.1f}" y="{PADT}" width="{X(end)-X(bs)+2*bw:.1f}" '
                   f'height="{ph:.1f}" class="baseband"/>')
        if geom.get("cluster_start") is not None:
            cs = int(geom["cluster_start"])
            out.append(f'<rect x="{X(cs)-bw:.1f}" y="{PADT}" width="{X(end)-X(cs)+2*bw:.1f}" '
                       f'height="{ph:.1f}" class="clusterband"/>')

    for i in range(s, e + 1):
        r = df.iloc[i]
        x = X(i)
        cls = "up" if r["Close"] >= r["Open"] else "dn"
        out.append(f'<line x1="{x:.1f}" y1="{Y(r["High"]):.1f}" x2="{x:.1f}" '
                   f'y2="{Y(r["Low"]):.1f}" class="wick {cls}"/>')
        y0, y1 = Y(max(r["Open"], r["Close"])), Y(min(r["Open"], r["Close"]))
        out.append(f'<rect x="{x-bw/2:.1f}" y="{y0:.1f}" width="{bw:.1f}" '
                   f'height="{max(1.0, y1-y0):.1f}" class="body {cls}"/>')

    if mode != "bare" and geom:
        bs = int(geom["base_start"])
        y0, y1 = geom["line_at_start"], geom["line_at_end"]
        out.append(f'<line x1="{X(bs):.1f}" y1="{Y(y0):.1f}" x2="{X(end):.1f}" y2="{Y(y1):.1f}" '
                   f'class="fit"/>')
        xt0, xt1 = X(bs) - bw, X(end) + pw * 0.06
        for level, cls, lbl in ((geom["trigger"], "trig", "trigger"), (geom["stop"], "stop", "stop")):
            out.append(f'<line x1="{xt0:.1f}" y1="{Y(level):.1f}" x2="{xt1:.1f}" '
                       f'y2="{Y(level):.1f}" class="{cls}"/>')
            out.append(f'<text x="{xt1+4:.1f}" y="{Y(level)+3:.1f}" class="lbl {cls}l">{lbl}</text>')

    if title:
        out.append(f'<text x="{PADL+4}" y="{PADT+14}" class="title">{title}</text>')
    out.append("</svg>")
    return "".join(out)


def common_scale(df, end, lookback=110):
    """Shared y-range so two drawings of the same bars are visually comparable."""
    s = max(0, end - lookback + 1)
    _, lo, hi = _frame(df, s, end)
    return lo, hi
