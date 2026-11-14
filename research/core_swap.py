"""Core-list variants on the Q + CRT book (trades from all_coins.py). Rule pick = non-core coins with 4h-return
correlation to BTC >= 0.70 and annualised vol < 100% over the last 12 months (similarity.py) - NOTE measured on the
last 12 months, so mild hindsight for the earlier two years. 'Top performers' = best non-core by backtest R
(cherry-picked, reference only). Eval = risk_opt rolling sim, live tilts (Q 1.5%, x0.5 when BTC vol contracting,
CRT x0.75), safe guards."""
import sys, pickle, statistics, bisect, math, collections
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps, risk_opt as ro
from ifvg_lab import report
SP = '/tmp/claude-0/-home-user-bitf-perps/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad/'
Q, C = pickle.load(open(SP + 'all_coins_trades.pkl', 'rb'))
sim = pickle.load(open(SP + 'similarity.pkl', 'rb'))
b4 = perps.load_json(perps.cache_file('BTC', '4h'), []); ts = [b[0] for b in b4]; c = [b[4] for b in b4]
lr = [0] + [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
exp = {ts[i]: statistics.pstdev(lr[i - 41:i + 1]) > statistics.pstdev(lr[i - 83:i - 41]) for i in range(84, len(c))}
for t in Q:
    t['rex'] = exp.get(ts[bisect.bisect_right(ts, t['sig_close'] - 4 * 3600_000) - 1]) if 'sig_close' in t else exp.get(ts[bisect.bisect_right(ts, t['t_in']) - 2])
for t in C:
    t.setdefault('rex', True)
CORE = ['BTC', 'ETH', 'BNB', 'XRP', 'SOL', 'HYPE', 'ZEC', 'ADA', 'UNI', 'LINK']
CORE8 = [s for s in CORE if s not in ('HYPE', 'ZEC')]
RULE = sorted(s for s, v in sim.items() if s not in CORE and (v['cb'] or 0) >= 0.70 and v['vol'] < 100)
TOP = ['AVAX', 'LTC', 'ARB', 'WIF', 'JASMY']
print('rule picks (corr>=0.70, vol<100%):', ' '.join(RULE))
END = max(t['t_out'] for t in Q); T12 = END - 365 * 86_400_000
books = {
    'live core 10': (CORE, CORE),
    'core 8 (no HYPE/ZEC)': (CORE8, CORE8),
    'core 8 + rule picks, CRT core 8 only': (CORE8 + RULE, CORE8),
    'core 8 + rule picks, both strategies': (CORE8 + RULE, CORE8 + RULE),
    'core 8 + top performers (cherry-picked)': (CORE8 + TOP, CORE8 + TOP),
    'core 8 + AVAX + LTC (rule AND results)': (CORE8 + ['AVAX', 'LTC'], CORE8 + ['AVAX', 'LTC']),
    'core 8 + AVAX LTC DOGE (lowest vol picks)': (CORE8 + ['AVAX', 'LTC', 'DOGE'], CORE8 + ['AVAX', 'LTC', 'DOGE']),
}
ev = dict(guard=4.25, buffer=1.0, open_cap=5, max_open=3, mpos=30, mtot=60, q=1.5, cmult=0.5, crt=0.75, dd_cut=True, finish=False, abandon=True)
print('\n%-42s | %-30s | %-22s | %5s %5s %6s %6s' % ('book', '3 years: n/mo  avgR  R/mo  maxDD', 'last 12m: avgR  R/mo', 'pass', 'med', 'Edays', 'w90'))
for name, (qs, cs) in books.items():
    tl = sorted([t for t in Q if t['sym'] in qs] + [t for t in C if t['sym'] in cs], key=lambda t: (t['t_in'], t['prio']))
    rs = [t['r'] for t in tl]; eq = pk = dd = 0
    for t in sorted(tl, key=lambda t: t['t_out']):
        eq += t['r']; pk = max(pk, eq); dd = max(dd, pk - eq)
    l12 = [t['r'] for t in tl if t['t_in'] >= T12]
    r = ro.evaluate(tl, ev, step_days=2)
    print('%-42s | %5.1f %+6.2f %+6.2f %5.1fR    | %+6.2f %+6.2f          | %4.0f%% %5.0f %6.0f %5.0f%%' % (
        name, len(rs) / 36, statistics.mean(rs), sum(rs) / 36, dd, statistics.mean(l12), sum(l12) / 12, r['pass'], r['med'], r['e_days'], r['w90']))
print('\nHYPE and ZEC on their own (3y):')
for s in ('HYPE', 'ZEC'):
    report([t for t in Q if t['sym'] == s], '  Q ' + s); report([t for t in C if t['sym'] == s], '  CRT ' + s)
print('\nrule picks individually (Q / CRT avg R, n):')
for s in RULE:
    q = [t['r'] for t in Q if t['sym'] == s]; cc = [t['r'] for t in C if t['sym'] == s]
    print('  %-8s Q %+.2f (%d)  CRT %+.2f (%d)  corr %.2f vol %.0f' % (s, statistics.mean(q) if q else 0, len(q), statistics.mean(cc) if cc else 0, len(cc), sim[s]['cb'], sim[s]['vol']))
