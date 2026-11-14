"""All 72 Bitfunded crypto perps on the live ticket strategies (Q, CRT) with the house execution rules, plus a
per-coin table joined with the similarity stats (similarity.py), and a 1/3/6-month weekly-block Monte Carlo of the
all-coin book (last 12 months) - uncapped, and capped like the live guards (max 3 open, 3 new per SGT day,
one position per coin, first to fill). Flat 1.5% eval risk ($750/R) and 1% funded ($400/R to the trader)."""
import sys, os, pickle, statistics, collections, random
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps, qlab, cycle2_crt
from ifvg_lab import report
SP = '/tmp/claude-0/-home-user-bitf-perps/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad/'
D = 86_400_000; W = 7 * D
END = int(perps.dt.datetime(2026, 11, 13, tzinfo=perps.UTC).timestamp() * 1000)
mk = perps.load_markets()
CR = [k for k, v in mk.items() if v['type'] == 'crypto' and v.get('binance')
      and os.path.exists(perps.cache_file(k, '15m'))]
CORE = ['BTC', 'ETH', 'BNB', 'XRP', 'SOL', 'HYPE', 'ZEC', 'ADA', 'UNI', 'LINK']
CACHE = SP + 'all_coins_trades.pkl'
if os.path.exists(CACHE):
    Q, C = pickle.load(open(CACHE, 'rb'))
else:
    Q = [dict(r, tag='Q', prio=0) for g in qlab.signals(syms=CR) for r in [qlab.execute(g, 'atr:0.5', pen=0.05)] if r and r.get('filled')]
    C = []
    for s in CR:
        try:
            C += [dict(t, tag='C', prio=1) for t in cycle2_crt.run(s, fill='touch', slip=0.05, dfilt=True, hours={8, 12, 16, 20})]
        except Exception as e:
            print('CRT skip', s, e)
    pickle.dump((Q, C), open(CACHE, 'wb'))
sim = pickle.load(open(SP + 'similarity.pkl', 'rb'))


def cap(book, max_open=3, per_day=3):
    taken, openp, day = [], [], collections.Counter()
    for t in sorted(book, key=lambda t: (t['t_in'], t['prio'])):
        openp = [p for p in openp if p['t_out'] > t['t_in']]
        k = perps.day_key(t['t_in'], 8)
        if any(p['sym'] == t['sym'] for p in openp) or len(openp) >= max_open or day[k] >= per_day:
            continue
        taken.append(t); openp.append(t); day[k] += 1
    return taken


def mc(tl, t0, months, n=10000, seed=7):
    nw = int((END - t0) // W); wk = [0.0] * nw
    for t in tl:
        k = int((t['t_in'] - t0) // W)
        if 0 <= k < nw:
            wk[k] += t['r']
    rnd = random.Random(seed); res = sorted(sum(wk[rnd.randrange(nw)] for _ in range(round(months * 4.35))) for _ in range(n))
    q = lambda x: res[int(x * (n - 1))]
    return q(.05), q(.5), q(.95), 100 * sum(r < 0 for r in res) / n


if __name__ == '__main__':
    print('coins with 15m data: %d' % len(CR))
    for name, tl in (('Q', Q), ('CRT', C)):
        report(tl, '%s all %d coins' % (name, len(CR)))
        report([t for t in tl if t['sym'] in CORE], '%s core 10' % name)
        report([t for t in tl if t['sym'] not in CORE], '%s the other %d' % (name, len(CR) - len(CORE)))
    # per-coin table
    rows = []
    for s in CR:
        q = [t['r'] for t in Q if t['sym'] == s]; c = [t['r'] for t in C if t['sym'] == s]
        v = sim.get(s, {})
        rows.append((s, len(q), statistics.mean(q) if q else 0, len(c), statistics.mean(c) if c else 0,
                     v.get('cb') or 0, v.get('beta') or 0, v.get('vol') or 0, v.get('trend') or 0, v.get('brk') or 0))
    rows.sort(key=lambda r: -(r[1] * r[2] + r[3] * r[4]))
    print('\n%-8s %4s %7s %4s %7s %8s | %5s %5s %5s %6s %5s' % ('coin', 'nQ', 'Q avgR', 'nC', 'C avgR', 'total R', 'cBTC', 'beta', 'vol', 'trend', 'brk'))
    for r in rows:
        print('%-8s %4d %+7.2f %4d %+7.2f %+8.1f | %5.2f %5.2f %5.0f %6.2f %4.0f%%%s' % (r[0], r[1], r[2], r[3], r[4], r[1] * r[2] + r[3] * r[4],
              r[5], r[6], r[7], r[8], 100 * r[9], '  *core' if r[0] in CORE else ''))
    # does similarity predict results? (coins with >= 8 Q trades)
    ok = [r for r in rows if r[1] >= 8]
    for i, lab in ((5, 'corr to BTC'), (6, 'beta'), (7, 'volatility'), (8, 'trend efficiency'), (9, 'breakout follow-through')):
        print('Q avg R vs %-24s: rank-corr %+.2f' % (lab, statistics.correlation([sorted(x[i] for x in ok).index(x[i]) for x in ok],
                                                                             [sorted(x[2] for x in ok).index(x[2]) for x in ok])))
    # projection
    t0 = END - 365 * D
    for label, book in (('core 10 (live)', [t for t in Q + C if t['sym'] in CORE]), ('all coins', Q + C)):
        for capname, tl in (('every ticket', book), ('capped: 3 open, 3/day', cap(book))):
            last = [t for t in tl if t['t_in'] >= t0]
            rs = [t['r'] for t in last]
            print('\n== %s, %s | last 12m: %d trades (%.1f/mo), win %.0f%%, avg %+.2fR, %+.1fR/mo' % (
                label, capname, len(rs), len(rs) / 12, 100 * sum(r > 0 for r in rs) / len(rs), statistics.mean(rs), sum(rs) / 12))
            for mo in (1, 3, 6):
                lo, med, hi, neg = mc(last, t0, mo)
                print('   %d mo: R worst5%% %+6.1f  median %+6.1f  best5%% %+6.1f | eval $ %+7.0f / %+7.0f / %+7.0f | P(loss) %3.0f%%' % (
                    mo, lo, med, hi, 750 * lo, 750 * med, 750 * hi, neg))
            lo, med, hi, _ = mc(last, t0, 1)
            print('   funded 1%%, per month to you: worst5 $%+.0f / median $%+.0f / best5 $%+.0f' % (400 * lo, 400 * med, 400 * hi))
