"""Swing hold-time test (user question 2026-11-20): ifvg2 G7 check-in tickets (08/12/16/20), all 72 coins,
hold 48 / 96 (live) / 144 / 240 hours. House standard: last 12 months first, prior 2 years as stability check."""
import sys, statistics, collections
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps, ifvg2
if '--noweekend' in sys.argv:          # live runs 7 days with no weekend close
    ifvg2.perps.next_weekend_stop = lambda *a, **k: 10 ** 15
    ifvg2.perps.in_weekend = lambda *a, **k: False
D = 86_400_000
END = int(perps.dt.datetime(2026, 11, 13, tzinfo=perps.UTC).timestamp() * 1000); T12 = END - 365 * D
mk = perps.load_markets(); CR = [k for k, v in mk.items() if v['type'] == 'crypto' and v.get('binance')]
for hold in (48, 96, 144, 240):
    allt = [t for s in CR for t in ifvg2.run(s, G=7.0, CHK={8, 12, 16, 20}, hold=hold)]
    l = [t for t in allt if t['t_in'] >= T12]; p = [t for t in allt if t['t_in'] < T12]
    ex = collections.Counter(t['exit'] for t in l)
    f = lambda xs: '%4d trades %+.3fR win %2.0f%%' % (len(xs), statistics.mean(t['r'] for t in xs), 100 * sum(t['r'] > 0 for t in xs) / len(xs))
    print('hold %3dh | last 12m: %s  total %+6.1fR | prior 2y: %s | exits 12m: %s' % (hold, f(l), sum(t['r'] for t in l), f(p), dict(ex)), flush=True)
