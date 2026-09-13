"""PROTOTYPE — throwaway. Nothing imports this. Not part of the pipeline, the rubric, or the backtest.

The momentum-coil detector, pure functions over oldest-first OHLCV rows.
One implementation, shared by extract.py (viewer) and scan.py (watchlist),
so the chart and the scan can never disagree about what a coil is.

The pattern, per the grilling of 2026-09-13:

  momentum candle  — close-to-close gain >= 1x ADR, close in the upper third
                     of the day's range, volume >= 1.8x its trailing 20-day
                     average (the 20 bars BEFORE the candle, so the spike
                     cannot inflate its own baseline).
  thrust           — the maximal run of consecutive up-closes containing at
                     least one momentum candle; if longer than 5 days, the
                     last 5. The box starts the next day.
  box              — 3..15 days, starting up to BOX_GAP bars after the thrust
                     (a pullback in between stays outside it). Height (highest
                     high - lowest low) <= 1.5x ADR-in-price as of the thrust
                     end. Closes hold above MA50 (up to 10% of box days
                     forgiven), MA50 rising. Mean box volume below the rolling
                     20-day average volume.
  score            — MA convergence: (max - min of MA5/10/20) in ADR units
                     on the evaluation day. Tighter sorts higher. Not a gate.

detect(rows, i) is point-in-time: it reads nothing past index i.
"""

from dataclasses import dataclass

# Momentum candle
GAIN_ADR = 1.0          # close-to-close gain, in units of that day's ADR
CLOSE_POS = 0.5         # close position in the day's range. Grilled as upper
                        # third (2/3), but that misses golden TINS: its thrust
                        # days closed at 0.60 and 0.53. Seeded at upper half.
VOL_MULT = 1.8          # volume vs mean of the 20 bars before the candle

# Thrust
THRUST_CAP = 5          # a longer up-close run keeps only its last 5 days
MAX_THRUST = 0.20       # total thrust gain cap. Labelled junk coils sat after
                        # parabolic thrusts (27.5%, 42.7%); every labelled good
                        # coil's thrust was <= 18.5%. In percent, not ADR: the
                        # ADR-unit split was 2.8 vs 2.9 — too thin to trust.

# Box
BOX_MIN = 3
BOX_MAX = 15
BOX_GAP = 6             # box start may trail the thrust end by up to this many
                        # bars (a pullback/flush between thrust and coil is
                        # excluded from the box) — the KOKA 2026-08-26 finding
HEIGHT_ADR = 1.5        # box high-low span, in ADR-in-price as of thrust end
MA_VIOL_FRAC = 0.10     # fraction of box days forgiven a close below MA50.
                        # MA20 was originally a gate too; golden KOKA closes
                        # below MA20 on all 10 box days while junk GTSI/PTRO
                        # passed it, so it was demoted to the convergence score.
MA50_RISE_BARS = 10     # MA50 today must exceed MA50 this many bars ago

ADR_WINDOW = 20
VOL_WINDOW = 20
MIN_HISTORY = 61        # MA50 + MA50_RISE_BARS + a prev close


@dataclass(frozen=True)
class Coil:
    end: int            # evaluation day (index into rows) — the day it fires
    box_start: int
    thrust_start: int
    thrust_end: int
    momentum_days: tuple  # indices of qualifying candles inside the thrust
    box_high: float
    box_low: float
    height_adr: float   # box span / ADR-in-price at thrust end
    vol_ratio: float    # mean box volume / rolling 20-day average volume
    score: float        # MA5/10/20 spread in ADR units — lower is tighter


def sma(values, i, window):
    """Mean of values[i-window+1 .. i], or None before the window fills."""
    if i + 1 < window:
        return None
    return sum(values[i - window + 1 : i + 1]) / window


def adr(highs, lows, i, window=ADR_WINDOW):
    """SMA20(high/low - 1) over the last 20 bars ending at i. The repo's
    volatility unit (CONTEXT.md: ADR — never 'ATR')."""
    if i + 1 < window:
        return None
    return sum(highs[j] / lows[j] - 1 for j in range(i - window + 1, i + 1)) / window


def is_momentum_candle(o, h, l, c, v, i):
    """The single-day event that licenses everything after it."""
    if i < ADR_WINDOW + 1 or i < VOL_WINDOW:
        return False
    a = adr(h, l, i)
    if a is None or c[i - 1] <= 0:
        return False
    gain = c[i] / c[i - 1] - 1
    if gain < GAIN_ADR * a:
        return False
    rng = h[i] - l[i]
    if rng > 0 and (c[i] - l[i]) / rng < CLOSE_POS:
        return False
    base = sma(v, i - 1, VOL_WINDOW)  # the 20 bars before the candle
    if base is None or base <= 0 or v[i] < VOL_MULT * base:
        return False
    return True


def _thrust_ending_at(o, h, l, c, v, t):
    """The thrust whose last day is t, or None.

    t must be an up-close; walk back through consecutive up-closes, keep the
    last THRUST_CAP days, and demand at least one momentum candle inside.
    Returns (start, end, momentum_days).
    """
    if t < 1 or c[t] <= c[t - 1]:
        return None
    s = t
    while s - 1 >= 1 and c[s - 1] > c[s - 2]:
        s -= 1
    s = max(s, t - THRUST_CAP + 1)
    if c[s - 1] <= 0 or c[t] / c[s - 1] - 1 > MAX_THRUST:  # parabolic — junk
        return None
    momentum = tuple(j for j in range(s, t + 1) if is_momentum_candle(o, h, l, c, v, j))
    if not momentum:
        return None
    return (s, t, momentum)


def detect(rows, i):
    """Evaluate day i. rows = oldest-first [(session, o, h, l, c, v), ...].

    Returns the freshest Coil forming as of day i, or None. Tries the most
    recent possible thrust end first, so a new thrust inside an old box wins.
    """
    if i < MIN_HISTORY:
        return None
    o = [r[1] for r in rows]
    h = [r[2] for r in rows]
    l = [r[3] for r in rows]
    c = [r[4] for r in rows]
    v = [r[5] for r in rows]
    return _detect(o, h, l, c, v, i)


def _detect(o, h, l, c, v, i):
    ma20 = sma(c, i, 20)
    ma50 = sma(c, i, 50)
    ma50_prev = sma(c, i - MA50_RISE_BARS, 50)
    if ma20 is None or ma50 is None or ma50_prev is None:
        return None
    if ma50 <= ma50_prev:  # MA50 rising — hard gate
        return None

    vol20 = sma(v, i, VOL_WINDOW)  # rolling, includes today (per grilling Q4)
    if vol20 is None or vol20 <= 0:
        return None

    for t in range(i - BOX_MIN, i - BOX_MAX - BOX_GAP - 1, -1):  # freshest first
        if t < 1:
            break
        thrust = _thrust_ending_at(o, h, l, c, v, t)
        if thrust is None:
            continue
        ts, te, momentum = thrust

        a = adr(h, l, te)
        if a is None:
            continue
        adr_px = a * c[te]  # ADR in price units as of the thrust end
        if adr_px <= 0:
            continue

        # The box may start up to BOX_GAP bars after the thrust ends — a
        # pullback between thrust and coil stays outside it. Fullest box first.
        for s in range(te + 1, te + 2 + BOX_GAP):
            box = range(s, i + 1)
            n = len(box)
            if n < BOX_MIN or n > BOX_MAX:
                continue
            box_high = max(h[j] for j in box)
            box_low = min(l[j] for j in box)
            if (box_high - box_low) > HEIGHT_ADR * adr_px:
                continue

            # MA gate: each box day's close vs that day's MA50
            allowed = int(n * MA_VIOL_FRAC)
            viol = 0
            ok = True
            for j in box:
                m50 = sma(c, j, 50)
                if m50 is None:
                    ok = False
                    break
                if c[j] < m50:
                    viol += 1
                    if viol > allowed:
                        ok = False
                        break
            if not ok:
                continue

            mean_box_vol = sum(v[j] for j in box) / n
            if mean_box_vol >= vol20:  # quiet-volume gate
                continue

            ma5 = sma(c, i, 5)
            spread = max(ma5, ma20, sma(c, i, 10)) - min(ma5, ma20, sma(c, i, 10))
            adr_px_now = (adr(h, l, i) or a) * c[i]
            score = spread / adr_px_now if adr_px_now > 0 else float("inf")

            return Coil(
                end=i, box_start=s, thrust_start=ts, thrust_end=te,
                momentum_days=momentum, box_high=box_high, box_low=box_low,
                height_adr=(box_high - box_low) / adr_px,
                vol_ratio=mean_box_vol / vol20, score=score,
            )
    return None


def detect_all(rows):
    """Every firing day over the whole series. For the viewer."""
    out = []
    for i in range(MIN_HISTORY, len(rows)):
        coil = detect(rows, i)
        if coil is not None:
            out.append(coil)
    return out
