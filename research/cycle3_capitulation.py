"""Cycle 3, ideas 1 and 2 - capitulation reversals.

IDEA 1 (CAP, trader's "VIX + weekly RSI + historically oversold" dip-buy; shorts = mirror):
  Decision: 4h closes at 08:00 / 20:00 / 00:00 SGT, not in the weekend pause (Sat 04:00 - Sun 20:00 SGT).
  Mondays are NOT skipped (brief says only "outside the weekend pause").
  (a) fear: BTC DVOL (last hourly row with t_open + 1h <= decision) percentile within its trailing 365 days
      of hourly closes >= P (needs >= 180 days of history - DVOL starts 2023-05) OR DVOL / DVOL 168h earlier
      - 1 >= 25%.  Long-history mode: fear = BTC 7d realized vol (42 x 4h log-ret stdev) percentile within
      its trailing 365 days >= 85%; or no fear condition at all.
  (b) coin's WEEKLY RSI(14, Wilder) on closed Monday-00:00-UTC weeks (built from complete UTC days built from
      4h bars) < R (long) / > 100-R (short).
  (c) last closed daily close < lower Bollinger(20, 2.5, population sd) OR the coin's 30-day drawdown
      (4h close / max high of the last 180 4h bars - 1) in the bottom 10% of all its prior values (>= 365 days
      of history). Short: close > upper band OR 30-day run-up (close / min low - 1) in the top 10%.
  (a) and (c) count if true at any 4h close in the last 72h (18 bars incl. the decision bar); (b) is weekly.
  Turn: the decision 4h candle closes above the prior candle's high (short: below its low).
  Entry: limit close -/+ 0.5 ATR(14, 4h), valid 8h, fills only if price trades 0.05 ATR through.
  Stop: lowest low of the last 6 4h candles - 0.1 ATR (short: highest high + 0.1 ATR); at least 1.5 ATR from
  the limit. Target: after-fee tr R. Max hold 9 days (held through weekends unless wflat=True).
IDEA 2 (FLUSH, liquidation flush reversal, 10 core coins, metrics from 2023-11):
  4h candle with OI (sum_open_interest, first vs last 5m row with t_open <= t < t_close, >= 40 rows) DOWN >= X%,
  long lower wick (lower wick >= 50% of range => close in the upper half) and a down move (its low < the lowest
  low of the prior 6 candles) -> LONG; mirror (upper wick, new 24h high) -> SHORT.
  Decision: any 4h close outside the weekend pause, or only the 08/12/16/20/00 SGT closes. Optional BTC 4h trend
  agreement (EMA50/200 on the signal bar). Entry limit close -/+ k ATR, 8h, pen 0.05 ATR. Stop: wick extreme
  -/+ 0.1 ATR. Target after-fee 2R. 48h hold, flat for the weekend (as Q/CRT).
Common: 15m execution (1h where 15m is missing - only UNI/LINK before 2023-11 in long history), 0.04% fee/side,
stop first if a bar touches both, no target on the fill bar, one open trade per coin.
R = (side*(exit-e)/e - 0.0008) / (stop_dist/e + 0.0008).
Book: book2.book([Q, C, N]) defaults on book_trades_v2.pkl Q/C; risk Q 2.0/1.0 by rex, C 1.0/0.5, N fixed;
rolling sim START+10d..START+1005d; MC 3000 paths x 60 weekly blocks, seed 7 (review/mc.py method)."""
import sys, math, bisect, statistics, pickle, random, collections, json
sys.path.insert(0, '/home/user/bitf-perps/research')
import cycle2_crt as cc
import perps, book2

S = cc.S
H, D = cc.H, cc.D
H4 = 4 * H; M15 = 15 * 60_000
FRT = 0.0008
START, END, SPLIT = cc.START, cc.END, cc.SPLIT
SCH = perps.load_config()['schedule']
SYMS = ['BTC', 'ETH', 'BNB', 'XRP', 'SOL', 'HYPE', 'ZEC', 'ADA', 'UNI', 'LINK']
load = lambda s, iv: perps.load_json(perps.cache_file(s, iv), [])
sgt = lambda t: (t // H + 8) % 24

# ---------------- BTC fear series ----------------
DV = json.load(open('/home/user/bitfunded-perps/trader/perps/cache/DVOL-BTC-1h.json'))
DVT = [r[0] + H for r in DV]; DVC = [r[4] for r in DV]


def dvol_state(T):
    k = bisect.bisect_right(DVT, T) - 1
    if k < 0 or DVT[k] < T - 3 * H:
        return None, None
    v = DVC[k]
    a = bisect.bisect_left(DVT, T - 365 * D)
    if DVT[k] - DVT[0] < 180 * D:
        pct = None
    else:
        win = DVC[a:k + 1]; pct = sum(x <= v for x in win) / len(win)
    j = bisect.bisect_left(DVT, DVT[k] - 168 * H)
    chg = v / DVC[j] - 1 if DVT[k] - DVT[j] <= 170 * H and DVT[k] - DVT[j] >= 166 * H else None
    return pct, chg


BT = cc.BT; SD = cc.SD   # BTC 4h close times, 42-bar stdev
RVP = {}
_sorted = []
for k in range(len(SD)):
    if SD[k] is None:
        continue
    # trailing-365d percentile, computed directly (2190 values)
    lo = max(0, k - 2190)
    win = [x for x in SD[lo:k + 1] if x is not None]
    if k - lo >= 2190:
        RVP[BT[k]] = sum(x <= SD[k] for x in win) / len(win)


def rv_pct(T):
    k = bisect.bisect_right(BT, T) - 1
    return RVP.get(BT[k]) if k >= 0 else None


# ---------------- per-coin indicators ----------------
_IND = {}


def ind(sym):
    if sym in _IND:
        return _IND[sym]
    b = load(sym, '4h')
    o = [x[1] for x in b]; h = [x[2] for x in b]; l = [x[3] for x in b]; c = [x[4] for x in b]
    at = perps.atr(h, l, c, 14)
    tc = [x[0] + H4 for x in b]
    # daily (complete UTC days)
    days = collections.OrderedDict()
    for x in b:
        k = x[0] // D
        d = days.get(k)
        if d is None:
            days[k] = [k * D, x[1], x[2], x[3], x[4], 1]
        else:
            d[2] = max(d[2], x[2]); d[3] = min(d[3], x[3]); d[4] = x[4]; d[5] += 1
    dr = [d for d in days.values() if d[5] == 6]
    dc = [d[4] for d in dr]
    bbl, bbu = [None] * len(dr), [None] * len(dr)
    for i in range(19, len(dr)):
        w = dc[i - 19:i + 1]; m = sum(w) / 20; sd = statistics.pstdev(w)
        bbl[i], bbu[i] = m - 2.5 * sd, m + 2.5 * sd
    dclose = [d[0] + D for d in dr]
    # weekly (Monday 00:00 UTC weeks, 7 complete days)
    wk = collections.OrderedDict()
    for d in dr:
        k = (d[0] + 3 * D) // (7 * D)
        if k not in wk:
            wk[k] = [k * 7 * D - 3 * D, d[4], 1]
        else:
            wk[k][1] = d[4]; wk[k][2] += 1
    wr = [w for w in wk.values() if w[2] == 7]
    wc = [w[1] for w in wr]; wclose = [w[0] + 7 * D for w in wr]
    rsi = [None] * len(wc); ag = al = None
    for i in range(1, len(wc)):
        ch = wc[i] - wc[i - 1]; g, ls = max(ch, 0), max(-ch, 0)
        if i < 14:
            continue
        if i == 14:
            chs = [wc[j] - wc[j - 1] for j in range(1, 15)]
            ag = sum(max(x, 0) for x in chs) / 14; al = sum(max(-x, 0) for x in chs) / 14
        else:
            ag = (ag * 13 + g) / 14; al = (al * 13 + ls) / 14
        rsi[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    # 30d drawdown / run-up percentiles (expanding history, >= 365 days)
    ddp, rup = [None] * len(b), [None] * len(b)
    hd, hr = [], []
    for i in range(179, len(b)):
        dd = c[i] / max(h[i - 179:i + 1]) - 1; ru = c[i] / min(l[i - 179:i + 1]) - 1
        if len(hd) >= 2190:
            ddp[i] = bisect.bisect_right(hd, dd) / len(hd); rup[i] = bisect.bisect_right(hr, ru) / len(hr)
        bisect.insort(hd, dd); bisect.insort(hr, ru)
    _IND[sym] = dict(b=b, o=o, h=h, l=l, c=c, at=at, tc=tc, dclose=dclose, dc=dc, bbl=bbl, bbu=bbu,
                     wclose=wclose, rsi=rsi, ddp=ddp, rup=rup)
    return _IND[sym]


def last_idx(times, T):
    return bisect.bisect_right(times, T) - 1


# ---------------- execution ----------------
_X = {}


def xbars(sym, iv):
    if (sym, iv) not in _X:
        r = load(sym, iv); _X[(sym, iv)] = (r, {x[0]: k for k, x in enumerate(r)})
    return _X[(sym, iv)]


def execute(sym, side, T, lim, stp, a, tr=2.0, pen=0.05, valid=8, hold=48, wflat=True):
    rows, idx = xbars(sym, '15m'); step = M15
    if T not in idx:
        rows, idx = xbars(sym, '1h'); step = H
        if T not in idx:
            return None
    n0 = idx[T]; s = side; n = e = None
    if (s == 1 and lim <= stp) or (s == -1 and lim >= stp):
        return None
    for m in range(n0, min(len(rows), n0 + valid * H // step)):
        x = rows[m]
        if (s == 1 and x[3] <= lim - pen * a) or (s == -1 and x[2] >= lim + pen * a):
            n, e = m, (min(x[1], lim) if s == 1 else max(x[1], lim)); break
    if n is None:
        return {'filled': False}
    if (s == 1 and stp >= e) or (s == -1 and stp <= e):
        return {'filled': False}
    d = abs(e - stp)
    if d / e < 0.002:
        return {'filled': False}
    tgt = e + s * (tr * (d + FRT * e) + FRT * e)
    flat = perps.next_weekend_stop(rows[n][0], SCH) if wflat else 1 << 62
    px = why = None
    for m in range(n, min(len(rows), n + hold * H // step)):
        o, hh, ll = rows[m][1], rows[m][2], rows[m][3]
        if rows[m][0] >= flat:
            px, why = o, 'weekend'; break
        if (s == 1 and ll <= stp) or (s == -1 and hh >= stp):
            px = ((min(o, stp) if s == 1 else max(o, stp)) if m > n else stp); why = 'stop'; break
        if m > n and ((s == 1 and hh >= tgt) or (s == -1 and ll <= tgt)):
            px, why = tgt, 'target'; break
    if px is None:
        px, why = rows[m][4], 'time'
    r = (s * (px - e) / e - FRT) / (d / e + FRT)
    return {'filled': True, 'r': r, 'exit': why, 't_in': rows[n][0], 't_out': rows[m][0] + step, 'sym': sym,
            'side': s, 'dec': T}


# ---------------- IDEA 1 ----------------
def cap(sides=(1,), P=0.85, R=35, tr=2.0, fear='dvol', wflat=False, start=START, end=END, syms=SYMS, hours=(8, 20, 0)):
    out = []
    fear_cache = {}

    def fear_ok(T):
        if fear == 'none':
            return True
        if T not in fear_cache:
            if fear == 'dvol':
                p, ch = dvol_state(T)
                fear_cache[T] = bool((p is not None and p >= P) or (ch is not None and ch >= 0.25))
            else:
                p = rv_pct(T); fear_cache[T] = bool(p is not None and p >= P)
        return fear_cache[T]

    for sym in syms:
        I = ind(sym); b, h, l, c, at, tc = I['b'], I['h'], I['l'], I['c'], I['at'], I['tc']
        busy = 0
        for i in range(200, len(b) - 1):
            T = tc[i]
            if T < start or T >= end or T < busy or sgt(T) not in hours or perps.in_weekend(T, SCH):
                continue
            a = at[i]
            for s in sides:
                if not ((s == 1 and c[i] > h[i - 1]) or (s == -1 and c[i] < l[i - 1])):
                    continue
                k = last_idx(I['wclose'], T)
                if k < 0 or I['rsi'][k] is None or T - I['wclose'][k] > 8 * D:
                    continue
                if not ((s == 1 and I['rsi'][k] < R) or (s == -1 and I['rsi'][k] > 100 - R)):
                    continue
                okc = False
                for j in range(i - 17, i + 1):
                    Tj = tc[j]; kd = last_idx(I['dclose'], Tj)
                    if kd >= 0 and I['bbl'][kd] is not None and Tj - I['dclose'][kd] <= 2 * D:
                        if (s == 1 and I['dc'][kd] < I['bbl'][kd]) or (s == -1 and I['dc'][kd] > I['bbu'][kd]):
                            okc = True; break
                    pp = I['ddp'][j] if s == 1 else I['rup'][j]
                    if pp is not None and ((s == 1 and pp <= 0.10) or (s == -1 and pp >= 0.90)):
                        okc = True; break
                if not okc:
                    continue
                if not any(fear_ok(tc[j]) for j in range(i - 17, i + 1)):
                    continue
                lim = c[i] - s * 0.5 * a
                ext = min(l[i - 5:i + 1]) - 0.1 * a if s == 1 else max(h[i - 5:i + 1]) + 0.1 * a
                stp = min(ext, lim - 1.5 * a) if s == 1 else max(ext, lim + 1.5 * a)
                r = execute(sym, s, T, lim, stp, a, tr=tr, hold=9 * 24, wflat=wflat)
                if r and r['filled']:
                    out.append(dict(r, tag='N', prio=2)); busy = r['t_out']
                break
    return sorted(out, key=lambda t: t['t_in'])


# ---------------- IDEA 2 ----------------
_M = {}


def oi_drop(sym, t0):
    if sym not in _M:
        rows = load(sym, 'metrics'); _M[sym] = ([r[0] for r in rows], [r[1] for r in rows])
    ts, oi = _M[sym]
    a = bisect.bisect_left(ts, t0); z = bisect.bisect_left(ts, t0 + H4) - 1
    if z - a + 1 < 40 or not oi[a] or not oi[z]:
        return None
    return (oi[a] - oi[z]) / oi[a] * 100


REG = cc.rq.REG


def flush(X=5, k=0.5, hours=None, btc=False, tr=2.0, sides=(1, -1)):
    out = []
    for sym in SYMS:
        I = ind(sym); b, o, h, l, c, at, tc = I['b'], I['o'], I['h'], I['l'], I['c'], I['at'], I['tc']
        busy = 0
        for i in range(210, len(b) - 1):
            T = tc[i]
            if T < START or T >= END or T < busy or perps.in_weekend(T, SCH):
                continue
            if hours is not None and sgt(T) not in hours:
                continue
            rg = h[i] - l[i]; a = at[i]
            if rg <= 0:
                continue
            lw = min(o[i], c[i]) - l[i]; uw = h[i] - max(o[i], c[i])
            s = 0
            if lw >= 0.5 * rg and l[i] < min(l[i - 6:i]):
                s = 1
            elif uw >= 0.5 * rg and h[i] > max(h[i - 6:i]):
                s = -1
            if s == 0 or s not in sides:
                continue
            dr = oi_drop(sym, b[i][0])
            if dr is None or dr < X:
                continue
            if btc:
                rg_ = REG.get(b[i][0])
                if rg_ is None or (rg_ > 0) != (s == 1):
                    continue
            lim = c[i] - s * k * a
            stp = l[i] - 0.1 * a if s == 1 else h[i] + 0.1 * a
            r = execute(sym, s, T, lim, stp, a, tr=tr, hold=48, wflat=True)
            if r and r['filled']:
                out.append(dict(r, tag='N', prio=2)); busy = r['t_out']
    return sorted(out, key=lambda t: t['t_in'])


# ---------------- reporting / book ----------------
def report_cal(tr, label):
    print('== %s (calendar years)' % label)
    yrs = sorted({perps.dt.datetime.fromtimestamp(t['t_in'] / 1000, perps.UTC).year for t in tr})
    for y in yrs:
        a = int(perps.dt.datetime(y, 1, 1, tzinfo=perps.UTC).timestamp() * 1000)
        z = int(perps.dt.datetime(y + 1, 1, 1, tzinfo=perps.UTC).timestamp() * 1000)
        xs = [t for t in tr if a <= t['t_in'] < z]
        print('   %d %s' % (y, cc.stats(xs, 12.0)))


T0, T1 = cc.T0, cc.T1


def mc(tr, risk, n=3000, seed=7, weeks_per=60):
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
        r = book2.sim(seq, risk, T0, T0 + 1)
        if r['pass'] > 0:
            ok += 1; days.append(r['med'])
    days.sort()
    return 100 * ok / n, days[len(days) // 2] if days else float('nan')


def tagged(trs):
    bk = book2.book(trs)
    return [dict(t, tag=('Qx' if t['rex'] else 'Qc') if t['tag'] == 'Q' else ('Cx' if t['rex'] else 'Cc') if t['tag'] == 'C'
                 else t['tag']) for t in bk]


def book_line(label, tr, nrisk=1.0):
    risk = {'Qx': 2.0, 'Qc': 1.0, 'Cx': 1.0, 'Cc': 0.5, 'N': nrisk}
    r = book2.sim(tr, risk, T0, T1); p, m = mc(tr, risk)
    pct = sum(t['r'] * risk[t['tag']] for t in tr if START <= t['t_in'] < END) / ((END - START) / D / 30.44)
    print('BOOK %-40s rolling %3.0f%% / %3.0fd (S1 fail %2.0f%%) | MC %4.1f%% / %3.0fd | %+.2f%%/mo | nN=%d' % (
        label, r['pass'], r['med'], r['f1'], p, m, pct, sum(t['tag'] == 'N' for t in tr)), flush=True)


def is_os_rmo(tr):
    mo = lambda a, b: (b - a) / D / 30.44
    i = [t['r'] for t in tr if t['t_in'] < SPLIT]; o = [t['r'] for t in tr if t['t_in'] >= SPLIT]
    return sum(i) / mo(START, SPLIT), sum(o) / mo(SPLIT, END)


if __name__ == '__main__':
    part = sys.argv[1] if len(sys.argv) > 1 else 'all'
    PK = pickle.load(open(S + '/book_trades_v2.pkl', 'rb')); Q, C = PK['Q'], PK['C']
    if part in ('all', '1'):
        V1 = collections.OrderedDict()
        for name, kw in (
                ('1a L P85|25% R35 2R', dict()),
                ('1b L P85|25% R35 3R', dict(tr=3.0)),
                ('1c L P90|25% R30 2R', dict(P=0.90, R=30)),
                ('1d L P80|25% R35 2R', dict(P=0.80)),
                ('1e L P85|25% R40 2R', dict(R=40)),
                ('1f S mirror P85|25% R35 2R', dict(sides=(-1,))),
                ('1g L+S P85|25% R35 2R', dict(sides=(1, -1)))):
            V1[name] = cap(**kw); cc.report(V1[name], name)
            print('   IS/OS R/mo %+.2f / %+.2f' % is_os_rmo(V1[name]), flush=True)
        pickle.dump(V1, open(S + '/cycle3_cap.pkl', 'wb'))
        best = max(V1, key=lambda k: is_os_rmo(V1[k])[0])
        print('selected on IS R/mo:', best)
        wf = cap(**dict([('1a L P85|25% R35 2R', {}), ('1b L P85|25% R35 3R', {'tr': 3.0}), ('1c L P90|25% R30 2R', {'P': .9, 'R': 30}),
                         ('1d L P80|25% R35 2R', {'P': .8}), ('1e L P85|25% R35 2R', {'R': 40}), ('1f S mirror P85|25% R35 2R', {'sides': (-1,)}),
                         ('1g L+S P85|25% R35 2R', {'sides': (1, -1)})])[best], wflat=True)
        cc.report(wf, best + ' + weekend flat (sensitivity)')
        N = V1[best]
        book_line('baseline Q+C', tagged(Q + C))
        for rk in (1.0, 0.5):
            book_line('Q+C+CAP %s @%.1f%%' % (best, rk), tagged(Q + C + N), rk)
        for rk in (1.0, 1.5, 2.0):
            book_line('CAP alone %s @%.1f%%' % (best, rk), tagged(N), rk)
        if '1a L P85|25% R35 2R' != best:
            for rk in (1.0, 1.5, 2.0):
                book_line('CAP alone 1a @%.1f%%' % rk, tagged(V1['1a L P85|25% R35 2R']), rk)
    if part in ('all', 'long'):
        t0 = int(perps.dt.datetime(2020, 7, 1, tzinfo=perps.UTC).timestamp() * 1000)
        for fear in ('none', 'rv'):
            for nm, kw in (('L R35 2R', dict()), ('L R35 3R', dict(tr=3.0))):
                tr = cap(fear=fear, start=t0, **kw)
                lbl = 'LONG-HIST fear=%s %s' % (fear, nm)
                report_cal(tr, lbl); print('   ALL %s' % cc.stats(tr, (END - t0) / D / 30.44), flush=True)
        tr = cap(fear='rv'); cc.report(tr, '3y window, RV-proxy fear (vs DVOL 1a)')
    if part in ('all', '2'):
        LIVE = (8, 12, 16, 20, 0)
        V2 = collections.OrderedDict()
        for name, kw in (
                ('2a X3 k.5 all', dict(X=3)),
                ('2b X5 k.5 all', dict(X=5)),
                ('2c X8 k.5 all', dict(X=8)),
                ('2d X5 k.25 all', dict(X=5, k=0.25)),
                ('2e X5 k.5 live', dict(X=5, hours=LIVE)),
                ('2f X5 k.5 all btc', dict(X=5, btc=True)),
                ('2g X3 k.5 all btc', dict(X=3, btc=True)),
                ('2h X3 k.25 live btc', dict(X=3, k=0.25, hours=LIVE, btc=True))):
            V2[name] = flush(**kw); cc.report(V2[name], name)
            ls = [t['r'] for t in V2[name] if t['side'] == 1]; ss = [t['r'] for t in V2[name] if t['side'] == -1]
            print('   IS/OS R/mo %+.2f / %+.2f | long n=%d %+.2fR short n=%d %+.2fR' % (
                *is_os_rmo(V2[name]), len(ls), statistics.mean(ls) if ls else 0, len(ss), statistics.mean(ss) if ss else 0), flush=True)
        pickle.dump(V2, open(S + '/cycle3_flush.pkl', 'wb'))
        best = max(V2, key=lambda k: is_os_rmo(V2[k])[0])
        print('selected on IS R/mo:', best)
        book_line('baseline Q+C', tagged(Q + C))
        for rk in (1.0, 0.5):
            book_line('Q+C+FLUSH %s @%.1f%%' % (best, rk), tagged(Q + C + V2[best]), rk)
