"""User strategy v2 (as clarified 2026-11-14): 50%-retracement structure + 1h inverted FVG, 1.5R.

STRUCTURE (run on 1h bars, sized with ATR(14) of the last CLOSED 4h bar):
  A swing low only counts once price retraces >= 50% of the leg into it (and the leg is >= minleg x ATR4h).
  Before that, a lower low just extends the leg (minor bounces < 50% are ignored). If a too-small counter leg breaks
  its own origin, it was noise: the previous leg resumes. Same for swing highs.
TREND: short only when the down leg starts at a LOWER HIGH and ends at a LOWER LOW vs the previous swings (bull mirror).
SETUP: the 50% retracement that confirms the new swing low (leg >= G x ATR4h) arms a short.
  [c4] optional: only accept triggers after the 4h candle that tagged 50% has closed.
TRIGGER: a 1h bullish FVG formed after the swing low is inverted by a 1h close below its bottom -> short limit at the
  FVG midline, valid V hours. Disarm on a 1h close beyond the inv retracement (78.6%) or after W hours.
STOP: retracement extreme (highest high since the swing low, at the trigger) + buf x ATR4h  [stop='ext']
      or the leg origin + 0.1 ATR  [stop='origin'].
TARGET: after-fee tgt R (1.5). [liq] optional filter: the nearest unswept 1h swing low (fractal 2/2, confirmed) below
  the entry must lie between the entry and the target (the target takes out the next liquidity).
EXECUTION: house rules as ifvg_lab (1h bars, pen 0.05 ATR, stop first, no target on the fill bar, 0.04%/side,
  weekend flat, one position per coin)."""
import sys, statistics, collections, bisect
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps
from ifvg_lab import START, SPLIT, SCH, load, report, stats, REG, H, H4, D, FRT
COINS = ['SUI', 'UNI', 'BTC', 'ETH', 'SOL', 'NEAR', 'ADA', 'LINK', 'HYPE']
OTHER = ['BNB', 'XRP', 'ZEC']


def structure(b1, a1, minleg, look=120):
    """Events (m, side, O, E, Ei, trend) when a leg O->E (>= minleg ATR4h) is 50% retraced at 1h bar m.
    side -1 = down leg (sets up a short). A leg's origin is never older than `look` 1h bars: an older origin is
    re-anchored to the extreme of the last `look` bars (traders read legs over the last few days)."""
    piv = []                                   # confirmed swings (price, +1 high / -1 low)
    d, O, Oi, E, Ei = -1, b1[0][2], 0, b1[0][3], 0
    ev = []
    for m in range(1, len(b1)):
        a = a1[m]
        if a is None:
            continue
        hi, lo = b1[m][2], b1[m][3]
        if m - Oi > look:                       # re-anchor a stale origin inside the window
            w = range(max(0, m - look), Ei + 1) if Ei >= m - look else None
            if w:
                if d == -1:
                    Oi = max(w, key=lambda q: b1[q][2]); O = b1[Oi][2]
                else:
                    Oi = min(w, key=lambda q: b1[q][3]); O = b1[Oi][3]
            else:                               # the extreme itself is stale: restart from the window
                w = range(m - look, m + 1)
                if d == -1:
                    Oi = max(w, key=lambda q: b1[q][2]); O = b1[Oi][2]
                    Ei = min(range(Oi, m + 1), key=lambda q: b1[q][3]); E = b1[Ei][3]
                else:
                    Oi = min(w, key=lambda q: b1[q][3]); O = b1[Oi][3]
                    Ei = max(range(Oi, m + 1), key=lambda q: b1[q][2]); E = b1[Ei][2]
        if d == -1:
            if lo < E:
                E, Ei = lo, m
            elif hi >= E + 0.5 * (O - E) and O - E >= minleg * a:
                hs = [p for p, k in piv if k == 1]; ls = [p for p, k in piv if k == -1]
                if hs and hs[-1] == O:
                    hs = hs[:-1]
                ev.append((m, -1, O, E, Ei, bool(hs) and bool(ls) and O < hs[-1] and E < ls[-1]))
                piv.append((E, -1)); d, O, Oi, E, Ei = 1, E, Ei, hi, m
                continue
            if hi > O:                          # origin broken before the leg counted: it was noise
                if piv and piv[-1][1] == 1:
                    piv.pop()
                d, O, Oi, E, Ei = 1, lo, m, hi, m
                lows = [q for q in range(max(0, m - look), m + 1)]
                Oi = min(lows, key=lambda q: b1[q][3]); O = b1[Oi][3]
        else:
            if hi > E:
                E, Ei = hi, m
            elif lo <= E - 0.5 * (E - O) and E - O >= minleg * a:
                hs = [p for p, k in piv if k == 1]; ls = [p for p, k in piv if k == -1]
                if ls and ls[-1] == O:
                    ls = ls[:-1]
                ev.append((m, 1, O, E, Ei, bool(hs) and bool(ls) and O > ls[-1] and E > hs[-1]))
                piv.append((E, 1)); d, O, Oi, E, Ei = -1, E, Ei, lo, m
                continue
            if lo < O:
                if piv and piv[-1][1] == -1:
                    piv.pop()
                highs = [q for q in range(max(0, m - look), m + 1)]
                Oi = max(highs, key=lambda q: b1[q][2]); O = b1[Oi][2]
                d, E, Ei = -1, lo, m
    return ev


def run(sym, look=120, minleg=2.0, G=3.0, W=48, V=12, inv=0.786, stop='ext', buf=0.5, tgt=1.5, liq=False, c4=False,
        trend=True, hold=96, btc=False, CHK=None, entry='ifvg', zone_valid=24):
    b1 = load(sym, '1h'); b4 = load(sym, '4h')
    if len(b1) < 3000:
        return []
    at4 = perps.atr([x[2] for x in b4], [x[3] for x in b4], [x[4] for x in b4], 14)
    t4 = {x[0]: k for k, x in enumerate(b4)}
    a1 = []
    for x in b1:
        k = t4.get((x[0] // H4) * H4 - H4)
        a1.append(at4[k] if k is not None else None)
    # 1h fractal swing lows/highs, known 2 bars later
    fl = [m for m in range(2, len(b1) - 2) if b1[m][3] < min(b1[m - 1][3], b1[m - 2][3], b1[m + 1][3], b1[m + 2][3])]
    fh = [m for m in range(2, len(b1) - 2) if b1[m][2] > max(b1[m - 1][2], b1[m - 2][2], b1[m + 1][2], b1[m + 2][2])]
    out = []; busy = 0
    for (m0, side0, O, E, Ei, tr) in structure(b1, a1, minleg, look):
        side = side0                                   # down leg retraced -> short, up leg -> long
        if b1[m0][0] < START or b1[m0][0] < busy:
            continue
        a = a1[m0]
        if (abs(O - E) < G * a) or (trend and not tr):
            continue
        if btc:
            r = REG.get((b1[m0][0] // H4) * H4 - H4)
            if r is None or (r > 0) != (side == 1):
                continue
        size = abs(O - E)
        inv_px = E - side * inv * size
        ok_from = m0
        if c4:
            ok_from = m0 + (4 - (b1[m0][0] // H) % 4)  # first 1h bar after the 4h candle closes
        fv = []
        for j in range(Ei + 2, m0 + 1):
            if side == -1 and b1[j][3] > b1[j - 2][2]:
                fv.append((b1[j - 2][2], b1[j][3]))
            if side == 1 and b1[j][2] < b1[j - 2][3]:
                fv.append((b1[j][2], b1[j - 2][3]))
        rx = max(x[2] for x in b1[Ei:m0 + 1]) if side == -1 else min(x[3] for x in b1[Ei:m0 + 1])
        sig = None
        zstop = None
        if entry.startswith('zone'):                  # two conditions only: limit straight into the zone
            f = float(entry[4:]) / 1000 if len(entry) > 4 else 0.5
            sig = (m0, E - side * f * size); zstop = inv_px - side * buf * a; V = zone_valid
        for m in (range(m0, min(len(b1) - 1, m0 + W)) if sig is None else []):
            x = b1[m]
            if m > m0:
                if side == -1 and b1[m][3] > b1[m - 2][2]:
                    fv.append((b1[m - 2][2], b1[m][3]))
                if side == 1 and b1[m][2] < b1[m - 2][3]:
                    fv.append((b1[m][2], b1[m - 2][3]))
            rx = max(rx, x[2]) if side == -1 else min(rx, x[3])
            if (side == -1 and x[4] > inv_px) or (side == 1 and x[4] < inv_px):
                break
            hit = [g for g in fv if (side == -1 and x[4] < g[0]) or (side == 1 and x[4] > g[1])]
            if hit and m >= ok_from:
                g = hit[-1]; sig = (m, (g[0] + g[1]) / 2); break
            fv = [g for g in fv if g not in hit]
        if sig is None:
            continue
        m, lim = sig
        t_place = b1[m][0] + H
        if perps.in_weekend(t_place, SCH):
            continue
        stp = zstop if zstop is not None else ((rx + (-side) * buf * a) if stop == 'ext' else (O + (-side) * 0.1 * a))
        if (lim - stp) * side <= 0 or abs(lim - stp) / lim < 0.002:
            continue
        n = e = None
        q0 = m + 1
        if CHK:                                       # ticket placed at the next check-in hour (SGT)
            dead = False
            while q0 < len(b1) - 1 and ((b1[q0][0] // H + 8) % 24) not in CHK:
                if (side == 1 and b1[q0][3] <= stp) or (side == -1 and b1[q0][2] >= stp):
                    dead = True; break
                q0 += 1
            if dead or perps.in_weekend(b1[q0][0], SCH):
                continue
        for q in range(q0, min(len(b1), q0 + V)):
            x = b1[q]
            if (side == 1 and x[3] <= stp) or (side == -1 and x[2] >= stp):
                break
            if (side == 1 and x[3] <= lim - 0.05 * a) or (side == -1 and x[2] >= lim + 0.05 * a):
                n, e = q, (min(x[1], lim) if side == 1 else max(x[1], lim)); break
        if n is None:
            continue
        d = abs(e - stp)
        tp = e + side * (tgt * (d + FRT * e) + FRT * e)
        if liq:
            if side == -1:
                cands = [b1[k][3] for k in fl if k + 2 <= n - 1 and b1[k][3] < e and
                         min((y[3] for y in b1[k + 1:n]), default=1e18) > b1[k][3]]
                nearest = max(cands) if cands else None
                if nearest is None or nearest < tp:
                    continue
            else:
                cands = [b1[k][2] for k in fh if k + 2 <= n - 1 and b1[k][2] > e and
                         max((y[2] for y in b1[k + 1:n]), default=-1) < b1[k][2]]
                nearest = min(cands) if cands else None
                if nearest is None or nearest > tp:
                    continue
        flat = perps.next_weekend_stop(b1[n][0], SCH)
        px = why = None
        for q in range(n, min(len(b1), n + hold)):
            o, hh, ll = b1[q][1], b1[q][2], b1[q][3]
            if b1[q][0] >= flat:
                px, why = o, 'weekend'; break
            if (side == 1 and ll <= stp) or (side == -1 and hh >= stp):
                px = (min(o, stp) if side == 1 else max(o, stp)) if q > n else stp; why = 'stop'; break
            if q > n and ((side == 1 and hh >= tp) or (side == -1 and ll <= tp)):
                px, why = tp, 'target'; break
        if px is None:
            px, why = b1[q][4], 'time'
        out.append({'sym': sym, 'side': side, 't_in': b1[n][0], 't_out': b1[q][0] + H, 'exit': why, 'e': e, 'stp': stp,
                    'sig_t': b1[m][0] + H, 'arm_t': b1[m0][0] + H,
                    'r': (side * (px - e) / e - FRT) / (d / e + FRT), 'stop_frac': d / e})
        busy = b1[q][0] + H
    return out


def book(syms=COINS, **kw):
    return sorted([t for s in syms for t in run(s, **kw)], key=lambda t: t['t_in'])


if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'base'
    if what == 'base':
        tl = book(); report(tl, 'V2 base (9 coins)')
        for s in COINS:
            report([t for t in tl if t['sym'] == s], '  ' + s)
        report(book(OTHER), 'V2 base other 3 coins')
        print('exits', collections.Counter(t['exit'] for t in tl), 'median stop %.2f%%' % (100 * statistics.median(t['stop_frac'] for t in tl)))
    else:
        for kw in (dict(look=72), dict(look=240), dict(buf=0.1), dict(buf=0.25), dict(buf=1.0), dict(stop='origin'), dict(tgt=1.0), dict(tgt=2.0),
                   dict(liq=True), dict(c4=True), dict(c4=True, liq=True), dict(trend=False), dict(btc=True),
                   dict(minleg=1.5), dict(minleg=3.0), dict(G=5.0), dict(G=8.0), dict(inv=1.0), dict(W=24), dict(W=96)):
            report(book(**kw), str(kw))
