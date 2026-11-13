"""30m-signal strategies, 15m execution, last 3 years, 0.04% fee per side, max 1 trade per coin per day,
entries 08:00-01:00 SGT outside the weekend pause, 24h max hold, weekend close.
  ema : EMA20 crosses EMA50 on 30m. stoch=under80: long only if StochRSI K < 80 (short if K > 20);
        stoch=extreme: long only if StochRSI K < 20 at the cross (short if K > 80). Stop 1.5 x ATR(30m), 2R.
  sr  : support/resistance flip. A 30m close through the prior UTC-day high (low); then a limit at that level
        for the next `valid` hours (retest); stop 1 x ATR(30m) beyond the level, target 2R.
btc=1 adds the BTC 4h trend filter."""
import sys, statistics, collections
sys.path.insert(0, '/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad')
sys.argv = [sys.argv[0]] + sys.argv[1:]
import rq, perps
P = dict(a.split('=') for a in sys.argv[2:] if '=' in a)
num = lambda k, d: float(P.get(k, d))
H, D, M15 = rq.H, rq.D, rq.M15
M30 = 2 * M15
FEE = 0.0004


def stochrsi(c, n=14, k=3):
    r = perps.rsi(c, n)
    out = [None] * len(c); raw = [None] * len(c)
    for i in range(len(c)):
        w = [x for x in r[max(0, i - n + 1):i + 1] if x is not None]
        if len(w) == n:
            lo, hi = min(w), max(w)
            raw[i] = 100 * (r[i] - lo) / (hi - lo) if hi > lo else 50
    for i in range(len(c)):
        w = [x for x in raw[max(0, i - k + 1):i + 1] if x is not None]
        if len(w) == k:
            out[i] = sum(w) / k
    return out


def ok_time(tc, side):
    if tc < rq.START or perps.in_weekend(tc, rq.sch):
        return False
    hs = perps.local_dt(tc, 8).hour
    if not (hs >= 8 or hs < 1):
        return False
    if P.get('btc', '0') == '1':
        r = rq.REG.get((tc // (4 * H)) * 4 * H - 4 * H)
        if r is None or (r > 0) != (side == 1):
            return False
    return True


def trade(sym, b15, n, side, e, stop, out):
    d = abs(stop - e)
    if d <= 0 or d / e < 0.002:
        return None
    tgt = e + side * num('tr', 2) * d
    px, why, to = rq.walk(b15, n, side, e, stop, tgt, b15[n][0] + 24 * H)
    out.append({'sym': sym, 'side': side, 't_in': b15[n][0], 't_out': to, 'exit': why,
                'r': (side * (px - e) / e - 2 * FEE) / (d / e + 2 * FEE), 'stop_pct': d / e * 100, 'tgt_pct': num('tr', 2) * d / e * 100})
    return to


def s_ema(sym):
    b15 = perps.load_json(perps.cache_file(sym, '15m'), [])
    i15 = {x[0]: k for k, x in enumerate(b15)}
    b = rq.aggregate(b15, M30)
    c = [x[4] for x in b]
    e20, e50 = perps.ema(c, 20), perps.ema(c, 50)
    at = perps.atr([x[2] for x in b], [x[3] for x in b], c, 14)
    sk = stochrsi(c)
    out, busy, days = [], 0, collections.Counter()
    for i in range(60, len(b) - 1):
        tc = b[i][0] + M30
        if tc < busy or e50[i - 1] is None or sk[i] is None or at[i] is None:
            continue
        up = e20[i - 1] <= e50[i - 1] and e20[i] > e50[i]
        dn = e20[i - 1] >= e50[i - 1] and e20[i] < e50[i]
        if not (up or dn):
            continue
        side = 1 if up else -1
        mode = P.get('stoch', 'none')
        if mode == 'under80' and ((side == 1 and sk[i] >= 80) or (side == -1 and sk[i] <= 20)):
            continue
        if mode == 'extreme' and ((side == 1 and sk[i] > 20) or (side == -1 and sk[i] < 80)):
            continue
        if not ok_time(tc, side) or days[tc // D] >= 1:
            continue
        n = i15.get(tc)
        if n is None:
            continue
        e = b15[n][1]
        to = trade(sym, b15, n, side, e, e - side * num('stop', 1.5) * at[i], out)
        if to:
            busy = to; days[tc // D] += 1
    return out


def s_sr(sym):
    b15 = perps.load_json(perps.cache_file(sym, '15m'), [])
    b = rq.aggregate(b15, M30)
    c = [x[4] for x in b]
    at = perps.atr([x[2] for x in b], [x[3] for x in b], c, 14)
    rng = {}
    for x in b15:
        k = x[0] // D
        r = rng.setdefault(k, [x[2], x[3]]); r[0] = max(r[0], x[2]); r[1] = min(r[1], x[3])
    i15 = {x[0]: k for k, x in enumerate(b15)}
    out, busy, days = [], 0, collections.Counter()
    valid = int(num('valid', 6) * 4)
    for i in range(20, len(b) - 1):
        tc = b[i][0] + M30
        if tc < busy or at[i] is None or (tc // D - 1) not in rng:
            continue
        PDH, PDL = rng[tc // D - 1]
        side = 1 if (b[i][4] > PDH and b[i - 1][4] <= PDH) else -1 if (b[i][4] < PDL and b[i - 1][4] >= PDL) else 0
        if not side or not ok_time(tc, side) or days[tc // D] >= 1:
            continue
        lvl = PDH if side == 1 else PDL
        n0 = i15.get(tc)
        if n0 is None:
            continue
        stop = lvl - side * num('stop', 1.0) * at[i]
        for m in range(n0, min(len(b15), n0 + valid)):
            if (side == 1 and b15[m][2] - 0 < lvl) and False:
                pass
            if (side == 1 and b15[m][3] <= lvl) or (side == -1 and b15[m][2] >= lvl):
                if (side == 1 and b15[m][1] <= stop) or (side == -1 and b15[m][1] >= stop):
                    break
                e = min(b15[m][1], lvl) if side == 1 else max(b15[m][1], lvl)
                to = trade(sym, b15, m, side, e, stop, out)
                if to:
                    busy = to; days[tc // D] += 1
                break
    return out


if __name__ == '__main__':
    fn = {'ema': s_ema, 'sr': s_sr}[sys.argv[1]]
    trades = sorted([t for s in rq.SYMS for t in fn(s)], key=lambda t: t['t_in'])
    rq.table(trades, ' '.join(sys.argv[1:]))
