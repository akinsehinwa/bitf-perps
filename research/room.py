"""Setup grading by 'running room': distance from the entry to the next opposing structure, in R.
Structure = nearest untouched 4h swing high above a long (swing low below a short): fractal (frac bars each side),
confirmed before the entry, not traded through since, within the last 90 days. Daily-swing version too.
None found = clear air (price at/through all recent structure). Buckets: blocked < 1.5R | 1.5-3R | >= 3R | clear air."""
import sys, bisect, statistics, pickle, collections
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps
from ifvg_lab import load, report, H4, D
T = pickle.load(open('/tmp/claude-0/-home-user-bitf-perps/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad/manage_trades.pkl', 'rb'))
_p = {}


def pivots(sym, tf, frac):
    key = (sym, tf, frac)
    if key not in _p:
        b = load(sym, '4h')
        if tf == '1d':
            days = collections.OrderedDict()
            for x in b:
                days.setdefault(x[0] // D, []).append(x)
            b = [[k * D, v[0][1], max(y[2] for y in v), min(y[3] for y in v), v[-1][4]] for k, v in days.items() if len(v) == 6]
        step = D if tf == '1d' else H4
        hi = [x[2] for x in b]; lo = [x[3] for x in b]; t = [x[0] for x in b]
        ph = [(t[i + frac] + step, t[i], hi[i]) for i in range(frac, len(b) - frac) if hi[i] > max(hi[i - frac:i]) and hi[i] > max(hi[i + 1:i + 1 + frac])]
        pl = [(t[i + frac] + step, t[i], lo[i]) for i in range(frac, len(b) - frac) if lo[i] < min(lo[i - frac:i]) and lo[i] < min(lo[i + 1:i + 1 + frac])]
        _p[key] = (b, t, hi, lo, ph, pl)
    return _p[key]


def room(tr, tf='4h', frac=3, look=90 * D):
    b, t, hi, lo, ph, pl = pivots(tr['sym'], tf, frac)
    e, stp, s = tr['e'], tr['stp'], tr['side']; risk = abs(e - stp)
    k = bisect.bisect_left(t, tr['t_in'])                 # bars before entry are [0, k)
    best = None
    for conf, tp, px in (ph if s == 1 else pl):
        if conf > tr['t_in'] or tp < tr['t_in'] - look:
            continue
        if (px - e) * s <= 0:
            continue
        j = bisect.bisect_right(t, tp)
        seg = hi[j:k] if s == 1 else lo[j:k]
        if seg and ((max(seg) >= px) if s == 1 else (min(seg) <= px)):
            continue                                       # already taken out
        dist = (px - e) * s / risk
        best = dist if best is None else min(best, dist)
    return best


def bucket(r):
    return 'clear air' if r is None else ('blocked <1.5R' if r < 1.5 else ('1.5-3R' if r < 3 else '>=3R'))


if __name__ == '__main__':
    for tf, frac in (('4h', 3), ('1d', 2)):
        print('\n######## structure = %s swings (fractal %d)' % (tf, frac))
        allt = []
        for name in ('Q', 'CRT'):
            tl = T[name]; lab = [(t, bucket(room(t, tf, frac))) for t in tl]
            allt += lab
            print('-- %s' % name)
            for bk in ('blocked <1.5R', '1.5-3R', '>=3R', 'clear air'):
                report([t for t, b in lab if b == bk], '   ' + bk)
        print('-- Q + CRT')
        for bk in ('blocked <1.5R', '1.5-3R', '>=3R', 'clear air'):
            report([t for t, b in allt if b == bk], '   ' + bk)
