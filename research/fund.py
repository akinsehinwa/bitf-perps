"""#3 Funding-rate fade (crowded positioning), last 3 years, Binance USDT-M funding history.
At a 4h close (hours=sched -> 08/20/00 SGT, awake -> 08..00 SGT every 4h; never in the weekend pause):
  crowded longs : latest settled funding >= its own trailing-90-day pct-th percentile AND >= abs_min,
                  and the 4h candle closes below the previous candle's low (longs failing)      -> SHORT
  crowded shorts: funding <= its (100-pct)-th percentile AND <= -abs_min, and the candle closes above
                  the previous candle's high                                                     -> LONG
btc=with|against|any : agree with / oppose / ignore BTC's 4h trend. rvol=x: signal candle volume >= x * 20-bar avg.
Entry: entry=mkt next 1h open, or entry=lim limit 0.5 ATR back for 8h. Stop: beyond the last 3 candles' extreme
+ 0.1 ATR (min 1 ATR). Target: after-fee tr x R. 48h time stop, weekend close, 0.04% fee per side, 1h execution."""
import sys, statistics, bisect, collections
S = '/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad'
sys.path.insert(0, S); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps
P = dict(a.split('=') for a in sys.argv[1:] if '=' in a)
num = lambda k, d: float(P.get(k, d))
H = perps.HOUR_MS; H4 = 4 * H; D = 86_400_000
cfg = perps.load_config(); sch = cfg['schedule']; st = dict(cfg['strategy'])
FEE = 0.0004; FEE_RT = 0.0008
START = int(perps.dt.datetime(2023, 11, 12, tzinfo=perps.UTC).timestamp() * 1000)
load = lambda s, iv: perps.load_json(perps.cache_file(s, iv), [])
REG = perps.btc_regime(load('BTC', '4h'), st)
mk = perps.load_markets()
if P.get('uni', '10') == 'all':
    SYMS = [k for k, v in mk.items() if v['type'] == 'crypto' and v.get('binance')]
else:
    SYMS = cfg['symbols']


def walk(b, n, side, e, stop, tgt, max_h=48):
    step = b[1][0] - b[0][0]
    flat = perps.next_weekend_stop(b[n][0], sch)
    m = n
    for m in range(n, min(len(b), n + int(max_h * H / step))):
        o, h, l = b[m][1], b[m][2], b[m][3]
        if b[m][0] >= flat:
            return o, 'weekend', b[m][0]
        if (side == 1 and l <= stop) or (side == -1 and h >= stop):
            return ((min(o, stop) if side == 1 else max(o, stop)) if m > n else stop), 'stop', b[m][0] + step
        if m > n and ((side == 1 and h >= tgt) or (side == -1 and l <= tgt)):
            return tgt, 'target', b[m][0] + step
    return b[m][4], 'time', b[m][0] + step


def run(sym):
    fr = load(sym, 'funding')
    b4, b1 = load(sym, '4h'), load(sym, '1h')
    if len(fr) < 300 or len(b4) < 300 or len(b1) < 1000:
        return []
    ft = [x[0] for x in fr]; fv = [x[1] for x in fr]
    i1 = {x[0]: k for k, x in enumerate(b1)}
    c4 = [x[4] for x in b4]
    at = perps.atr([x[2] for x in b4], [x[3] for x in b4], c4, 14)
    out, busy = [], 0
    pct = num('pct', 95); amin = num('abs', 0.0001)
    for i in range(30, len(b4) - 1):
        tc = b4[i][0] + H4
        if tc < START or tc < busy or at[i] is None or perps.in_weekend(tc, sch):
            continue
        hs = perps.local_dt(tc, 8).hour
        hours = P.get('hours', 'sched')
        if hours == 'sched' and hs not in (8, 20, 0):
            continue
        if hours == 'awake' and hs == 4:
            continue
        k = bisect.bisect_right(ft, tc) - 1          # latest funding settled at or before the close
        if k < 270:
            continue
        cur = fv[k]
        hist = sorted(fv[k - 270:k])                  # ~90 days of 8h fundings
        hi_th = hist[int(pct / 100 * (len(hist) - 1))]
        lo_th = hist[int((100 - pct) / 100 * (len(hist) - 1))]
        o, h, l, c = b4[i][1:5]
        side = 0
        if cur >= hi_th and cur >= amin and c < b4[i - 1][3]:
            side = -1
        elif cur <= lo_th and cur <= -amin and c > b4[i - 1][2]:
            side = 1
        if not side:
            continue
        b = P.get('btc', 'any')
        r = REG.get(b4[i][0])
        if b != 'any' and (r is None or ((r > 0) == (side == 1)) != (b == 'with')):
            continue
        if num('rvol', 0) > 0:
            v = [x[5] for x in b4[i - 20:i]]
            if b4[i][5] < num('rvol', 0) * statistics.mean(v):
                continue
        n0 = i1.get(tc)
        if n0 is None:
            continue
        a = at[i]
        ext = max(x[2] for x in b4[i - 2:i + 1]) if side == -1 else min(x[3] for x in b4[i - 2:i + 1])
        if P.get('entry', 'mkt') == 'lim':
            lim = c - side * 0.5 * a
            n = None
            for m in range(n0, min(len(b1), n0 + 8)):
                if (side == 1 and b1[m][3] <= lim) or (side == -1 and b1[m][2] >= lim):
                    n, e = m, (min(b1[m][1], lim) if side == 1 else max(b1[m][1], lim)); break
            if n is None:
                continue
        else:
            n, e = n0, b1[n0][1]
        stop = ext - side * 0.1 * a
        if abs(e - stop) < a:
            stop = e - side * a
        if (side == 1 and stop >= e) or (side == -1 and stop <= e):
            continue
        d = abs(e - stop)
        tgt = e + side * (num('tr', 2) * (d + FEE_RT * e) + FEE_RT * e)
        px, why, to = walk(b1, n, side, e, stop, tgt)
        out.append({'sym': sym, 't_in': b1[n][0], 't_out': to, 'exit': why, 'side': side, 'fund': cur,
                    'r': (side * (px - e) / e - 2 * FEE) / (d / e + FEE_RT)})
        busy = to
    return out


if __name__ == '__main__':
    sys.argv = [sys.argv[0]]
    import family as F
    tr = sorted([t for s in SYMS for t in run(s)], key=lambda t: t['t_in'])
    lab = ' '.join('%s=%s' % kv for kv in P.items()) or 'defaults'
    if not tr:
        print(lab, 'no trades'); sys.exit()
    rs = [t['r'] for t in tr]
    sides = collections.Counter('long' if t['side'] == 1 else 'short' for t in tr)
    print('%-44s %+.2fR win %2.0f%% %5.1f/mo %+5.1fR/mo | %s | %s' % (lab, statistics.mean(rs), 100 * sum(x > 0 for x in rs) / len(rs),
          len(rs) / 36.5, sum(rs) / 36.5, F.yr(tr), dict(sides)))
    if P.get('sim'):
        q = F.q_4h(55)
        print('    alone   risk 1.5%%: %s' % F.sim(F.book(tr), 1.5))
        print('    with Q  risk 1.5%%: %s' % F.sim(F.book(q, tr), 1.5))
