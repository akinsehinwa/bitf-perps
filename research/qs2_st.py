"""SuperTrend follow-up: both directions, BTC trend filter, Bitfunded max-hold cap (7 days), hold-time stats."""
import sys, statistics
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import qs2, perps
D = qs2.D


def run(sym, m=3.0, cap=None, filt=None, tf='1d', roll=False):
    b = qs2.bars(sym, tf)
    if len(b) < 60:
        return []
    o = [x[1] for x in b]; h = [x[2] for x in b]; l = [x[3] for x in b]; c = [x[4] for x in b]
    st, up = qs2.supertrend(h, l, c, 10, m)
    bb = qs2.bars('BTC', tf); bst, bup = qs2.supertrend([x[2] for x in bb], [x[3] for x in bb], [x[4] for x in bb], 10, 3.0)
    bdir = {bb[i][0]: bup[i] for i in range(len(bb))}
    step = D if tf == '1d' else qs2.H4
    out = []; i = 30
    while i < len(b) - 1:
        if up[i] is None or up[i - 1] is None or up[i] == up[i - 1]:
            i += 1; continue
        side = up[i]
        if filt == 'btc' and bdir.get(b[i][0]) != side:
            i += 1; continue
        e = c[i]; risk = abs(e - st[i]); px = None
        if risk / e < 0.002:
            i += 1; continue
        for j in range(i + 1, len(b)):
            if (side == 1 and l[j] <= st[j - 1]) or (side == -1 and h[j] >= st[j - 1]):
                px = (min(o[j], st[j - 1]) if side == 1 else max(o[j], st[j - 1])); break
            if cap and (j - i) * step >= cap * D:
                px = c[j]; break
        if px is None:
            break
        ret = side * (px - e) / e - qs2.FRT
        out.append({'sym': sym, 't': b[i][0] + step, 'ret': ret, 'r': ret / (risk / e + qs2.FRT), 'days': (j - i) * step / D})
        if roll and cap and up[j] == side and (j - i) * step >= cap * D and not ((side == 1 and l[j] <= st[j - 1]) or (side == -1 and h[j] >= st[j - 1])):
            i = j; up[i - 1] = -side                     # re-open at this close: treat as a fresh entry
            continue
        i = j
    return out


for label, kw in (('daily (10,3) both, BTC agrees, 7-day cap + ROLL', dict(cap=7, filt='btc', roll=True)),
                  ('daily (10,2) both, BTC agrees, 7-day cap + ROLL', dict(m=2.0, cap=7, filt='btc', roll=True)),
                  ('daily (10,2.5) both, BTC agrees, 7-day cap + ROLL', dict(m=2.5, cap=7, filt='btc', roll=True)),
                  ('daily (10,2.5) both, BTC agrees, 7-day cap', dict(m=2.5, cap=7, filt='btc'))):
    tl = [t for s in qs2.CR for t in run(s, **kw)]
    print('== ' + label)
    qs2.rep('all 72', tl); qs2.rep('core 10', [t for t in tl if t['sym'] in qs2.CORE])
    ds = sorted(t['days'] for t in tl)
    print('     hold days: median %.1f, 75%% %.1f, 90%% %.1f, max %.0f' % (ds[len(ds) // 2], ds[3 * len(ds) // 4], ds[9 * len(ds) // 10], ds[-1]), flush=True)
