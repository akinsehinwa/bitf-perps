"""Cycle 2 - Strategy CRT (4h) re-checked under realistic stop-order execution.

RULE (crt3.py htf=4h btc=1, copied here unchanged in logic):
  4h candles built from 15m. C1 = range candle: body >= 70% of range, range >= 1 x ATR(14, 4h).
  C2 sweeps C1's high (C1 bullish) / low (C1 bearish) and closes back inside C1 -> trade AGAINST C1,
  only in BTC's 4h trend direction (EMA50 vs EMA200 on the C2 bar).
  Optional live-skill filter: BTC DAILY EMA20/50 trend agrees: daily.bias('BTC', C2 close, 'ema') == side.
  Entry: STOP order at C2's low (short) / high (long), valid only during C3 (next 4h candle), worked on 15m;
  cancelled if the protective stop trades before the trigger.
  Stop = C2's sweep extreme + 0.1 ATR. Target = C1's far end. Skip if planned R:R < 1 (checked on the fill
  price used by the model) or stop < 0.2%. 24h max hold, weekend pause/close, max 1 trade per coin per UTC day.
  Scan schedule: C2 close (= C3 open) at given SGT hours.
FILL MODELS
  old  : fills at the trigger when a 15m bar touches it (or the open if gapped) - crt3 as-is.
  real : fills only if the 15m bar trades THROUGH the trigger by pen x ATR(4h) (pen 0.05); fill price =
         trigger (or the bar open if it opened beyond the trigger) moved against us by slip % of price.
  touch: triggers on a touch (as a real stop order does) and fills at trigger/open + slip  (conservative).
Exits (rq.walk): stop first if a bar touches stop and target; never a target on the fill bar; 0.04% fee/side;
R = (side*(exit-e)/e - 2 fee) / (stop_dist/e + 2 fee)  (house convention, as crt3).
Book: Q (book_trades_v2.pkl) + CRT via book2.book defaults; risk Q 2.0/1.0 by Q 'rex', CRT 1.0/0.5 by BTC 7d realized
vol expanding at the C2 close (42 x 4h log-return stdev vs 42 bars earlier, bars closed <= decision).
Rolling sim START+10d..START+1005d; MC = 3000 paths of 60 weekly blocks drawn from that window (seed 7)."""
import sys, os, math, bisect, statistics, pickle, random, collections
S = '/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad'
sys.path.insert(0, S); sys.path.insert(0, '/home/user/bitfunded-perps')
sys.argv = sys.argv[:1]
import perps, rq, daily, book2

H, D, M15 = rq.H, rq.D, rq.M15
H4 = 4 * H
FEE = 0.0004
START = rq.START
END = int(perps.dt.datetime(2026, 11, 13, tzinfo=perps.UTC).timestamp() * 1000)
SPLIT = int(perps.dt.datetime(2025, 12, 18, tzinfo=perps.UTC).timestamp() * 1000)

# BTC 7-day realized vol state (as rev/dz.py vexp)
B4 = perps.load_json(perps.cache_file('BTC', '4h'), []); BT = [b[0] + H4 for b in B4]
LR = [None] + [math.log(B4[k][4] / B4[k - 1][4]) for k in range(1, len(B4))]
SD = [None] * len(B4)
for k in range(43, len(B4)):
    SD[k] = statistics.pstdev(LR[k - 41:k + 1])


def vexp(t):
    k = bisect.bisect_right(BT, t) - 1
    if k < 90 or SD[k - 42] is None:
        return None
    return SD[k] > SD[k - 42]


_B = {}


def bars(sym):
    if sym not in _B:
        b15 = perps.load_json(perps.cache_file(sym, '15m'), [])
        b = rq.aggregate(b15, H4)
        at = perps.atr([x[2] for x in b], [x[3] for x in b], [x[4] for x in b], 14)
        _B[sym] = (b15, {x[0]: k for k, x in enumerate(b15)}, b, at)
    return _B[sym]


def run(sym, fill='old', slip=0.0, pen=0.05, dfilt=False, hours=None):
    b15, i15, b, at = bars(sym)
    if len(b15) < 2000:
        return []
    o = [x[1] for x in b]; h = [x[2] for x in b]; l = [x[3] for x in b]; c = [x[4] for x in b]
    out, busy, days = [], 0, collections.Counter()
    for i in range(20, len(b) - 1):
        a = at[i]; t3 = b[i][0] + H4
        if a is None or t3 < START or t3 >= END or t3 < busy or perps.in_weekend(t3, rq.sch) or days[t3 // D] >= 1:
            continue
        if hours is not None and ((t3 // H + 8) % 24) not in hours:
            continue
        j = i - 1
        rng1 = h[j] - l[j]
        if rng1 <= 0 or abs(c[j] - o[j]) < 0.7 * rng1 or rng1 < 1.0 * a:
            continue
        bull1 = c[j] > o[j]
        if bull1 and h[i] > h[j] and l[j] < c[i] < h[j]:
            side, sweep, trig, tgt = -1, h[i], l[i], l[j]
        elif not bull1 and l[i] < l[j] and l[j] < c[i] < h[j]:
            side, sweep, trig, tgt = 1, l[i], h[i], h[j]
        else:
            continue
        r = rq.REG.get(t3 - H4)
        if r is None or (r > 0) != (side == 1):
            continue
        if dfilt and daily.bias('BTC', t3, 'ema') != side:
            continue
        stop = sweep - side * 0.1 * a
        n0 = i15.get(t3)
        if n0 is None:
            continue
        n = e = None
        for m in range(n0, min(len(b15), n0 + 16)):
            x = b15[m]
            if (side == -1 and x[2] >= stop) or (side == 1 and x[3] <= stop):
                break
            if fill in ('old', 'touch'):          # touch: triggers on a touch, fills trigger/open + slip
                if (side == -1 and x[3] < trig) or (side == 1 and x[2] > trig):
                    base = min(x[1], trig) if side == -1 else max(x[1], trig)
                    n, e = m, base * (1 + side * slip / 100 if fill == 'touch' else 1); break
            else:
                if (side == -1 and x[3] <= trig - pen * a) or (side == 1 and x[2] >= trig + pen * a):
                    base = min(x[1], trig) if side == -1 else max(x[1], trig)
                    n, e = m, base * (1 + side * slip / 100); break
        if n is None:
            continue
        d = abs(stop - e)
        if (stop - e) * side >= 0 or d / e < 0.002 or (tgt - e) * side <= 0 or abs(tgt - e) / d < 1.0:
            continue
        px, why, to = rq.walk(b15, n, side, e, stop, tgt, b15[n][0] + 24 * H)
        out.append({'sym': sym, 'side': side, 't_in': b15[n][0], 't_out': to, 'exit': why, 'dec': t3,
                    'r': (side * (px - e) / e - 2 * FEE) / (d / e + 2 * FEE), 'tag': 'C', 'prio': 1,
                    'rex': vexp(t3), 'stop_frac': d / e})
        busy = to; days[t3 // D] += 1
    return out


def crt(**kw):
    return sorted([t for s in rq.SYMS for t in run(s, **kw)], key=lambda t: t['t_in'])


def stats(xs, months):
    rs = [t['r'] for t in xs]
    if not rs:
        return '  n=0'
    gw = sum(x for x in rs if x > 0); gl = -sum(x for x in rs if x <= 0)
    eq = pk = dd = 0
    for t in sorted(xs, key=lambda t: t['t_out']):
        eq += t['r']; pk = max(pk, eq); dd = max(dd, pk - eq)
    return 'n=%3d %4.1f/mo win %2.0f%% %+.3fR pf %4.2f %+5.2fR/mo dd %4.1fR' % (
        len(rs), len(rs) / months, 100 * sum(x > 0 for x in rs) / len(rs), statistics.mean(rs), gw / gl if gl else 9,
        sum(rs) / months, dd)


def report(tr, label):
    mo = lambda a, b: (b - a) / D / 30.44
    Y = [START, START + 365 * D, START + 730 * D, END]
    print('== %s\n   ALL %s' % (label, stats(tr, mo(START, END))))
    for y in range(3):
        print('   Y%d  %s' % (y + 1, stats([t for t in tr if Y[y] <= t['t_in'] < Y[y + 1]], mo(Y[y], Y[y + 1]))))
    print('   IS  %s' % stats([t for t in tr if t['t_in'] < SPLIT], mo(START, SPLIT)))
    print('   OS  %s' % stats([t for t in tr if t['t_in'] >= SPLIT], mo(SPLIT, END)))


T0, T1 = START + 10 * D, START + 1005 * D
RISK = {'Qx': 2.0, 'Qc': 1.0, 'Cx': 1.0, 'Cc': 0.5}


def tagged(Q, C):
    bk = book2.book(Q + C)
    return [dict(t, tag=('Qx' if t['rex'] else 'Qc') if t['tag'] == 'Q' else ('Cx' if t['rex'] else 'Cc')) for t in bk]


def mc(tr, n=3000, seed=7, weeks_per=60):
    rnd = random.Random(seed); W = 7 * D; wk = collections.defaultdict(list)
    for t in tr:
        if T0 <= t['t_in'] < T1:
            wk[(t['t_in'] - T0) // W].append(t)
    keys = list(range(int((T1 - T0) // W))); ok = 0; days = []
    for _ in range(n):
        seq = []
        for j in range(weeks_per):
            w = rnd.choice(keys)
            for t in wk.get(w, []):
                off = T0 + w * W
                seq.append(dict(t, t_in=t['t_in'] - off + j * W + T0, t_out=t['t_out'] - off + j * W + T0))
        r = book2.sim(seq, RISK, T0, T0 + 1)
        if r['pass'] > 0:
            ok += 1; days.append(r['med'])
    days.sort()
    return 100 * ok / n, days[len(days) // 2] if days else float('nan')


def book_line(label, tr):
    r = book2.sim(tr, RISK, T0, T1); p, m = mc(tr)
    pct = sum(t['r'] * RISK[t['tag']] for t in tr if START <= t['t_in'] < END) / ((END - START) / D / 30.44)
    print('BOOK %-34s rolling %3.0f%% / %3.0fd (S1 fail %2.0f%%) | MC %4.1f%% / %3.0fd | %+.2f%%/mo | nC=%d' % (
        label, r['pass'], r['med'], r['f1'], p, m, pct, sum(t['tag'][0] == 'C' for t in tr)))


if __name__ == '__main__':
    LIVE = {8, 12, 16, 20}
    V = {}
    for name, kw in (
            ('1 old  live-hrs  no-daily', dict(fill='old', hours=LIVE)),
            ('2 old  live-hrs  daily', dict(fill='old', hours=LIVE, dfilt=True)),
            ('3 real .02 live-hrs no-daily', dict(fill='real', slip=0.02, hours=LIVE)),
            ('4 real .02 live-hrs daily', dict(fill='real', slip=0.02, hours=LIVE, dfilt=True)),
            ('5 real .05 live-hrs no-daily', dict(fill='real', slip=0.05, hours=LIVE)),
            ('6 real .05 live-hrs daily', dict(fill='real', slip=0.05, hours=LIVE, dfilt=True)),
            ('7 old  all-hrs   daily (=v2 C)', dict(fill='old', dfilt=True)),
            ('8 real .02 all-hrs daily', dict(fill='real', slip=0.02, dfilt=True)),
            ('9 real .02 no-00 (adds 04) daily', dict(fill='real', slip=0.02, hours=LIVE | {4}, dfilt=True)),
            ('10 touch .05 live-hrs daily', dict(fill='touch', slip=0.05, hours=LIVE, dfilt=True))):
        V[name] = crt(**kw); report(V[name], name)
    # selection check: old-model trades that the pen rule never fills
    key = lambda t: (t['sym'], t['dec'])
    for a_, b_ in (('2 old  live-hrs  daily', '4 real .02 live-hrs daily'), ('2 old  live-hrs  daily', '10 touch .05 live-hrs daily')):
        kb = {key(t) for t in V[b_]}; drop = [t['r'] for t in V[a_] if key(t) not in kb]
        print('dropped by %s vs old: n=%d avg %+.3fR' % (b_, len(drop), statistics.mean(drop) if drop else 0))
    PK = pickle.load(open(S + '/book_trades_v2.pkl', 'rb'))
    Q = PK['Q']; C2 = PK['C']
    print()
    book_line('baseline (v2 Q + v2 C)', tagged(Q, C2))
    book_line('Q only (tilted)', tagged(Q, []))
    for k in ('2 old  live-hrs  daily', '4 real .02 live-hrs daily', '6 real .05 live-hrs daily', '8 real .02 all-hrs daily', '10 touch .05 live-hrs daily'):
        book_line('Q + ' + k, tagged(Q, V[k]))
