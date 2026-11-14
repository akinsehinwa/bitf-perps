"""The user's two setups across all 72 Bitfunded crypto perps (house standard: last 12 months first, prior 2 years
as a stability check). iFVG v2 big legs (ifvg2 G=7) and the BB20 set-and-forget limit (bb_limit confirm='red',
limit at the close). Per-coin counts are tiny; the pooled numbers are what matter."""
import sys, os, statistics
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps, ifvg2, bb_limit
D = 86_400_000
END = int(perps.dt.datetime(2026, 11, 13, tzinfo=perps.UTC).timestamp() * 1000); T12 = END - 365 * D
mk = perps.load_markets(); CR = [k for k, v in mk.items() if v['type'] == 'crypto' and v.get('binance')]
CORE = ['BTC', 'ETH', 'BNB', 'XRP', 'SOL', 'ADA', 'UNI', 'LINK', 'AVAX', 'LTC']
def line(lab, tl):
    l = [t['r'] for t in tl if t['t_in'] >= T12]; p = [t['r'] for t in tl if t['t_in'] < T12]
    if not l:
        print('%-36s no trades' % lab); return
    print('%-36s last 12m: n %4d (%4.1f/mo) win %3.0f%% avg %+.2fR %+5.2fR/mo | prior 2y: n %4d avg %+.2fR' % (
        lab, len(l), len(l) / 12, 100 * sum(r > 0 for r in l) / len(l), statistics.mean(l), sum(l) / 12, len(p), statistics.mean(p) if p else 0))
for name, fn in (('iFVG v2 big legs (G7)', lambda s: ifvg2.run(s, G=7.0)),
                 ('BB20 limit (red candle, at close)', lambda s: bb_limit.run(s, confirm='red', lim='close+0'))):
    allt = []
    for s in CR:
        try:
            allt += fn(s)
        except Exception as e:
            print('  skip', s, e)
    print('\n==', name)
    line('  all 72 coins', allt)
    line('  new core 10', [t for t in allt if t['sym'] in CORE])
    line('  other 62', [t for t in allt if t['sym'] not in CORE])
