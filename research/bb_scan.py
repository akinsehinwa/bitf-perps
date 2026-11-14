"""BB20-engulf, executable at 4h check-ins only. Takes the 1h-mode trades from bb_lab and delays each entry to the
first check-in hour (SGT) at or after the engulfing candle closes: skipped if, before the check-in, the stop traded
or price already reached the 1.5R target. Entry at the check-in hour's open, same stop, 1.5R from the new entry,
same exits (stop first, weekend flat, 48h hold, 0.04%/side). Then the eval sim with Q + CRT at 1.5% per trade."""
import sys, pickle, os, statistics
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps, risk_opt as ro
from ifvg_lab import report, load, SCH, FRT, H
P = '/tmp/claude-0/-home-user-bitf-perps/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad/bb_trades.pkl'
BB1 = pickle.load(open(P, 'rb'))
_b = {}


def bars(s):
    if s not in _b:
        r = load(s, '1h'); _b[s] = (r, {x[0]: k for k, x in enumerate(r)})
    return _b[s]


def delay(t, hours, tgt=1.5, hold=48):
    rows, idx = bars(t['sym']); k = idx[t['t_in']]; s, stp = t['side'], t['stp']
    e0 = t['e']; d0 = abs(e0 - stp); tp0 = e0 + s * (tgt * (d0 + FRT * e0) + FRT * e0)
    n = k
    while ((rows[n][0] // H + 8) % 24) not in hours:
        x = rows[n]
        if (s == -1 and x[2] >= stp) or (s == 1 and x[3] <= stp) or (s == -1 and x[3] <= tp0) or (s == 1 and x[2] >= tp0):
            return None
        n += 1
    if perps.in_weekend(rows[n][0], SCH):
        return None
    e = rows[n][1]; d = abs(e - stp)
    if (stp - e) * s >= 0 or d / e < 0.002:
        return None
    tp = e + s * (tgt * (d + FRT * e) + FRT * e)
    flat = perps.next_weekend_stop(rows[n][0], SCH); px = None
    for q in range(n, min(len(rows), n + hold)):
        o, hh, ll = rows[q][1], rows[q][2], rows[q][3]
        if rows[q][0] >= flat:
            px = o; break
        if (s == 1 and ll <= stp) or (s == -1 and hh >= stp):
            px = (min(o, stp) if s == 1 else max(o, stp)); break
        if q > n and ((s == 1 and hh >= tp) or (s == -1 and ll <= tp)):
            px = tp; break
    if px is None:
        px = rows[q][4]
    return dict(t, t_in=rows[n][0], t_out=rows[q][0] + H, e=e, stop_frac=d / e, r=(s * (px - e) / e - FRT) / (d / e + FRT),
                wait=n - k)


KEEP = {'SUI', 'UNI', 'BTC', 'ETH', 'SOL', 'NEAR', 'ADA'}
if __name__ == '__main__':
    base = [t for t in BB1 if t['sym'] in KEEP]
    report(base, 'BB20-engulf 1h entries (7 coins)')
    sets = {}
    for name, hrs in (('check-ins 08/12/16/20/00', {0, 8, 12, 16, 20}), ('check-ins 08/12/16/20', {8, 12, 16, 20}),
                      ('check-ins 08/20/00', {0, 8, 20})):
        tl = [x for x in (delay(t, hrs) for t in base) if x]
        sets[name] = tl
        report(tl, name)
        print('      kept %d of %d, median wait %.0fh' % (len(tl), len(base), statistics.median(x['wait'] for x in tl)))
    B = [dict(t, tag='B', prio=2, rex=True) for t in sets['check-ins 08/12/16/20/00']]
    Q, C = ro.build_trades()
    ev = dict(guard=4.25, buffer=1.0, open_cap=5, max_open=3, mpos=30, mtot=60, q=1.5, cmult=0.5, crt=0.75, dd_cut=True,
              finish=False, abandon=True)
    flat15 = dict(ev, cmult=1.0, crt=1.0)          # everything at a flat 1.5%
    print('\n%-46s %5s %5s | %4s %4s | %4s %4s | %6s %6s' % ('eval, 1.5% per trade, up to 3 open', 'pass', 'fail', 'p25', 'med', 'w60', 'w90', 'Edays', 'Efees'))
    for name, tl, cfg in (('Q+CRT (live tilts)', [], dict(ev, bb=0)), ('Q+CRT+B x0.5 (live tilts)', B, dict(ev, bb=0.5)),
                          ('Q+CRT+B x1.0 (live tilts)', B, dict(ev, bb=1.0)), ('Q+CRT flat 1.5%', [], dict(flat15, bb=0)),
                          ('Q+CRT+B flat 1.5% all', B, dict(flat15, bb=1.0)), ('Q+CRT+B flat, B x0.5', B, dict(flat15, bb=0.5))):
        trades = sorted(Q + C + tl, key=lambda t: (t['t_in'], t.get('prio', 1)))
        r = ro.evaluate(trades, cfg, step_days=2)
        print('%-46s %4.0f%% %4.0f%% | %4.0f %4.0f | %3.0f%% %3.0f%% | %6.0f %6.0f' % (name, r['pass'], r['fail'], r['p25'], r['med'], r['w60'], r['w90'], r['e_days'], r['e_fees']))
    fd = dict(guard=4.5, buffer=0.25, open_cap=5, max_open=3, mpos=30, mtot=60, cmult=0.5, crt=0.75, abandon=True)
    print('\nfunded 1% per trade, payout every 15 days, 365-day horizon (80% split, USD per 50K account)')
    for name, tl, cfg in (('Q+CRT', [], dict(fd, q=1.0, bb=0)), ('Q+CRT+B x0.5', B, dict(fd, q=1.0, bb=0.5)), ('Q+CRT+B x1.0', B, dict(fd, q=1.0, bb=1.0))):
        trades = sorted(Q + C + tl, key=lambda t: (t['t_in'], t.get('prio', 1)))
        f = ro.evaluate_funded(trades, cfg, 365)
        print('  %-20s mean $%6.0f  median $%6.0f  worst10%% $%6.0f  blown %3.0f%%' % (name, f['mean'], f['med'], f['p10'], f['blown']))
