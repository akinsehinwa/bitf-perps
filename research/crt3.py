"""Candle range theory, 3-candle version (trader's description).
HTF (htf=1h|2h|4h, built from 15m):
  C1 range candle: body >= body% of its range (small wicks) and range >= rng x ATR(14, HTF).
  C2 sweeps one end of C1 (bullish C1 -> sweeps C1 high; bearish C1 -> sweeps C1 low) and closes back inside C1.
  -> trade AGAINST C1's direction, toward C1's far end.
Entry on 15m during C3 (the next HTF candle): when price breaks C2's low (short) / high (long); entry=brk (default)
  or entry=open: market at C3 open.
Stop: beyond C2's sweep extreme + buf x ATR. Target: C1's far end (low for a short, high for a long). Skip if < minrr.
Filters: wick=x C2 sweep wick >= x of C2's range; level=1 C2's sweep extreme within 0.5 ATR of a prior HTF swing
  (3-bar pivot) in the last 60 HTF bars (a 'key level to the left'); btc=1 BTC 4h trend agrees.
Exits on 15m; stop first if a bar touches both; target never on the fill bar; time stop hold= hours; weekend close.
Last 3 years, 10 coins, 0.04% fee per side, max 1 trade per coin per day, weekend pause."""
import sys, statistics, collections
sys.path.insert(0, '/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad')
import rq, perps
P = dict(a.split('=') for a in sys.argv[1:] if '=' in a)
num = lambda k, d: float(P.get(k, d))
H, D, M15 = rq.H, rq.D, rq.M15
FEE = num('fee', 0.04) / 100
TF = {'1h': 4 * M15, '2h': 8 * M15, '4h': 16 * M15}


def pivots_of(bars, n, ms):
    out = []
    hh = [x[2] for x in bars]; ll = [x[3] for x in bars]
    for p in range(n, len(bars) - n):
        conf = bars[p + n][0] + ms            # confirmed when the n-th bar after it closes
        if hh[p] == max(hh[p - n:p + n + 1]):
            out.append((conf, hh[p], 'H'))
        if ll[p] == min(ll[p - n:p + n + 1]):
            out.append((conf, ll[p], 'L'))
    return out


def levels(b15, mode):
    """Higher-timeframe key levels as (confirmed_at_ms, price, 'H'|'L')."""
    if not mode:
        return None
    if mode == 'daily':
        return pivots_of(rq.aggregate(b15, D), 2, D)
    b4 = rq.aggregate(b15, 16 * M15)
    if mode == '4hmajor':
        return pivots_of(b4, 5, 16 * M15)
    if mode == 'cluster':
        pv = pivots_of(b4, 3, 16 * M15)
        a4 = perps.atr([x[2] for x in b4], [x[3] for x in b4], [x[4] for x in b4], 14)
        atr_at = {x[0] + 16 * M15: a4[k] for k, x in enumerate(b4)}
        out = []
        for k, (tc, px, kd) in enumerate(pv):
            a = atr_at.get(tc - 3 * 16 * M15) or 0
            prior = [q for q in pv[max(0, k - 60):k] if q[2] == kd and abs(q[1] - px) <= 0.5 * a]
            if prior:
                out.append((tc, max(px, max(q[1] for q in prior)) if kd == 'H' else min(px, min(q[1] for q in prior)), kd))
        return out
    return None


def run(sym):
    b15 = perps.load_json(perps.cache_file(sym, '15m'), [])
    if len(b15) < 2000:
        return []
    i15 = {x[0]: k for k, x in enumerate(b15)}
    tms = TF[P.get('htf', '1h')]
    b = rq.aggregate(b15, tms)
    o = [x[1] for x in b]; h = [x[2] for x in b]; l = [x[3] for x in b]; c = [x[4] for x in b]
    at = perps.atr(h, l, c, 14)
    LV = levels(b15, P.get('klev', ''))
    out, busy, days = [], 0, collections.Counter()
    for i in range(20, len(b) - 1):
        a = at[i]
        t3 = b[i][0] + tms                       # C3 opens when C2 (bar i) closes
        if a is None or t3 < rq.START or t3 < busy or perps.in_weekend(t3, rq.sch) or days[t3 // D] >= 1:
            continue
        j = i - 1                                 # C1
        rng1 = h[j] - l[j]
        if rng1 <= 0 or abs(c[j] - o[j]) < num('body', 0.7) * rng1 or rng1 < num('rng', 1.0) * a:
            continue
        bull1 = c[j] > o[j]
        if bull1 and h[i] > h[j] and l[j] < c[i] < h[j]:
            side, sweep, trig, tgt = -1, h[i], l[i], l[j]
            wick = h[i] - max(o[i], c[i])
        elif not bull1 and l[i] < l[j] and l[j] < c[i] < h[j]:
            side, sweep, trig, tgt = 1, l[i], h[i], h[j]
            wick = min(o[i], c[i]) - l[i]
        else:
            continue
        if h[i] - l[i] <= 0 or wick < num('wick', 0) * (h[i] - l[i]):
            continue
        if P.get('level', '0') == '1':
            near = False
            for p in range(max(3, i - 60), i - 3):
                if side == -1 and h[p] == max(h[p - 3:p + 4]) and abs(h[p] - sweep) <= 0.5 * a:
                    near = True; break
                if side == 1 and l[p] == min(l[p - 3:p + 4]) and abs(l[p] - sweep) <= 0.5 * a:
                    near = True; break
            if not near:
                continue
        if LV is not None:
            tol = num('tol', 0.25) * a
            t2 = b[i][0]
            hit = False
            for (tc_, px_, kind_) in LV:
                if tc_ > t2 or tc_ < t2 - 60 * D:
                    continue
                if side == -1 and kind_ == 'H' and h[i] >= px_ - tol and c[i] < px_:
                    hit = True; break
                if side == 1 and kind_ == 'L' and l[i] <= px_ + tol and c[i] > px_:
                    hit = True; break
            if not hit:
                continue
        if P.get('btc', '0') == '1':
            r = rq.REG.get((t3 // (4 * H)) * 4 * H - 4 * H)
            if r is None or (r > 0) != (side == 1):
                continue
        stop = sweep - side * num('buf', 0.1) * a
        n0 = i15.get(t3)
        if n0 is None:
            continue
        n = e = None
        if P.get('conf', '0') == '1':
            # fractal confirmation: a 15m CRT in the trade's direction inside C3, entry on its C2' break
            lim = min(len(b15), n0 + tms // M15)
            for m in range(n0 + 1, lim):
                x1, x2 = b15[m - 1], b15[m]
                if (side == -1 and x2[2] >= stop) or (side == 1 and x2[3] <= stop):
                    break
                r1 = x1[2] - x1[3]
                if r1 <= 0 or abs(x1[4] - x1[1]) < num('lbody', 0.5) * r1:
                    continue
                ok = (side == -1 and x1[4] > x1[1] and x2[2] > x1[2] and x1[3] < x2[4] < x1[2]) or \
                     (side == 1 and x1[4] < x1[1] and x2[3] < x1[3] and x1[3] < x2[4] < x1[2])
                if not ok:
                    continue
                ltrig = x2[3] if side == -1 else x2[2]
                lstop = (x2[2] if side == -1 else x2[3]) - side * 0.1 * a * (0.25 if P.get('stopm') == 'ltf' else 1)
                if P.get('stopm') == 'ltf':
                    stop = lstop
                for q in range(m + 1, min(len(b15), m + 5)):
                    y = b15[q]
                    if (side == -1 and y[2] >= stop) or (side == 1 and y[3] <= stop):
                        break
                    if (side == -1 and y[3] < ltrig) or (side == 1 and y[2] > ltrig):
                        n, e = q, (min(y[1], ltrig) if side == -1 else max(y[1], ltrig))
                        break
                if n is not None:
                    break
        elif P.get('entry', 'brk') == 'open':
            n, e = n0, b15[n0][1]
        else:
            for m in range(n0, min(len(b15), n0 + tms // M15)):      # only during C3
                x = b15[m]
                if (side == -1 and x[2] >= stop) or (side == 1 and x[3] <= stop):
                    break                                            # stop taken out before the break
                if (side == -1 and x[3] < trig) or (side == 1 and x[2] > trig):
                    n, e = m, (min(x[1], trig) if side == -1 else max(x[1], trig))
                    break
        if n is None:
            continue
        d = abs(stop - e)
        if d <= 0 or d / e < 0.002 or (tgt - e) * side <= 0 or abs(tgt - e) / d < num('minrr', 1.0):
            continue
        px, why, to = rq.walk(b15, n, side, e, stop, tgt, b15[n][0] + num('hold', 24) * H)
        out.append({'sym': sym, 'side': side, 't_in': b15[n][0], 't_out': to, 'exit': why,
                    'r': (side * (px - e) / e - 2 * FEE) / (d / e + 2 * FEE), 'stop_pct': d / e * 100,
                    'tgt_pct': abs(tgt - e) / e * 100, 'rr': abs(tgt - e) / d})
        busy = to; days[t3 // D] += 1
    return out


if __name__ == '__main__':
    trades = sorted([t for s in rq.SYMS for t in run(s)], key=lambda t: t['t_in'])
    rq.table(trades, ' '.join(sys.argv[1:]) or 'htf=1h defaults')
    if trades and P.get('show'):
        print('    median planned R:R %.2f' % statistics.median(t['rr'] for t in trades))
