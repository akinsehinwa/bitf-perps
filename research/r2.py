"""Round-2 ideas on 15m execution, last 3 years, 10 coins, 0.04% fee per side, weekend pause respected.
  night : at the 00:00 SGT scan, for coins in trend (coin 4h EMA50/200 and BTC 4h trend agree) whose last
          close is within `near` ATR of the 55-candle extreme but not through it: a STOP order at the extreme
          +/- 0.1 ATR, valid until 08:00 SGT. Stop 2 ATR from entry, after-fee 2R, 48h.
          ('stop orders fill at the level or worse if price gaps through')
  leg2  : after a Q trade exits at its target, re-enter the same direction on the first pullback to the 4h
          EMA20 (limit) within the next 48h, if the coin and BTC trends still agree. Stop 2 ATR, 2R, 48h.
  us    : session drift. In BTC's 4h trend direction, enter at the 20:00 SGT open (US session), exit at
          08:00 SGT (or stop 1.5 ATR / after-fee 1.5R first). sess=asia: 08:00 -> 16:00 SGT instead.
  cme   : CME weekend gap proxy (BTC/ETH): Friday 22:00 UTC price vs the Monday 08:00 SGT scan price. If the
          gap is >= g ATR(4h), fade it toward the Friday level (target = Friday price, stop 1.5 x gap beyond);
          must be >= 1 R:R."""
import sys, statistics, collections
S = '/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad'
sys.path.insert(0, S); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps, qlab
P = dict(a.split('=') for a in sys.argv[1:] if '=' in a)
num = lambda k, d: float(P.get(k, d))
H, H4, M15, D = qlab.H, qlab.H4, qlab.M15, qlab.D
FRT = qlab.FRT; START = qlab.START; SCH = qlab.SCH; ST = qlab.ST
SYMS = P.get('syms', ','.join(qlab.SYMS)).split(',')


def run_bracket(sym, n, side, e, stop, tgt, hold_h, exit_ms=None):
    rows, _ = qlab.b15(sym)
    flat = perps.next_weekend_stop(rows[n][0], SCH)
    d = abs(e - stop); m = n; px = why = None
    for m in range(n, min(len(rows), n + int(hold_h * 4))):
        o, h, l = rows[m][1], rows[m][2], rows[m][3]
        if rows[m][0] >= flat or (exit_ms and rows[m][0] >= exit_ms):
            px, why = o, 'time'; break
        if (side == 1 and l <= stop) or (side == -1 and h >= stop):
            px = ((min(o, stop) if side == 1 else max(o, stop)) if m > n else stop); why = 'stop'; break
        if m > n and ((side == 1 and h >= tgt) or (side == -1 and l <= tgt)):
            px, why = tgt, 'target'; break
    if px is None:
        px, why = rows[m][4], 'time'
    return {'sym': sym, 'side': side, 't_in': rows[n][0], 't_out': rows[m][0] + M15, 'exit': why,
            'r': (side * (px - e) / e - FRT) / (d / e + FRT)}


def aft(e, side, d, tr):
    return e + side * (tr * (d + FRT * e) + FRT * e)


def night():
    out = []
    for s in SYMS:
        b4 = qlab.load(s, '4h'); ind = perps.indicators(b4, ST)
        rows, idx = qlab.b15(s); busy = 0
        for i in range(ST['ema_slow'] + 1, len(b4) - 1):
            close = b4[i][0] + H4
            if close < START or close < busy or perps.local_dt(close, 8).hour != 0 or perps.in_weekend(close, SCH):
                continue
            a = ind['atr'][i]; c = ind['c'][i]
            if a is None or ind['ef'][i] is None:
                continue
            side = 1 if ind['ef'][i] > ind['es'][i] else -1
            r = qlab.REG.get(b4[i][0])
            if r is None or (r > 0) != (side == 1):
                continue
            lvl = max(ind['h'][i - ST['donchian'] + 1:i + 1]) if side == 1 else min(ind['l'][i - ST['donchian'] + 1:i + 1])
            dist = (lvl - c) * side / a
            if dist < 0 or dist > num('near', 1.0):
                continue
            trig = lvl + side * 0.1 * a
            n0 = idx.get(close)
            if n0 is None:
                continue
            n = e = None
            for m in range(n0, min(len(rows), n0 + 32)):            # until 08:00 SGT
                x = rows[m]
                if (side == 1 and x[2] >= trig) or (side == -1 and x[3] <= trig):
                    n, e = m, (max(x[1], trig) if side == 1 else min(x[1], trig)); break
            if n is None:
                continue
            stop = e - side * 2 * a
            t = run_bracket(s, n, side, e, stop, aft(e, side, 2 * a, 2), 48)
            out.append(t); busy = t['t_out']
    return out


def leg2():
    sig = qlab.signals()
    out = []
    for g in sig:
        r = qlab.execute(g, 'atr:0.5', pen=0.05)
        if not (r and r.get('filled') and r['exit'] == 'target'):
            continue
        s, side = g['sym'], g['side']
        b4 = qlab.load(s, '4h'); ind = perps.indicators(b4, ST)
        tix = {b[0]: k for k, b in enumerate(b4)}
        rows, idx = qlab.b15(s)
        start = r['t_out']
        k = tix.get((start // H4) * H4 - H4)
        if k is None:
            continue
        e20 = perps.ema(ind['c'], 20)
        n = None
        for m in range(idx.get((start // M15) * M15, 0), min(len(rows), idx.get((start // M15) * M15, 0) + 48 * 4)):
            t = rows[m][0]
            kk = tix.get((t // H4) * H4 - H4)
            if kk is None or e20[kk] is None:
                continue
            if (ind['ef'][kk] > ind['es'][kk]) != (side == 1):
                break
            lim = e20[kk]
            if (side == 1 and rows[m][3] <= lim) or (side == -1 and rows[m][2] >= lim):
                n, e, a = m, (min(rows[m][1], lim) if side == 1 else max(rows[m][1], lim)), ind['atr'][kk]
                break
        if n is None or perps.in_weekend(rows[n][0], SCH):
            continue
        stop = e - side * 2 * a
        out.append(run_bracket(s, n, side, e, stop, aft(e, side, 2 * a, 2), 48))
    return out


def us():
    sess = P.get('sess', 'us')
    h_in, h_out = (20, 8) if sess == 'us' else (8, 16)
    out = []
    for s in SYMS:
        b4 = qlab.load(s, '4h'); ind = perps.indicators(b4, ST); rows, idx = qlab.b15(s)
        for i in range(ST['ema_slow'] + 1, len(b4) - 1):
            close = b4[i][0] + H4
            if close < START or perps.local_dt(close, 8).hour != h_in or perps.in_weekend(close, SCH):
                continue
            r = qlab.REG.get(b4[i][0]); a = ind['atr'][i]
            if r is None or a is None:
                continue
            if P.get('coin', '1') == '1' and ((ind['ef'][i] > ind['es'][i]) != (r > 0)):
                continue
            side = 1 if r > 0 else -1
            n = idx.get(close)
            if n is None:
                continue
            e = rows[n][1]; stop = e - side * 1.5 * a
            exit_ms = close + ((h_out - h_in) % 24) * H
            out.append(run_bracket(s, n, side, e, stop, aft(e, side, 1.5 * a, 1.5), 24, exit_ms))
    return out


def cme():
    out = []
    for s in [x for x in SYMS if x in ('BTC', 'ETH', 'SOL', 'XRP', 'BNB', 'ADA', 'LINK')]:
        rows, idx = qlab.b15(s)
        b4 = qlab.load(s, '4h'); at = perps.atr([x[2] for x in b4], [x[3] for x in b4], [x[4] for x in b4], 14)
        a4 = {b[0]: at[k] for k, b in enumerate(b4)}
        for k, x in enumerate(rows):
            t = x[0]
            d = perps.dt.datetime.fromtimestamp(t / 1000, perps.UTC)
            if not (d.weekday() == 4 and d.hour == 21 and d.minute == 45) or t < START:
                continue
            fri = x[4]                                   # close of the 21:45-22:00 UTC bar = CME Friday close proxy
            mon = t + 15 * 60_000 + 2 * D + 2 * H        # Monday 00:00 UTC = 08:00 SGT
            n = idx.get(mon)
            a = a4.get(mon - H4)
            if n is None or not a:
                continue
            e = rows[n][1]; gap = e - fri
            if abs(gap) < num('g', 1.0) * a:
                continue
            side = -1 if gap > 0 else 1
            stop = e - side * max(1.0 * a, 0.75 * abs(gap))
            tgt = fri
            if abs(tgt - e) < abs(e - stop):
                continue
            out.append(run_bracket(s, n, side, e, stop, tgt, 96))
    return out


if __name__ == '__main__':
    mode = P.get('mode', 'night')
    tr = sorted({'night': night, 'leg2': leg2, 'us': us, 'cme': cme}[mode](), key=lambda t: t['t_in'])
    lab = ' '.join('%s=%s' % kv for kv in P.items())
    if not tr:
        print(lab, 'no trades'); sys.exit()
    rs = [t['r'] for t in tr]
    Y = [START, START + 365 * D, START + 730 * D, START + 1100 * D]
    cells = []
    for y in range(3):
        xs = [t['r'] for t in tr if Y[y] <= t['t_in'] < Y[y + 1]]
        cells.append('%+.2fR n=%d' % (statistics.mean(xs), len(xs)) if xs else 'n/a')
    print('%-30s %+.2fR win %2.0f%% %4.1f/mo %+4.1fR/mo | %s | %s' % (lab, statistics.mean(rs), 100 * sum(x > 0 for x in rs) / len(rs),
          len(rs) / 36.5, sum(rs) / 36.5, ' | '.join(cells), dict(collections.Counter(t['exit'] for t in tr))))
    if P.get('save'):
        import pickle
        pickle.dump(tr, open(S + '/r2_%s.pkl' % P['save'], 'wb'))
