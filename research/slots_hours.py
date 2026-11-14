"""Q and CRT by signal hour (SGT) and weekday on the NEW core 10, every 4h close allowed (no scan-hour / Monday /
weekend filters), house execution. House standard: last 12 months first, prior 2 years as a stability check."""
import sys, statistics, collections
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import qlab, cycle2_crt, perps
qlab.perps.in_weekend = lambda *a, **k: False
FAR = 10 ** 15
qlab.perps.next_weekend_stop = lambda *a, **k: FAR
cycle2_crt.perps.in_weekend = lambda *a, **k: False
import rq
rq.perps.next_weekend_stop = lambda *a, **k: FAR
CORE = ['BTC', 'ETH', 'BNB', 'XRP', 'SOL', 'ADA', 'UNI', 'LINK', 'AVAX', 'LTC']
D = 86_400_000; END = int(perps.dt.datetime(2026, 11, 13, tzinfo=perps.UTC).timestamp() * 1000); T12 = END - 365 * D
sch = dict(qlab.SCH, scan_hours=[0, 4, 8, 12, 16, 20], skip_days=[])
Q = [dict(r, h=perps.local_dt(g['close'], 8).hour, wd=perps.local_dt(g['close'], 8).strftime('%a'))
     for g in qlab.signals(sch=sch, syms=CORE) for r in [qlab.execute(g, 'atr:0.5', pen=0.05)] if r and r.get('filled')]
C = []
for s in CORE:
    for t in cycle2_crt.run(s, fill='touch', slip=0.05, dfilt=True, hours=None):
        C.append(dict(t, h=perps.local_dt(t['dec'], 8).hour, wd=perps.local_dt(t['dec'], 8).strftime('%a')))
def cell(tl):
    l = [t['r'] for t in tl if t['t_in'] >= T12]; p = [t['r'] for t in tl if t['t_in'] < T12]
    f = lambda x: ('%+.2f (%2d)' % (statistics.mean(x), len(x))) if x else '   -     '
    return '%s | %s' % (f(l), f(p))
for name, tl, live in (('Q', Q, {0, 8, 20}), ('CRT', C, {8, 12, 16, 20})):
    print('\n== %s on the new core 10 - avg R (trades): last 12 months | prior 2 years      (* = hours used live)' % name)
    for h in (0, 4, 8, 12, 16, 20):
        print('  %02d:00 SGT %s  %s' % (h, '*' if h in live else ' ', cell([t for t in tl if t['h'] == h])))
    for wd in ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'):
        print('  %s        %s' % (wd, cell([t for t in tl if t['wd'] == wd])))
