"""Two QuantifiedStrategies posts (user 2026-11-21) on all 72 Bitfunded crypto perps.

A) RSI + EMA + rolling VWAP pullback (QQQ daily; settings not published -> standard ones, plus neighbours):
   long when RSI(n) < lo, close > EMA200, EMA50 rising (vs 5 bars ago), close < rolling VWAP(20) - k x ATR(14);
   buy at the close; exit at the close when RSI(n) > 50 or close > VWAP; protective stop s x ATR (for prop sizing).
B) SuperTrend (ATR 10, x3): long when the close crosses above the prior SuperTrend, exit when it crosses below;
   short mirror; 'close' exit (as published) or 'stop' = the SuperTrend line as a trailing stop hit intrabar.
   R = result / initial risk (entry -> SuperTrend at entry).
Bars: UTC daily built from cached 4h perp candles, or 4h. Fees 0.04%/side. House standard: last 12 months, then the
2 years before."""
import sys, statistics, collections
sys.path.insert(0, '/home/user/bitfunded-perps'); import perps
D = 86_400_000; H4 = 4 * 3600_000; FRT = 0.0008
END = int(perps.dt.datetime(2026, 11, 20, tzinfo=perps.UTC).timestamp() * 1000); T12 = END - 365 * D
mk = perps.load_markets(); CR = [k for k, v in mk.items() if v['type'] == 'crypto' and v.get('binance')]
CORE = ['BTC', 'ETH', 'BNB', 'XRP', 'SOL', 'ADA', 'UNI', 'LINK', 'AVAX', 'LTC']
_c = {}


def bars(sym, tf):
    if (sym, tf) not in _c:
        b4 = perps.load_json(perps.cache_file(sym, '4h'), [])
        if tf == '4h':
            b = [x[:6] for x in b4]
        else:
            days = collections.OrderedDict()
            for x in b4:
                days.setdefault(x[0] // D, []).append(x)
            b = [[k * D, v[0][1], max(y[2] for y in v), min(y[3] for y in v), v[-1][4], sum(y[5] for y in v)]
                 for k, v in days.items() if len(v) == 6]
        _c[(sym, tf)] = b
    return _c[(sym, tf)]


def rsi(c, n):
    out = [None] * len(c); g = l = 0.0
    for i in range(1, len(c)):
        ch = c[i] - c[i - 1]; up, dn = max(ch, 0), max(-ch, 0)
        if i <= n:
            g += up / n; l += dn / n
            if i == n:
                out[i] = 100 - 100 / (1 + g / l) if l else 100
        else:
            g = (g * (n - 1) + up) / n; l = (l * (n - 1) + dn) / n
            out[i] = 100 - 100 / (1 + g / l) if l else 100
    return out


def pullback(sym, tf='1d', n=5, lo=30, k=1.0, stop=2.5):
    b = bars(sym, tf)
    if len(b) < 260:
        return []
    o = [x[1] for x in b]; h = [x[2] for x in b]; l = [x[3] for x in b]; c = [x[4] for x in b]; v = [x[5] for x in b]
    r = rsi(c, n); at = perps.atr(h, l, c, 14); e50 = perps.ema(c, 50); e200 = perps.ema(c, 200)
    tp = [(h[i] + l[i] + c[i]) / 3 for i in range(len(b))]
    out = []; i = 210; step = D if tf == '1d' else H4
    while i < len(b) - 1:
        if None in (r[i], at[i], e200[i], e50[i - 5]):
            i += 1; continue
        vw = sum(tp[j] * v[j] for j in range(i - 19, i + 1)) / max(1e-9, sum(v[i - 19:i + 1]))
        if not (r[i] < lo and c[i] > e200[i] and e50[i] > e50[i - 5] and c[i] < vw - k * at[i]):
            i += 1; continue
        e = c[i]; a = at[i]; stp = e - stop * a; px = None
        for j in range(i + 1, len(b)):
            if l[j] <= stp:
                px = min(o[j], stp); break
            vwj = sum(tp[q] * v[q] for q in range(j - 19, j + 1)) / max(1e-9, sum(v[j - 19:j + 1]))
            if r[j] > 50 or c[j] > vwj:
                px = c[j]; break
        if px is None:
            break
        ret = (px - e) / e - FRT
        out.append({'sym': sym, 't': b[i][0] + step, 'ret': ret, 'r': ret / (stop * a / e + FRT)})
        i = j + 1
    return out


def supertrend(h, l, c, n=10, m=3.0):
    at = perps.atr(h, l, c, n); st = [None] * len(c); up = [None] * len(c)
    fu = fl = None; trend = 1
    for i in range(len(c)):
        if at[i] is None:
            continue
        hl2 = (h[i] + l[i]) / 2; bu = hl2 + m * at[i]; bl = hl2 - m * at[i]
        fu = bu if fu is None or bu < fu or c[i - 1] > fu else fu
        fl = bl if fl is None or bl > fl or c[i - 1] < fl else fl
        if trend == 1 and c[i] < fl:
            trend = -1
        elif trend == -1 and c[i] > fu:
            trend = 1
        st[i] = fl if trend == 1 else fu; up[i] = trend
    return st, up


def st_run(sym, tf='1d', side=1, exitmode='close', n=10, m=3.0):
    b = bars(sym, tf)
    if len(b) < 60:
        return []
    o = [x[1] for x in b]; h = [x[2] for x in b]; l = [x[3] for x in b]; c = [x[4] for x in b]
    st, up = supertrend(h, l, c, n, m)
    out = []; i = 30; step = D if tf == '1d' else H4
    while i < len(b) - 1:
        if up[i] is None or up[i - 1] is None or up[i] == up[i - 1] or up[i] != side:
            i += 1; continue
        e = c[i]; risk = abs(e - st[i]); px = None
        if risk / e < 0.002:
            i += 1; continue
        for j in range(i + 1, len(b)):
            if exitmode == 'stop' and ((side == 1 and l[j] <= st[j - 1]) or (side == -1 and h[j] >= st[j - 1])):
                px = (min(o[j], st[j - 1]) if side == 1 else max(o[j], st[j - 1])); break
            if up[j] != side:
                px = c[j]; break
        if px is None:
            break
        ret = side * (px - e) / e - FRT
        out.append({'sym': sym, 't': b[i][0] + step, 'ret': ret, 'r': ret / (risk / e + FRT)})
        i = j
    return out


def rep(label, tl):
    for per, sel in (('12m', lambda t: t['t'] >= T12), ('2y ', lambda t: t['t'] < T12)):
        xs = [t for t in tl if sel(t)]
        if not xs:
            print('  %-50s %s: none' % (label, per)); continue
        rs = sorted(t['r'] for t in xs)
        print('  %-50s %s: n %4d (%5.1f/mo) win %3.0f%% avg %+6.2f%% avg %+.2fR | worst %+.1fR, 10%% worst %+.2fR' % (
            label, per, len(xs), len(xs) / (12 if per == '12m' else 24), 100 * sum(t['ret'] > 0 for t in xs) / len(xs),
            100 * statistics.mean(t['ret'] for t in xs), statistics.mean(rs), rs[0], rs[len(rs) // 10]), flush=True)


if __name__ == '__main__':
    print('######## A) RSI + EMA + rolling VWAP pullback (long)')
    for label, kw in (('daily RSI5<30, 1 ATR below VWAP, stop 2.5 ATR', {}), ('daily RSI5<20', dict(lo=20)),
                      ('daily RSI2<10', dict(n=2, lo=10)), ('daily 0.5 ATR below VWAP', dict(k=0.5)),
                      ('daily 2 ATR below VWAP', dict(k=2.0)), ('daily stop 4 ATR', dict(stop=4.0)),
                      ('4h RSI5<30, 1 ATR below VWAP', dict(tf='4h'))):
        tl = [t for s in CR for t in pullback(s, **kw)]
        print('== ' + label); rep('all 72', tl); rep('core 10', [t for t in tl if t['sym'] in CORE])
    print('\n######## B) SuperTrend (10, 3)')
    for label, kw in (('daily LONG, close exit (as published)', {}), ('daily LONG, trailing stop on the line', dict(exitmode='stop')),
                      ('daily SHORT, close exit', dict(side=-1)), ('daily SHORT, trailing stop', dict(side=-1, exitmode='stop')),
                      ('4h LONG, trailing stop', dict(tf='4h', exitmode='stop')), ('4h SHORT, trailing stop', dict(tf='4h', side=-1, exitmode='stop')),
                      ('daily LONG (10,2), trailing stop', dict(m=2.0, exitmode='stop')), ('daily LONG (10,4), trailing stop', dict(m=4.0, exitmode='stop'))):
        tl = [t for s in CR for t in st_run(s, **kw)]
        print('== ' + label); rep('all 72', tl); rep('core 10', [t for t in tl if t['sym'] in CORE])
