import sys, statistics
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import risk_opt as ro
Q, C = ro.build_trades(); tr = sorted(Q + C, key=lambda t: (t['t_in'], t.get('prio', 1)))
START = int(ro.perps.dt.datetime(2023, 11, 12, tzinfo=ro.perps.UTC).timestamp() * 1000)
aggr = dict(abandon=True, guard=4.9, buffer=0.1, open_cap=8.0, max_open=4, mpos=32.5, mtot=64, cmult=1.0, crt=1.0, hot=None)
safe = dict(abandon=True, guard=4.5, buffer=0.25, open_cap=5, max_open=3, mpos=30, mtot=60, cmult=0.5, crt=0.75)
H = 180
print('funded, %d-day horizon, payout every 15d (80%% split)' % H)
print('%-14s %7s %7s %7s %7s | %6s %5s | %6s' % ('cfg', 'mean$', 'med$', 'p10$', 'p90$', 'blown', 'life', '$/day'))
for name, cfg in [('safe Q1.5', dict(safe, q=1.5)), ('safe Q2', dict(safe, q=2.0)), ('aggr Q2', dict(aggr, q=2)), ('aggr Q3', dict(aggr, q=3)), ('aggr Q4', dict(aggr, q=4)), ('aggr Q5', dict(aggr, q=5))]:
    t0 = START + 10 * ro.D; t1 = max(t['t_out'] for t in tr) - H * ro.D; res = []; s = t0
    while s < t1:
        res.append(ro.funded(tr, cfg, s, H, 15)); s += 2 * ro.D
    paid = sorted(r[0] for r in res); q = lambda x: paid[int(x * (len(paid) - 1))]
    life = statistics.mean(r[2] for r in res)
    print('%-14s %7.0f %7.0f %7.0f %7.0f | %5.0f%% %5.0f | %6.1f' % (name, statistics.mean(paid), q(.5), q(.1), q(.9), 100 * statistics.mean(r[1] for r in res), life, statistics.mean(paid) / life))
