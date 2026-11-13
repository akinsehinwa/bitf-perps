import sys, statistics
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import risk_opt as ro
Q, C = ro.build_trades()
tr = sorted(Q + C, key=lambda t: (t['t_in'], t.get('prio', 1)))
base = dict(abandon=True, guard=4.9, buffer=0.1, open_cap=8.0, max_open=4, mpos=32.5, mtot=64, cmult=1.0, crt=1.0, dd_cut=False, finish=True)
safe = dict(abandon=True, guard=4.25, buffer=1.0, open_cap=5, max_open=3, mpos=30, mtot=60, cmult=0.5, crt=0.75, dd_cut=True, finish=False)
print('%-22s %5s %5s %5s | %4s %4s | %5s %5s %5s | %6s %6s' % ('cfg', 'pass', 'fail', 'open', 'p25', 'med', 'w14', 'w30', 'w60', 'Edays', 'Efees'))
import collections
def ev(cfg):
    import perps
    START = ro.perps.dt.datetime(2023, 11, 12, tzinfo=ro.perps.UTC).timestamp() * 1000
    t0, t1 = int(START) + 10 * ro.D, int(START) + 1005 * ro.D
    end = max(t['t_out'] for t in tr); res = []; s = t0
    while s < t1:
        res.append(ro.simulate(tr, cfg, s, end)); s += 2 * ro.D
    n = len(res); ps = sorted(d for r, d in res if r == 'pass'); p = len(ps) / n
    q = lambda x: ps[int(x * (len(ps) - 1))] if ps else float('nan')
    return dict(pass_=100 * p, fail=100 * sum(r == 'fail' for r, _ in res) / n, open=100 * sum(r == 'open' for r, _ in res) / n,
                p25=q(.25), med=q(.5), w14=100 * sum(d <= 14 for d in ps) / n, w30=100 * sum(d <= 30 for d in ps) / n,
                w60=100 * sum(d <= 60 for d in ps) / n, ed=statistics.mean(d for _, d in res) / p if p else 1e9, ef=399 / p if p else 1e9)
rows = [('safe Q1.5 (tuned)', dict(safe, q=1.5))]
for q in (2, 3, 4, 5, 6, 8):
    rows.append(('aggr Q%d' % q, dict(base, q=q)))
for name, cfg in rows:
    r = ev(cfg)
    print('%-22s %4.0f%% %4.0f%% %4.0f%% | %4.0f %4.0f | %4.0f%% %4.0f%% %4.0f%% | %6.0f %6.0f' % (name, r['pass_'], r['fail'], r['open'], r['p25'], r['med'], r['w14'], r['w30'], r['w60'], r['ed'], r['ef']))
