"""User strategy "BB13 + key level": with-bias fade of the 4h Bollinger band extreme at a key level, 1h reversal entry.

RULE (bearish bias shown; bullish mirrored):
  Bias: coin's DAILY EMA20 < EMA50 (completed days)   [bias='daily']; or BTC 4h EMA50/200 [bias='btc']; or both.
  Setup candle (4h, completed): high >= upper Bollinger band (13 SMA, 2 st.dev, incl. this candle) AND the same candle
    trades above a KEY LEVEL to its left: an unswept 4h swing high (fractal, 3 candles each side, confirmed before the
    setup candle, within the last 30 days, not traded through since).  [key='sr']: the swing high must be part of a
    cluster (another swing high/low within 0.3 ATR in the window) = support/resistance.  [key='none']: no level needed.
  Trigger (1h, within W hours after the setup candle closes): a bearish reversal candle -
    engulf: red body engulfing the previous green body | pin: upper wick >= 2x body and close in the lower 40% |
    ifvg: a 1h bullish FVG from the last 6 bars closed below. [pat] picks which count. Disarm if price closes above
    the setup candle's high.
  Entry: market at the next 1h open. Stop: highest high since the setup candle + buf x ATR(4h).
  Target: after-fee tgt R, or 'mid' = the band's middle (13 SMA of the setup candle) if >= 1R.
EXECUTION: house rules (1h bars, stop first, no target on the entry bar, 0.04%/side, weekend: no entries in the pause,
  flat at Sat 04:00 SGT, max hold 48h, one position per coin)."""
import sys, statistics, collections, bisect
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps
from ifvg_lab import START, SPLIT, SCH, load, report, REG, H, H4, D, FRT
COINS = ['SUI', 'UNI', 'BTC', 'ETH', 'SOL', 'NEAR', 'ADA', 'LINK', 'HYPE']
OTHER = ['BNB', 'XRP', 'ZEC']
_daily = {}


def daily_bias(sym):
    if sym not in _daily:
        days = collections.OrderedDict()
        for b in load(sym, '4h'):
            days.setdefault(b[0] // D, []).append(b)
        keys = [k for k, v in days.items() if len(v) == 6]
        c = [days[k][-1][4] for k in keys]
        e20, e50 = perps.ema(c, 20), perps.ema(c, 50)
        _daily[sym] = ([(k + 1) * D for k in keys], e20, e50)
    return _daily[sym]


def bias_at(sym, t):
    ts, e20, e50 = daily_bias(sym)
    k = bisect.bisect_right(ts, t) - 1
    if k < 50:
        return 0
    return 1 if e20[k] > e50[k] else -1


def run(sym, bias='daily', key='swing', pat=('engulf', 'pin', 'ifvg'), W=8, buf=0.25, tgt=1.5, n_bb=13, k_bb=2.0,
        look=180, frac=3, hold=48, sides=(1, -1)):
    b4 = load(sym, '4h'); b1 = load(sym, '1h')
    if len(b4) < 400:
        return []
    i1 = {x[0]: n for n, x in enumerate(b1)}
    c = [x[4] for x in b4]; hi = [x[2] for x in b4]; lo = [x[3] for x in b4]
    atr = perps.atr(hi, lo, c, 14)
    ph = [i for i in range(frac, len(b4) - frac) if hi[i] > max(hi[i - frac:i]) and hi[i] > max(hi[i + 1:i + 1 + frac])]
    pl = [i for i in range(frac, len(b4) - frac) if lo[i] < min(lo[i - frac:i]) and lo[i] < min(lo[i + 1:i + 1 + frac])]
    out = []; busy = 0
    for i in range(max(60, n_bb), len(b4) - 1):
        T = b4[i][0] + H4
        if T < START or T < busy or atr[i] is None:
            continue
        w = c[i - n_bb + 1:i + 1]; m = sum(w) / n_bb; sd = statistics.pstdev(w)
        up, dn = m + k_bb * sd, m - k_bb * sd
        a = atr[i]
        for side in sides:
            if side == -1 and hi[i] < up or side == 1 and lo[i] > dn:
                continue
            if bias in ('daily', 'both') and bias_at(sym, T) != side:
                continue
            if bias in ('btc', 'both'):
                r = REG.get(b4[i][0])
                if r is None or (r > 0) != (side == 1):
                    continue
            if key != 'none':
                piv = ph if side == -1 else pl
                lv = []
                for p in piv[bisect.bisect_left(piv, i - look):]:
                    if p + frac > i - 1:
                        break
                    px = hi[p] if side == -1 else lo[p]
                    seg = hi[p + 1:i] if side == -1 else lo[p + 1:i]
                    taken = (max(seg) >= px) if side == -1 else (min(seg) <= px)
                    crossed = hi[i] > px if side == -1 else lo[i] < px
                    if not taken and crossed:
                        lv.append((p, px))
                if key == 'sr':
                    others = [hi[q] for q in ph if i - look <= q <= i - 1 - frac] + [lo[q] for q in pl if i - look <= q <= i - 1 - frac]
                    lv = [(p, px) for p, px in lv if sum(abs(o - px) <= 0.3 * a for o in others) >= 2]
                if not lv:
                    continue
            n0 = i1.get(T)
            if n0 is None:
                continue
            ext = hi[i] if side == -1 else lo[i]
            sig = None
            for q in range(n0, min(len(b1) - 1, n0 + W)):
                o, h, l, cl = b1[q][1], b1[q][2], b1[q][3], b1[q][4]
                ext = max(ext, h) if side == -1 else min(ext, l)
                if (side == -1 and cl > hi[i]) or (side == 1 and cl < lo[i]):
                    break
                po, pc = b1[q - 1][1], b1[q - 1][4]
                body = abs(cl - o); rng = h - l
                ok = False
                if 'engulf' in pat:
                    if side == -1 and cl < o and pc > po and cl <= po and o >= pc:
                        ok = True
                    if side == 1 and cl > o and pc < po and cl >= po and o <= pc:
                        ok = True
                if 'pin' in pat and rng > 0:
                    if side == -1 and h - max(o, cl) >= 2 * body and (h - cl) >= 0.6 * rng:
                        ok = True
                    if side == 1 and min(o, cl) - l >= 2 * body and (cl - l) >= 0.6 * rng:
                        ok = True
                if 'ifvg' in pat:
                    for j in range(q - 5, q):
                        if side == -1 and b1[j][3] > b1[j - 2][2] and cl < b1[j - 2][2] and b1[q - 1][4] >= b1[j - 2][2]:
                            ok = True
                        if side == 1 and b1[j][2] < b1[j - 2][3] and cl > b1[j - 2][3] and b1[q - 1][4] <= b1[j - 2][3]:
                            ok = True
                if ok:
                    sig = q; break
            if sig is None:
                continue
            n = sig + 1
            if perps.in_weekend(b1[n][0], SCH):
                continue
            e = b1[n][1]
            stp = ext - side * buf * a
            d = abs(e - stp)
            if (stp - e) * side >= 0 or d / e < 0.002:
                continue
            if tgt == 'mid':
                tp = m
                if (tp - e) * side / d < 1.0:
                    continue
            else:
                tp = e + side * (tgt * (d + FRT * e) + FRT * e)
            flat = perps.next_weekend_stop(b1[n][0], SCH)
            px = why = None
            for q in range(n, min(len(b1), n + hold)):
                o, hh, ll = b1[q][1], b1[q][2], b1[q][3]
                if b1[q][0] >= flat:
                    px, why = o, 'weekend'; break
                if (side == 1 and ll <= stp) or (side == -1 and hh >= stp):
                    px = (min(o, stp) if side == 1 else max(o, stp)); why = 'stop'; break
                if q > n and ((side == 1 and hh >= tp) or (side == -1 and ll <= tp)):
                    px, why = tp, 'target'; break
            if px is None:
                px, why = b1[q][4], 'time'
            out.append({'sym': sym, 'side': side, 't_in': b1[n][0], 't_out': b1[q][0] + H, 'exit': why, 'e': e, 'stp': stp,
                        'r': (side * (px - e) / e - FRT) / (d / e + FRT), 'stop_frac': d / e})
            busy = b1[q][0] + H
            break
    return out


def book(syms=COINS, **kw):
    return sorted([t for s in syms for t in run(s, **kw)], key=lambda t: t['t_in'])


if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'base'
    if what == 'base':
        tl = book(); report(tl, 'BB13 base (daily bias, swing level, any pattern)')
        for s in COINS:
            report([t for t in tl if t['sym'] == s], '  ' + s)
        report(book(OTHER), 'BB13 base other 3 coins')
        print('exits', collections.Counter(t['exit'] for t in tl), 'median stop %.2f%%' % (100 * statistics.median(t['stop_frac'] for t in tl)))
    else:
        for kw in (dict(key='none'), dict(key='sr'), dict(bias='none'), dict(bias='btc'), dict(bias='both'),
                   dict(pat=('engulf',)), dict(pat=('pin',)), dict(pat=('ifvg',)), dict(tgt=1.0), dict(tgt=2.0),
                   dict(tgt='mid'), dict(buf=0.1), dict(buf=0.5), dict(W=4), dict(W=16), dict(n_bb=20),
                   dict(k_bb=2.5), dict(frac=5), dict(look=90)):
            report(book(**kw), str(kw))
