"""Q family + CRT, last 3 years, then all of them run together as one book.
  Q55   : current strategy (4h, 55-candle breakout, quality filter, BTC trend, 1h limit entry)
  Q30   : same with a 30-candle breakout
  Q20   : same with a 20-candle breakout
  Q30m  : Q's rules on 30-minute candles (55-candle breakout, body >= 1 ATR, BTC 4h trend, coin 30m trend,
          entries 08:00-01:00 SGT, no Monday, limit 0.5 ATR back for 2h, stop 2 ATR, 2R, 12h time stop)
  CRT4h : 4h candle range theory + BTC trend (crt3.py htf=4h btc=1)
Combined book: one position per coin at a time, max 3 open, max 3 new a day, R-based challenge sim at a fixed
risk per trade: stage 1 +8% / -10%, stage 2 +5% / -8%, daily -5%, a new start every day."""
import sys, statistics, collections
sys.argv = [sys.argv[0], 'htf=4h', 'btc=1'] + sys.argv[1:]
sys.path.insert(0, '/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad')
import rq, crt3, perps
H, D, M15 = rq.H, rq.D, rq.M15
cfg = perps.load_config(); sch = cfg['schedule']; st = dict(cfg['strategy'])
FEE = 0.0004
SYMS = cfg['symbols']
REG = rq.REG
load = lambda s, iv: perps.load_json(perps.cache_file(s, iv), [])


def q_4h(don):
    out = []
    s2 = dict(st, donchian=don)
    for s in SYMS:
        for t in perps.gen_trades_exec(s, load(s, '4h'), load(s, '1h'), s2, sch, {'fee': FEE, 'side': 0, 'hold_per_hour': 0}, REG):
            if t['t_in'] >= rq.START:
                out.append({'sym': s, 't_in': t['t_in'], 't_out': t['t_out'], 'r': perps.trade_r(t, FEE, 0), 'exit': t['exit']})
    return out


def q_30m():
    out = []
    M30 = 2 * M15
    s2 = dict(st)
    for s in SYMS:
        b15 = load(s, '15m'); i15 = {x[0]: k for k, x in enumerate(b15)}
        b = rq.aggregate(b15, M30)
        b = [x + [0] for x in b]
        ind = perps.indicators(b, s2)
        busy = 0
        for i in range(s2['ema_slow'] + 1, len(b) - 1):
            tc = b[i][0] + M30
            if tc < rq.START or tc < busy or perps.in_weekend(tc, sch):
                continue
            ld = perps.local_dt(tc, 8)
            if not (ld.hour >= 8 or ld.hour < 1) or ld.weekday() == 0:
                continue
            sg = perps.signal(ind, i, s2)
            if not sg:
                continue
            side = 1 if sg['side'] == 'long' else -1
            r = REG.get((tc // (4 * H)) * 4 * H - 4 * H)
            if r is None or (r > 0) != (side == 1):
                continue
            n0 = i15.get(tc)
            if n0 is None:
                continue
            c, a = ind['c'][i], ind['atr'][i]
            lim = c - side * 0.5 * a; stop = c - side * 2.0 * a
            n = None
            for m in range(n0, min(len(b15), n0 + 8)):
                if (side == 1 and b15[m][3] <= lim) or (side == -1 and b15[m][2] >= lim):
                    n, e = m, (min(b15[m][1], lim) if side == 1 else max(b15[m][1], lim)); break
            if n is None:
                continue
            d = abs(e - stop)
            if d / e < 0.002:
                continue
            px, why, to = rq.walk(b15, n, side, e, stop, e + side * 2 * d, b15[n][0] + 12 * H)
            out.append({'sym': s, 't_in': b15[n][0], 't_out': to, 'exit': why,
                        'r': (side * (px - e) / e - 2 * FEE) / (d / e + 2 * FEE)})
            busy = to
    return out


def crt4h():
    return [dict(t) for s in SYMS for t in crt3.run(s)]


def yr(tr):
    Y = [rq.START, rq.START + 365 * D, rq.START + 730 * D, rq.START + 1100 * D]
    cells = []
    for y in range(3):
        xs = [t['r'] for t in tr if Y[y] <= t['t_in'] < Y[y + 1]]
        cells.append('%+.2fR %2.0f%% n=%3d' % (statistics.mean(xs), 100 * sum(x > 0 for x in xs) / len(xs), len(xs)) if xs else 'n/a')
    return ' | '.join(cells)


def book(*sets):
    """Merge strategies: one position per coin, max 3 open, max 3 new a day (SGT day)."""
    allt = sorted([t for ss in sets for t in ss], key=lambda t: t['t_in'])
    out, openp, per = [], [], collections.Counter()
    for t in allt:
        openp = [p for p in openp if p['t_out'] > t['t_in']]
        k = perps.day_key(t['t_in'], 8)
        if len(openp) >= 3 or per[k] >= 3 or any(p['sym'] == t['sym'] for p in openp):
            continue
        out.append(t); openp.append(t); per[k] += 1
    return out


def sim(tr, risk):
    """Challenge sim on realized R (exit order), new start every day."""
    ev = sorted(tr, key=lambda t: t['t_out'])
    t0, t1 = rq.START + 10 * D, rq.START + 1095 * D - 90 * D
    res = []
    s = t0
    while s < t1:
        t = s; out = []
        for tgt, mx in ((8, 10), (5, 8)):
            bal, day, dp, done = 0.0, None, 0.0, None
            for x in ev:
                if x['t_in'] < t:
                    continue
                k = x['t_out'] // D
                if k != day:
                    day, dp = k, 0.0
                bal += x['r'] * risk; dp += x['r'] * risk
                if -dp >= 5 or -bal >= mx:
                    done = ('fail', x['t_out']); break
                if bal >= tgt:
                    done = ('pass', x['t_out']); break
            done = done or ('open', None)
            out.append(done)
            if done[0] != 'pass':
                break
            t = done[1] + 30 * 60_000
        res.append((s, out)); s += D
    n = len(res)
    p1 = sum(o[0][0] == 'pass' for _, o in res); f1 = sum(o[0][0] == 'fail' for _, o in res)
    both = sorted((o[1][1] - s) / D for s, o in res if len(o) > 1 and o[1][0] == 'pass')
    f2 = sum(len(o) > 1 and o[1][0] == 'fail' for _, o in res)
    pc = lambda q: both[int(q * len(both))] if both else float('nan')
    return '%3.0f%% S1 pass, %3.0f%% S1 fail | both pass %3.0f%% (S2 fail %2.0f%%) | days to pass both: median %3.0f, 75%% %3.0f, within 14d %2.0f%%, within 30d %2.0f%%' % (
        100 * p1 / n, 100 * f1 / n, 100 * len(both) / n, 100 * f2 / n, pc(.5), pc(.75),
        100 * sum(x <= 14 for x in both) / n, 100 * sum(x <= 30 for x in both) / n)


if __name__ == '__main__':
    S = {'Q55': q_4h(55), 'Q30': q_4h(30), 'Q20': q_4h(20), 'Q30m': q_30m(), 'CRT4h': crt4h()}
    print('Each strategy alone (Nov23-24 | Nov24-25 | Nov25-26):')
    for k, v in S.items():
        rs = [t['r'] for t in v]
        print('  %-6s %+.2fR win %2.0f%% %4.1f trades/mo %+4.1fR/mo | %s' % (k, statistics.mean(rs), 100 * sum(x > 0 for x in rs) / len(rs), len(rs) / 36.5, sum(rs) / 36.5, yr(v)))
    combos = [('Q55',), ('Q55', 'Q30'), ('Q55', 'CRT4h'), ('Q55', 'Q30', 'CRT4h'), ('Q55', 'Q30', 'Q30m'), ('Q55', 'Q30', 'Q30m', 'CRT4h')]
    print('\nCombined books (overlaps removed):')
    for c in combos:
        b = book(*[S[k] for k in c])
        rs = [t['r'] for t in b]
        print('  %-24s %+.2fR win %2.0f%% %4.1f trades/mo %+4.1fR/mo | %s' % ('+'.join(c), statistics.mean(rs), 100 * sum(x > 0 for x in rs) / len(rs), len(rs) / 36.5, sum(rs) / 36.5, yr(b)))
        for risk in (1.5, 2.0, 2.5):
            print('      risk %.1f%%: %s' % (risk, sim(b, risk)))
