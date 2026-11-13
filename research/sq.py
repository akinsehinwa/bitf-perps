"""#4 Volatility squeeze breakout and #9 BTC-leader catch-up, on Q's execution engine, last 3 years.
  sq : Q's trigger with donchian `don` but ONLY if the 20-bar Bollinger bandwidth one candle before the
       breakout was in the bottom `q` quantile of its last 120 bars (a squeeze).
  cu : catch-up. When BTC (or >= `breadth` of the coins) printed a Q breakout on the previous scan close,
       enter coins that did NOT break, are in the same trend, and sit within `dist` ATR of their own
       `don`-bar extreme: a limit 0.5 ATR back at the next scan, stop 2 ATR, after-fee 2R, 48h.
Usage: sq.py mode=sq don=20 q=0.25 [rvol=] [sim=1] | sq.py mode=cu dist=1.5 [sim=1]"""
import sys, statistics
S = '/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad'
sys.path.insert(0, S); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps
P = dict(a.split('=') for a in sys.argv[1:] if '=' in a)
num = lambda k, d: float(P.get(k, d))
H = perps.HOUR_MS; H4 = 4 * H
cfg = perps.load_config(); sch = cfg['schedule']; st0 = dict(cfg['strategy'])
FEE = 0.0004
START = int(perps.dt.datetime(2023, 11, 12, tzinfo=perps.UTC).timestamp() * 1000)
load = lambda s, iv: perps.load_json(perps.cache_file(s, iv), [])
REG = perps.btc_regime(load('BTC', '4h'), st0)
SYMS = cfg['symbols']
COST = {'fee': FEE, 'side': 0, 'hold_per_hour': 0}


def bandwidth(c, n=20):
    out = [None] * len(c)
    for i in range(n - 1, len(c)):
        w = c[i - n + 1:i + 1]; m = sum(w) / n
        sd = (sum((x - m) ** 2 for x in w) / n) ** 0.5
        out[i] = 4 * sd / m if m else None
    return out


BW = {}


def sq_gate(sym, close_ms, side, i, ind, bars4):
    if sym not in BW:
        BW[sym] = bandwidth([x[4] for x in bars4])
    bw = BW[sym]
    if i < 121 or bw[i - 1] is None:
        return False
    hist = sorted(x for x in bw[i - 121:i - 1] if x is not None)
    if not hist or bw[i - 1] > hist[int(num('q', 0.25) * (len(hist) - 1))]:
        return False
    if num('rvol', 0) > 0:
        v = [x[5] for x in bars4[i - 20:i]]
        if bars4[i][5] < num('rvol', 0) * statistics.mean(v):
            return False
    return True


def run_sq():
    st = dict(st0, donchian=int(num('don', 20)), min_body_atr=num('body', 1.0))
    out = []
    for s in SYMS:
        for t in perps.gen_trades_exec(s, load(s, '4h'), load(s, '1h'), st, sch, COST, REG, sq_gate):
            if t['t_in'] >= START:
                out.append({'sym': s, 't_in': t['t_in'], 't_out': t['t_out'], 'r': perps.trade_r(t, FEE, 0), 'exit': t['exit']})
    return out


def run_cu():
    st = dict(st0)
    don = int(num('don', 55))
    st['donchian'] = don
    inds = {s: perps.indicators(load(s, '4h'), st) for s in SYMS}
    tidx = {s: {t: k for k, t in enumerate(inds[s]['t'])} for s in SYMS}
    b1s = {s: load(s, '1h') for s in SYMS}
    i1 = {s: {x[0]: k for k, x in enumerate(b1s[s])} for s in SYMS}
    times = sorted(set(inds['BTC']['t']))
    out, busy = [], {s: 0 for s in SYMS}
    for t in times:
        close = t + H4
        if close < START or not perps.entry_allowed(close, sch):
            continue
        breakers, side = [], None
        for s in SYMS:
            k = tidx[s].get(t)
            if k is None:
                continue
            sg = perps.signal(inds[s], k, st)
            if sg:
                breakers.append((s, sg['side']))
        btc_brk = [sd for s, sd in breakers if s == 'BTC']
        r = REG.get(t)
        if r is None:
            continue
        want = 'long' if r > 0 else 'short'
        if P.get('trigger', 'btc') == 'btc':
            fire = btc_brk and btc_brk[0] == want
        else:
            fire = sum(1 for _, sd in breakers if sd == want) >= int(num('breadth', 3))
        if not fire:
            continue
        broke = {s for s, _ in breakers}
        sgn = 1 if want == 'long' else -1
        for s in SYMS:
            if s in broke or s == 'BTC' or close < busy[s]:
                continue
            ind = inds[s]; k = tidx[s].get(t)
            if k is None or ind['atr'][k] is None or ind['ef'][k] is None or ind['es'][k] is None:
                continue
            if (ind['ef'][k] > ind['es'][k]) != (sgn == 1):
                continue
            a = ind['atr'][k]; c = ind['c'][k]
            lvl = ind['hh'][k] if sgn == 1 else ind['ll'][k]
            if lvl is None or (lvl - c) * sgn > num('dist', 1.5) * a or (lvl - c) * sgn < 0:
                continue
            n0 = i1[s].get(close)
            if n0 is None:
                continue
            b1 = b1s[s]
            lim = c - sgn * 0.5 * a; stop = c - sgn * 2.0 * a
            n = None
            for m in range(n0, min(len(b1), n0 + 8)):
                if (sgn == 1 and b1[m][3] <= lim) or (sgn == -1 and b1[m][2] >= lim):
                    n, e = m, (min(b1[m][1], lim) if sgn == 1 else max(b1[m][1], lim)); break
            if n is None:
                continue
            d = abs(e - stop)
            tgt = e + sgn * (2 * (d + 0.0008 * e) + 0.0008 * e)
            flat = perps.next_weekend_stop(b1[n][0], sch)
            px = why = None
            for q in range(n, min(len(b1), n + 48)):
                o, h, l = b1[q][1:4]
                if b1[q][0] >= flat:
                    px, why = o, 'weekend'; break
                if (sgn == 1 and l <= stop) or (sgn == -1 and h >= stop):
                    px, why = ((min(o, stop) if sgn == 1 else max(o, stop)) if q > n else stop), 'stop'; break
                if q > n and ((sgn == 1 and h >= tgt) or (sgn == -1 and l <= tgt)):
                    px, why = tgt, 'target'; break
            if px is None:
                px, why = b1[q][4], 'time'
            out.append({'sym': s, 't_in': b1[n][0], 't_out': b1[q][0] + H, 'exit': why,
                        'r': (sgn * (px - e) / e - 0.0008) / (d / e + 0.0008)})
            busy[s] = b1[q][0] + H
    return out


if __name__ == '__main__':
    lab = ' '.join('%s=%s' % kv for kv in P.items())
    tr = sorted(run_sq() if P.get('mode', 'sq') == 'sq' else run_cu(), key=lambda t: t['t_in'])
    sys.argv = [sys.argv[0]]
    import family as F
    if not tr:
        print(lab, 'no trades'); sys.exit()
    rs = [t['r'] for t in tr]
    print('%-34s %+.2fR win %2.0f%% %4.1f/mo %+4.1fR/mo | %s' % (lab, statistics.mean(rs), 100 * sum(x > 0 for x in rs) / len(rs),
          len(rs) / 36.5, sum(rs) / 36.5, F.yr(tr)))
    if P.get('sim'):
        q = F.q_4h(55)
        qs = {(t['sym'], t['t_in'] // 86_400_000) for t in q}
        overlap = sum((t['sym'], t['t_in'] // 86_400_000) in qs for t in tr)
        print('    overlap with Q (same coin, same day): %d of %d' % (overlap, len(tr)))
        print('    with Q, risk 1.5%%: %s' % F.sim(F.book(q, tr), 1.5))
