"""Stop / target study on the current strategy (4h breakout, BTC bias, 1h limit entry, 4 scans).
Part 1: why trades exit, and whether stopped trades would have won with more room.
Part 2: stop variants (ATR multiple from the signal close, or beyond the last 4h swing) x targets,
        scored per year and in $/month (via s2.month_pnl)."""
import sys, statistics, collections
sys.argv = [sys.argv[0], 'current'] + sys.argv[1:]
sys.path.insert(0, '/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad')
import s2, perps
H = perps.HOUR_MS
cfg, sch, FEE = s2.cfg, s2.sch, s2.FEE
SYMS = s2.SYMS
Y = s2.Y


def pivots_before(b4, i, n, kind):
    """Most recent confirmed 4h swing low (kind='L') / high ('H') at or before bar i (n bars each side)."""
    for p in range(i - n, n, -1):
        seg = b4[p - n:p + n + 1]
        if kind == 'L' and b4[p][3] == min(x[3] for x in seg):
            return b4[p][3]
        if kind == 'H' and b4[p][2] == max(x[2] for x in seg):
            return b4[p][2]
    return None


def run(sym, stop_mode='atr', k=2.5, tr=2.0, piv=3, buf=0.25, cap=(1.0, 4.0), limit_atr=0.5, study=False):
    st = dict(cfg['strategy'])
    b4, b1 = s2.bars(sym, '4h'), s2.bars(sym, '1h')
    ind = perps.indicators(b4, st)
    i1 = {x[0]: n for n, x in enumerate(b1)}
    out, busy = [], 0
    for i in range(st['ema_slow'] + 1, len(b4) - 1):
        t = ind['t'][i] + 4 * H
        if t < busy or not perps.entry_allowed(t, sch):
            continue
        sg = perps.signal(ind, i, st)
        if not sg:
            continue
        r = s2.reg_at(t)
        if r is None or (r > 0) != (sg['side'] == 'long'):
            continue
        n0 = i1.get(t)
        if n0 is None:
            continue
        s = 1 if sg['side'] == 'long' else -1
        c, a = ind['c'][i], ind['atr'][i]
        if stop_mode == 'atr':
            stop = c - s * k * a
        else:
            sw = pivots_before(b4, i, piv, 'L' if s == 1 else 'H')
            if sw is None:
                continue
            stop = sw - s * buf * a
            dist = abs(c - stop) / a
            if dist < cap[0]:
                stop = c - s * cap[0] * a
            elif dist > cap[1]:
                continue                     # swing too far away: skip rather than oversize the stop
        lim = c - s * limit_atr * a
        n = None
        for m in range(n0, min(len(b1), n0 + st['limit_valid_hours'])):
            if (s == 1 and b1[m][3] <= lim) or (s == -1 and b1[m][2] >= lim):
                n, e = m, (min(b1[m][1], lim) if s == 1 else max(b1[m][1], lim))
                break
        if n is None:
            continue
        if (s == 1 and stop >= e) or (s == -1 and stop <= e):
            continue
        d = abs(e - stop)
        tgt = e + s * tr * d
        px, why, to = s2.walk(b1, n, s, e, stop, tgt, 48)
        trd = s2.rec(sym, s, b1[n][0], e, stop, px, why, to)
        trd['stop_atr'] = d / a
        if study and why == 'stop':
            # after the stop: within the original 48h window, did price reach the target anyway?
            end = n + 48
            later = b1[i1.get(to - H, n) + 1:min(len(b1), end)] if i1.get(to - H) is not None else []
            trd['would_win'] = any((s == 1 and x[2] >= tgt) or (s == -1 and x[3] <= tgt) for x in later)
            # how far past the stop did price go before turning (in ATR)? = deepest adverse excursion in the window
            seg = b1[n:min(len(b1), end)]
            worst = min(x[3] for x in seg) if s == 1 else max(x[2] for x in seg)
            trd['mae_atr'] = abs(worst - e) / a
            trd['stop_dist_atr'] = d / a
        out.append(trd)
        busy = to
    return out


def score(label, **kw):
    trades = sorted([t for s_ in SYMS for t in run(s_, **kw)], key=lambda t: t['t_in'])
    rs = lambda ts: [perps.trade_r(t, FEE, 0) for t in ts]
    cells = []
    for y in range(3):
        r = rs([t for t in trades if Y[y] <= t['t_in'] < Y[y + 1]])
        cells.append('%+.3fR n=%3d w%2.0f%%' % (statistics.mean(r), len(r), 100 * sum(x > 0 for x in r) / len(r)) if r else 'n/a')
    mm = s2.month_pnl(trades, 1.5)
    allp = [p for k_, p, b in mm]
    ex = collections.Counter(t['exit'] for t in trades)
    print('%-34s %s | $%+5.0f/mo | stop %2.0f%% tgt %2.0f%% time %2.0f%% wknd %2.0f%%' % (
        label, ' | '.join(cells), statistics.mean(allp),
        *(100 * ex[k_] / len(trades) for k_ in ('stop', 'target', 'time', 'weekend'))))
    return trades


if __name__ == '__main__':
    print('== Part 1: the current rules, why trades exit')
    tr = sorted([t for s_ in SYMS for t in run(s_, study=True)], key=lambda t: t['t_in'])
    ex = collections.Counter(t['exit'] for t in tr)
    print('  %d trades: %s' % (len(tr), ', '.join('%s %d (%.0f%%)' % (k, v, 100 * v / len(tr)) for k, v in ex.most_common())))
    stp = [t for t in tr if t['exit'] == 'stop']
    print('  stop distance from fill: median %.2f ATR' % statistics.median(t['stop_dist_atr'] for t in stp))
    print('  stopped trades that then reached the target inside the same 48h: %d of %d (%.0f%%)' % (
        sum(t['would_win'] for t in stp), len(stp), 100 * sum(t['would_win'] for t in stp) / len(stp)))
    print('  how far stopped trades went against us in that 48h (ATR): median %.2f, 75%% %.2f, 90%% %.2f' % (
        statistics.median(t['mae_atr'] for t in stp), sorted(t['mae_atr'] for t in stp)[int(.75 * len(stp))],
        sorted(t['mae_atr'] for t in stp)[int(.9 * len(stp))]))
    rs = [perps.trade_r(t, FEE, 0) for t in tr]
    for k in ('time', 'weekend'):
        sub = [perps.trade_r(t, FEE, 0) for t in tr if t['exit'] == k]
        if sub:
            print('  %s exits: avg %+.2fR, %d%% in profit' % (k, statistics.mean(sub), 100 * sum(x > 0 for x in sub) / len(sub)))
    print('\n== Part 2: stop and target variants (per year: Nov23-24 | Nov24-25 | Nov25-26), $/month at 1.5%')
    for k in (1.5, 2.0, 2.5, 3.0, 3.5, 4.0):
        score('ATR stop %.1f x, 2R' % k, k=k)
    for tr_ in (1.5, 2.5, 3.0):
        score('ATR stop 2.5 x, %.1fR' % tr_, k=2.5, tr=tr_)
    for piv in (2, 3, 5):
        for buf in (0.25, 0.5):
            score('swing stop piv%d +%.2fATR, 2R' % (piv, buf), stop_mode='swing', piv=piv, buf=buf)
    score('swing stop piv3 +0.5, cap 1.5-5ATR', stop_mode='swing', piv=3, buf=0.5, cap=(1.5, 5.0))
