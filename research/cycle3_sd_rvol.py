"""Cycle 3, ideas 4 and 5 (trader's ideas). Reuses cycle2_crt (fills, report, book_line, MC), rq.walk, daily, book2.

IDEA 4 - supply/demand zone retest (trend continuation), 4h bars, 10 core coins.
  Trend: coin 4h EMA50 > EMA200 on the impulse's last bar = longs only (mirror shorts).
  Impulse: 1-3 consecutive candles ending at bar i, each closing in the trend direction, net move
    (close[i] - open[first]) >= 2.5 x ATR14 (ATR of the base's last bar). Shortest impulse L that qualifies.
  Base: the 1-4 candles right before the impulse with total range (max high - min low) <= 1.2 ATR; the
    LONGEST qualifying base is used. A zone whose base overlaps an earlier zone's base/impulse bars is skipped.
  Zone: base low..high ('wick') or min/max of base bodies ('body'). Confirmed at bar i's close.
  Ticket: first scheduled scan (08/20/00 SGT, no Mon, no weekend) at/after confirmation; skipped if price
    already entered the zone between confirmation and the scan (first return already happened).
  Order: resting LIMIT at the zone's near edge (top for longs), live until 30 4h candles after confirmation,
    cancelled when a 4h candle closes beyond the far edge; no fills Sat 04:00-Sun 20:00 SGT.
    Fills only if a 15m bar trades 0.05 ATR through the limit; fill at the limit (or the open if gapped).
  Stop: far edge -/+ 0.25 ATR. Target: after-fee 2R (or 3R). 48h max hold after the fill, weekend flat.
  Filters (at the ticket scan, closed bars only): BTC 4h EMA50/200 trend agrees; coin daily EMA20/50 agrees.
  One open trade per coin.
IDEA 5a - volume climax fade. RVOL = 4h volume / mean(prior 20 4h volumes).
  Climax candle i: RVOL >= 3 (or 4); move over 6 candles to the candle's extreme >= 3 ATR
  (up: high[i] - close[i-6]; down: close[i-6] - low[i]); wick against that move >= 50% of the range
  (up-move: upper wick). Fade at the first scan within 8h after the candle closes: limit 0.25 ATR back
  (short: close + 0.25 ATR), stop beyond the wick + 0.1 ATR, valid 8h, pen 0.05 ATR, after-fee 2R, 24h hold.
  Skipped if the stop traded between candle close and the scan.
IDEA 5b - RVOL confirmation for CRT: keep CRT trades only if C2 (the sweep candle) has RVOL >= 1.5 / >= 2.
  CRT = cycle2_crt touch+0.05% slip, live hours, BTC daily filter (honest model) and the v2 pickle C.
Costs 0.04%/side; stop first; no target on the fill bar; R per qlab/cycle2 convention.
Book: book2.book([Q, C, NEW]) defaults; risk Q 2/1 by rex, CRT 1/0.5 by rex, NEW 1.0%. Rolling + MC as cycle2_crt."""
import sys, statistics, collections, pickle
sys.path.insert(0, '/home/user/bitf-perps/research')
import cycle2_crt as C2
from cycle2_crt import perps, rq, daily, book2, H, D, H4, START, END, SPLIT, S

FEE = 0.0004; FRT = 2 * FEE
SCH = perps.load_config()['schedule']
CORE = rq.SYMS
C2.RISK['N'] = 1.0
_D = {}


def data(sym):
    if sym not in _D:
        b4 = perps.load_json(perps.cache_file(sym, '4h'), [])
        o = [x[1] for x in b4]; h = [x[2] for x in b4]; l = [x[3] for x in b4]; c = [x[4] for x in b4]; v = [x[5] for x in b4]
        b15 = perps.load_json(perps.cache_file(sym, '15m'), [])
        _D[sym] = dict(b4=b4, o=o, h=h, l=l, c=c, v=v, at=perps.atr(h, l, c, 14), e50=perps.ema(c, 50), e200=perps.ema(c, 200),
                       i4={x[0]: k for k, x in enumerate(b4)}, b15=b15, i15={x[0]: k for k, x in enumerate(b15)})
    return _D[sym]


def rvol(sym, k):
    d = data(sym)
    if k < 20:
        return None
    m = statistics.mean(d['v'][k - 20:k])
    return d['v'][k] / m if m > 0 else None


def next_scan(t, maxwait):
    s = t
    while s <= t + maxwait:
        if perps.entry_allowed(s, SCH):
            return s
        s += H4
    return None


def finish(sym, side, b15, n, e, stop, tr, hold, a, extra):
    d = abs(e - stop)
    if (stop - e) * side >= 0:           # gapped through the stop on the fill bar: book a full loss
        return dict(sym=sym, side=side, t_in=b15[n][0], t_out=b15[n][0] + rq.M15, r=-1.0, exit='gap', **extra)
    if d / e < 0.002:
        return None
    tgt = e + side * (tr * (d + FRT * e) + FRT * e)
    px, why, to = rq.walk(b15, n, side, e, stop, tgt, b15[n][0] + hold * H)
    return dict(sym=sym, side=side, t_in=b15[n][0], t_out=to, exit=why,
                r=(side * (px - e) / e - FRT) / (d / e + FRT), **extra)


def zones(sym, body=False):
    d = data(sym); o, h, l, c, at = d['o'], d['h'], d['l'], d['c'], d['at']
    out, used = [], set()
    for i in range(210, len(o) - 1):
        tc = d['b4'][i][0] + H4
        if tc < START - 40 * D or tc >= END or d['e50'][i] is None or d['e200'][i] is None:
            continue
        side = 1 if d['e50'][i] > d['e200'][i] else -1
        z = None
        for L in (1, 2, 3):
            f = i - L + 1; a = at[f - 1]
            if a is None:
                break
            if any((c[j] - o[j]) * side <= 0 for j in range(f, i + 1)):
                break                                   # impulse candles must all move with the trend
            if (c[i] - o[f]) * side < 2.5 * a:
                continue
            for B in (4, 3, 2, 1):
                bb = range(f - B, f)
                if max(h[j] for j in bb) - min(l[j] for j in bb) <= 1.2 * a:
                    z = (L, B, f, a); break
            break                                       # shortest qualifying impulse only
        if not z:
            continue
        L, B, f, a = z
        bb = list(range(f - B, f))
        if used & set(bb):
            continue
        used |= set(range(f - B, i + 1))
        lo = min(min(o[j], c[j]) for j in bb) if body else min(l[j] for j in bb)
        hi = max(max(o[j], c[j]) for j in bb) if body else max(h[j] for j in bb)
        out.append(dict(sym=sym, side=side, i=i, tc=tc, lo=lo, hi=hi, a=a))
    return out


def zone_trade(z, tr=2.0, btc=False, dly=False):
    d = data(z['sym']); s, a, i = z['side'], z['a'], z['i']
    lim = z['hi'] if s == 1 else z['lo']; far = z['lo'] if s == 1 else z['hi']
    stop = far - s * 0.25 * a; expiry = z['tc'] + 30 * H4
    ts = next_scan(z['tc'], 30 * H4)
    if ts is None or ts < START:
        return None
    for k in range(i + 1, d['i4'].get(ts, i + 1)):    # bars closed before the ticket scan
        if (s == 1 and d['l'][k] <= lim) or (s == -1 and d['h'][k] >= lim) or (d['c'][k] - far) * s < 0:
            return None
    if btc and (rq.REG.get(ts - H4) or 0) != s:
        return None
    if dly and daily.bias(z['sym'], ts, 'ema') != s:
        return None
    b15, i15 = d['b15'], d['i15']; n0 = i15.get(ts)
    if n0 is None:
        return None
    for m in range(n0, len(b15)):
        t = b15[m][0]
        if t >= expiry or t >= END:
            return None
        if t % H4 == 0 and t > ts:                       # 4h candle just closed beyond the far edge -> cancel
            k = d['i4'].get(t - H4)
            if k is not None and (d['c'][k] - far) * s < 0:
                return None
        if perps.in_weekend(t, SCH):
            continue
        x = b15[m]
        if (s == 1 and x[3] <= lim - 0.05 * a) or (s == -1 and x[2] >= lim + 0.05 * a):
            e = min(x[1], lim) if s == 1 else max(x[1], lim)
            return finish(z['sym'], s, b15, m, e, stop, tr, 48, a, dict(tag='N', prio=2, dec=ts, rex=C2.vexp(ts)))
    return None


def climax(sym, thr=3.0):
    d = data(sym); o, h, l, c, at = d['o'], d['h'], d['l'], d['c'], d['at']
    tickets = {}
    for i in range(30, len(o) - 1):
        tc = d['b4'][i][0] + H4
        if tc < START or tc >= END or at[i] is None:
            continue
        rv = rvol(sym, i); a = at[i]; rg = h[i] - l[i]
        if rv is None or rv < thr or rg <= 0:
            continue
        if h[i] - c[i - 6] >= 3 * a and h[i] - max(o[i], c[i]) >= 0.5 * rg:
            s = -1
        elif c[i - 6] - l[i] >= 3 * a and min(o[i], c[i]) - l[i] >= 0.5 * rg:
            s = 1
        else:
            continue
        ts = next_scan(tc, 8 * H)
        if ts is None:
            continue
        tickets[ts] = (i, s)                             # latest climax before the scan wins
    out = []
    b15, i15 = d['b15'], d['i15']
    for ts, (i, s) in sorted(tickets.items()):
        a = at[i]; lim = c[i] - s * 0.25 * a
        stop = (l[i] - 0.1 * a) if s == 1 else (h[i] + 0.1 * a)
        if (lim - stop) * s <= 0:
            continue
        if any((s == 1 and l[k] <= stop) or (s == -1 and h[k] >= stop) for k in range(i + 1, d['i4'].get(ts, i + 1))):
            continue
        n0 = i15.get(ts)
        if n0 is None:
            continue
        for m in range(n0, min(len(b15), n0 + 32)):
            x = b15[m]
            if perps.in_weekend(x[0], SCH):
                break
            if (s == 1 and x[3] <= stop) or (s == -1 and x[2] >= stop):
                break
            if (s == 1 and x[3] <= lim - 0.05 * a) or (s == -1 and x[2] >= lim + 0.05 * a):
                e = min(x[1], lim) if s == 1 else max(x[1], lim)
                t = finish(sym, s, b15, m, e, stop, 2.0, 24, a, dict(tag='N', prio=2, dec=ts, rex=C2.vexp(ts)))
                if t:
                    out.append(t)
                break
    return out


def one_per_coin(tr):
    out, busy = [], collections.defaultdict(int)
    for t in sorted(tr, key=lambda t: t['t_in']):
        if START <= t['t_in'] < END and t['t_in'] >= busy[t['sym']]:
            out.append(t); busy[t['sym']] = t['t_out']
    return out


def tag3(Q, C, N):
    bk = book2.book(Q + C + N)
    f = lambda t: ('Qx' if t['rex'] else 'Qc') if t['tag'] == 'Q' else ('Cx' if t['rex'] else 'Cc') if t['tag'] == 'C' else 'N'
    return [dict(t, tag=f(t)) for t in bk]


def crt_rvol(t):
    c2open = t['t_in'] // H4 * H4 - H4
    k = data(t['sym'])['i4'].get(c2open)
    return rvol(t['sym'], k) if k is not None else None


if __name__ == '__main__':
    PK = pickle.load(open(S + '/book_trades_v2.pkl', 'rb')); Q, CV2 = PK['Q'], PK['C']
    CT = C2.crt(fill='touch', slip=0.05, hours={8, 12, 16, 20}, dfilt=True)
    V = {}
    ZW = [z for s in CORE for z in zones(s)]; ZB = [z for s in CORE for z in zones(s, body=True)]
    print('zones: wick %d, body %d' % (len(ZW), len(ZB)))
    for name, zs, kw in (('4.1 SD wick 2R', ZW, {}), ('4.2 SD body 2R', ZB, {}), ('4.3 SD wick 3R', ZW, dict(tr=3.0)),
                         ('4.4 SD body 3R', ZB, dict(tr=3.0)), ('4.5 SD wick 2R +BTC', ZW, dict(btc=True)),
                         ('4.6 SD wick 2R +daily', ZW, dict(dly=True)), ('4.7 SD wick 2R +BTC+daily', ZW, dict(btc=True, dly=True)),
                         ('4.8 SD body 2R +BTC+daily', ZB, dict(btc=True, dly=True))):
        V[name] = one_per_coin([t for t in (zone_trade(z, **kw) for z in zs) if t])
        C2.report(V[name], name)
    for thr in (3.0, 4.0):
        name = '5a.%d climax fade RVOL>=%g' % (thr, thr)
        V[name] = one_per_coin([t for s in CORE for t in climax(s, thr)]); C2.report(V[name], name)
    CF = {}
    for cname, cc in (('touch', CT), ('v2', CV2)):
        C2.report(cc, 'CRT %s (all)' % cname)
        for thr in (1.5, 2.0):
            name = '5b CRT %s C2 RVOL>=%g' % (cname, thr)
            CF[name] = [t for t in cc if (crt_rvol(t) or 0) >= thr]; C2.report(CF[name], name)
    print()
    C2.book_line('baseline v2 Q + v2 C', tag3(Q, CV2, []))
    C2.book_line('Q + C touch.05 (honest)', tag3(Q, CT, []))
    for k, tr in V.items():
        C2.book_line('Q+Cv2+' + k[:22], tag3(Q, CV2, tr))
        C2.book_line('Q+Ct +' + k[:22], tag3(Q, CT, tr))
    for k, cc in CF.items():
        C2.book_line('Q + ' + k[4:], tag3(Q, cc, []))
