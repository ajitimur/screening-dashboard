"""Candle chart drawing the PRIMARY window only, with both candidate upper boundaries.

Two differences from ticket 09's `chart.py`, both deliberate:

  1. **The primary window only.** Ticket 11's I5 settled this — drawing D3's retained set renders
     the degeneracy, not the setup. `chart.py` drew both bands and fitted the triangle over the
     LONGEST window while the trigger came from the SHORTEST, so its charts showed a triangle over
     one base and a trigger from another. That conformance bug is the other half of what the trader
     saw on deck A, and it is fixed here rather than decided.
  2. **Both upper fits, blind.** Each card draws the OLS line and the envelope line in a randomised
     A/B assignment, so the question "which line sits where you would draw it" can be asked without
     announcing which one the detector currently uses.
"""

import numpy as np

import envelope as E

W, H = 900, 420
PADL, PADR, PADT, PADB = 8, 62, 12, 22


def svg(df, end, L, adr, close, assign, lookback=110, title=""):
    """assign: dict with 'A' and 'B' each 'ols' or 'env' — the blind randomisation."""
    df = df.reset_index(drop=True)
    s = max(0, end - lookback + 1)
    e = end
    n = e - s + 1

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
    lo, hi = lo - pad, hi + pad

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

    # ---- the primary window, and only it
    bs = end - L + 1
    out.append(f'<rect x="{X(bs)-bw:.1f}" y="{PADT}" width="{X(end)-X(bs)+2*bw:.1f}" '
               f'height="{ph:.1f}" class="primaryband"/>')

    for i in range(s, e + 1):
        r = df.iloc[i]
        x = X(i)
        cls = "up" if r["Close"] >= r["Open"] else "dn"
        out.append(f'<line x1="{x:.1f}" y1="{Y(r["High"]):.1f}" x2="{x:.1f}" '
                   f'y2="{Y(r["Low"]):.1f}" class="wick {cls}"/>')
        y0, y1 = Y(max(r["Open"], r["Close"])), Y(min(r["Open"], r["Close"]))
        out.append(f'<rect x="{x-bw/2:.1f}" y="{y0:.1f}" width="{bw:.1f}" '
                   f'height="{max(1.0, y1-y0):.1f}" class="body {cls}"/>')

    high = df["High"].to_numpy(float)
    low = df["Low"].to_numpy(float)
    adr_abs = adr * close
    ols_end, ols_m = E.ols_upper(high, bs, end)
    env_end, env_m, anchor = E.envelope_upper(high, bs, end, adr_abs)
    lines = {
        "ols": (ols_end - ols_m * (L - 1), ols_end),      # value at bs, value at end
        "env": (float(high[anchor]) + env_m * (bs - anchor), env_end),
    }

    for tag in ("A", "B"):
        y0, y1 = lines[assign[tag]]
        out.append(f'<line x1="{X(bs):.1f}" y1="{Y(y0):.1f}" x2="{X(end):.1f}" y2="{Y(y1):.1f}" '
                   f'class="fit fit{tag}"/>')
        out.append(f'<text x="{X(end)+4:.1f}" y="{Y(y1)+3:.1f}" class="lbl fitlbl{tag}">{tag}</text>')

    bl = float(low[bs:end + 1].min())
    xt0, xt1 = X(bs) - bw, X(end) + pw * 0.06
    out.append(f'<line x1="{xt0:.1f}" y1="{Y(bl):.1f}" x2="{xt1:.1f}" y2="{Y(bl):.1f}" class="stop"/>')
    out.append(f'<text x="{xt1+4:.1f}" y="{Y(bl)+11:.1f}" class="lbl stp">stop</text>')

    if title:
        out.append(f'<text x="{PADL+4}" y="{PADT+14}" class="title">{title}</text>')
    out.append("</svg>")
    return "".join(out)
