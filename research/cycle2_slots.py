"""Cycle 2 - rank-based slot priority ("ticket desk") vs the fill-time FCFS book.

Rule under test (pre-specified, 7 variants):
  Today book2.book gives slots first-come-first-served by FILL time (Q before CRT on ties): max 3 open,
  3 new per SGT day, one per coin. The ticket desk allocates at SIGNAL time instead:
    * decision times: Q and W at their 4h signal close (08/20/00 SGT scans); CRT at the 4h close that ends
      its candle 2 (C3 opens; the stop-entry order lives only during C3).
    * at each decision time collect all new tickets, sort by the variant's rank key, and place them while
      (open positions + pending tickets) < 3, no position/ticket on the same coin, and < 3 tickets placed
      that SGT day (the daily cap counts PLACED tickets - a desk assumption).
    * a placed ticket holds its slot from the decision time until t_out if it fills, else until expiry
      (Q/W limit: signal close + 8h; CRT stop order: C3 close = decision + 4h). Unplaced tickets are dropped.
  Ticket pools:
    Q  : qlab.signals() + qlab.execute(sig, 'atr:0.5', pen=0.05) (15m fills), unfilled kept as reservations.
    C  : crt3 logic (htf=4h, btc=1, defaults) re-run here so unfilled stop orders also exist, plus the BTC daily
         EMA20/50 filter daily.bias('BTC', decision, 'ema') == side.
    W  : h3_regime extra-coin Q (1h fills, pen 0.05) with core breadth >= 3, unfilled kept as reservations.
  Variants: a  fill-time FCFS book2.book(Q+C) (baseline)       b  ticket desk, no ranking (Q before C, coin order)
            c  rank by breadth desc, then Q > W > C          d  rank by expected R per ticket for strategy x BTC
               vol regime, buckets estimated ONLY on tickets decided before 2025-11-12 (unfilled = 0R)
            e  c with W tickets                               f  d with W tickets     g  b with W tickets (Q > W > C)
  Breadth of a ticket = number of the 10 core coins printing a raw 4h breakout on the bar that closes at the
  decision time (for CRT that is its C2 bar). Risk: BTC 7d realized vol (42 x 4h stdev vs the prior 42, closed
  bars at the decision time) expanding -> Q 2.0%, W 2.0%, CRT 1.0%; contracting -> 1.0%, 1.0%, 0.5%.
  Sim: book2.sim rolling starts START+10d..START+1005d, and a 3000-path weekly-block Monte Carlo (60 weeks,
  blocks from START+10d..START+1005d, seed 7, the rev/mc.py method)."""
import sys, os, math, bisect, statistics, pickle, collections, random
S = '/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad'
sys.argv = sys.argv[:1]
sys.path.insert(0, S); sys.path.insert(0, '/home/user/bitfunded-perps'); sys.path.insert(1, '/home/user/bitfunded-perps/research')
os.chdir('/home/user/bitfunded-perps')
import perps, qlab, book2, daily, rq
import h3_regime as h3
H = perps.HOUR_MS; H4 = 4 * H; D = 86_400_000; M15 = 15 * 60_000; FEE = 0.0004
START = qlab.START; END = START + 1096 * D
SPLIT = int(perps.dt.datetime(2025, 12, 18, tzinfo=perps.UTC).timestamp() * 1000)
RANK_CUT = int(perps.dt.datetime(2025, 11, 12, tzinfo=perps.UTC).timestamp() * 1000)
CORE = qlab.SYMS; CORDER = {s: k for k, s in enumerate(CORE)}
PRIO = {'Q': 0, 'W': 1, 'C': 2}


def breadth(t_close):
    return h3.RAW[t_close - H4]


def vexp(t):
    return h3.vol_state(t)[0]


# ---------------- Q tickets
def q_tickets():
    out = []
    for g in qlab.signals():
        r = qlab.execute(g, 'atr:0.5', pen=0.05)
        if r is None:
            continue
        tk = dict(sym=g['sym'], side=g['side'], tag='Q', dec=g['close'], exp=g['close'] + 8 * H, br=g['f']['breadth'],
                  filled=bool(r.get('filled')))
        if tk['filled']:
            tk.update(t_in=r['t_in'], t_out=r['t_out'], r=r['r'])
        out.append(tk)
    return out


# ---------------- CRT tickets (copy of crt3.run, htf=4h btc=1 defaults, keeps unfilled stop orders)
def c_run(sym):
    b15 = perps.load_json(perps.cache_file(sym, '15m'), [])
    if len(b15) < 2000:
        return []
    i15 = {x[0]: k for k, x in enumerate(b15)}
    tms = 16 * M15
    b = rq.aggregate(b15, tms)
    o = [x[1] for x in b]; h = [x[2] for x in b]; l = [x[3] for x in b]; c = [x[4] for x in b]
    at = perps.atr(h, l, c, 14)
    out, busy, days = [], 0, collections.Counter()
    for i in range(20, len(b) - 1):
        a = at[i]; t3 = b[i][0] + tms
        if a is None or t3 < rq.START or t3 < busy or perps.in_weekend(t3, rq.sch) or days[t3 // D] >= 1:
            continue
        j = i - 1; rng1 = h[j] - l[j]
        if rng1 <= 0 or abs(c[j] - o[j]) < 0.7 * rng1 or rng1 < 1.0 * a:
            continue
        bull1 = c[j] > o[j]
        if bull1 and h[i] > h[j] and l[j] < c[i] < h[j]:
            side, sweep, trig, tgt = -1, h[i], l[i], l[j]
        elif not bull1 and l[i] < l[j] and l[j] < c[i] < h[j]:
            side, sweep, trig, tgt = 1, l[i], h[i], h[j]
        else:
            continue
        if h[i] - l[i] <= 0:
            continue
        r = rq.REG.get((t3 // H4) * H4 - H4)
        if r is None or (r > 0) != (side == 1):
            continue
        if daily.bias('BTC', t3, 'ema') != side:
            continue
        stop = sweep - side * 0.1 * a
        n0 = i15.get(t3)
        if n0 is None:
            continue
        # a ticket is only issued if the planned R:R at the trigger clears the 1.0 floor (known at decision time)
        d0 = abs(stop - trig)
        if d0 <= 0 or d0 / trig < 0.002 or (tgt - trig) * side <= 0 or abs(tgt - trig) / d0 < 1.0:
            continue
        tk = dict(sym=sym, side=side, tag='C', dec=t3, exp=t3 + tms, br=breadth(t3), filled=False)
        n = e = None
        for m in range(n0, min(len(b15), n0 + tms // M15)):
            x = b15[m]
            if (side == -1 and x[2] >= stop) or (side == 1 and x[3] <= stop):
                break
            if (side == -1 and x[3] < trig) or (side == 1 and x[2] > trig):
                n, e = m, (min(x[1], trig) if side == -1 else max(x[1], trig)); break
        if n is not None:
            d = abs(stop - e)
            if d > 0 and d / e >= 0.002 and (tgt - e) * side > 0 and abs(tgt - e) / d >= 1.0:
                px, why, to = rq.walk(b15, n, side, e, stop, tgt, b15[n][0] + 24 * H)
                tk.update(filled=True, t_in=b15[n][0], t_out=to, r=(side * (px - e) / e - 2 * FEE) / (d / e + 2 * FEE))
                busy = to; days[t3 // D] += 1
        out.append(tk)
    return out


# ---------------- W tickets (copy of h3_regime.gen, keeps unfilled limits)
def w_run(sym, pen=0.05):
    bars4, bars1 = h3.load(sym, '4h'), h3.load(sym, '1h')
    if len(bars4) < 300 or not bars1:
        return []
    st = h3.ST; ind = perps.indicators(bars4, st); idx = {x[0]: n for n, x in enumerate(bars1)}
    reg = perps.btc_regime(h3.B4, st); hold = st['max_hold_bars'] * 4
    out, busy = [], 0
    for i in range(st['ema_slow'] + 1, len(bars4) - 1):
        close_ms = ind['t'][i] + H4
        if close_ms < START or close_ms < busy or not perps.entry_allowed(close_ms, h3.SCH):
            continue
        sig = perps.signal(ind, i, st)
        if not sig:
            continue
        s = 1 if sig['side'] == 'long' else -1
        r = reg.get(ind['t'][i])
        if r is None or (r > 0) != (s == 1):
            continue
        if (daily.bias('BTC', close_ms, 'strict') or 0) * s <= 0 or (daily.bias(sym, close_ms, 'ema') or 0) * s <= 0:
            continue
        if h3.RAW[ind['t'][i]] < 3:
            continue
        n0 = idx.get(close_ms)
        if n0 is None:
            continue
        c, a = ind['c'][i], ind['atr'][i]
        stop = c - s * st['atr_stop'] * a; lim = c - s * st['limit_atr'] * a
        tk = dict(sym=sym, side=s, tag='W', dec=close_ms, exp=close_ms + st['limit_valid_hours'] * H, br=h3.RAW[ind['t'][i]],
                  filled=False)
        n = None
        for m in range(n0, min(len(bars1), n0 + st['limit_valid_hours'])):
            if (s == 1 and bars1[m][3] <= lim - pen * a) or (s == -1 and bars1[m][2] >= lim + pen * a):
                n, e = m, (min(bars1[m][1], lim) if s == 1 else max(bars1[m][1], lim)); break
        if n is not None and not ((s == 1 and stop >= e) or (s == -1 and stop <= e)):
            d = abs(e - stop)
            tgt = e + s * (st['target_r'] * (d + 2 * FEE * e) + 2 * FEE * e)
            flat = perps.next_weekend_stop(bars1[n][0], h3.SCH)
            px, why = None, 'time'
            for m in range(n, min(len(bars1), n + hold)):
                o, hh, ll = bars1[m][1], bars1[m][2], bars1[m][3]
                if bars1[m][0] >= flat:
                    px, why = o, 'weekend'; break
                if (s == 1 and ll <= stop) or (s == -1 and hh >= stop):
                    px = (min(o, stop) if s == 1 else max(o, stop)) if m > n else stop; why = 'stop'; break
                if m > n and ((s == 1 and hh >= tgt) or (s == -1 and ll <= tgt)):
                    px, why = tgt, 'target'; break
            if px is None:
                px = bars1[m][4]
            t_out = bars1[m][0] + (0 if why == 'weekend' else H)
            tk.update(filled=True, t_in=bars1[n][0], t_out=t_out, r=(s * (px - e) / e - 2 * FEE) / (d / e + 2 * FEE))
            busy = t_out
        out.append(tk)
    return out


# ---------------- allocation
def desk(tickets, key, max_open=3, per_day=3):
    placed, out, pd = [], [], collections.Counter()
    groups = collections.defaultdict(list)
    for t in tickets:
        groups[t['dec']].append(t)
    for T in sorted(groups):
        live = [p for p in placed if p['end'] > T]
        placed = live
        k = perps.day_key(T, 8)
        for t in sorted(groups[T], key=key):
            if len(placed) >= max_open or pd[k] >= per_day or any(p['sym'] == t['sym'] for p in placed):
                continue
            t = dict(t, end=t['t_out'] if t['filled'] else t['exp'])
            placed.append(t); pd[k] += 1
            if t['filled']:
                out.append(t)
    return out


def stats(tr):
    rs = [t['r'] for t in tr]
    eq = pk = dd = 0
    for t in sorted(tr, key=lambda t: t['t_out']):
        eq += t['r']; pk = max(pk, eq); dd = max(dd, pk - eq)
    mo = lambda a, b: (b - a) / D / 30.44
    Y = [START, START + 365 * D, START + 731 * D, END]
    ys = []
    for y in range(3):
        xs = [t['r'] for t in tr if Y[y] <= t['t_in'] < Y[y + 1]]
        ys.append('%+.2f/%d' % (statistics.mean(xs), len(xs)) if xs else 'n/a')
    i_s = [t['r'] for t in tr if t['t_in'] < SPLIT]; o_s = [t['r'] for t in tr if t['t_in'] >= SPLIT]
    return '%3d %4.1f/mo avg %+.3f %+5.2fR/mo DD %4.1f | %s | IS %+.2f %+.2fR/mo OS %+.2f %+.2fR/mo' % (
        len(rs), len(rs) / mo(START, END), statistics.mean(rs), sum(rs) / mo(START, END), dd, ' '.join(ys),
        statistics.mean(i_s), sum(i_s) / mo(START, SPLIT), statistics.mean(o_s), sum(o_s) / mo(SPLIT, END))


RISK = {'Qx': 2.0, 'Qc': 1.0, 'Wx': 2.0, 'Wc': 1.0, 'Cx': 1.0, 'Cc': 0.5}
T0, T1 = START + 10 * D, START + 1005 * D


def mc(tr, n=3000, seed=7, nw=60):
    rnd = random.Random(seed); W = 7 * D; wk = collections.defaultdict(list)
    for t in tr:
        if T0 <= t['t_in'] < T1:
            wk[(t['t_in'] - T0) // W].append(t)
    keys = list(range(int((T1 - T0) // W))); ok = 0; days = []
    for _ in range(n):
        seq = []
        for j in range(nw):
            w = rnd.choice(keys)
            for t in wk.get(w, []):
                off = T0 + w * W; seq.append(dict(t, t_in=t['t_in'] - off + j * W + T0, t_out=t['t_out'] - off + j * W + T0))
        r = book2.sim(seq, RISK, T0, T0 + 1)
        if r['pass'] > 0:
            ok += 1; days.append(r['med'])
    days.sort()
    return 100 * ok / n, days[len(days) // 2]


if __name__ == '__main__':
    cache = S + '/cycle2_tickets.pkl'
    if os.path.exists(cache):
        Qt, Ct, Wt = pickle.load(open(cache, 'rb'))
    else:
        Qt = q_tickets(); Ct = [t for s in rq.SYMS for t in c_run(s)]
        wsyms = sorted(set(t['sym'] for t in pickle.load(open(S + '/book_trades.pkl', 'rb'))['W']))
        Wt = [t for s in wsyms for t in w_run(s)]
        pickle.dump((Qt, Ct, Wt), open(cache, 'wb'))
    win = lambda xs: [t for t in xs if START <= t['dec'] < END and (not t['filled'] or t['t_in'] < END)]
    Qt, Ct, Wt = win(Qt), win(Ct), win(Wt)
    for t in Qt + Ct + Wt:
        t['vx'] = vexp(t['dec']); t['prio'] = PRIO[t['tag']]
    v2 = pickle.load(open(S + '/book_trades_v2.pkl', 'rb'))
    for lbl, tk, ref in (('Q', Qt, v2['Q']), ('C', Ct, v2['C']), ('W', Wt, None)):
        f = [t for t in tk if t['filled']]
        msg = '' if ref is None else ' | v2 pickle n=%d avg %+.3f, same (sym,t_in): %d' % (
            len(ref), statistics.mean(t['r'] for t in ref), len({(t['sym'], t['t_in']) for t in ref} & {(t['sym'], t['t_in']) for t in f}))
        print('%s tickets %d filled %d (%.0f%%) avg %+.3f%s' % (lbl, len(tk), len(f), 100 * len(f) / len(tk), statistics.mean(t['r'] for t in f), msg))
    # expected R per ticket by strategy x vol regime, tickets decided before RANK_CUT only
    ER = {}
    for tag, tk in (('Q', Qt), ('C', Ct), ('W', Wt)):
        for vx in (True, False):
            xs = [t.get('r', 0.0) if t['filled'] else 0.0 for t in tk if t['dec'] < RANK_CUT and t['vx'] == vx]
            ER[(tag, vx)] = statistics.mean(xs) if xs else 0.0
    print('E[R]/ticket (in-sample < 2025-11-12):', ' '.join('%s%s %+.3f' % (k[0], 'x' if k[1] else 'c', v) for k, v in ER.items()))
    fcfs = lambda t: (t['prio'], CORDER.get(t['sym'], 99), t['sym'])
    brk = lambda t: (-t['br'], t['prio'], CORDER.get(t['sym'], 99), t['sym'])
    erk = lambda t: (-ER[(t['tag'], t['vx'])], -t['br'], t['prio'], CORDER.get(t['sym'], 99), t['sym'])
    fill = lambda xs: [dict(t, prio=0 if t['tag'] == 'Q' else 1) for t in xs if t['filled']]
    V = collections.OrderedDict()
    V['a fill-FCFS'] = book2.book(fill(Qt + Ct))
    V['b desk FCFS'] = desk(Qt + Ct, fcfs)
    V['c breadth'] = desk(Qt + Ct, brk)
    V['d E[R]'] = desk(Qt + Ct, erk)
    V['e c+W'] = desk(Qt + Ct + Wt, brk)
    V['f d+W'] = desk(Qt + Ct + Wt, erk)
    V['g b+W'] = desk(Qt + Ct + Wt, fcfs)
    tagd = lambda bk: [dict(t, tag=t['tag'] + ('x' if t['vx'] else 'c')) for t in bk]
    base_v2 = [dict(t, tag=t['tag'] + ('x' if t['rex'] else 'c')) for t in book2.book(v2['Q'] + v2['C'])]
    rs = book2.sim(base_v2, RISK, T0, T1)
    print('\nreference v2-pickle baseline: roll %3.0f%% med %3.0fd | MC %.1f%% med %.0fd' % ((rs['pass'], rs['med']) + mc(base_v2)))
    print('\nvariant      n  tr/mo   avgR   R/mo   DD | by year avg/n | 70/30   || mix Q/C/W | rolling pass/med | MC pass/med')
    for k, bk in V.items():
        tb = tagd(bk); r = book2.sim(tb, RISK, T0, T1); m = mc(tb)
        mix = collections.Counter(t['tag'] for t in bk)
        print('%-11s %s || %d/%d/%d | %3.0f%% %3.0fd | %.1f%% %3.0fd' % (k, stats(bk), mix['Q'], mix['C'], mix['W'], r['pass'], r['med'], m[0], m[1]))
