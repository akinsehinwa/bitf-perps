"""Does v2 work only in 'healthy' daily trends? Label each trade by the DAILY chart before entry (completed UTC days only).
  ER = Kaufman efficiency ratio over N days = |net move| / sum of |daily moves|  (1 = straight line 'knife', ~0 = chop)
  aligned = the N-day net move points the same way as the trade
  buckets: chop ER<0.2 | healthy trend 0.2<=ER<0.45 aligned | knife ER>=0.45 aligned | counter-trend (ER>=0.2, against)
Also: daily EMA20 vs EMA50 agreement with the trade side."""
import sys, statistics, bisect, collections
sys.path.insert(0, '/home/user/bitf-perps/research')
import ifvg2 as V, perps
from ifvg_lab import load, report, D, H4
_d = {}


def daily(sym):
    if sym not in _d:
        days = collections.OrderedDict()
        for b in load(sym, '4h'):
            days.setdefault(b[0] // D, []).append(b)
        keys = [k for k, v in days.items() if len(v) == 6]
        c = [days[k][-1][4] for k in keys]
        e20, e50 = perps.ema(c, 20), perps.ema(c, 50)
        _d[sym] = ([(k + 1) * D for k in keys], c, e20, e50)
    return _d[sym]


def label(t, N=20, lo=0.2, hi=0.45):
    ts, c, e20, e50 = daily(t['sym'])
    k = bisect.bisect_right(ts, t['t_in']) - 1          # last day completed before entry
    if k < N + 50:
        return None, None
    net = c[k] - c[k - N]; path = sum(abs(c[j] - c[j - 1]) for j in range(k - N + 1, k + 1))
    er = abs(net) / path if path else 0
    al = (net > 0) == (t['side'] == 1)
    b = 'chop' if er < lo else ('counter-trend' if not al else ('healthy trend' if er < hi else 'knife'))
    ema_ok = (e20[k] > e50[k]) == (t['side'] == 1)
    return b, ema_ok


if __name__ == '__main__':
    for name, kw in (('v2 base (legs>=3 ATR)', {}), ('v2 legs>=6 ATR', dict(G=6.0))):
        tl = V.book(**kw)
        print('\n==', name)
        for N, lo, hi in ((20, 0.2, 0.45), (10, 0.25, 0.5), (30, 0.15, 0.4)):
            lab = [(t, *label(t, N, lo, hi)) for t in tl]
            print(' -- daily ER over %d days (chop <%.2f, knife >=%.2f)' % (N, lo, hi))
            for b in ('healthy trend', 'knife', 'chop', 'counter-trend'):
                report([t for t, x, _ in lab if x == b], '   ' + b)
        lab = [(t, *label(t)) for t in tl]
        report([t for t, _, e in lab if e], ' daily EMA20/50 agrees')
        report([t for t, _, e in lab if e is False], ' daily EMA20/50 disagrees')
        report([t for t, b, e in lab if b == 'healthy trend' and e], ' healthy trend + EMA agrees')
