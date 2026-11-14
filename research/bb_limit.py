"""BB extreme + key level as a SET-AND-FORGET limit order (user places it at a 4h check-in; no 1h watching).

Setup (bearish shown, bullish mirrored), on the completed 4h candle i:
  bias: 4h close below a falling EMA50 (6-bar slope); candle high >= upper band (n_bb SMA, 2 sd, incl. candle i);
  key level: the candle's range spans a 4h horizontal S/R (>= 3 confirmed fractal-3 swing points within tol x ATR,
  last 90 days) [key='none' skips]; confirm (4h only): 'none' | 'red' candle closes bearish | 'reject' closes back
  below the level it swept and below the upper band.
Ticket at the first check-in (SGT hours CHK) at/after the candle close, skipped if the stop already traded:
  SELL LIMIT at  'close+k': candle close + k x ATR  |  'wick': close + 50% of the upper wick  |  'level': the S/R level
  STOP: candle high + buf x ATR (moved up to the highest high before placement)  |  TP: after-fee 1.5R from the limit.
  Valid V hours; cancelled if the stop trades first. Fill when a 1h bar trades through the limit by 0.05 ATR.
Exits: stop first, no TP on the fill bar, 0.04%/side, weekend flat, 48h hold, one position per coin."""
import sys, statistics, bisect, collections
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps
from ifvg_lab import START, SPLIT, SCH, load, report, H, H4, D, FRT
COINS = ['SUI', 'UNI', 'BTC', 'ETH', 'SOL', 'NEAR', 'ADA']
ALL9 = COINS + ['LINK', 'HYPE']


def run(sym, n_bb=20, k_bb=2.0, key='hz', confirm='reject', lim='close+0.25', buf=0.25, tgt=1.5, V=8,
        CHK=(8, 12, 16, 20), touches=3, tol=0.25, hold=48, frac=3, hz_look=540):
    b4 = load(sym, '4h'); b1 = load(sym, '1h')
    if len(b4) < 400:
        return []
    i1 = {x[0]: n for n, x in enumerate(b1)}
    o = [x[1] for x in b4]; hi = [x[2] for x in b4]; lo = [x[3] for x in b4]; c = [x[4] for x in b4]
    atr = perps.atr(hi, lo, c, 14); ema = perps.ema(c, 50)
    ph = [i for i in range(frac, len(b4) - frac) if hi[i] > max(hi[i - frac:i]) and hi[i] > max(hi[i + 1:i + 1 + frac])]
    pl = [i for i in range(frac, len(b4) - frac) if lo[i] < min(lo[i - frac:i]) and lo[i] < min(lo[i + 1:i + 1 + frac])]
    out = []; busy = 0
    for i in range(60, len(b4) - 1):
        T = b4[i][0] + H4
        if T < START or T < busy or atr[i] is None or ema[i - 6] is None:
            continue
        a = atr[i]
        w = c[i - n_bb + 1:i + 1]; m = sum(w) / n_bb; sd = statistics.pstdev(w)
        for side in (-1, 1):
            band = m + k_bb * sd if side == -1 else m - k_bb * sd
            if (side == -1 and hi[i] < band) or (side == 1 and lo[i] > band):
                continue
            if not ((c[i] - ema[i]) * side > 0 and (ema[i] - ema[i - 6]) * side > 0):
                continue
            lvl = None
            if key == 'hz':
                pts = [hi[q] for q in ph[bisect.bisect_left(ph, i - hz_look):] if q + frac <= i - 1] + \
                      [lo[q] for q in pl[bisect.bisect_left(pl, i - hz_look):] if q + frac <= i - 1]
                cands = [px for px in pts if lo[i] <= px <= hi[i] and sum(abs(x - px) <= tol * a for x in pts) >= touches]
                if not cands:
                    continue
                lvl = max(cands) if side == -1 else min(cands)       # the most extreme level swept
            if confirm == 'red' and (c[i] - o[i]) * side <= 0:
                continue
            if confirm == 'reject':
                ref = lvl if lvl is not None else band
                if (c[i] - ref) * side <= 0 or (c[i] - band) * side <= 0:
                    continue
            ext = hi[i] if side == -1 else lo[i]
            n0 = i1.get(T)
            if n0 is None:
                continue
            n = n0                                                    # wait for a check-in hour
            dead = False
            while ((b1[n][0] // H + 8) % 24) not in CHK:
                ext = max(ext, b1[n][2]) if side == -1 else min(ext, b1[n][3])
                n += 1
                if n >= len(b1) - 1:
                    dead = True; break
            if dead or perps.in_weekend(b1[n][0], SCH):
                continue
            stp = ext - side * buf * a
            kind, _, arg = lim.partition('+')
            if kind == 'close':
                L = c[i] - side * float(arg) * a
            elif kind == 'wick':
                L = c[i] - side * 0.5 * ((hi[i] - max(o[i], c[i])) if side == -1 else (min(o[i], c[i]) - lo[i]))
            else:
                L = lvl if lvl is not None else c[i]
            if (stp - L) * side >= 0 or abs(L - stp) / L < 0.002:
                continue
            f = e = None
            for q in range(n, min(len(b1), n + V)):
                x = b1[q]
                if (side == -1 and x[2] >= stp) or (side == 1 and x[3] <= stp):
                    if (side == -1 and x[2] >= L + 0.05 * a) or (side == 1 and x[3] <= L - 0.05 * a):
                        f, e = q, (max(x[1], L) if side == -1 else min(x[1], L))   # filled then stopped same bar
                    break
                if (side == -1 and x[2] >= L + 0.05 * a) or (side == 1 and x[3] <= L - 0.05 * a):
                    f, e = q, (max(x[1], L) if side == -1 else min(x[1], L)); break
            if f is None:
                continue
            d = abs(e - stp)
            if (e - stp) * side >= 0:
                continue
            tp = e + side * (tgt * (d + FRT * e) + FRT * e)
            flat = perps.next_weekend_stop(b1[f][0], SCH); px = None
            for q in range(f, min(len(b1), f + hold)):
                oo, hh, ll = b1[q][1], b1[q][2], b1[q][3]
                if b1[q][0] >= flat:
                    px = oo; break
                if (side == 1 and ll <= stp) or (side == -1 and hh >= stp):
                    px = (min(oo, stp) if side == 1 else max(oo, stp)) if q > f else stp; break
                if q > f and ((side == 1 and hh >= tp) or (side == -1 and ll <= tp)):
                    px = tp; break
            if px is None:
                px = b1[q][4]
            out.append({'sym': sym, 'side': side, 't_in': b1[f][0], 't_out': b1[q][0] + H, 'e': e, 'stp': stp,
                        'r': (side * (px - e) / e - FRT) / (d / e + FRT), 'stop_frac': d / e, 'placed': b1[n][0]})
            busy = b1[q][0] + H
            break
    return out


def book(syms=COINS, **kw):
    return sorted([t for s in syms for t in run(s, **kw)], key=lambda t: t['t_in'])


if __name__ == '__main__':
    rows = []
    for confirm in ('none', 'red', 'reject'):
        for lim in ('close+0', 'close+0.25', 'close+0.5', 'wick', 'level'):
            report(book(confirm=confirm, lim=lim), 'confirm %-6s limit %s' % (confirm, lim))
    for kw in (dict(n_bb=13), dict(n_bb=25), dict(key='none'), dict(V=12), dict(buf=0.5), dict(tgt=2.0), dict(CHK=(0, 8, 12, 16, 20))):
        report(book(**kw), 'reject close+0.25 ' + str(kw))
    report(book(ALL9), 'reject close+0.25, all 9 coins')
