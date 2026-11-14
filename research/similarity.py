"""Which Bitfunded crypto perps move like the majors? Last 12 months of 4h closes (aligned timestamps).
corr_BTC/ETH/SOL: correlation of 4h log returns; beta: vs BTC; vol: annualised; trend: mean 20-day efficiency ratio
(|net move| / path, daily closes) - how cleanly the coin trends; brk: share of 4h bars making a 55-bar Donchian
breakout that follows through 2 ATR within 48h (Q-style behaviour). Saved to the scratchpad for the strategy study."""
import sys, math, statistics, collections, pickle
sys.path.insert(0, '/home/user/bitfunded-perps'); import perps
D = 86_400_000; H4 = 4 * 3600_000
END = int(perps.dt.datetime(2026, 11, 13, tzinfo=perps.UTC).timestamp() * 1000); T0 = END - 365 * D
mk = perps.load_markets(); CR = [k for k, v in mk.items() if v['type'] == 'crypto' and v.get('binance')]
ser = {}
for s in CR:
    b = perps.load_json(perps.cache_file(s, '4h'), [])
    ser[s] = {x[0]: x for x in b if T0 <= x[0] < END}
def rets(s):
    d = ser[s]; ks = sorted(d)
    return {k: math.log(d[k][4] / d[p][4]) for p, k in zip(ks, ks[1:]) if k - p == H4}
R = {s: rets(s) for s in CR}
def corr(a, b):
    ks = sorted(set(R[a]) & set(R[b]))
    if len(ks) < 500:
        return None, None
    x = [R[a][k] for k in ks]; y = [R[b][k] for k in ks]
    c = statistics.correlation(x, y); beta = statistics.covariance(x, y) / statistics.variance(y)
    return c, beta
out = {}
for s in CR:
    if len(R[s]) < 500:
        continue
    cb, beta = corr(s, 'BTC'); ce, _ = corr(s, 'ETH'); cs, _ = corr(s, 'SOL')
    vol = statistics.pstdev(R[s].values()) * math.sqrt(6 * 365) * 100
    b = [ser[s][k] for k in sorted(ser[s])]
    days = collections.OrderedDict()
    for x in b:
        days.setdefault(x[0] // D, []).append(x[4])
    dc = [v[-1] for v in days.values()]
    ers = []
    for i in range(20, len(dc)):
        path = sum(abs(dc[j] - dc[j - 1]) for j in range(i - 19, i + 1))
        ers.append(abs(dc[i] - dc[i - 20]) / path if path else 0)
    hi = [x[2] for x in b]; lo = [x[3] for x in b]; c = [x[4] for x in b]
    at = perps.atr(hi, lo, c, 14); n = ok = 0
    for i in range(56, len(b) - 12):
        if at[i] is None:
            continue
        if c[i] > max(hi[i - 55:i]):
            n += 1; ok += max(hi[i + 1:i + 13]) >= c[i] + 2 * at[i]
        elif c[i] < min(lo[i - 55:i]):
            n += 1; ok += min(lo[i + 1:i + 13]) <= c[i] - 2 * at[i]
    out[s] = dict(cb=cb, ce=ce, cs=cs, beta=beta, vol=vol, trend=statistics.mean(ers), brk=ok / n if n else 0, nbrk=n)
pickle.dump(out, open('/tmp/claude-0/-home-user-bitf-perps/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad/similarity.pkl', 'wb'))
print('%-8s %6s %6s %6s %6s %6s %6s %8s' % ('coin', 'cBTC', 'cETH', 'cSOL', 'beta', 'vol%', 'trend', 'brk-follow'))
for s, v in sorted(out.items(), key=lambda kv: -((kv[1]['cb'] or 0) + (kv[1]['ce'] or 0) + (kv[1]['cs'] or 0))):
    print('%-8s %6.2f %6.2f %6.2f %6.2f %6.0f %6.2f %5.0f%% (%d)' % (s, v['cb'] or 0, v['ce'] or 0, v['cs'] or 0, v['beta'] or 0, v['vol'], v['trend'], 100 * v['brk'], v['nbrk']))
