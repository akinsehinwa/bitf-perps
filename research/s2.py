"""Round 2: strategies aimed at more trades or bigger winners, scored in $/month under prop rules.
  trail    : 4h Donchian breakout with BTC trend, market entry next 1h bar, chandelier trailing stop, no target
  pullback : 4h trend + BTC trend; 1h pullback into EMA20 then a 1h close above the prior bar's high
  rsi2     : 4h trend + BTC trend; 1h RSI(2) dip, exit on close above EMA5 / stop / 24h
usage: s2.py STRAT key=val ... [risk=1.5]"""
import sys, statistics, collections
sys.path.insert(0, '/home/user/bitfunded-perps')
import perps

H = perps.HOUR_MS; D = 86_400_000
cfg = perps.load_config(); sch = cfg['schedule']
FEE = cfg['firm']['fee_pct_per_side'] / 100
P = dict(a.split('=') for a in sys.argv[2:])
num = lambda k, d: float(P.get(k, d))
SYMS = P.get('syms', 'BTC,ETH,BNB,XRP,SOL,HYPE,ZEC,ADA,UNI,LINK').split(',')
ms = lambda d: int(perps.dt.datetime.fromisoformat(d).replace(tzinfo=perps.UTC).timestamp() * 1000)
Y = [ms('2023-11-01'), ms('2024-11-12'), ms('2025-11-12'), ms('2026-11-13')]
WEEKEND = P.get('weekend', 'flat')     # flat: close Sat 04:00 SGT; hold: keep server-side stops over the weekend
C = {}


def bars(s, iv):
    if (s, iv) not in C:
        C[(s, iv)] = perps.load_json(perps.cache_file(s, iv), [])
    return C[(s, iv)]


REG = perps.btc_regime(bars('BTC', '4h'), cfg['strategy'])


def reg_at(t):
    return REG.get((t // (4 * H)) * 4 * H - 4 * H)


def trend4h(sym):
    b = bars(sym, '4h'); c = [x[4] for x in b]
    ef, es = perps.ema(c, 50), perps.ema(c, 200)
    return {x[0]: (0 if ef[k] is None or es[k] is None else (1 if ef[k] > es[k] and c[k] > ef[k] else -1 if ef[k] < es[k] and c[k] < ef[k] else 0))
            for k, x in enumerate(b)}


def tr_at(tmap, t):
    return tmap.get((t // (4 * H)) * 4 * H - 4 * H, 0)


def walk(b, n, side, e, stop, tgt=None, max_h=48, trail_k=None, atr=None, exit_fn=None):
    flat = perps.next_weekend_stop(b[n][0], sch) if WEEKEND == 'flat' else None
    step = b[1][0] - b[0][0]
    last = min(len(b), n + int(max_h * H / step))
    best = e; m = n
    for m in range(n, last):
        o, h, l, c = b[m][1:5]
        if flat and b[m][0] >= flat:
            return o, 'weekend', b[m][0]
        if (side == 1 and l <= stop) or (side == -1 and h >= stop):
            px = (min(o, stop) if side == 1 else max(o, stop)) if m > n else stop
            return px, 'stop', b[m][0] + step
        if tgt is not None and ((side == 1 and h >= tgt) or (side == -1 and l <= tgt)):
            return tgt, 'target', b[m][0] + step
        if exit_fn and exit_fn(m):
            return c, 'signal', b[m][0] + step
        if trail_k:
            best = max(best, h) if side == 1 else min(best, l)
            nt = best - side * trail_k * atr
            stop = max(stop, nt) if side == 1 else min(stop, nt)
    return b[m][4], 'time', b[m][0] + step


def rec(sym, side, t, e, stop, px, why, t_out):
    return {'sym': sym, 'side': 'long' if side == 1 else 'short', 'setup': P.get('_s'), 't_in': t, 't_out': t_out,
            'ret': side * (px - e) / e, 'stop_frac': abs(e - stop) / e, 'exit': why, 'fee': FEE, 'cost_side': 0.0}


def s_trail(sym):
    st = dict(cfg['strategy'], donchian=int(num('don', 55)), atr_stop=num('stop', 2.5))
    b4, b1 = bars(sym, '4h'), bars(sym, '1h')
    ind = perps.indicators(b4, st); i1 = {x[0]: k for k, x in enumerate(b1)}
    out, busy = [], 0
    sched = P.get('hours', 'sched')
    for i in range(st['ema_slow'] + 1, len(b4) - 1):
        t = ind['t'][i] + 4 * H
        if t < busy or perps.in_weekend(t, sch) or (sched == 'sched' and not perps.entry_allowed(t, sch)):
            continue
        sg = perps.signal(ind, i, st)
        if not sg:
            continue
        r = reg_at(t)
        if r is None or (r > 0) != (sg['side'] == 'long'):
            continue
        n = i1.get(t)
        if n is None:
            continue
        s = 1 if sg['side'] == 'long' else -1
        e = b1[n][1]; a = ind['atr'][i]
        stop = e - s * st['atr_stop'] * a
        tgt = e + s * num('tr', 0) * st['atr_stop'] * a if num('tr', 0) else None
        px, why, to = walk(b1, n, s, e, stop, tgt, num('hold', 216), num('trail', 3.0), a)
        out.append(rec(sym, s, b1[n][0], e, stop, px, why, to)); busy = to
    return out


def s_pullback(sym):
    b1 = bars(sym, '1h'); c = [x[4] for x in b1]
    e20, e50 = perps.ema(c, 20), perps.ema(c, 50)
    a1 = perps.atr([x[2] for x in b1], [x[3] for x in b1], c, 14)
    tm = trend4h(sym)
    out, busy = [], 0
    sched = P.get('hours', 'any')
    look = int(num('look', 6))
    for i in range(60, len(b1) - 1):
        t = b1[i][0] + H
        if t < busy or e50[i] is None or a1[i] is None or perps.in_weekend(t, sch):
            continue
        if sched == 'sched':
            hs = perps.local_dt(t, 8).hour
            if not any(0 <= (hs - s0) % 24 < 3 for s0 in sch['scan_hours']):
                continue
        side = tr_at(tm, t)
        if not side:
            continue
        r = reg_at(t)
        if r is None or (r > 0) != (side == 1):
            continue
        o, h, l, cl = b1[i][1:5]
        if side == 1:
            touched = min(x[3] for x in b1[i - 3:i + 1]) <= e20[i] and e20[i] > e50[i]
            trig = cl > b1[i - 1][2] and cl > e20[i]
        else:
            touched = max(x[2] for x in b1[i - 3:i + 1]) >= e20[i] and e20[i] < e50[i]
            trig = cl < b1[i - 1][3] and cl < e20[i]
        if not (touched and trig):
            continue
        n = i + 1; e = b1[n][1]
        sw = min(x[3] for x in b1[i - look:i + 1]) if side == 1 else max(x[2] for x in b1[i - look:i + 1])
        stop = sw - side * num('buf', 0.3) * a1[i]
        d = abs(e - stop)
        if d <= 0 or (side == 1 and stop >= e) or (side == -1 and stop <= e) or d / e < 0.004:
            continue
        tgt = e + side * num('tr', 2) * d if num('tr', 2) else None
        tk = num('trail', 0) or None
        px, why, to = walk(b1, n, side, e, stop, tgt, num('hold', 48), tk, a1[i])
        out.append(rec(sym, side, b1[n][0], e, stop, px, why, to)); busy = to
    return out


def s_rsi2(sym):
    b1 = bars(sym, '1h'); c = [x[4] for x in b1]
    r2 = perps.rsi(c, 2); e5 = perps.ema(c, 5)
    a1 = perps.atr([x[2] for x in b1], [x[3] for x in b1], c, 14)
    tm = trend4h(sym); out, busy = [], 0
    lv = num('lv', 10)
    for i in range(30, len(b1) - 1):
        t = b1[i][0] + H
        if t < busy or r2[i] is None or a1[i] is None or perps.in_weekend(t, sch):
            continue
        side = tr_at(tm, t)
        r = reg_at(t)
        if not side or r is None or (r > 0) != (side == 1):
            continue
        if not ((side == 1 and r2[i] < lv) or (side == -1 and r2[i] > 100 - lv)):
            continue
        n = i + 1; e = b1[n][1]
        stop = e - side * num('stop', 2.0) * a1[i]
        ex = (lambda m: c[m] > e5[m]) if side == 1 else (lambda m: c[m] < e5[m])
        px, why, to = walk(b1, n, side, e, stop, None, num('hold', 24), None, None, ex)
        out.append(rec(sym, side, b1[n][0], e, stop, px, why, to)); busy = to
    return out


def monthly(trades, risk):
    """Funded-style month by month: start each month at 50,000 (profits withdrawn), stage-2 limits
    (5% daily, 8% max), this tool's guards, max 3 new trades a day. Returns list of (month, pnl, breach)."""
    cfg['risk'].update(stage2_risk_pct=risk, max_risk_pct=max(2.0, risk), max_open_risk_pct=max(3.0, 2 * risk), finish_line=False)
    by_m = collections.defaultdict(list)
    for t in trades:
        k = perps.local_dt(t['t_in'], 8).strftime('%Y-%m')
        by_m[k].append(t)
    out = []
    for k in sorted(by_m):
        ts = by_m[k]
        y, mo = map(int, k.split('-'))
        start = int((perps.dt.datetime(y, mo, 1) - perps.dt.timedelta(hours=8)).replace(tzinfo=perps.UTC).timestamp() * 1000)
        cfg['stages']['2']['profit_target_pct'] = 1000
        res, end, n = perps.sim_stage(cfg, ts, start, '2', max_days=31)
        # recompute realized P&L for the month by replaying (sim_stage returns result only)
        out.append((k, res, n))
    return out


def month_pnl(trades, risk):
    """Simple replay mirroring sim_stage sizing, returning $ per month."""
    acct = cfg['account_size']; off = 8
    cfg['risk'].update(stage2_risk_pct=risk, max_risk_pct=max(2.0, risk), max_open_risk_pct=max(3.0, 2 * risk), finish_line=False)
    cap = sch['max_trades_per_day']
    by_m = collections.defaultdict(list)
    for t in trades:
        by_m[perps.local_dt(t['t_in'], 8).strftime('%Y-%m')].append(t)
    res = []
    for k in sorted(by_m):
        realized, day, dpnl, opened, per = 0.0, None, 0.0, [], collections.Counter()
        breach = False
        evs = sorted(by_m[k], key=lambda t: t['t_in'])
        def settle(upto):
            nonlocal realized, day, dpnl, breach
            opened.sort(key=lambda p: p['t_out'])
            while opened and opened[0]['t_out'] <= upto:
                p = opened.pop(0); dk = perps.day_key(p['t_out'], off)
                if dk != day:
                    day, dpnl = dk, 0.0
                realized += p['pnl']; dpnl += p['pnl']
                if -dpnl > 0.05 * acct or -realized > 0.08 * acct:
                    breach = True
        for t in evs:
            settle(t['t_in'])
            if breach:
                break
            dk = perps.day_key(t['t_in'], off)
            if dk != day:
                day, dpnl = dk, 0.0
            if per[dk] >= cap or any(p['sym'] == t['sym'] for p in opened):
                continue
            orisk = sum(p['risk'] for p in opened); onot = sum(p['notional'] for p in opened)
            rb, _ = perps.risk_budget(cfg, '2', realized, dpnl, orisk, onot, len(opened))
            if rb <= 0:
                continue
            sz = perps.size_trade(cfg, 1.0, 1.0 - t['stop_frac'], rb, onot, FEE, 0.0)
            opened.append({'sym': t['sym'], 't_out': t['t_out'], 'risk': sz['loss_at_stop'], 'notional': sz['notional'],
                           'pnl': sz['notional'] * (t['ret'] - 2 * FEE)})
            per[dk] += 1
        settle(10 ** 15)
        res.append((k, realized, breach))
    return res


def daily_bias(name, n):
    """+1 risk-on (series below its EMA n -> dollar / USDT dominance weakening), -1 risk-off. Keyed by UTC day."""
    rows = perps.load_json(perps.cache_file(name, '1d'), [])
    c = [r[1] for r in rows]; e = perps.ema(c, n)
    out = {}
    for k, r in enumerate(rows):
        if e[k] is not None:
            out[r[0] // D] = -1 if c[k] > e[k] else 1
    return out


BIAS = {}


def bias_ok(t, side):
    """Every filter in bias= must agree with the trade side, using the last CLOSED daily bar."""
    for f in P.get('bias', '').split(','):
        if not f:
            continue
        name, n = (f.split(':') + ['20'])[:2]
        key = (name, int(n))
        if key not in BIAS:
            BIAS[key] = daily_bias({'dxy': 'DXY', 'usdtd': 'USDTD'}[name], int(n))
        day = t // D - 1
        v = None
        for back in range(5):           # DXY has no weekend bars
            v = BIAS[key].get(day - back)
            if v is not None:
                break
        if v is None or (v > 0) != (side == 1):
            return False
    return True


def s_current(sym):
    st = dict(cfg['strategy'])
    for k in ('target_r', 'atr_stop', 'limit_atr'):
        if k in P: st[k] = float(P[k])
    if 'don' in P: st['donchian'] = int(P['don'])
    if 'entry' in P: st['entry'] = P['entry']
    sc = dict(sch)
    if 'hours' in P: sc['scan_hours'] = [int(x) for x in P['hours'].split('/')]
    ts = perps.gen_trades_exec(sym, bars(sym, '4h'), bars(sym, '1h'), st, sc, {'fee': FEE, 'side': 0.0, 'hold_per_hour': 0.0}, REG)
    return [t for t in ts if bias_ok(t['t_in'], 1 if t['side'] == 'long' else -1)]


def s_crt(sym):
    """Daily candle range theory: day i sweeps day i-1's low (high) and closes back inside its range ->
    trade toward the other side of day i-1's range at the next daily open (08:00 SGT)."""
    b4, b1 = bars(sym, '4h'), bars(sym, '1h')
    days = collections.OrderedDict()
    for x in b4:
        k = x[0] // D
        if k not in days:
            days[k] = [x[0], x[1], x[2], x[3], x[4]]
        else:
            d = days[k]; d[2] = max(d[2], x[2]); d[3] = min(d[3], x[3]); d[4] = x[4]
    dl = list(days.values()); i1 = {x[0]: k for k, x in enumerate(b1)}
    out, busy = [], 0
    for i in range(1, len(dl) - 1):
        t = dl[i][0] + D
        if t < busy or perps.in_weekend(t, sch):
            continue
        o, h, l, c = dl[i][1:5]; ph, pl = dl[i - 1][2], dl[i - 1][3]
        side = 1 if (l < pl and pl < c < ph) else -1 if (h > ph and pl < c < ph) else 0
        if not side:
            continue
        if P.get('btc', '1') == '1':
            r = reg_at(t)
            if r is None or (r > 0) != (side == 1):
                continue
        if not bias_ok(t, side):
            continue
        n = i1.get(t)
        if n is None:
            continue
        e = b1[n][1]
        rng = h - l
        stop = (l - 0.05 * rng) if side == 1 else (h + 0.05 * rng)
        d = abs(e - stop)
        if d <= 0 or d / e < 0.004:
            continue
        tgt = ph if side == 1 else pl
        if P.get('tgt') == 'fixed':
            tgt = e + side * num('tr', 2) * d
        elif (tgt - e) * side / d < num('minrr', 1.5):
            continue
        px, why, to = walk(b1, n, side, e, stop, tgt, num('hold', 72))
        out.append(rec(sym, side, b1[n][0], e, stop, px, why, to)); busy = to
    return out


if __name__ == '__main__':
    P['_s'] = sys.argv[1]
    fn = {'trail': s_trail, 'pullback': s_pullback, 'rsi2': s_rsi2, 'current': s_current, 'crt': s_crt}[sys.argv[1]]
    trades = sorted([t for s in SYMS for t in fn(s)], key=lambda t: t['t_in'])
    rs = lambda ts: [perps.trade_r(t, FEE, 0) for t in ts]
    cells = []
    for y in range(3):
        r = rs([t for t in trades if Y[y] <= t['t_in'] < Y[y + 1]])
        gw = sum(x for x in r if x > 0); gl = -sum(x for x in r if x <= 0)
        cells.append('%+.3fR n=%4d w%2.0f%% pf%.2f' % (statistics.mean(r), len(r), 100 * sum(x > 0 for x in r) / len(r), gw / gl if gl else 9) if r else 'n/a')
    print('%-44s %s' % (' '.join(sys.argv[1:]), ' | '.join(cells)))
    big = sorted(rs(trades))[-5:]
    print('    biggest winners (R): %s   trades/month %.1f' % (' '.join('%.1f' % x for x in big), len(trades) / 36.4))
    for risk in [float(x) for x in P.get('risk', '1.5,2').split(',')]:
        mm = month_pnl(trades, risk)
        last12 = [p for k, p, b in mm if k >= '2025-11']
        allp = [p for k, p, b in mm]
        print('    risk %.1f%%: avg month $%+.0f (last 12 mo $%+.0f), median $%+.0f, best $%+.0f, worst $%+.0f, months >= $5k: %d/%d, breach months: %d' % (
            risk, statistics.mean(allp), statistics.mean(last12) if last12 else 0, statistics.median(allp), max(allp), min(allp),
            sum(p >= 5000 for p in allp), len(allp), sum(b for k, p, b in mm)))
