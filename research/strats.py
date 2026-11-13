"""Research: three trader strategies, mechanised, same costs/exits/sim as perps.py.
  vwap  : EMA9 crosses daily VWAP (anchored 00:00 UTC = 08:00 SGT)  [15m or 1h]
  retr  : qualified 4h swing leg -> 50% retracement -> 15m inverse FVG -> limit at FVG midline
  po3   : 4h candle sweeps the previous candle's low/high, closes back inside, trade with bias
Usage: strats.py STRAT [key=val ...]"""
import sys, statistics, json, math
sys.path.insert(0, '/home/user/bitfunded-perps')
import perps

H = perps.HOUR_MS
cfg = perps.load_config()
sch = cfg['schedule']
FEE = cfg['firm']['fee_pct_per_side'] / 100
SYMS = ["BTC", "ETH", "BNB", "XRP", "SOL", "HYPE", "ZEC", "ADA", "UNI", "LINK"]
ms = lambda d: int(perps.dt.datetime.fromisoformat(d).replace(tzinfo=perps.UTC).timestamp() * 1000)
Y = [ms('2023-11-01'), ms('2024-11-12'), ms('2025-11-12'), ms('2026-11-13')]
P = dict(a.split('=') for a in sys.argv[2:])
num = lambda k, d: float(P.get(k, d))
_cache = {}


def bars(sym, iv):
    k = (sym, iv)
    if k not in _cache:
        _cache[k] = perps.load_json(perps.cache_file(sym, iv), [])
    return _cache[k]


BTC_REG = perps.btc_regime(bars('BTC', '4h'), cfg['strategy'])


def regime_at(t_ms):
    """BTC 4h regime of the last CLOSED 4h bar at time t."""
    b = (t_ms // (4 * H)) * 4 * H - 4 * H
    return BTC_REG.get(b)


def walk(b, n, side, e, stop, tgt, max_h):
    """Exit on bars b starting at index n (the fill bar). Stop first if both."""
    flat = perps.next_weekend_stop(b[n][0], sch)
    step = b[1][0] - b[0][0]
    last = min(len(b), n + int(max_h * H / step))
    m = n
    for m in range(n, last):
        o, h, l = b[m][1], b[m][2], b[m][3]
        if b[m][0] >= flat:
            return o, 'weekend', b[m][0]
        if (side == 1 and l <= stop) or (side == -1 and h >= stop):
            px = (min(o, stop) if side == 1 else max(o, stop)) if m > n else stop
            return px, 'stop', b[m][0] + step
        if (side == 1 and h >= tgt) or (side == -1 and l <= tgt):
            return tgt, 'target', b[m][0] + step
    return b[m][4], 'time', b[m][0] + step


def rec(sym, side, t_in, e, stop, px, why, t_out, setup):
    return {'sym': sym, 'side': 'long' if side == 1 else 'short', 'setup': setup, 't_in': t_in, 't_out': t_out,
            'ret': side * (px - e) / e, 'stop_frac': abs(e - stop) / e, 'exit': why, 'fee': FEE, 'cost_side': 0.0}


def ema(xs, n):
    return perps.ema(xs, n)


# ------------------------------------------------------------------ VWAP x EMA9
def strat_vwap(sym):
    tf = P.get('tf', '15m')
    b = bars(sym, tf)
    if not b:
        return []
    c = [x[4] for x in b]
    e9 = ema(c, 9)
    at = perps.atr([x[2] for x in b], [x[3] for x in b], c, 14)
    vw, day, pv, vv = [None] * len(b), None, 0.0, 0.0
    for i, x in enumerate(b):
        d = x[0] // 86_400_000
        if d != day:
            day, pv, vv = d, 0.0, 0.0
        tp = (x[2] + x[3] + x[4]) / 3
        pv += tp * x[5]; vv += x[5]
        vw[i] = pv / vv if vv else tp
    b4 = bars(sym, '4h'); c4 = [x[4] for x in b4]
    t4 = {x[0]: k for k, x in enumerate(b4)}
    ef4, es4 = ema(c4, 50), ema(c4, 200)
    k_stop, tr, hold = num('stop', 1.5), num('tr', 2.0), num('hold', 24)
    filt = P.get('filter', 'btc')
    min_bars_in_day = int(num('warm', 4))   # skip the first bars after the VWAP reset
    out, busy = [], 0
    step = b[1][0] - b[0][0]
    for i in range(30, len(b) - 1):
        if b[i][0] < busy or e9[i - 1] is None or at[i] is None:
            continue
        up = e9[i - 1] <= vw[i - 1] and e9[i] > vw[i]
        dn = e9[i - 1] >= vw[i - 1] and e9[i] < vw[i]
        if not (up or dn):
            continue
        if (b[i][0] % 86_400_000) // step < min_bars_in_day:
            continue
        t_close = b[i][0] + step
        if perps.in_weekend(t_close, sch):
            continue
        side = 1 if up else -1
        if filt == 'btc':
            r = regime_at(t_close)
            if r is None or (r > 0) != (side == 1):
                continue
        elif filt == 'coin4h':
            k = t4.get((t_close // (4 * H)) * 4 * H - 4 * H)
            if k is None or ef4[k] is None or es4[k] is None or (ef4[k] > es4[k]) != (side == 1):
                continue
        if P.get('hours') == 'sched':
            h_sgt = perps.local_dt(t_close, 8).hour
            if not any(0 <= (h_sgt - s) % 24 < 3 for s in sch['scan_hours']):
                continue
        n = i + 1
        e = b[n][1]
        stop = e - side * k_stop * at[i]
        tgt = e + side * tr * k_stop * at[i]
        px, why, t_out = walk(b, n, side, e, stop, tgt, hold)
        out.append(rec(sym, side, b[n][0], e, stop, px, why, t_out, 'vwap'))
        busy = t_out
    return out


# ------------------------------------------------------------------ 4h swing 50% + 15m IFVG
def pivots(b4, n):
    """Confirmed pivots: (confirm_index, pivot_index, price, kind)."""
    out = []
    for p in range(n, len(b4) - n):
        hi = b4[p][2]; lo = b4[p][3]
        if hi == max(x[2] for x in b4[p - n:p + n + 1]):
            out.append((p + n, p, hi, 'H'))
        if lo == min(x[3] for x in b4[p - n:p + n + 1]):
            out.append((p + n, p, lo, 'L'))
    out.sort()
    return out


def strat_retr(sym):
    b4 = bars(sym, '4h'); b15 = bars(sym, '15m')
    if not b4 or not b15:
        return []
    N = int(num('piv', 3)); min_leg = num('minleg', 3.0); tr = num('tr', 2.0)
    tgt_mode = P.get('tgt', 'fixed')     # fixed: tr x R; swing: leg extreme (needs >= 1.5R)
    fib = num('fib', 0.5); valid_h = num('valid', 8); hold = num('hold', 48)
    stop_mode = P.get('stopm', 'retr')   # retr: beyond the retracement extreme; leg: beyond the leg origin
    filt = P.get('filter', 'none')
    c4 = [x[4] for x in b4]
    at4 = perps.atr([x[2] for x in b4], [x[3] for x in b4], c4, 14)
    piv = pivots(b4, N)
    i15 = {x[0]: k for k, x in enumerate(b15)}
    # walk 4h bars; maintain last confirmed pivot high/low
    pv_by_confirm = {}
    for cf, p, px, kind in piv:
        pv_by_confirm.setdefault(cf, []).append((p, px, kind))
    lastH = lastL = None      # (index, price)
    prevH = prevL = None
    setups = []               # legs: dict(side, origin, extreme, t_start)
    for i in range(N * 2 + 15, len(b4)):
        for p, px, kind in pv_by_confirm.get(i, []):
            if kind == 'H':
                prevH, lastH = lastH, (p, px)
            else:
                prevL, lastL = lastL, (p, px)
        a = at4[i]
        if a is None:
            continue
        # bearish BOS: close below the last pivot low, with a lower high since (qualified LH->LL)
        if lastL and lastH and b4[i][4] < lastL[1] and b4[i - 1][4] >= lastL[1] and lastH[0] > lastL[0]:
            if prevH is None or lastH[1] < prevH[1]:
                origin = lastH[1]
                ext = min(x[3] for x in b4[lastH[0]:i + 1])
                if origin - ext >= min_leg * a:
                    setups.append(dict(side=-1, origin=origin, ext=ext, t=b4[i][0] + 4 * H, atr=a))
        if lastL and lastH and b4[i][4] > lastH[1] and b4[i - 1][4] <= lastH[1] and lastL[0] > lastH[0]:
            if prevL is None or lastL[1] > prevL[1]:
                origin = lastL[1]
                ext = max(x[2] for x in b4[lastL[0]:i + 1])
                if ext - origin >= min_leg * a:
                    setups.append(dict(side=1, origin=origin, ext=ext, t=b4[i][0] + 4 * H, atr=a))
    out, busy = [], 0
    for su in setups:
        if su['t'] < busy:
            continue
        s = su['side']; origin, ext = su['origin'], su['ext']
        n = i15.get(su['t'])
        if n is None:
            continue
        if filt == 'btc':
            r = regime_at(su['t'])
            if r is None or (r > 0) != (s == 1):
                continue
        # phase 1: wait for the leg to finish extending and price to retrace to fib level
        in_zone = False
        retr_ext = None
        fvgs = []
        pending = None   # (limit, stop, expiry_ms)
        for m in range(n, min(len(b15), n + 4 * 24 * 10)):   # setup lives max 10 days
            o, h, l, c = b15[m][1:5]
            t = b15[m][0]
            if (s == -1 and h > origin) or (s == 1 and l < origin):
                break                                        # deeper than the origin: invalid
            if not in_zone:
                if (s == -1 and l < ext) or (s == 1 and h > ext):
                    ext = l if s == -1 else h                # leg still extending
                lvl = ext + (origin - ext) * fib if s == -1 else ext - (ext - origin) * fib
                if (s == -1 and h >= lvl) or (s == 1 and l <= lvl):
                    in_zone = True
                    retr_ext = h if s == -1 else l
                continue
            if (s == -1 and l < ext) or (s == 1 and h > ext):
                break                                        # made a new extreme: target hit without us
            retr_ext = max(retr_ext, h) if s == -1 else min(retr_ext, l)
            if pending:
                lim, stop, exp = pending
                if t >= exp:
                    pending = None
                elif (s == -1 and h >= lim) or (s == 1 and l <= lim):
                    if perps.in_weekend(t, sch):
                        break
                    e = max(o, lim) if s == -1 else min(o, lim)
                    d = abs(stop - e)
                    if d <= 0:
                        break
                    if tgt_mode == 'swing':
                        tgt = ext
                        if abs(tgt - e) / d < 1.5:
                            break
                    else:
                        tgt = e - s * -tr * d if False else e + s * tr * d
                    px, why, t_out = walk(b15, m, s, e, stop, tgt, hold)
                    out.append(rec(sym, s, t, e, stop, px, why, t_out, 'retr'))
                    busy = t_out
                    break
                continue
            # 15m FVG in the retracement direction, then its inversion
            if m >= 2:
                if s == -1 and b15[m][3] > b15[m - 2][2]:       # bullish FVG (gap up)
                    fvgs.append((b15[m - 2][2], b15[m][3]))
                if s == 1 and b15[m][2] < b15[m - 2][3]:        # bearish FVG (gap down)
                    fvgs.append((b15[m][2], b15[m - 2][3]))
            fvgs = fvgs[-6:]
            for lo_, hi_ in list(fvgs):
                if (s == -1 and c < lo_) or (s == 1 and c > hi_):   # inversion close
                    mid = (lo_ + hi_) / 2
                    if stop_mode == 'leg':
                        stop = origin + s * -1 * 0.1 * su['atr'] if False else origin - s * 0.1 * su['atr']
                    else:
                        stop = retr_ext - s * 0.1 * su['atr']
                    if perps.in_weekend(t, sch):
                        break
                    pending = (mid, stop, t + valid_h * H)
                    fvgs = []
                    break
    return out


# ------------------------------------------------------------------ Power of three (4h sweep & reclaim)
def strat_po3(sym):
    b4 = bars(sym, '4h'); b1 = bars(sym, '1h')
    if not b4 or not b1:
        return []
    c4 = [x[4] for x in b4]
    ef, es = ema(c4, 50), ema(c4, 200)
    at = perps.atr([x[2] for x in b4], [x[3] for x in b4], c4, 14)
    i1 = {x[0]: k for k, x in enumerate(b1)}
    look = int(num('look', 20)); minrr = num('minrr', 1.5); hold = num('hold', 48)
    tgt_mode = P.get('tgt', 'liq'); tr = num('tr', 2.0)
    bias = P.get('bias', 'both')     # coin / btc / both
    sched = P.get('hours', 'sched')
    out, busy = [], 0
    for i in range(201, len(b4) - 1):
        close_ms = b4[i][0] + 4 * H
        if close_ms < busy or at[i] is None or ef[i] is None or es[i] is None:
            continue
        if sched == 'sched' and not perps.entry_allowed(close_ms, sch):
            continue
        if perps.in_weekend(close_ms, sch):
            continue
        o, h, l, c = b4[i][1:5]
        pl, ph = b4[i - 1][3], b4[i - 1][2]
        side = 0
        if l < pl and c > pl and c > o:
            side = 1
        elif h > ph and c < ph and c < o:
            side = -1
        if not side:
            continue
        coin_ok = (ef[i] > es[i]) == (side == 1)
        r = regime_at(close_ms)
        btc_ok = r is not None and (r > 0) == (side == 1)
        if (bias in ('coin', 'both') and not coin_ok) or (bias in ('btc', 'both') and not btc_ok):
            continue
        n = i1.get(close_ms)
        if n is None:
            continue
        e = b1[n][1]
        stop = (l - 0.1 * at[i]) if side == 1 else (h + 0.1 * at[i])
        d = abs(e - stop)
        if d <= 0 or (side == 1 and stop >= e) or (side == -1 and stop <= e):
            continue
        if tgt_mode == 'liq':
            liq = max(x[2] for x in b4[i - look:i]) if side == 1 else min(x[3] for x in b4[i - look:i])
            if abs(liq - e) / d < minrr or (side == 1 and liq <= e) or (side == -1 and liq >= e):
                continue
            tgt = liq
        else:
            tgt = e + side * tr * d
        px, why, t_out = walk(b1, n, side, e, stop, tgt, hold)
        out.append(rec(sym, side, b1[n][0], e, stop, px, why, t_out, 'po3'))
        busy = t_out
    return out


def report(trades, label):
    rs = lambda ts: [perps.trade_r(t, FEE, 0) for t in ts]
    cells = []
    for y in range(3):
        r = rs([t for t in trades if Y[y] <= t['t_in'] < Y[y + 1]])
        if r:
            gw = sum(x for x in r if x > 0); gl = -sum(x for x in r if x <= 0)
            cells.append('%+.3fR n=%4d win%3.0f%% pf%.2f' % (statistics.mean(r), len(r), 100 * sum(x > 0 for x in r) / len(r), gw / gl if gl else 9))
        else:
            cells.append('n/a')
    a = rs(trades)
    days = (Y[3] - Y[0]) / 86_400_000
    print('%-46s all %+.3fR n=%4d (%.2f/day) | %s' % (label, statistics.mean(a) if a else 0, len(a), len(a) / days, ' | '.join(cells)))


if __name__ == '__main__':
    fn = {'vwap': strat_vwap, 'retr': strat_retr, 'po3': strat_po3}[sys.argv[1]]
    syms = P.get('syms', ','.join(SYMS)).split(',')
    trades = sorted([t for s in syms for t in fn(s)], key=lambda t: t['t_in'])
    report(trades, sys.argv[1] + ' ' + ' '.join(sys.argv[2:]))
    if P.get('sim'):
        r = float(P['sim'])
        cfg['risk'].update(stage1_risk_pct=r, stage2_risk_pct=r, max_risk_pct=max(r, 2.0), max_open_risk_pct=max(3.0, 2 * r))
        perps.SIM_MAX_DAYS = 365
        rows = perps.run_challenges(cfg, trades, Y[0] + 30 * 86_400_000, Y[3] - 60 * 86_400_000, 1)
        print('   ' + perps.summarize(rows, 'risk %.2f%%' % r))
