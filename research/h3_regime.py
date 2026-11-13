"""H3: Q breakouts on the ~61 EXTRA Bitfunded coins (not the 10 core), restricted to regimes.

Rule (pre-specified, 12 variants):
  W trades = live Q signal (perps.signal, live strategy config, BTC 4h trend filter, scan hours) on each
  extra coin, 1h limit execution as perps.gen_trades_exec BUT a limit fills only if price trades through it
  by 0.05 ATR (house rule 2); kept only if BTC daily 'strict' bias and the coin's daily 'ema' bias agree with
  the side (daily candles closed before the signal close).
  Regime gates, all measured at the signal candle's close with closed bars only:
   a  vexp : BTC stdev of the last 42 4h log returns > stdev of the 42 before (7-day vol expanding)
   b  vtop : that 42-bar stdev is in the top third of its own values over the trailing 180 days
   c  br3  : >= 3 of the 10 core coins print a raw 4h breakout (perps.signal, min_body_atr=0) on that candle
   e  liq  : coin's trailing 30-day median daily quote volume (sum of 4h base vol x close) >= $100M
  Variants: all, a, b, c, a&b, a&c, b&c, a|c, e, e&a, e&c, e&a&c.
Book: book2.book([Q, C, W], per_scan_tag={'W':1}, max_same_dir=2) vs book2.book([Q, C], max_same_dir=2);
book2.sim at Q 2 / C 1 / W 1 and with the Q vol tilt (2.5% expanding / 1.25% contracting at the Q entry)."""
import sys, os, math, bisect, statistics, pickle, collections
S = '/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad'
sys.path.insert(0, S); sys.path.insert(0, '/home/user/bitfunded-perps')
os.chdir('/home/user/bitfunded-perps')
import perps, daily, book2
H = perps.HOUR_MS; H4 = 4 * H; D = 86_400_000; FEE = 0.0004
cfg = perps.load_config(); ST = dict(cfg['strategy']); SCH = cfg['schedule']; CORE = cfg['symbols']
START = int(perps.dt.datetime(2023, 11, 12, tzinfo=perps.UTC).timestamp() * 1000)
END = int(perps.dt.datetime(2026, 11, 13, tzinfo=perps.UTC).timestamp() * 1000)
SPLIT = int(perps.dt.datetime(2025, 12, 18, tzinfo=perps.UTC).timestamp() * 1000)
load = lambda s, iv: perps.load_json(perps.cache_file(s, iv), [])
PEN = 0.05

# ---- BTC realized vol (closed 4h bars only)
B4 = load('BTC', '4h'); BT = [b[0] + H4 for b in B4]      # close times
LR = [None] + [math.log(B4[k][4] / B4[k - 1][4]) for k in range(1, len(B4))]
SD = [None] * len(B4)
for k in range(43, len(B4)):
    SD[k] = statistics.pstdev(LR[k - 41:k + 1])


def vol_state(t):
    k = bisect.bisect_right(BT, t) - 1          # last BTC bar closed at or before t
    if k < 84 + 1080 or SD[k] is None or SD[k - 42] is None:
        return None, None
    exp = SD[k] > SD[k - 42]
    hist = [x for x in SD[k - 1080:k] if x is not None]
    top = sum(x < SD[k] for x in hist) / len(hist) >= 2 / 3
    return exp, top


# ---- breadth over the 10 core coins (raw breakout, any side) keyed by bar open time
RAW = collections.Counter()
st0 = dict(ST, min_body_atr=0)
for s in CORE:
    b = load(s, '4h'); ind = perps.indicators(b, st0)
    for i in range(ST['ema_slow'] + 1, len(b)):
        if perps.signal(ind, i, st0):
            RAW[b[i][0]] += 1


# ---- liquidity: trailing 30 closed UTC days median quote volume
_liq = {}


def liq(sym, t):
    if sym not in _liq:
        dv = collections.defaultdict(float); cnt = collections.Counter()
        for b in load(sym, '4h'):
            dv[b[0] // D] += b[5] * b[4]; cnt[b[0] // D] += 1
        ks = sorted(k for k in dv if cnt[k] == 6)
        _liq[sym] = (ks, [dv[k] for k in ks])
    ks, vs = _liq[sym]
    j = bisect.bisect_right(ks, t // D - 1)          # days fully closed before t
    w = vs[max(0, j - 30):j]
    return statistics.median(w) if len(w) >= 20 else 0.0


def gen(sym, pen=PEN):
    """Copy of perps.gen_trades_exec (live config) with a through-the-limit fill penalty and features."""
    bars4, bars1 = load(sym, '4h'), load(sym, '1h')
    if len(bars4) < 300 or not bars1:
        return []
    st = ST; ind = perps.indicators(bars4, st); idx = {b[0]: n for n, b in enumerate(bars1)}
    reg = perps.btc_regime(B4, st); hold = st['max_hold_bars'] * 4
    out, busy = [], 0
    for i in range(st['ema_slow'] + 1, len(bars4) - 1):
        close_ms = ind['t'][i] + H4
        if close_ms < START or close_ms < busy or not perps.entry_allowed(close_ms, SCH):
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
        n0 = idx.get(close_ms)
        if n0 is None:
            continue
        c, a = ind['c'][i], ind['atr'][i]
        stop = c - s * st['atr_stop'] * a; lim = c - s * st['limit_atr'] * a
        n = None
        for m in range(n0, min(len(bars1), n0 + st['limit_valid_hours'])):
            if (s == 1 and bars1[m][3] <= lim - pen * a) or (s == -1 and bars1[m][2] >= lim + pen * a):
                n, e = m, (min(bars1[m][1], lim) if s == 1 else max(bars1[m][1], lim)); break
        if n is None:
            continue
        d = abs(e - stop)
        if (s == 1 and stop >= e) or (s == -1 and stop <= e):
            continue
        tgt = e + s * (st['target_r'] * (d + 2 * FEE * e) + 2 * FEE * e)
        flat = perps.next_weekend_stop(bars1[n][0], SCH)
        px, why = None, 'time'
        for m in range(n, min(len(bars1), n + hold)):
            o, h, l = bars1[m][1], bars1[m][2], bars1[m][3]
            if bars1[m][0] >= flat:
                px, why = o, 'weekend'; break
            if (s == 1 and l <= stop) or (s == -1 and h >= stop):
                px = (min(o, stop) if s == 1 else max(o, stop)) if m > n else stop; why = 'stop'; break
            if m > n and ((s == 1 and h >= tgt) or (s == -1 and l <= tgt)):
                px, why = tgt, 'target'; break
        if px is None:
            px = bars1[m][4]
        t_out = bars1[m][0] + (0 if why == 'weekend' else H)
        R = (s * (px - e) / e - 2 * FEE) / (d / e + 2 * FEE)
        ve, vt = vol_state(close_ms)
        out.append({'sym': sym, 'side': s, 't_in': bars1[n][0], 't_out': t_out, 'r': R, 'tag': 'W', 'prio': 2,
                    'close': close_ms, 'vexp': ve, 'vtop': vt, 'br': RAW[ind['t'][i]], 'liq': liq(sym, close_ms)})
        busy = t_out
    return out


VARIANTS = {
    'all': lambda t: True,
    'a vexp': lambda t: t['vexp'],
    'b vtop': lambda t: t['vtop'],
    'c br3': lambda t: t['br'] >= 3,
    'a&b': lambda t: t['vexp'] and t['vtop'],
    'a&c': lambda t: t['vexp'] and t['br'] >= 3,
    'b&c': lambda t: t['vtop'] and t['br'] >= 3,
    'a|c': lambda t: t['vexp'] or t['br'] >= 3,
    'e liq100': lambda t: t['liq'] >= 1e8,
    'e&a': lambda t: t['liq'] >= 1e8 and t['vexp'],
    'e&c': lambda t: t['liq'] >= 1e8 and t['br'] >= 3,
    'e&a&c': lambda t: t['liq'] >= 1e8 and t['vexp'] and t['br'] >= 3,
}


def stats(tr):
    rs = [t['r'] for t in tr]
    if not rs:
        return dict(n=0, tpm=0, win=0, avg=0, pf=0, rpm=0, dd=0, y=['n/a'] * 3, IS=0, OS=0)
    eq = pk = dd = 0
    for t in sorted(tr, key=lambda t: t['t_out']):
        eq += t['r']; pk = max(pk, eq); dd = max(dd, pk - eq)
    gw = sum(x for x in rs if x > 0); gl = -sum(x for x in rs if x <= 0)
    Y = [START, START + 365 * D, START + 731 * D, END]
    ys = []
    for y in range(3):
        xs = [t['r'] for t in tr if Y[y] <= t['t_in'] < Y[y + 1]]
        ys.append('%+.2f(%d)' % (statistics.mean(xs), len(xs)) if xs else 'n/a')
    half = lambda a, b: [t['r'] for t in tr if a <= t['t_in'] < b]
    i_s, o_s = half(START, SPLIT), half(SPLIT, END)
    mo = (END - START) / D / 30.44
    return dict(n=len(rs), tpm=len(rs) / mo, win=100 * sum(x > 0 for x in rs) / len(rs), avg=statistics.mean(rs),
                pf=gw / gl if gl else 9, rpm=sum(rs) / mo, dd=dd, y=ys,
                IS=statistics.mean(i_s) if i_s else 0, OS=statistics.mean(o_s) if o_s else 0,
                nIS=len(i_s), nOS=len(o_s))


def line(lbl, s):
    return '%-9s n=%4d %4.1f/mo win %2.0f%% avg %+.3fR pf %.2f %+5.2fR/mo DD %5.1fR | %s | IS %+.2f(%d) OS %+.2f(%d)' % (
        lbl, s['n'], s['tpm'], s['win'], s['avg'], s['pf'], s['rpm'], s['dd'], ' '.join(s['y']), s['IS'], s.get('nIS', 0),
        s['OS'], s.get('nOS', 0))


def tilt(tr):
    out = []
    for t in tr:
        if t['tag'] == 'Q':
            ve, _ = vol_state(t['t_in'])
            t = dict(t, tag='Qx' if ve else 'Qc')
        out.append(t)
    return out


if __name__ == '__main__':
    bt = pickle.load(open(S + '/book_trades.pkl', 'rb'))
    Q, C = bt['Q'], bt['C']
    syms = sorted(set(t['sym'] for t in bt['W']))
    W = [t for s in syms for t in gen(s)]
    W = [t for t in W if START <= t['t_in'] < END]
    print('pickle W: n=%d avg %+.3f | regenerated (pen %.2f): n=%d avg %+.3f' % (
        len(bt['W']), statistics.mean(t['r'] for t in bt['W']), PEN, len(W), statistics.mean(t['r'] for t in W)))
    print('missing vol state: %d' % sum(t['vexp'] is None for t in W))
    print('\nSTANDALONE (every extra-coin trade passing the gate, no book caps)')
    for k, f in VARIANTS.items():
        print(line(k, stats([t for t in W if f(t)])))
    R1 = {'Q': 2.0, 'C': 1.0, 'W': 1.0}; R2 = {'Qx': 2.5, 'Qc': 1.25, 'C': 1.0, 'W': 1.0}
    send = END - 120 * D
    base = book2.book(Q + C, max_same_dir=2)
    print('\nBOOK (sim starts daily %s..%s)' % (perps.local_dt(START, 8).date(), perps.local_dt(send, 8).date()))
    def bl(lbl, bk):
        w = [t for t in bk if t['tag'] == 'W']; sw = stats(w); sb = stats(bk)
        r1 = book2.sim(bk, R1, START, send); r2 = book2.sim(tilt(bk), R2, START, send)
        print('%-9s book n=%3d %+.2fR/mo DD %4.1f | W in book n=%3d avg %+.3f IS %+.2f OS %+.2f | flat: pass %3.0f%% med %3.0fd | tilt: pass %3.0f%% med %3.0fd f1 %2.0f%% f2 %2.0f%%' % (
            lbl, sb['n'], sb['rpm'], sb['dd'], sw['n'], sw['avg'], sw['IS'], sw['OS'], r1['pass'], r1['med'], r2['pass'], r2['med'], r2['f1'], r2['f2']))
    bl('Q+C', base)
    bl('pickleW', book2.book(Q + C + bt['W'], per_scan_tag={'W': 1}, max_same_dir=2))
    for k, f in VARIANTS.items():
        bl(k, book2.book(Q + C + [t for t in W if f(t)], per_scan_tag={'W': 1}, max_same_dir=2))
