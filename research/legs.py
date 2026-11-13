"""Parent-leg 50% retracement variant (user spec), backtested next to the current bot.
A: current logic (control)    B: steps 1-6    C: steps 1-7 (displacement guard)
ATR(20) on H4, T = t x ATR, G = g x ATR. Swings: 4h pivots, 3 candles each side, confirmed 3 candles later.
Parent leg = zigzag over confirmed swings with reversal threshold T (counter-moves < T extend the leg),
from the leg's origin to the running extreme. Orders placed/updated only at scan closes (08/16/20/00 SGT),
never in the weekend pause. Same exits as A: target 2R from the fill, 48h time stop, weekend close,
0.04% fee per side, no slippage, stop-first if a 1h bar touches both."""
import sys, statistics, collections
sys.path.insert(0, '/home/user/bitfunded-perps')
import perps

H = perps.HOUR_MS; H4 = 4 * H; D = 86_400_000
cfg = perps.load_config(); sch = cfg['schedule']; st0 = cfg['strategy']
FEE = cfg['firm']['fee_pct_per_side'] / 100
SYMS = cfg['symbols']
NPIV = 3
C_ = {}
UNF = []


def bars(s, iv):
    if (s, iv) not in C_:
        C_[(s, iv)] = perps.load_json(perps.cache_file(s, iv), [])
    return C_[(s, iv)]


END = bars('BTC', '4h')[-1][0] + H4
REG = perps.btc_regime(bars('BTC', '4h'), st0)


def walk(b, n, side, e, stop, tgt, max_h=48):
    flat = perps.next_weekend_stop(b[n][0], sch)
    m = n
    for m in range(n, min(len(b), n + max_h)):
        o, h, l = b[m][1], b[m][2], b[m][3]
        if b[m][0] >= flat:
            return o, 'weekend', b[m][0]
        if (side == 1 and l <= stop) or (side == -1 and h >= stop):
            return ((min(o, stop) if side == 1 else max(o, stop)) if m > n else stop), 'stop', b[m][0] + H
        if m > n and ((side == 1 and h >= tgt) or (side == -1 and l <= tgt)):
            return tgt, 'target', b[m][0] + H     # never on the fill bar itself (order inside the bar unknown)
    return b[m][4], 'time', b[m][0] + H


def mk(sym, side, t, e, stop, px, why, t_out):
    ret = side * (px - e) / e
    return {'sym': sym, 'side': side, 't_in': t, 't_out': t_out, 'exit': why,
            'r': (ret - 2 * FEE) / (abs(e - stop) / e + 2 * FEE)}


def control(sym):
    ts = perps.gen_trades_exec(sym, bars(sym, '4h'), bars(sym, '1h'), dict(st0), sch,
                               {'fee': FEE, 'side': 0.0, 'hold_per_hour': 0.0}, REG)
    return [{'sym': sym, 'side': 1 if t['side'] == 'long' else -1, 't_in': t['t_in'], 't_out': t['t_out'],
             'exit': t['exit'], 'r': perps.trade_r(t, FEE, 0)} for t in ts]


def legs(sym, T=2.0, G=3.0, guard=False, tr=2.0, log=None):
    b4, b1 = bars(sym, '4h'), bars(sym, '1h')
    o4 = [x[1] for x in b4]; h4 = [x[2] for x in b4]; l4 = [x[3] for x in b4]; c4 = [x[4] for x in b4]
    atr = perps.atr(h4, l4, c4, 20)
    i1 = {x[0]: k for k, x in enumerate(b1)}
    n = len(b4)
    conf = collections.defaultdict(list)      # confirm index -> pivots
    for p in range(NPIV, n - NPIV):
        if h4[p] == max(h4[p - NPIV:p + NPIV + 1]):
            conf[p + NPIV].append(('H', p, h4[p]))
        if l4[p] == min(l4[p - NPIV:p + NPIV + 1]):
            conf[p + NPIV].append(('L', p, l4[p]))
    M = None          # leg origin (major pivot): (kind, idx, price)
    cand = None       # best opposite pivot since M: (kind, idx, price)
    last_two = []     # last confirmed pivots, for the 40% sub-swing log
    order = None      # dict(side, lim, stop, L, H, placed)
    guard_until = -1
    out, busy_until = [], 0
    for i in range(30, n - 1):
        a = atr[i]
        if a is None:
            continue
        # 1) confirmed swings -> zigzag with threshold T (counter-moves smaller than T extend the leg)
        for kind, p, px in sorted(conf.get(i, []), key=lambda z: z[1]):
            last_two = (last_two + [(kind, p, px)])[-2:]
            if M is None:
                M = (kind, p, px); continue
            if kind == M[0]:
                if (kind == 'H' and px > M[2]) or (kind == 'L' and px < M[2]):
                    if cand is None or abs(px - cand[2]) < T * a:
                        M, cand = (kind, p, px), None      # origin moves further out, leg restarts from it
                    else:
                        M, cand = cand, (kind, p, px)
                elif cand is not None and abs(px - cand[2]) >= T * a:
                    M, cand = cand, (kind, p, px)          # counter-move >= T confirms a new pivot: reversal
            else:
                if cand is None or (kind == 'L' and px < cand[2]) or (kind == 'H' and px > cand[2]):
                    cand = (kind, p, px)
        if M is None:
            continue
        # parent leg: from origin M to the running extreme since M
        if M[0] == 'H':
            side, Hh = -1, M[2]
            Ll = min(l4[M[1]:i + 1]); leg = Hh - Ll
        else:
            side, Ll = 1, M[2]
            Hh = max(h4[M[1]:i + 1]); leg = Hh - Ll
        # 7) displacement guard: a counter-trend candle with range >= 2 ATR blocks new orders for 3 candles
        if guard:
            ct = (c4[i] > o4[i]) if side == -1 else (c4[i] < o4[i])
            if ct and h4[i] - l4[i] >= 2 * a:
                guard_until = i + 3
        close_ms = b4[i][0] + H4
        if close_ms < busy_until:
            continue
        # cancel a live order whose leg is gone (new extreme or reversal)
        if order and (order['side'] != side or (side == -1 and Ll < order['L']) or (side == 1 and Hh > order['H'])):
            log['unfilled'] += 1; UNF.append(b4[i][0]); order = None
        if order is None and perps.entry_allowed(close_ms, sch):
            if leg < G * a:
                log['skip: leg too small'] += 1
            elif guard and i <= guard_until:
                log['skip: guard active'] += 1
            else:
                if len(last_two) == 2 and last_two[0][0] != last_two[1][0] and abs(last_two[0][2] - last_two[1][2]) < 0.4 * leg:
                    log['skip: sub-swing <40% of parent (no own order)'] += 1
                lim = Ll + 0.5 * leg if side == -1 else Hh - 0.5 * leg
                stop = Hh + 0.3 * a if side == -1 else Ll - 0.3 * a
                if abs(stop - lim) / lim >= 0.004:
                    order = {'side': side, 'lim': lim, 'stop': stop, 'L': Ll, 'H': Hh}
                    log['limits placed'] += 1
        if order is None:
            continue
        if perps.in_weekend(close_ms, sch):
            log['unfilled'] += 1; UNF.append(b4[i][0]); order = None; continue
        # fills on the next four 1h bars
        n0 = i1.get(close_ms)
        if n0 is None:
            continue
        for m in range(n0, min(len(b1), n0 + 4)):
            o, h, l = b1[m][1], b1[m][2], b1[m][3]
            if perps.in_weekend(b1[m][0], sch):
                break
            s = order['side']
            if (s == -1 and l < order['L']) or (s == 1 and h > order['H']) or \
               (s == -1 and o >= order['stop']) or (s == 1 and o <= order['stop']):
                log['unfilled'] += 1; UNF.append(b4[i][0]); order = None; break      # 6) new extreme / gapped past the stop
            if (s == -1 and h >= order['lim']) or (s == 1 and l <= order['lim']):
                e = max(o, order['lim']) if s == -1 else min(o, order['lim'])
                d = abs(order['stop'] - e)
                tgt = e + s * tr * d
                px, why, to = walk(b1, m, s, e, order['stop'], tgt)
                out.append(mk(sym, s, b1[m][0], e, order['stop'], px, why, to))
                busy_until, order = to, None
                break
    return out


def stats(tr):
    if not tr:
        return dict(n=0, win=0, avg=0, tot=0, stop=0, dd=0)
    rs = [t['r'] for t in tr]
    eq = pk = dd = 0.0
    for t in sorted(tr, key=lambda t: t['t_out']):
        eq += t['r']; pk = max(pk, eq); dd = max(dd, pk - eq)
    return dict(n=len(rs), win=100 * sum(r > 0 for r in rs) / len(rs), avg=statistics.mean(rs), tot=sum(rs),
                stop=100 * sum(t['exit'] == 'stop' for t in tr) / len(tr), dd=dd)


def removed(A, X):
    rem = [a for a in A if not any(x['sym'] == a['sym'] and x['side'] == a['side'] and abs(x['t_in'] - a['t_in']) <= D for x in X)]
    return len(rem), (100 * sum(t['r'] > 0 for t in rem) / len(rem) if rem else 0)


def window(tr, days):
    return [t for t in tr if t['t_in'] >= END - days * D]


def line(label, X, A, unf, extra=''):
    s = stats(X); k, w = removed(A, X)
    return '%-24s %4d %5d %5.0f%% %+6.2f %+7.1f %5.0f%% %6.1f   %3d (%3.0f%% won)%s' % (
        label, s['n'], unf, s['win'], s['avg'], s['tot'], s['stop'], s['dd'], k, w, extra)


if __name__ == '__main__':
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    A = window([t for s in SYMS for t in control(s)], days)
    hdr = '%-24s %4s %5s %6s %6s %7s %6s %6s   %s' % ('variant', 'n', 'unfil', 'win', 'avgR', 'totR', 'stop%', 'maxDD', "A's trades removed")
    print('Last %d days of H4 (to %s), %d symbols. R per trade net of 0.04%%/side; maxDD in R.' % (
        days, perps.dt.datetime.fromtimestamp(END / 1000, perps.UTC).date(), len(SYMS)))
    print(hdr)
    print(line('A current (control)', A, A, 0))
    logs = {}
    for lab, g in (('B steps 1-6 (T2 G3)', False), ('C steps 1-7 (T2 G3)', True)):
        lg = collections.Counter(); X = []; UNF.clear()
        for s in SYMS:
            X += legs(s, 2.0, 3.0, g, log=lg)
        Xw = window(X, days)
        logs[lab] = lg
        print(line(lab, Xw, A, sum(u >= END - days * D for u in UNF)))
    print('\nSkip log, whole history (counts every scan where a setup was skipped):')
    for lab, lg in logs.items():
        print('  %s: %s' % (lab, ', '.join('%s %d' % kv for kv in sorted(lg.items()))))
    print('\nSweep, last %d days (unfilled = limits cancelled without a fill in the window):' % days)
    print(hdr)
    for g in (False, True):
        for T in (1.5, 2.0, 2.5):
            for G in (2, 3, 4):
                lg = collections.Counter(); X = []; UNF.clear()
                for s in SYMS:
                    X += legs(s, T, G, g, log=lg)
                print(line('%s T=%.1f G=%d' % ('C' if g else 'B', T, G), window(X, days), A, sum(u >= END - days * D for u in UNF),
                           '   | 3y: n=%d avg %+.2fR' % (len(X), statistics.mean([t['r'] for t in X]) if X else 0)))
