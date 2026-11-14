"""Q lab: Q's 4h signals (with features) + entry / stop / exit variants simulated on 15m bars.
Signals: perps.signal with the live strategy config (donchian, body filter, BTC 4h trend, scan hours, no Monday).
Entry (entry=):
  atr:k     limit at close -/+ k x ATR                (live Q = atr:0.5)
  lvl:k     limit at the broken level +/- k x ATR     (retest; k<0 = beyond the level)
  body:f    limit at close -/+ f x breakout-candle body
  fvg:top|mid  limit at the latest 1h fair value gap formed in the breakout's direction during the
            breakout candle (top = shallow edge, mid = middle); no FVG -> no trade
  mkt       market at the next 15m open
  split:k   half market, half limit atr:k (each half risks half)
Fill model: a limit fills only if price trades THROUGH it by pen x ATR (pen=0 -> touch); fill at the limit
  (or the open if it gapped through). Valid valid= hours.
Stop (stop=): sig:k close -/+ k ATR (live: sig:2) | cand  beyond the breakout candle's extreme + 0.1 ATR
  | lvl:k  broken level -/+ k ATR.
Exit: after-fee tr= R target; part=1 takes half at 1R (rest to the target); be=x moves the stop to entry
  (+fees) once price is x R in favour; hold= hours; weekend close. Stop first if a bar touches both;
  no target on the fill bar. 0.04% fee per side."""
import sys, statistics, collections, bisect
S = '/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad'
sys.path.insert(0, S); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps, daily
H = perps.HOUR_MS; H4 = 4 * H; M15 = 15 * 60_000; D = 86_400_000
FEE = 0.0004; FRT = 0.0008
cfg = perps.load_config(); SCH = cfg['schedule']; ST = dict(cfg['strategy'])
START = int(perps.dt.datetime(2023, 11, 12, tzinfo=perps.UTC).timestamp() * 1000)
SYMS = cfg['symbols']
load = lambda s, iv: perps.load_json(perps.cache_file(s, iv), [])
REG = perps.btc_regime(load('BTC', '4h'), ST)
_b15 = {}


def b15(sym):
    if sym not in _b15:
        rows = load(sym, '15m')
        _b15[sym] = (rows, {r[0]: k for k, r in enumerate(rows)})
    return _b15[sym]


_met = {}


def metrics_window(sym, t0, t1):
    if sym not in _met:
        rows = load(sym, 'metrics'); _met[sym] = ([r[0] for r in rows], rows)
    ts, rows = _met[sym]
    a = bisect.bisect_left(ts, t0); b = bisect.bisect_right(ts, t1) - 1
    return rows[a:b + 1] if b - a >= 30 else None


def signals(st=None, sch=None, syms=None, start=START):
    st = st or ST; sch = sch or SCH; syms = syms or SYMS
    inds = {s: (load(s, '4h'), None) for s in syms}
    raw = collections.Counter()
    for s in syms:
        b4 = inds[s][0]; ind = perps.indicators(b4, dict(st, min_body_atr=0)); inds[s] = (b4, ind)
        for i in range(st['ema_slow'] + 1, len(b4)):
            if perps.signal(ind, i, dict(st, min_body_atr=0)):
                raw[b4[i][0]] += 1
    out = []
    for s in syms:
        b4, _ = inds[s]
        ind = perps.indicators(b4, st)
        for i in range(st['ema_slow'] + 1, len(b4) - 1):
            close = b4[i][0] + H4
            if close < start or not perps.entry_allowed(close, sch):
                continue
            sg = perps.signal(ind, i, st)
            if not sg:
                continue
            side = 1 if sg['side'] == 'long' else -1
            r = REG.get(b4[i][0])
            if st.get('regime_filter') and (r is None or (r > 0) != (side == 1)):
                continue
            a = ind['atr'][i]; c = ind['c'][i]; o = ind['o'][i]
            lvl = ind['hh'][i] if side == 1 else ind['ll'][i]
            vol = [x[5] for x in b4[i - 20:i]]
            w = metrics_window(s, b4[i][0], close)
            f = {'body_atr': abs(c - o) / a, 'breadth': raw[b4[i][0]], 'rvol': b4[i][5] / statistics.mean(vol) if vol else 1,
                 'atr_pct': a / c * 100, 'ext_atr': (c - lvl) * side / a, 'dist_ema50': (c - ind['ef'][i]) * side / a,
                 'coin_daily': (daily.bias(s, close, 'ema') or 0) * side, 'btc_daily': (daily.bias('BTC', close, 'strict') or 0) * side,
                 'hour': perps.local_dt(close, 8).hour, 'oi_chg': None, 'taker': None}
            if w and w[0][1]:
                f['oi_chg'] = (w[-1][1] / w[0][1] - 1) * 100
                m = statistics.mean(x[6] for x in w)
                f['taker'] = m if side == 1 else 1 / m
            out.append({'sym': s, 'side': side, 'close': close, 'i': i, 'c': c, 'o': o, 'h': ind['h'][i], 'l': ind['l'][i],
                        'a': a, 'lvl': lvl, 'f': f})
    return sorted(out, key=lambda x: x['close'])


def fvg_level(sig, how):
    rows, idx = b15(sig['sym'])
    t0 = sig['close'] - H4 - 2 * H
    hrs = []
    for t in range(t0, sig['close'], H):
        k = idx.get(t)
        if k is None or k + 3 >= len(rows):
            return None
        seg = rows[k:k + 4]
        hrs.append((max(x[2] for x in seg), min(x[3] for x in seg)))
    s = sig['side']; best = None
    for j in range(2, len(hrs)):
        if s == 1 and hrs[j][1] > hrs[j - 2][0]:
            best = (hrs[j - 2][0], hrs[j][1])
        if s == -1 and hrs[j][0] < hrs[j - 2][1]:
            best = (hrs[j][0], hrs[j - 2][1])
    if not best:
        return None
    lo, hi = best
    if how == 'mid':
        return (lo + hi) / 2
    return hi if s == 1 else lo


def execute(sig, entry='atr:0.5', stop='sig:2', tr=2.0, pen=0.0, valid=8, hold=48, part=0, be=0):
    rows, idx = b15(sig['sym'])
    n0 = idx.get(sig['close'])
    if n0 is None:
        return None
    s, c, a = sig['side'], sig['c'], sig['a']
    kind, _, arg = entry.partition(':')
    if kind == 'split':
        r1 = execute(sig, 'mkt', stop, tr, pen, valid, hold, part, be)
        r2 = execute(sig, 'atr:' + arg, stop, tr, pen, valid, hold, part, be)
        if r1 is None:
            return None
        if r2 is None or not r2['filled']:
            return dict(r1, r=r1['r'] / 2, legs=1)
        return dict(r1, r=(r1['r'] + r2['r']) / 2, legs=2)
    if kind == 'mkt':
        lim = None
    elif kind == 'atr':
        lim = c - s * float(arg) * a
    elif kind == 'lvl':
        lim = sig['lvl'] + s * float(arg) * a
    elif kind == 'body':
        lim = c - s * float(arg) * abs(c - sig['o'])
    elif kind == 'fvg':
        lim = fvg_level(sig, arg)
        if lim is None:
            return {'filled': False, 'nofvg': True}
    sk, _, sarg = stop.partition(':')
    if sk == 'sig':
        stp = c - s * float(sarg) * a
    elif sk == 'cand':
        stp = (sig['l'] - 0.1 * a) if s == 1 else (sig['h'] + 0.1 * a)
    else:
        stp = sig['lvl'] - s * float(sarg) * a
    n = e = None
    if lim is None:
        n, e = n0, rows[n0][1]
    else:
        if (s == 1 and lim <= stp) or (s == -1 and lim >= stp):
            return {'filled': False}
        for m in range(n0, min(len(rows), n0 + int(valid * 4))):
            x = rows[m]
            if (s == 1 and x[3] <= lim - pen * a) or (s == -1 and x[2] >= lim + pen * a):
                n, e = m, (min(x[1], lim) if s == 1 else max(x[1], lim)); break
        if n is None:
            return {'filled': False}
    if (s == 1 and stp >= e) or (s == -1 and stp <= e):
        return {'filled': False}
    d = abs(e - stp)
    if d / e < 0.002:
        return {'filled': False}
    tgt = e + s * (tr * (d + FRT * e) + FRT * e)
    t1 = e + s * (1 * (d + FRT * e) + FRT * e)
    flat = perps.next_weekend_stop(rows[n][0], SCH)
    cur_stop = stp; half_done = None; px = why = None
    for m in range(n, min(len(rows), n + hold * 4)):
        o, h, l = rows[m][1], rows[m][2], rows[m][3]
        if rows[m][0] >= flat:
            px, why = o, 'weekend'; break
        if (s == 1 and l <= cur_stop) or (s == -1 and h >= cur_stop):
            px = ((min(o, cur_stop) if s == 1 else max(o, cur_stop)) if m > n else cur_stop); why = 'stop'; break
        if m > n:
            if part and half_done is None and ((s == 1 and h >= t1) or (s == -1 and l <= t1)):
                half_done = t1
            if (s == 1 and h >= tgt) or (s == -1 and l <= tgt):
                px, why = tgt, 'target'; break
            if be and ((s == 1 and h >= e + be * d) or (s == -1 and l <= e - be * d)):
                cur_stop = max(cur_stop, e * (1 + FRT)) if s == 1 else min(cur_stop, e * (1 - FRT))
    if px is None:
        px, why = rows[m][4], 'time'
    R = lambda p: (s * (p - e) / e - FRT) / (d / e + FRT)
    r = R(px) if not (part and half_done is not None) else (R(half_done) + R(px)) / 2
    return {'filled': True, 'r': r, 'exit': why, 't_in': rows[n][0], 't_out': rows[m][0] + M15, 'sym': sig['sym'], 'side': s, 'stop_frac': d / e, 'e': e, 'stp': stp,
            'wait_h': (rows[n][0] - sig['close']) / H}


def summarize(label, sigs, res):
    filled = [(g, r) for g, r in zip(sigs, res) if r and r.get('filled')]
    rs = [r['r'] for _, r in filled]
    if not rs:
        print('%-34s no fills' % label); return
    Y = [START, START + 365 * D, START + 730 * D, START + 1100 * D]
    cells = []
    for y in range(3):
        xs = [r['r'] for g, r in filled if Y[y] <= g['close'] < Y[y + 1]]
        cells.append('%+.2f' % statistics.mean(xs) if xs else ' n/a')
    eq = pk = dd = 0
    for _, r in sorted(filled, key=lambda x: x[1]['t_out']):
        eq += r['r']; pk = max(pk, eq); dd = max(dd, pk - eq)
    gw = sum(x for x in rs if x > 0); gl = -sum(x for x in rs if x <= 0)
    print('%-34s fill %3.0f%% n=%3d win %2.0f%% avg %+.2fR pf %.2f  %+5.1fR/mo  maxDD %4.1fR | %s' % (
        label, 100 * len(filled) / len(sigs), len(rs), 100 * sum(x > 0 for x in rs) / len(rs), statistics.mean(rs),
        gw / gl if gl else 9, sum(rs) / 36.5, dd, ' / '.join(cells)))
    return filled
