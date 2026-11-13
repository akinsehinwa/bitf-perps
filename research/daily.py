"""Daily-bias diagnostics and gates (no look-ahead: only daily candles closed before the signal).
Daily candles = UTC days (08:00 SGT open) built from 4h bars. Biases, +1 / -1 / 0:
  ema     : EMA20 > EMA50 (bull) / < (bear)
  strict  : EMA20 > EMA50 and close > EMA20 (bull); mirror for bear; else 0 (no clear trend)
  crt     : the Trading Floor CRT carry-forward bias (close outside prior range or one-sided sweep)
  hl      : daily structure - last close above the prior day's high (bull) / below its low (bear), carried"""
import sys, collections
sys.path.insert(0, '/home/user/bitfunded-perps')
import perps
D = 86_400_000
_cache = {}


def daily(sym):
    if sym in _cache:
        return _cache[sym]
    days = collections.OrderedDict()
    for b in perps.load_json(perps.cache_file(sym, '4h'), []):
        k = b[0] // D
        d = days.get(k)
        if d is None:
            days[k] = [k * D, b[1], b[2], b[3], b[4], 1]
        else:
            d[2] = max(d[2], b[2]); d[3] = min(d[3], b[3]); d[4] = b[4]; d[5] += 1
    rows = [d for d in days.values() if d[5] == 6]
    c = [r[4] for r in rows]
    e20, e50 = perps.ema(c, 20), perps.ema(c, 50)
    out = {}
    crt = hl = 0
    for i, r in enumerate(rows):
        close_ms = r[0] + D
        ema = strict = 0
        if e20[i] is not None and e50[i] is not None:
            ema = 1 if e20[i] > e50[i] else -1
            strict = 1 if (e20[i] > e50[i] and c[i] > e20[i]) else -1 if (e20[i] < e50[i] and c[i] < e20[i]) else 0
        if i > 0:
            ph, pl = rows[i - 1][2], rows[i - 1][3]
            if c[i] > ph:
                crt = hl = 1
            elif c[i] < pl:
                crt = hl = -1
            elif r[2] > ph and r[3] >= pl:
                crt = -1
            elif r[3] < pl and r[2] <= ph:
                crt = 1
        out[close_ms] = {'ema': ema, 'strict': strict, 'crt': crt, 'hl': hl}
    keys = sorted(out)
    _cache[sym] = (keys, out)
    return _cache[sym]


def bias(sym, t_ms, mode='strict'):
    import bisect
    keys, out = daily(sym)
    k = bisect.bisect_right(keys, t_ms) - 1
    if k < 0 or t_ms - keys[k] > 2 * D:
        return None
    return out[keys[k]][mode]


def breakdown(trades, label, side_key='side'):
    """Average R by daily alignment, for the coin's own daily trend and for BTC's."""
    rows = []
    for who in ('coin', 'BTC'):
        for mode in ('ema', 'strict', 'crt'):
            g = collections.defaultdict(list)
            for t in trades:
                s = t[side_key]
                s = 1 if s in (1, 'long') else -1
                b = bias(t['sym'] if who == 'coin' else 'BTC', t['t_in'], mode)
                key = 'none' if not b else ('with' if b == s else 'against')
                g[key].append(t['r'])
            cell = '  '.join('%s %+.2fR n=%d' % (k, sum(v) / len(v), len(v)) for k, v in sorted(g.items()))
            rows.append('    %-4s daily %-6s: %s' % (who, mode, cell))
    print(label); print('\n'.join(rows))
