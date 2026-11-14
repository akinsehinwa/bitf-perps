"""Swing timing study (all 72 coins, big legs G7): how fast the inverted-FVG midline gets retested, what a check-in
schedule misses, and the two-condition alternative (limit straight into the 50% / 61.8% zone, placed at the check-in
after the 50% touch, stop beyond 78.6% + 0.5 ATR, valid 24h)."""
import sys, statistics, collections
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps, ifvg2
D = 86_400_000; H = 3600_000
END = int(perps.dt.datetime(2026, 11, 13, tzinfo=perps.UTC).timestamp() * 1000); T12 = END - 365 * D
mk = perps.load_markets(); CR = [k for k, v in mk.items() if v['type'] == 'crypto' and v.get('binance')]
CHK = {8, 12, 16, 20}
def nxt(t):
    while ((t // H + 8) % 24) not in CHK:
        t += H
    return t
def stat(lab, tl):
    for per, sel in (('last 12m', lambda t: t['t_in'] >= T12), ('prior 2y', lambda t: t['t_in'] < T12)):
        rs = [t['r'] for t in tl if sel(t)]
        if rs:
            print('  %-40s %s: n %4d (%4.1f/mo) win %3.0f%% avg %+.2fR  total %+6.1fR' % (lab, per, len(rs), len(rs) / (12 if per == 'last 12m' else 24),
                  100 * sum(r > 0 for r in rs) / len(rs), statistics.mean(rs), sum(rs)))
inst = [t for s in CR for t in ifvg2.run(s, G=7.0)]
chk = [t for s in CR for t in ifvg2.run(s, G=7.0, CHK=CHK)]
print('== 1) instant version (someone watching the 1h): hours from the inversion close to the midline fill')
w = [(t['t_in'] - t['sig_t']) / H for t in inst]
for lim in (1, 2, 4, 8, 12):
    print('   filled within %2dh: %3.0f%%' % (lim, 100 * sum(x < lim for x in w) / len(w)))
print('   median wait %.0fh' % statistics.median(w))
miss = [t for t in inst if t['t_in'] < nxt(t['sig_t'])]
kept = [t for t in inst if t['t_in'] >= nxt(t['sig_t'])]
print('\n== 2) instant trades that fill BEFORE the next check-in (a check-in schedule cannot take these):')
stat('filled before the next check-in (missed)', miss)
stat('filled after the next check-in', kept)
print('\n== 3) versions side by side')
stat('instant (all 3 conditions, 1h watching)', inst)
stat('check-in ticket (all 3 conditions)', chk)
for e, lab in (('zone', 'zone 50% limit (2 conditions)'), ('zone618', 'zone 61.8% limit (2 conditions)')):
    stat(lab, [t for s in CR for t in ifvg2.run(s, G=7.0, CHK=CHK, entry=e)])
