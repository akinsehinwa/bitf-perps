"""Swing setup (iFVG v2, big legs G7) as a check-in ticket: limit placed at the first check-in hour after the 1h
inversion (cancelled if the stop traded meanwhile), valid V hours. Compared with instant placement."""
import sys, statistics
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps, ifvg2
D = 86_400_000
END = int(perps.dt.datetime(2026, 11, 13, tzinfo=perps.UTC).timestamp() * 1000); T12 = END - 365 * D
mk = perps.load_markets(); CR = [k for k, v in mk.items() if v['type'] == 'crypto' and v.get('binance')]
CORE = ['BTC', 'ETH', 'BNB', 'XRP', 'SOL', 'ADA', 'UNI', 'LINK', 'AVAX', 'LTC']
def line(lab, tl):
    l = [t['r'] for t in tl if t['t_in'] >= T12]; p = [t['r'] for t in tl if t['t_in'] < T12]
    print('%-46s last 12m: n %4d (%4.1f/mo) win %3.0f%% avg %+.2fR %+5.2fR/mo | prior 2y: n %4d avg %+.2fR' % (
        lab, len(l), len(l) / 12, 100 * sum(r > 0 for r in l) / max(1, len(l)), statistics.mean(l) if l else 0, sum(l) / 12, len(p), statistics.mean(p) if p else 0), flush=True)
for name, kw in (('instant (1h watching)', {}), ('check-ins 08/12/16/20/00, valid 12h', dict(CHK={0, 8, 12, 16, 20})),
                 ('check-ins 08/12/16/20/00, valid 24h', dict(CHK={0, 8, 12, 16, 20}, V=24)),
                 ('check-ins 08/12/16/20, valid 12h', dict(CHK={8, 12, 16, 20}))):
    allt = []
    for s in CR:
        allt += ifvg2.run(s, G=7.0, **kw)
    line(name + ' | all 72', allt)
    line(name + ' | core 10', [t for t in allt if t['sym'] in CORE])
