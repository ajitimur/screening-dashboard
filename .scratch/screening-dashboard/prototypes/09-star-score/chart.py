"""Self-contained SVG candle charts with the detector's evidence drawn on top."""

import numpy as np
import pandas as pd

W, H = 900, 420
PADL, PADR, PADT, PADB = 8, 62, 12, 22


def _fit(y):
    x = np.arange(len(y), dtype=float)
    m, b = np.polyfit(x, y, 1)
    return m, b


def svg(df, end, sig, lookback=110, forward=0, title=""):
    """Draw bars [end-lookback+1 .. end+forward]. forward>0 reveals the outcome."""
    df = df.reset_index(drop=True)
    s = max(0, end - lookback + 1)
    e = min(len(df) - 1, end + forward)
    w = df.iloc[s : e + 1]
    n = len(w)

    close = df["Close"]
    sma10 = close.rolling(10).mean()
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    ema65 = close.ewm(span=65, adjust=False).mean()

    lo = float(w["Low"].min())
    hi = float(w["High"].max())
    for series in (sma10, sma20, sma50, ema65):
        seg = series.iloc[s : e + 1].dropna()
        if len(seg):
            lo = min(lo, float(seg.min()))
            hi = max(hi, float(seg.max()))
    pad = (hi - lo) * 0.06 or 1.0
    lo -= pad
    hi += pad

    pw = W - PADL - PADR
    ph = H - PADT - PADB

    def X(i):  # i is an index into df
        return PADL + (i - s) / max(n - 1, 1) * pw

    def Y(p):
        return PADT + (hi - p) / (hi - lo) * ph

    bw = max(1.6, pw / n * 0.62)
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" class="chart">']
    out.append(f'<rect x="0" y="0" width="{W}" height="{H}" class="bg"/>')

    # gridlines + price axis
    for k in range(5):
        p = lo + (hi - lo) * k / 4
        y = Y(p)
        out.append(f'<line x1="{PADL}" y1="{y:.1f}" x2="{W-PADR}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{W-PADR+6}" y="{y+3.5:.1f}" class="axis">{p:.2f}</text>')

    # detection boundary when the future is revealed
    if forward > 0:
        xb = X(end) + bw
        out.append(f'<line x1="{xb:.1f}" y1="{PADT}" x2="{xb:.1f}" y2="{H-PADB}" class="nowline"/>')
        out.append(f'<text x="{xb+5:.1f}" y="{PADT+12}" class="lbl now">detection</text>')

    # moving averages
    for series, cls in ((sma10, "ma10"), (sma20, "ma20"), (sma50, "ma50"), (ema65, "ema65")):
        pts = [
            f"{X(i):.1f},{Y(float(series.iloc[i])):.1f}"
            for i in range(s, e + 1)
            if not np.isnan(series.iloc[i])
        ]
        if len(pts) > 1:
            out.append(f'<polyline points="{" ".join(pts)}" class="{cls}"/>')

    # candles
    for i in range(s, e + 1):
        r = df.iloc[i]
        x = X(i)
        up = r["Close"] >= r["Open"]
        cls = "up" if up else "dn"
        fut = " fut" if i > end else ""
        out.append(
            f'<line x1="{x:.1f}" y1="{Y(r["High"]):.1f}" x2="{x:.1f}" y2="{Y(r["Low"]):.1f}" class="wick {cls}{fut}"/>'
        )
        y0, y1 = Y(max(r["Open"], r["Close"])), Y(min(r["Open"], r["Close"]))
        out.append(
            f'<rect x="{x-bw/2:.1f}" y="{y0:.1f}" width="{bw:.1f}" height="{max(1.0,y1-y0):.1f}" class="body {cls}{fut}"/>'
        )

    if sig and sig.get("detected"):
        L = sig["L"]
        Lm = sig["L_longest"]
        bs = end - L + 1
        bms = end - Lm + 1

        # the base envelope (primary window) and the full retained extent
        out.append(
            f'<rect x="{X(bms)-bw:.1f}" y="{PADT}" width="{X(end)-X(bms)+2*bw:.1f}" height="{ph:.1f}" class="baseband"/>'
        )
        out.append(
            f'<rect x="{X(bs)-bw:.1f}" y="{PADT}" width="{X(end)-X(bs)+2*bw:.1f}" height="{ph:.1f}" class="primaryband"/>'
        )

        # §3.2's triangle, fitted over the LONGEST valid window so the shape is visible
        hh = df["High"].to_numpy()[bms : end + 1]
        ll = df["Low"].to_numpy()[bms : end + 1]
        mh, bh = _fit(hh)
        ml, bl = _fit(ll)
        out.append(
            f'<line x1="{X(bms):.1f}" y1="{Y(bh):.1f}" x2="{X(end):.1f}" y2="{Y(mh*(Lm-1)+bh):.1f}" class="tri"/>'
        )
        out.append(
            f'<line x1="{X(bms):.1f}" y1="{Y(bl):.1f}" x2="{X(end):.1f}" y2="{Y(ml*(Lm-1)+bl):.1f}" class="tri"/>'
        )

        # trigger and stop
        xt0, xt1 = X(bs) - bw, min(X(e), X(end) + pw * 0.10)
        out.append(
            f'<line x1="{xt0:.1f}" y1="{Y(sig["trigger"]):.1f}" x2="{xt1:.1f}" y2="{Y(sig["trigger"]):.1f}" class="trigger"/>'
        )
        out.append(f'<text x="{xt1+4:.1f}" y="{Y(sig["trigger"])-4:.1f}" class="lbl trg">trigger</text>')
        out.append(
            f'<line x1="{xt0:.1f}" y1="{Y(sig["base_low"]):.1f}" x2="{xt1:.1f}" y2="{Y(sig["base_low"]):.1f}" class="stop"/>'
        )
        out.append(f'<text x="{xt1+4:.1f}" y="{Y(sig["base_low"])+11:.1f}" class="lbl stp">stop</text>')

    if title:
        out.append(f'<text x="{PADL+4}" y="{PADT+14}" class="title">{title}</text>')
    out.append("</svg>")
    return "".join(out)
