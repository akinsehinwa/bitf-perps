"""Cycle 3, idea 3 - daily time-series momentum / trend-following with a 4h-clock limit entry.

RULE (pre-specified; variants listed in VARIANTS below, every one counted):
  Daily bars = UTC days (open 08:00 SGT) built from 4h bars, closed days only (6 x 4h present).
  Signal on the close of day i (time T = 08:00 SGT):
    long  : close[i] > max(close[i-N .. i-1])  and  EMA50(daily)[i] > EMA50[i-1]   (N = 20; variant 55)
    short : close[i] < min(close[i-N .. i-1])  and  EMA50[i] < EMA50[i-1]
    variant btc: BTC daily EMA20 > EMA50 (long) / < (short) on the same closed day (daily.bias 'ema').
  Ticket: first scheduled scan in {T, T+12h (20:00 SGT), T+16h (00:00 SGT)} that is not in the weekend
    window (Sat 04:00 - Sun 20:00 SGT). LIMIT = signal close -/+ 0.5 x ATR(daily,14) (variant: 1.0 x ATR(4h,14)
    of the last 4h bar closed at the ticket time). Valid 24h from the ticket, cut at the next Sat 04:00 SGT.
    Fill only if a 15m bar trades THROUGH the limit by 0.05 x (the ATR used for the limit); fill at the limit
    (or the open if it gapped through).
  Stop = signal close -/+ k x ATR(daily,14), k = 2.0 (variant 1.5). Skip if stop < 0.2% from the fill.
  Exit: after-fee target tr R (3R; variant 2R) | 'trail' = no target, exit at the daily close when the day closes
    below the prior 10-day low (long) / above the prior 10-day high (short) - executed at that 08:00 SGT open
    (if that falls in the weekend window with weekend-hold, at the Sun 20:00 SGT scan).
  Max hold: closed at the last scan (08/20/00 SGT, not weekend) <= fill + 9 days.
  Weekend: 'flat' = closed at Sat 04:00 SGT (live house rule); 'hold' = held with server-side SL/TP.
  Stop first if a 15m bar touches stop and target; never a target on the fill bar; 0.04% fee/side;
  R = (side*(exit-e)/e - 2 fee) / (stop_dist/e + 2 fee). One position (or pending ticket) per coin.
Window 2023-11-12 .. 2026-11-13, by year (365d) and 70/30 split at 2025-12-18 (t_in).
Variant selection uses the IN-SAMPLE half only.
Book: book2.book([Q, C, NEW]) defaults (Q/C from book_trades_v2.pkl, NEW prio 2); risk Q 2.0/1.0 and CRT 1.0/0.5
by BTC 7d vol (rex), NEW 1.0% flat or 1.0/0.5 by the same vol state at the signal close.
Rolling sim START+10d..START+1005d and the standard MC (3000 paths, 60 weekly blocks, seed 7)."""
import sys, statistics, pickle, random, collections, bisect
S = '/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad'
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, S); sys.path.insert(0, '/home/user/bitfunded-perps')
import os; os.chdir("/home/user/bitfunded-perps")
import perps, daily, book2
import cycle2_crt as c2

H = perps.HOUR_MS; H4 = 4 * H; D = 86_400_000; M15 = 15 * 60_000
FEE = 0.0004; FRT = 2 * FEE; PEN = 0.05
START, END, SPLIT = c2.START, c2.END, c2.SPLIT
SCH = perps.load_config()['schedule']
SYMS = 'BTC,ETH,BNB,XRP,SOL,HYPE,ZEC,ADA,UNI,LINK'.split(',')
load = lambda s, iv: perps.load_json(perps.cache_file(s, iv), [])
SCAN_UTC = (0, 12, 16)                         # 08:00 / 20:00 / 00:00 SGT
wk = lambda t: perps.in_weekend(t, SCH)


def scan_ok(t):
    return (t // H) % 24 in SCAN_UTC and t % H == 0 and not wk(t)


def last_scan_le(t):
    t = t // H * H
    while not scan_ok(t):
        t -= H
    return t


def next_scan_ge(t):
    t = -(-t // H) * H
    while not scan_ok(t):
        t += H
    return t


_DATA = {}


def data(sym):
    if sym in _DATA:
        return _DATA[sym]
    b4 = load(sym, '4h')
    days = collections.OrderedDict()
    for b in b4:
        k = b[0] // D
        d = days.get(k)
        if d is None:
            days[k] = [k * D, b[1], b[2], b[3], b[4], 1]
        else:
            d[2] = max(d[2], b[2]); d[3] = min(d[3], b[3]); d[4] = b[4]; d[5] += 1
    dr = [d for d in days.values() if d[5] == 6]
    h = [x[2] for x in dr]; l = [x[3] for x in dr]; c = [x[4] for x in dr]
    dat = perps.atr(h, l, c, 14); e50 = perps.ema(c, 50)
    a4 = perps.atr([x[2] for x in b4], [x[3] for x in b4], [x[4] for x in b4], 14)
    b4close = [x[0] + H4 for x in b4]
    rows = load(sym, '15m'); idx = {r[0]: k for k, r in enumerate(rows)}
    dclose = {x[0] + D: k for k, x in enumerate(dr)}
    _DATA[sym] = dict(dr=dr, h=h, l=l, c=c, dat=dat, e50=e50, a4=a4, b4close=b4close, rows=rows, idx=idx, dclose=dclose)
    return _DATA[sym]


def run(sym, N=20, btc=False, entry='d0.5', k=2.0, ex='3', weekend='flat'):
    X = data(sym); dr, c, h, l = X['dr'], X['c'], X['h'], X['l']; rows, idx = X['rows'], X['idx']
    out, busy = [], 0
    for i in range(max(N, 51), len(dr)):
        T = dr[i][0] + D
        if T < START or T >= END or X['dat'][i] is None or X['e50'][i - 1] is None:
            continue
        side = 1 if (c[i] > max(c[i - N:i]) and X['e50'][i] > X['e50'][i - 1]) else \
            -1 if (c[i] < min(c[i - N:i]) and X['e50'][i] < X['e50'][i - 1]) else 0
        if not side:
            continue
        if btc and daily.bias('BTC', T, 'ema') != side:
            continue
        tk = next((T + o * H for o in (0, 12, 16) if not wk(T + o * H)), None)
        if tk is None or tk < busy:
            continue
        ad = X['dat'][i]
        if entry.startswith('d'):
            ua = ad; lim = c[i] - side * float(entry[1:]) * ad
        else:
            j = bisect.bisect_right(X['b4close'], tk) - 1
            ua = X['a4'][j]; lim = c[i] - side * float(entry[1:]) * ua
        stp = c[i] - side * k * ad
        exp_t = min(tk + 24 * H, perps.next_weekend_stop(tk, SCH))
        n0 = idx.get(tk)
        if n0 is None:
            continue
        n = e = None
        for m in range(n0, len(rows)):
            x = rows[m]
            if x[0] >= exp_t:
                break
            if (side == 1 and x[3] <= lim - PEN * ua) or (side == -1 and x[2] >= lim + PEN * ua):
                n, e = m, (min(x[1], lim) if side == 1 else max(x[1], lim)); break
        if n is None:
            busy = exp_t; continue
        d = abs(e - stp)
        if (stp - e) * side >= 0 or d / e < 0.002:
            busy = exp_t; continue
        tr = None if ex == 'trail' else float(ex)
        tgt = e + side * (tr * (d + FRT * e) + FRT * e) if tr else None
        tin = rows[n][0]
        t_max = last_scan_le(tin + 9 * D)
        flat = perps.next_weekend_stop(tin, SCH) if weekend == 'flat' else None
        px = why = None; pend = None
        for m in range(n, len(rows)):
            t, o, hh, ll = rows[m][0], rows[m][1], rows[m][2], rows[m][3]
            if flat and t >= flat:
                px, why = o, 'weekend'; break
            if m > n and t >= t_max:
                px, why = o, 'time'; break
            if pend is not None and t >= pend:
                px, why = o, 'trail'; break
            if (side == 1 and ll <= stp) or (side == -1 and hh >= stp):
                px = ((min(o, stp) if side == 1 else max(o, stp)) if m > n else stp); why = 'stop'; break
            if m > n and tgt and ((side == 1 and hh >= tgt) or (side == -1 and ll <= tgt)):
                px, why = tgt, 'target'; break
            # trail: evaluated when a daily bar closes (at the end of this 15m bar), executed at the next scan
            tc = t + M15
            if ex == 'trail' and pend is None and tc % D == 0 and tc > tin and tc in X['dclose']:
                q = X['dclose'][tc]
                if q >= 10 and ((side == 1 and c[q] < min(l[q - 10:q])) or (side == -1 and c[q] > max(h[q - 10:q]))):
                    pend = tc if not wk(tc) else next_scan_ge(tc)
        if px is None:
            break                                          # data ended with the trade open
        r = (side * (px - e) / e - FRT) / (d / e + FRT)
        tout = rows[m][0] if why in ('weekend', 'time', 'trail') else rows[m][0] + M15
        out.append({'sym': sym, 'side': side, 't_in': tin, 't_out': tout, 'r': r, 'exit': why, 'sig': T,
                    'tag': 'N', 'prio': 2, 'rex': c2.vexp(T)})
        busy = tout
    return out


def trend(**kw):
    return sorted([t for s in SYMS for t in run(s, **kw)], key=lambda t: t['t_in'])


def overlap(tr, Q):
    n = 0
    for t in tr:
        if any(q['sym'] == t['sym'] and q['side'] == t['side'] and q['t_in'] < t['t_out'] and t['t_in'] < q['t_out'] for q in Q):
            n += 1
    return n


RISK = {'Qx': 2.0, 'Qc': 1.0, 'Cx': 1.0, 'Cc': 0.5, 'Nx': 1.0, 'Nc': 1.0}
T0, T1 = START + 10 * D, START + 1005 * D


def mc(tr, risk, n=3000, seed=7, weeks_per=60):
    rnd = random.Random(seed); W = 7 * D; wkb = collections.defaultdict(list)
    for t in tr:
        if T0 <= t['t_in'] < T1:
            wkb[(t['t_in'] - T0) // W].append(t)
    keys = list(range(int((T1 - T0) // W))); ok = 0; days = []
    for _ in range(n):
        seq = []
        for j in range(weeks_per):
            w = rnd.choice(keys)
            for t in wkb.get(w, []):
                off = T0 + w * W
                seq.append(dict(t, t_in=t['t_in'] - off + j * W + T0, t_out=t['t_out'] - off + j * W + T0))
        r = book2.sim(seq, risk, T0, T0 + 1)
        if r['pass'] > 0:
            ok += 1; days.append(r['med'])
    days.sort()
    return 100 * ok / n, days[len(days) // 2] if days else float('nan')


def book_line(label, trades, risk):
    bk = book2.book(trades)
    tr = [dict(t, tag=t['tag'][0] + ('x' if t['rex'] else 'c')) for t in bk]
    r = book2.sim(tr, risk, T0, T1); p, m = mc(tr, risk)
    nN = [t for t in tr if t['tag'][0] == 'N']
    rmo = sum(t['r'] for t in tr) / ((END - START) / D / 30.44)
    print('BOOK %-30s rolling %3.0f%% / %3.0fd (S1 fail %2.0f%%) | MC %4.1f%% / %3.0fd | book %+.2fR/mo | N in book %d (%+.2fR)' % (
        label, r['pass'], r['med'], r['f1'], p, m, rmo, len(nN), statistics.mean(t['r'] for t in nN) if nN else 0))


VARIANTS = [
    ('V1 core N20 d0.5 k2 3R flat', {}),
    ('V2 exit 2R', dict(ex='2')),
    ('V3 exit trail10', dict(ex='trail')),
    ('V4 stop 1.5', dict(k=1.5)),
    ('V5 entry 1.0 ATR4h', dict(entry='h1.0')),
    ('V6 N55', dict(N=55)),
    ('V7 +BTC EMA20/50', dict(btc=True)),
    ('V8 weekend hold', dict(weekend='hold')),
    ('V9 trail + weekend hold', dict(ex='trail', weekend='hold')),
]

if __name__ == '__main__':
    PK = pickle.load(open('/home/user/bitfunded-perps/research/book_trades_v2.pkl', 'rb'))
    Q, C = PK['Q'], PK['C']
    mo = lambda a, b: (b - a) / D / 30.44
    V = {}
    for name, kw in VARIANTS:
        V[name] = trend(**kw); c2.report(V[name], name)
        print('   exits', dict(collections.Counter(t['exit'] for t in V[name])), '| overlap with Q (same coin/side/time):',
              overlap(V[name], Q))
    # V10: per-dimension choice by IN-SAMPLE R/month only
    ism = lambda tr: sum(t['r'] for t in tr if t['t_in'] < SPLIT)
    base = ism(V['V1 core N20 d0.5 k2 3R flat'])
    pick = {}
    for name, kw in VARIANTS[1:]:
        if ism(V[name]) > base and len(kw) == 1:
            for kk, vv in kw.items():
                if kk not in pick or ism(V[name]) > pick[kk][1]:
                    pick[kk] = (vv, ism(V[name]))
    kw10 = {kk: vv for kk, (vv, _) in pick.items()}
    print('\nV10 IS-selected dims:', kw10)
    V['V10 IS-combo'] = trend(**kw10); c2.report(V['V10 IS-combo'], 'V10 IS-combo %s' % kw10)
    print('   overlap with Q:', overlap(V['V10 IS-combo'], Q))
    best = max(V, key=lambda k: ism(V[k]))
    print('\nbest by IS R:', best)
    print()
    book_line('baseline Q + C', Q + C, RISK)
    for nm in dict.fromkeys(['V1 core N20 d0.5 k2 3R flat', best]):
        book_line('+ %s @1.0' % nm[:20], Q + C + V[nm], RISK)
        book_line('+ %s tilt 1.0/0.5' % nm[:14], Q + C + V[nm], dict(RISK, Nc=0.5))
    pickle.dump(V, open(S + '/cycle3_trend.pkl', 'wb'))
