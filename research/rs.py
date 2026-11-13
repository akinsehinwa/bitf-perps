"""#2 Relative-strength rotation on all Bitfunded crypto perps (+ relative volume), last 3 years.
Cross-section at each 4h close: RS = coin's lookback return minus BTC's. Liquidity floor: trailing 30-day median
daily quote volume >= liq ($M). Long only coins in the top `top` by RS when BTC's 4h trend is up; short only
the bottom `top` when it is down. Trigger: Q's breakout (donchian `don`, body >= body x ATR, scans 08/20/00 SGT,
no Monday) or none (trig=rs: enter any scan where the coin is in the top/bottom set and its own trend agrees,
once per coin per 2 days). Execution = Q's (1h limit 0.5 ATR, stop 2 ATR, after-fee 2R, 48h, weekend close).
rvol=x: signal candle volume >= x times its 20-candle average.
Universe: uni=all (every coin with history), uni=ex10 (excluding Q's 10 coins), uni=10 (Q's 10 only)."""
import sys, statistics, collections, bisect
sys.argv = [sys.argv[0]] + sys.argv[1:]
S = '/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad'
sys.path.insert(0, S); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps
P = dict(a.split('=') for a in sys.argv[1:] if '=' in a)
num = lambda k, d: float(P.get(k, d))
H = perps.HOUR_MS; H4 = 4 * H; D = 86_400_000
cfg = perps.load_config(); sch = cfg['schedule']; st0 = dict(cfg['strategy'])
FEE = 0.0004
START = int(perps.dt.datetime(2023, 11, 12, tzinfo=perps.UTC).timestamp() * 1000)
mk = perps.load_markets()
Q10 = cfg['symbols']
load = lambda s, iv: perps.load_json(perps.cache_file(s, iv), [])
btc4 = load('BTC', '4h')
REG = perps.btc_regime(btc4, st0)
LB = int(num('lb', 42))        # 42 x 4h = 7 days
uni = P.get('uni', 'all')
coins = [k for k, v in mk.items() if v['type'] == 'crypto' and v.get('binance')]
if uni == 'ex10':
    coins = [c for c in coins if c not in Q10]
elif uni == '10':
    coins = list(Q10)
B4 = {c: load(c, '4h') for c in coins}
B4 = {c: b for c, b in B4.items() if len(b) > 300}
# per-coin maps: t -> (close index), trailing liquidity
btc_c = {b[0]: b[4] for b in btc4}
ret, liq = {}, {}
for c, b in B4.items():
    tt = [x[0] for x in b]
    r, l = {}, {}
    qv = [x[4] * x[5] for x in b]
    for i in range(LB, len(b)):
        t = b[i][0]
        if t in btc_c and (t - LB * H4) in btc_c:
            r[t] = (b[i][4] / b[i - LB][4] - 1) - (btc_c[t] / btc_c[t - LB * H4] - 1)
        if i >= 180:
            l[t] = statistics.median(sum(qv[j:j + 6]) for j in range(i - 180, i - 5, 6)) / 1e6
    ret[c], liq[c] = r, l
# cross-sectional rank per 4h bar open time
RANK = {}
times = sorted({t for c in ret for t in ret[c]})
for t in times:
    rows = [(ret[c][t], c) for c in ret if t in ret[c] and liq[c].get(t, 0) >= num('liq', 50)]
    if len(rows) < 8:
        continue
    rows.sort()
    k = int(num('top', 5))
    RANK[t] = ({c for _, c in rows[-k:]}, {c for _, c in rows[:k]})


def gate(sym, close_ms, side, i, ind, bars4):
    t = bars4[i][0]
    if t not in RANK:
        return False
    top, bot = RANK[t]
    if (side == 'long' and sym not in top) or (side == 'short' and sym not in bot):
        return False
    if num('rvol', 0) > 0:
        v = [x[5] for x in bars4[max(0, i - 20):i]]
        if not v or bars4[i][5] < num('rvol', 0) * statistics.mean(v):
            return False
    return True


def run():
    st = dict(st0, donchian=int(num('don', 55)), min_body_atr=num('body', 1.0))
    out = []
    for c in B4:
        b1 = load(c, '1h')
        if len(b1) < 1000:
            continue
        for t in perps.gen_trades_exec(c, B4[c], b1, st, sch, {'fee': FEE, 'side': 0, 'hold_per_hour': 0}, REG, gate):
            if t['t_in'] >= START:
                out.append({'sym': c, 't_in': t['t_in'], 't_out': t['t_out'], 'r': perps.trade_r(t, FEE, 0), 'exit': t['exit']})
    return sorted(out, key=lambda t: t['t_in'])


if __name__ == '__main__':
    import family as F
    tr = run()
    rs = [x['r'] for x in tr]
    if not rs:
        print(' '.join(sys.argv[1:]), 'no trades'); sys.exit()
    syms = collections.Counter(x['sym'] for x in tr)
    print('%-40s %+.2fR win %2.0f%% %4.1f/mo %+4.1fR/mo | %s | %d coins traded' % (
        ' '.join(sys.argv[1:]) or 'defaults', statistics.mean(rs), 100 * sum(x > 0 for x in rs) / len(rs),
        len(rs) / 36.5, sum(rs) / 36.5, F.yr(tr), len(syms)))
    if P.get('sim'):
        q = F.q_4h(55)
        for lab, book in (('alone', F.book(tr)), ('with Q', F.book(q, tr))):
            print('    %-7s risk 1.5%%: %s' % (lab, F.sim(book, 1.5)))
