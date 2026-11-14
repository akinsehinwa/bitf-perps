"""Forward projection from recent history (user request 2026-11-14).

Per strategy and for the combined book: trades/month, win rate, avg R over the last 12 months and since 2026-05-01,
then a Monte Carlo: draw whole WEEKS (with replacement) from the window, so busy/quiet weeks and the overlap between
strategies stay realistic; 10,000 paths of 1, 3 and 6 months (4.35 weeks/month). Sizing flat: eval 1.5% of 50K per
trade ($750/R), funded 1% ($500/R, trader keeps 80%). Reports p5 / p25 / median / p75 / p95 and the chance of
ending below zero; for the eval, the chance of reaching +8% within the horizon (simple, no daily-loss guard)."""
import sys, statistics, random, collections, pickle, os
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps, risk_opt as ro
D = 86_400_000; W = 7 * D
END = int(perps.dt.datetime(2026, 11, 13, tzinfo=perps.UTC).timestamp() * 1000)
WINDOWS = {'last 12 months': END - 365 * D, 'since 1 May 2026': int(perps.dt.datetime(2026, 5, 1, tzinfo=perps.UTC).timestamp() * 1000)}
EXTRA = '/tmp/claude-0/-home-user-bitf-perps/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad/proj_extra.pkl'


def load_books():
    Q, C = ro.build_trades()
    books = {'Q (4h breakout, limit)': Q, 'CRT (4h range, stop-entry)': C}
    if os.path.exists(EXTRA):
        books.update(pickle.load(open(EXTRA, 'rb')))
    return books


def weekly(tl, t0):
    nw = int((END - t0) // W)
    wk = [[] for _ in range(nw)]
    for t in tl:
        k = int((t['t_in'] - t0) // W)
        if 0 <= k < nw:
            wk[k].append(t['r'])
    return wk


def mc(weeks_by_strat, months, n=10000, seed=7):
    rnd = random.Random(seed); nw = len(next(iter(weeks_by_strat.values())))
    k = round(months * 4.35); res = []
    for _ in range(n):
        tot = 0.0
        for _ in range(k):
            j = rnd.randrange(nw)
            tot += sum(sum(w[j]) for w in weeks_by_strat.values())
        res.append(tot)
    res.sort()
    q = lambda x: res[int(x * (n - 1))]
    return {'p5': q(.05), 'p25': q(.25), 'med': q(.5), 'p75': q(.75), 'p95': q(.95), 'neg': 100 * sum(r < 0 for r in res) / n,
            'hit8': 100 * sum(r * 1.5 >= 8 for r in res) / n}


if __name__ == '__main__':
    books = load_books()
    for wname, t0 in WINDOWS.items():
        months = (END - t0) / D / 30.44
        print('\n================ %s (%.1f months) ================' % (wname, months))
        print('%-30s %6s %6s %6s %7s %8s' % ('strategy', 'trades', '/month', 'win', 'avg R', 'R/month'))
        wbs = {}
        for name, tl in books.items():
            xs = [t for t in tl if t0 <= t['t_in'] < END]
            rs = [t['r'] for t in xs]
            if rs:
                print('%-30s %6d %6.1f %5.0f%% %+7.2f %+8.2f' % (name, len(rs), len(rs) / months, 100 * sum(r > 0 for r in rs) / len(rs),
                      statistics.mean(rs), sum(rs) / months))
            wbs[name] = weekly(xs, t0)
        for scope, sel in [(n, {n: wbs[n]}) for n in wbs] + [('ALL COMBINED', wbs)]:
            print('\n  %s' % scope)
            print('   %-9s | %-44s | %-38s | %5s %6s' % ('horizon', 'R:  worst5%   p25   median   p75   best5%', 'eval $ @1.5% (750/R): worst5 / median / best5',
                  'P<0', 'P+8%'))
            for mo in (1, 3, 6):
                r = mc(sel, mo)
                print('   %-9s | %+8.1f %+6.1f %+8.1f %+6.1f %+8.1f   | %+8.0f / %+8.0f / %+8.0f   | %4.0f%% %5.0f%%' % (
                    '%d month%s' % (mo, 's' if mo > 1 else ''), r['p5'], r['p25'], r['med'], r['p75'], r['p95'],
                    750 * r['p5'], 750 * r['med'], 750 * r['p95'], r['neg'], r['hit8']))
            r = mc(sel, 1)
            print('   funded 1%% risk, per month, trader 80%%: worst5 $%+.0f / median $%+.0f / best5 $%+.0f' % (
                400 * r['p5'], 400 * r['med'], 400 * r['p95']))
