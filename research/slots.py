"""Slot rules on the Q + CRT ticket book (first tickets to FILL get the slots, in time order).
  all          : take every ticket (one position per coin)
  N/day        : at most N new fills per SGT day
  N open       : at most N positions open at once (a slot frees when a trade exits)
Full 3 years and last 12 months; R totals, win rate, max drawdown, $ at 1.5% of 50K ($750/R)."""
import sys, statistics
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps, risk_opt as ro
D = 86_400_000
END = int(perps.dt.datetime(2026, 11, 13, tzinfo=perps.UTC).timestamp() * 1000)
Q, C = ro.build_trades()
book = sorted(Q + C, key=lambda t: (t['t_in'], t.get('prio', 1)))


def pick(per_day=None, max_open=None):
    taken = []; day = collections.Counter(); openp = []
    for t in book:
        openp = [p for p in openp if p['t_out'] > t['t_in']]
        if any(p['sym'] == t['sym'] for p in openp):
            continue
        k = perps.day_key(t['t_in'], 8)
        if per_day and day[k] >= per_day:
            continue
        if max_open and len(openp) >= max_open:
            continue
        taken.append(t); openp.append(t); day[k] += 1
    return taken


import collections
rules = [('all tickets', {}), ('1 per day', dict(per_day=1)), ('2 per day', dict(per_day=2)), ('3 per day', dict(per_day=3)),
         ('1 open at a time', dict(max_open=1)), ('2 open at a time', dict(max_open=2)), ('3 open at a time', dict(max_open=3)),
         ('2/day + 2 open', dict(per_day=2, max_open=2))]
for wname, t0 in (('full 3 years', 0), ('last 12 months', END - 365 * D)):
    mo = 36.0 if not t0 else 12.0
    print('\n== %s' % wname)
    print('%-18s %6s %6s %5s %7s %8s %7s %9s %9s' % ('rule', 'trades', '/month', 'win', 'avg R', 'total R', 'maxDD', '$/month', 'worst mo'))
    for name, kw in rules:
        tl = [t for t in pick(**kw) if t['t_in'] >= t0]
        rs = [t['r'] for t in tl]
        eq = pk = dd = 0
        for t in sorted(tl, key=lambda t: t['t_out']):
            eq += t['r']; pk = max(pk, eq); dd = max(dd, pk - eq)
        m = collections.Counter()
        for t in tl:
            m[perps.local_dt(t['t_out'], 8).strftime('%Y-%m')] += t['r']
        print('%-18s %6d %6.1f %4.0f%% %+7.2f %+8.1f %6.1fR %+9.0f %+8.1fR' % (name, len(rs), len(rs) / mo, 100 * sum(r > 0 for r in rs) / len(rs),
              statistics.mean(rs), sum(rs), dd, 750 * sum(rs) / mo, min(m.values())))
print('\nhow often does a day have more than 2 fills? (full period)')
cnt = collections.Counter(perps.day_key(t['t_in'], 8) for t in pick())
print('  days with fills %d | 1: %d | 2: %d | 3+: %d' % (len(cnt), sum(v == 1 for v in cnt.values()), sum(v == 2 for v in cnt.values()), sum(v >= 3 for v in cnt.values())))
