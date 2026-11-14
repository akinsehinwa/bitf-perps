"""Core-list variants judged on the LAST 12 MONTHS only (user standard from 2026-11-14), with the earlier 2 years shown
as a stability check. MC = weekly blocks drawn from the last 12 months, 10k paths, flat 1.5% (no guards)."""
import sys, pickle, statistics, random, collections
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import core_swap as cs
D = 86_400_000; W = 7 * D; END = cs.END; T12 = END - 365 * D
def mc(tl, months, n=10000):
    nw = 52; wk = [0.0] * nw
    for t in tl:
        k = int((t['t_in'] - T12) // W)
        if 0 <= k < nw:
            wk[k] += t['r']
    rnd = random.Random(7); res = sorted(sum(wk[rnd.randrange(nw)] for _ in range(round(months * 4.35))) for _ in range(n))
    return res[int(.05 * n)], res[n // 2], 100 * sum(r * 1.5 >= 8 for r in res) / n
print('%-42s | %-44s | %-16s | %s' % ('book', 'LAST 12 MONTHS: n  /mo  win   avgR  R/mo  maxDD', 'prior 2y avgR', '3-month MC: worst5% / median R, P(+8%)'))
for name, (qs, crs) in cs.books.items():
    tl = sorted([t for t in cs.Q if t['sym'] in qs] + [t for t in cs.C if t['sym'] in crs], key=lambda t: t['t_in'])
    l = [t for t in tl if t['t_in'] >= T12]; p = [t['r'] for t in tl if t['t_in'] < T12]
    rs = [t['r'] for t in l]; eq = pk = dd = 0
    for t in sorted(l, key=lambda t: t['t_out']):
        eq += t['r']; pk = max(pk, eq); dd = max(dd, pk - eq)
    lo, med, hit = mc(l, 3)
    print('%-42s | %4d %4.1f %3.0f%% %+6.2f %+5.2f %5.1fR      | %+6.2f (%3d)     | %+5.1f / %+5.1f  %3.0f%%' % (
        name, len(rs), len(rs) / 12, 100 * sum(r > 0 for r in rs) / len(rs), statistics.mean(rs), sum(rs) / 12, dd,
        statistics.mean(p), len(p), lo, med, hit))
print('\ntrades per coin in the last 12 months (Q + CRT):')
cnt = collections.Counter(t['sym'] for t in cs.Q + cs.C if t['t_in'] >= T12)
print('  ' + '  '.join('%s %d' % (s, cnt[s]) for s in cs.CORE + ['AVAX', 'LTC', 'DOGE']))
