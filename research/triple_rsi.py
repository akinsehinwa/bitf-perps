"""Triple RSI (QuantifiedStrategies, user idea 2026-11-21) on all 72 Bitfunded crypto perps.

As published (daily, long only): RSI(5) < 30, RSI(5) down 3 days in a row, RSI(5) 3 days ago < 60, close > SMA(200)
-> buy at the close; sell at the close when RSI(5) crosses above 50. No stop.
Daily bars = UTC days built from cached 4h perp candles (fees 0.04%/side). Variants:
  stop k:  protective stop k x ATR(14) below entry (checked on daily lows, stop first), used for R and sizing
  time n:  also exit after n days
  short:   mirror (RSI > 70 rising 3 days, RSI 3 days ago > 40, close < SMA200; exit when RSI < 50)
  4h:      same rules on 4h bars (SMA200 = ~33 days)
Report: last 12 months and the 2 years before (house standard); win rate, avg % per trade, avg R (with a stop),
avg days held, worst intratrade drawdown (MAE) in % and in ATR - what a stop would have to survive."""
import sys, statistics, collections
sys.path.insert(0, '/home/user/bitfunded-perps'); import perps
D = 86_400_000; H4 = 4 * 3600_000; FRT = 0.0008
END = int(perps.dt.datetime(2026, 11, 20, tzinfo=perps.UTC).timestamp() * 1000); T12 = END - 365 * D
mk = perps.load_markets(); CR = [k for k, v in mk.items() if v['type'] == 'crypto' and v.get('binance')]


def bars(sym, tf):
    b4 = perps.load_json(perps.cache_file(sym, '4h'), [])
    if tf == '4h':
        return [x[:5] for x in b4]
    days = collections.OrderedDict()
    for x in b4:
        days.setdefault(x[0] // D, []).append(x)
    return [[k * D, v[0][1], max(y[2] for y in v), min(y[3] for y in v), v[-1][4]] for k, v in days.items() if len(v) == 6]


def rsi(c, n=5):
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


def run(sym, tf='1d', side=1, stop_k=None, time_n=None):
    b = bars(sym, tf)
    if len(b) < 260:
        return []
    o = [x[1] for x in b]; h = [x[2] for x in b]; l = [x[3] for x in b]; c = [x[4] for x in b]
    r = rsi(c); at = perps.atr(h, l, c, 14)
    step = D if tf == '1d' else H4
    out = []; i = 205
    while i < len(b) - 1:
        if None in (r[i], r[i - 3], at[i]):
            i += 1; continue
        sma = sum(c[i - 199:i + 1]) / 200
        if side == 1:
            sig = r[i] < 30 and r[i] < r[i - 1] < r[i - 2] < r[i - 3] and r[i - 3] < 60 and c[i] > sma
        else:
            sig = r[i] > 70 and r[i] > r[i - 1] > r[i - 2] > r[i - 3] and r[i - 3] > 40 and c[i] < sma
        if not sig:
            i += 1; continue
        e = c[i]; a = at[i]; stp = e - side * stop_k * a if stop_k else None
        worst = e; px = None; j = i
        for j in range(i + 1, len(b)):
            worst = min(worst, l[j]) if side == 1 else max(worst, h[j])
            if stp is not None and ((side == 1 and l[j] <= stp) or (side == -1 and h[j] >= stp)):
                px = min(o[j], stp) if side == 1 else max(o[j], stp); why = 'stop'; break
            if (side == 1 and r[j] > 50) or (side == -1 and r[j] < 50):
                px = c[j]; why = 'rsi'; break
            if time_n and j - i >= time_n:
                px = c[j]; why = 'time'; break
        if px is None:
            break
        ret = side * (px - e) / e - FRT
        d = (stop_k * a / e) if stop_k else None
        out.append({'sym': sym, 't': b[i][0] + step, 'ret': ret, 'r': (ret / (d + FRT)) if d else None, 'days': (j - i) * step / D,
                    'mae': side * (worst - e) / e, 'mae_atr': side * (worst - e) / a, 'why': why})
        i = j + 1
    return out


def rep(label, tl):
    for per, sel in (('12m', lambda t: t['t'] >= T12), ('2y ', lambda t: t['t'] < T12)):
        xs = [t for t in tl if sel(t)]
        if not xs:
            print('  %-44s %s: none' % (label, per)); continue
        rs = [t['r'] for t in xs if t['r'] is not None]
        print('  %-44s %s: n %4d (%4.1f/mo) win %3.0f%% avg %+.2f%% %s held %4.1fd | worst MAE %5.1f%% (%4.1f ATR), 10%% worst %5.1f%%' % (
            label, per, len(xs), len(xs) / (12 if per == '12m' else 24), 100 * sum(t['ret'] > 0 for t in xs) / len(xs),
            100 * statistics.mean(t['ret'] for t in xs), ('avg %+.2fR' % statistics.mean(rs)) if rs else '          ',
            statistics.mean(t['days'] for t in xs), 100 * min(t['mae'] for t in xs), min(t['mae_atr'] for t in xs),
            100 * sorted(t['mae'] for t in xs)[len(xs) // 10]), flush=True)


if __name__ == '__main__':
    CORE = ['BTC', 'ETH', 'BNB', 'XRP', 'SOL', 'ADA', 'UNI', 'LINK', 'AVAX', 'LTC']
    for label, kw in (('AS PUBLISHED (daily, long, no stop)', {}),
                      ('daily long, stop 2 ATR', dict(stop_k=2.0)), ('daily long, stop 3 ATR', dict(stop_k=3.0)),
                      ('daily long, stop 3 ATR, max 10 days', dict(stop_k=3.0, time_n=10)),
                      ('daily SHORT mirror, stop 3 ATR', dict(side=-1, stop_k=3.0)),
                      ('4h long, stop 3 ATR', dict(tf='4h', stop_k=3.0)), ('4h SHORT mirror, stop 3 ATR', dict(tf='4h', side=-1, stop_k=3.0))):
        tl = [t for s in CR for t in run(s, **kw)]
        print('\n== %s' % label)
        rep('all 72 coins', tl)
        rep('core 10', [t for t in tl if t['sym'] in CORE])
