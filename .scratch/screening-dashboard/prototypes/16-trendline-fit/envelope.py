"""The two candidate upper-boundary fits, side by side on one window.

Ticket 08 D2 fits the highs by ordinary least squares; q-scanner-v2 anchors at the base's max
high and picks a descending slope by minimising an asymmetric loss (overshoot weighted 3:1).
Both take the same window [s, end] and return a value at `end` — the trigger before D5's min().

Nothing here re-implements the window search: ticket 08's end-anchored backward search and its
OLS-slope-sign validity test are not up for re-litigation, so both fits are handed the same
primary window and asked only where the line sits.
"""

import numpy as np

OVER_W = 3.0
UNDER_W = 1.0
SLOPE_STEPS = 200
MAX_SLOPE_ADR = 0.5  # steepest allowed descent, ADR/bar


def ols_upper(high, s, end):
    """Ticket 08 D2/D5: least-squares line through the highs, evaluated at `end`."""
    h = high[s:end + 1].astype(float)
    L = len(h)
    i = np.arange(L, dtype=float)
    m = np.polyfit(i, h, 1)[0] if L >= 2 else 0.0
    return float(h.mean() + m * ((L - 1) - (L - 1) / 2.0)), float(m)


CLUSTER_K = 5  # trailing bars standing in for q-scanner's 3-7 bar tight cluster


def cluster_bounds(high, low, s, end, k=CLUSTER_K):
    """The trailing cluster q-scanner anchors on. Ticket 08 has no cluster concept, so the
    last k bars of the primary window stand in for it (capped at the window length)."""
    cs = max(s, end - k + 1)
    return cs, float(high[cs:end + 1].max()), float(low[cs:end + 1].min())


def envelope_upper(high, s, end, adr_abs, k=CLUSTER_K):
    """q-scanner's upper envelope: anchored at the max high **of the trailing cluster** and
    extrapolated BACKWARDS over the prior highs, its descending slope chosen by minimising
    over_w*overshoot + under_w*undershoot over every high in the window.

    The anchor is the cluster's max high, not the whole window's — anchoring on the window max
    lets an early spike drag the line down across the base and puts the line's value at `end`
    below the OLS line on ~14% of detections, which is the opposite of the intended effect.
    """
    h = high[s:end + 1].astype(float)
    t = np.arange(s, end + 1)
    cs = max(s, end - k + 1)
    anchor = cs + int(np.argmax(high[cs:end + 1]))
    y_a = float(high[anchor])

    slopes = np.linspace(-MAX_SLOPE_ADR * adr_abs, 0.0, SLOPE_STEPS)
    resid = h[None, :] - (y_a + slopes[:, None] * (t - anchor)[None, :])
    loss = OVER_W * np.clip(resid, 0, None) + UNDER_W * np.clip(-resid, 0, None)
    m = float(slopes[int(np.argmin(loss.sum(axis=1)))])

    return float(y_a + m * (end - anchor)), m, anchor


def both(high, low, s, end, adr_pct, close):
    """The 2x2 this ticket actually has to choose from, for one window.

    The fit and the clamp are separable, and the reference implementation differs from ticket 08
    on BOTH — so measuring "envelope vs OLS" alone would confound them:

      fit    OLS (08 D2)            vs  envelope (q-scanner)
      clamp  min(base_high, line)   vs  max(line, cluster_high)
             (08 D5, clamps DOWN)       (q-scanner, clamps UP)

    q-scanner clamps up deliberately: its line only descends from the cluster high, so projecting
    it forward always lands at or below that high, and in steep flags below the cluster LOW —
    which would put the trigger under the stop. Ticket 08's min() clamps the other way.
    """
    adr_abs = adr_pct * close
    bh = float(high[s:end + 1].max())
    bl = float(low[s:end + 1].min())
    _, ch, cl_low = cluster_bounds(high, low, s, end)

    ols_line, ols_m = ols_upper(high, s, end)
    env_line, env_m, anchor = envelope_upper(high, s, end, adr_abs)

    trig = {
        "ols_min": min(bh, ols_line),      # V0 — today
        "env_min": min(bh, env_line),      # V1 — swap the fit only
        "env_max": max(env_line, ch),      # V2 — q-scanner as written
        "ols_max": max(ols_line, ch),      # V3 — swap the clamp only
    }
    out = {
        "base_high": bh, "base_low": bl, "cluster_high": ch, "cluster_low": cl_low,
        "ols_line": ols_line, "env_line": env_line,
        "ols_slope_adr": ols_m / adr_abs if adr_abs else np.nan,
        "env_slope_adr": env_m / adr_abs if adr_abs else np.nan,
        "env_anchor": anchor,
    }
    for k, t in trig.items():
        out[f"trig_{k}"] = t
        # D6 affordability: trigger-to-base-low must be within 1 x ADR (08 keeps the base low
        # as the stop; q-scanner uses the cluster low, which is a separate question)
        out[f"stopw_{k}"] = (t - bl) / t if t > 0 else np.nan
        out[f"breached_{k}"] = t < close
    return out
