"""User strategy "iFVG retrace": 4h parent leg -> 50/61.8% retracement -> 1h inverted FVG -> limit at the FVG midline.

RULE (as described by the user, made mechanical):
  Swings: 4h zigzag; a swing high/low is confirmed only when price reverses k x ATR(14, 4h) from it, so
          small pauses (1-2 tiny counter candles) inside a big leg are not swings. Pivot known at confirmation.
  Parent leg: most recent leg (completed pivot->pivot, or last pivot -> running extreme), size >= G x ATR.
  Arm: a 1h bar trades into the 50% retracement of the leg (bull leg: low <= H - 0.5 x size).
       Disarm if a 1h close goes beyond the inv level (default 78.6%) or after W hours without a trigger.
  Trigger (bull leg / long; short is mirrored): a 1h bearish FVG formed during the retracement
       (high[j] < low[j-2], after the leg end) is INVERTED: a later 1h close > its top (low[j-2]).
       Limit buy at the FVG midline, valid V hours.
  Stop: retracement extreme (lowest low since the leg end) - 0.1 ATR(4h)   [stop='ext']
        or leg origin - 0.1 ATR                                          [stop='leg']
  Target: after-fee tgt R (house formula) or the leg end (tgt='leg', skipped if < 1R).
  One shot per leg; one position per coin; max hold 72h; no orders in the weekend pause, flat at Sat 04:00 SGT.
EXECUTION (house rules): 1h bars; limit fills only if a bar trades through it by 0.05 ATR(4h); stop first if a bar
  touches both; no target on the fill bar; 0.04% fee per side; R = (side*(exit-e)/e - 0.08%) / (stop/e + 0.08%).
  Window: 2023-11-12 .. data end, 70/30 split 2025-12-18."""
import sys, statistics, collections
sys.path.insert(0, '/home/user/bitfunded-perps')
import perps

H = 3600_000; H4 = 4 * H; D = 86_400_000; FRT = 0.0008
START = int(perps.dt.datetime(2023, 11, 12, tzinfo=perps.UTC).timestamp() * 1000)
SPLIT = int(perps.dt.datetime(2025, 12, 18, tzinfo=perps.UTC).timestamp() * 1000)
CFG = perps.load_config(); SCH = CFG['schedule']
USER = ['SUI', 'UNI', 'BTC', 'ETH', 'SOL', 'NEAR', 'ADA', 'LINK']
OTHER = ['BNB', 'XRP', 'HYPE', 'ZEC']
load = lambda s, iv: perps.load_json(perps.cache_file(s, iv), [])
REG = perps.btc_regime(load('BTC', '4h'), CFG['strategy'])


def zigzag(b, atr, k):
    """Return pivots [(idx, price, +1 high / -1 low, confirm_idx)]."""
    piv = []; d = 0; ext_i = 0
    for i in range(15, len(b)):
        a = atr[i]
        if a is None:
            continue
        if d == 0:
            d, ext_i = 1, i
            continue
        if d == 1:
            if b[i][2] >= b[ext_i][2]:
                ext_i = i
            elif b[ext_i][2] - b[i][3] >= k * a:
                piv.append((ext_i, b[ext_i][2], 1, i)); d, ext_i = -1, i
        else:
            if b[i][3] <= b[ext_i][3]:
                ext_i = i
            elif b[i][2] - b[ext_i][3] >= k * a:
                piv.append((ext_i, b[ext_i][3], -1, i)); d, ext_i = 1, i
    return piv


def run(sym, k=2.0, G=3.0, W=48, V=12, inv=0.786, stop='ext', tgt=2.0, btc=False, hold=72, arm=0.5):
    b4 = load(sym, '4h'); b1 = load(sym, '1h')
    if len(b4) < 300:
        return []
    atr = perps.atr([x[2] for x in b4], [x[3] for x in b4], [x[4] for x in b4], 14)
    piv = zigzag(b4, atr, k)
    i1 = {x[0]: n for n, x in enumerate(b1)}
    out = []; used = set(); busy = 0; pk = 0
    for i in range(200, len(b4) - 1):
        T = b4[i][0] + H4
        if T < START:
            continue
        while pk < len(piv) and piv[pk][3] <= i:
            pk += 1
        known = piv[:pk]
        if len(known) < 2:
            continue
        a = atr[i]
        last = known[-1]; prev = known[-2]
        legs = []
        # completed leg prev -> last
        legs.append((prev, last[0], last[1]))
        # in-progress leg last -> running extreme
        seg = b4[last[0] + 1:i + 1]
        if seg:
            if last[2] == -1:
                j = max(range(last[0] + 1, i + 1), key=lambda q: b4[q][2]); legs.append((last, j, b4[j][2]))
            else:
                j = min(range(last[0] + 1, i + 1), key=lambda q: b4[q][3]); legs.append((last, j, b4[j][3]))
        n0 = i1.get(T)
        if n0 is None:
            continue
        for org, end_i, end_px in legs:
            side = 1 if org[2] == -1 else -1           # leg up from a low -> buy the pullback
            size = (end_px - org[1]) * side
            if size < G * a or (org[0], side) in used:
                continue
            lvl = lambda f: end_px - side * f * size
            # retracement so far (4h bars after the leg end up to i) must not already be beyond inv
            after = b4[end_i + 1:i + 1]
            ext = min((x[3] for x in after), default=end_px) if side == 1 else max((x[2] for x in after), default=end_px)
            if (ext - lvl(inv)) * side < 0:
                used.add((org[0], side)); continue
            if btc:
                r = REG.get(b4[i][0])
                if r is None or (r > 0) != (side == 1):
                    continue
            # walk the next 4 1h bars for the arm touch
            armed = None
            for m in range(n0, min(len(b1), n0 + 4)):
                x = b1[m]
                if (side == 1 and x[2] > end_px) or (side == -1 and x[3] < end_px):
                    break                                   # leg still extending
                if (side == 1 and x[3] <= lvl(arm)) or (side == -1 and x[2] >= lvl(arm)):
                    armed = m; break
            if armed is None:
                continue
            used.add((org[0], side))
            if b1[armed][0] < busy:
                continue
            t_end = b4[end_i][0] + H4                       # retracement starts after the leg-end candle
            s_fvg = i1.get(t_end)
            if s_fvg is None:
                continue
            fv = []                                         # (top/bottom pair) opposite-direction FVGs
            for j in range(s_fvg + 2, armed + 1):
                if side == 1 and b1[j][2] < b1[j - 2][3]:
                    fv.append((b1[j][2], b1[j - 2][3]))
                if side == -1 and b1[j][3] > b1[j - 2][2]:
                    fv.append((b1[j - 2][2], b1[j][3]))
            sig = None
            rx = min(x[3] for x in b1[s_fvg:armed + 1]) if side == 1 else max(x[2] for x in b1[s_fvg:armed + 1])
            for m in range(armed, min(len(b1) - 1, armed + W)):
                x = b1[m]
                if m > armed and m - 2 >= s_fvg:
                    j = m
                    if side == 1 and b1[j][2] < b1[j - 2][3]:
                        fv.append((b1[j][2], b1[j - 2][3]))
                    if side == -1 and b1[j][3] > b1[j - 2][2]:
                        fv.append((b1[j - 2][2], b1[j][3]))
                rx = min(rx, x[3]) if side == 1 else max(rx, x[2])
                if (side == 1 and x[4] < lvl(inv)) or (side == -1 and x[4] > lvl(inv)):
                    break
                hit = [g for g in fv if (side == 1 and x[4] > g[1]) or (side == -1 and x[4] < g[0])]
                if hit:
                    g = hit[-1]; sig = (m, (g[0] + g[1]) / 2); break
                fv = [g for g in fv if not ((side == 1 and x[4] > g[1]) or (side == -1 and x[4] < g[0]))]
            if sig is None:
                continue
            m, lim = sig
            t_place = b1[m][0] + H
            if perps.in_weekend(t_place, SCH):
                continue
            stp = (rx if stop == 'ext' else org[1]) - side * 0.1 * a
            if (lim - stp) * side <= 0 or abs(lim - stp) / lim < 0.002:
                continue
            n = e = None
            for q in range(m + 1, min(len(b1), m + 1 + V)):
                x = b1[q]
                if (side == 1 and x[3] <= stp) or (side == -1 and x[2] >= stp):
                    break                                   # stop traded before the fill: cancel
                if (side == 1 and x[3] <= lim - 0.05 * a) or (side == -1 and x[2] >= lim + 0.05 * a):
                    n, e = q, (min(x[1], lim) if side == 1 else max(x[1], lim)); break
            if n is None:
                continue
            d = abs(e - stp)
            if (stp - e) * side >= 0:
                continue
            if tgt == 'leg':
                tp = end_px
                if (tp - e) * side / d < 1.0:
                    continue
            else:
                tp = e + side * (tgt * (d + FRT * e) + FRT * e)
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
            r = (side * (px - e) / e - FRT) / (d / e + FRT)
            out.append({'sym': sym, 'side': side, 't_in': b1[n][0], 't_out': b1[q][0] + H, 'r': r, 'exit': why,
                        'stop_frac': d / e, 'sig': t_place, 'e': e, 'stp': stp})
            busy = b1[q][0] + H
    return out


def stats(tl, months=None):
    rs = [t['r'] for t in tl]
    if not rs:
        return 'n=0'
    months = months or (max(t['t_in'] for t in tl) - START) / D / 30.44
    eq = pk = dd = 0
    for t in sorted(tl, key=lambda t: t['t_out']):
        eq += t['r']; pk = max(pk, eq); dd = max(dd, pk - eq)
    gw = sum(x for x in rs if x > 0); gl = -sum(x for x in rs if x <= 0)
    return 'n=%4d %4.1f/mo win %3.0f%% avg %+.3fR pf %4.2f %+5.2fR/mo dd %5.1fR' % (
        len(rs), len(rs) / months, 100 * sum(x > 0 for x in rs) / len(rs), statistics.mean(rs), gw / gl if gl else 9,
        sum(rs) / months, dd)


def book(syms, **kw):
    return sorted([t for s in syms for t in run(s, **kw)], key=lambda t: t['t_in'])


def report(tl, label):
    END = max(t['t_in'] for t in tl) if tl else START
    Y = [START, START + 365 * D, START + 730 * D, END + 1]
    yr = []
    for y in range(3):
        xs = [t['r'] for t in tl if Y[y] <= t['t_in'] < Y[y + 1]]
        yr.append('%+.2f' % statistics.mean(xs) if xs else 'n/a')
    isr = [t['r'] for t in tl if t['t_in'] < SPLIT]; osr = [t['r'] for t in tl if t['t_in'] >= SPLIT]
    print('%-40s %s | yrs %s | IS %+.2f OS %+.2f' % (label, stats(tl, 36.0), '/'.join(yr),
          statistics.mean(isr) if isr else 0, statistics.mean(osr) if osr else 0), flush=True)


if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'base'
    if what == 'base':
        tl = book(USER); report(tl, 'BASE user 8 coins')
        for s in USER:
            report([t for t in tl if t['sym'] == s], '  ' + s)
        report(book(OTHER), 'BASE other 4 coins')
        print('exits', collections.Counter(t['exit'] for t in tl))
    elif what == 'grid':
        for k in (1.5, 2.0, 3.0):
            for G in (3.0, 5.0, 8.0):
                report(book(USER, k=k, G=G), 'k %.1f G %.0f' % (k, G))
        for kw in (dict(tgt=1.0), dict(tgt=1.5), dict(tgt=3.0), dict(tgt='leg'), dict(stop='leg'), dict(btc=True),
                   dict(inv=1.0), dict(arm=0.618), dict(W=24), dict(W=96), dict(V=4), dict(V=24)):
            report(book(USER, **kw), str(kw))
