"""What separates A's winners from its losers? Features at the signal (4h close), split into terciles
on the DEV period (Nov 2023 - Nov 2025), then checked on the TEST year (Nov 2025 - Nov 2026)."""
import sys, statistics, collections
sys.path.insert(0, '/home/user/bitfunded-perps')
import perps
H = perps.HOUR_MS; H4 = 4 * H; D = 86_400_000
cfg = perps.load_config(); sch = cfg['schedule']; st = dict(cfg['strategy'])
DON = int(sys.argv[1]) if len(sys.argv) > 1 else st['donchian']; st['donchian'] = DON
FEE = cfg['firm']['fee_pct_per_side'] / 100
SYMS = cfg['symbols']
CUT = int(perps.dt.datetime(2025, 11, 12, tzinfo=perps.UTC).timestamp() * 1000)
load = lambda s, iv: perps.load_json(perps.cache_file(s, iv), [])
btc4 = load('BTC', '4h')
REG = perps.btc_regime(btc4, st)
bind = perps.indicators(btc4, st)
bt = {t: k for k, t in enumerate(bind['t'])}
dxy = load('DXY', '1d'); dc = [r[1] for r in dxy]; de = perps.ema(dc, 20)
dxy_map = {r[0] // D: (dc[k] / de[k] - 1) * 100 for k, r in enumerate(dxy) if de[k]}

# breadth: how many of the 10 coins printed a breakout (any side) on each 4h bar
INDS = {s: perps.indicators(load(s, '4h'), st) for s in SYMS}
breadth = collections.Counter()
for s, ind in INDS.items():
    for i in range(st['ema_slow'] + 1, len(ind['t'])):
        if perps.signal(ind, i, st):
            breadth[ind['t'][i]] += 1


def features(sym, ind, i, side):
    c, a = ind['c'][i], ind['atr'][i]
    ef, es = ind['ef'][i], ind['es'][i]
    s = 1 if side == 'long' else -1
    lvl = ind['hh'][i] if s == 1 else ind['ll'][i]
    vol = [x for x in (load_cache[sym][k][5] for k in range(i - 20, i)) if x]
    t = ind['t'][i]
    k = bt.get(t)
    bt_trend = (bind['ef'][k] / bind['es'][k] - 1) * 100 * s if k is not None and bind['es'][k] else None
    bt_mom = (bind['c'][k] / bind['c'][k - 6] - 1) * 100 * s if k is not None and k >= 6 else None
    day = (t + H4) // D - 1
    dx = None
    for back in range(5):
        if day - back in dxy_map:
            dx = dxy_map[day - back] * -s       # positive = dollar moving in the trade's favour
            break
    rng55 = (max(ind['h'][i - 55:i]) - min(ind['l'][i - 55:i])) / a
    return {
        'side (long=1)': 1 if s == 1 else 0,
        'scan hour SGT': perps.local_dt(t + H4, 8).hour,
        'weekday (Mon=0)': perps.local_dt(t + H4, 8).weekday(),
        'breakout size (ATR past level)': (c - lvl) * s / a,
        'breakout candle body/ATR': abs(c - ind['o'][i]) / a,
        'coin trend: EMA50 vs EMA200 %': (ef / es - 1) * 100 * s,
        'coin distance from EMA50 (ATR)': (c - ef) * s / a,
        'ATR % of price (volatility)': a / c * 100,
        '55-bar range / ATR (base width)': rng55,
        'volume vs 20-bar avg': load_cache[sym][i][5] / statistics.mean(vol) if vol else None,
        'BTC trend strength %': bt_trend,
        'BTC 24h momentum % (with trade)': bt_mom,
        'breadth: coins breaking same bar': breadth[t],
        'DXY vs EMA20 % (with trade)': dx,
        'RSI14 (with trade: 100-RSI for shorts)': ind['rsi'][i] if s == 1 else 100 - ind['rsi'][i],
    }


load_cache = {}
rows = []
for sym in SYMS:
    b4 = load(sym, '4h'); b1 = load(sym, '1h'); load_cache[sym] = b4
    ind = INDS[sym]
    trades = perps.gen_trades_exec(sym, b4, b1, st, sch, {'fee': FEE, 'side': 0.0, 'hold_per_hour': 0.0}, REG)
    sig_at = {}
    for i in range(st['ema_slow'] + 1, len(b4) - 1):
        sig_at[ind['t'][i] + H4] = i
    for tr in trades:
        # signal bar = the 4h close at or before the fill, within the limit window
        close = (tr['t_in'] // H4) * H4
        i = None
        for back in range(0, 3):
            cand = close - back * H4
            if cand in sig_at and perps.signal(ind, sig_at[cand], st):
                i = sig_at[cand]; break
        if i is None:
            continue
        f = features(sym, ind, i, tr['side'])
        f['_r'] = perps.trade_r(tr, FEE, 0); f['_t'] = tr['t_in']; f['_exit'] = tr['exit']
        rows.append(f)

dev = [r for r in rows if r['_t'] < CUT]; test = [r for r in rows if r['_t'] >= CUT]
print('A trades with features: %d (dev %d, test %d). Overall avg R: dev %+.2f, test %+.2f; win: dev %.0f%%, test %.0f%%' % (
    len(rows), len(dev), len(test), statistics.mean(r['_r'] for r in dev), statistics.mean(r['_r'] for r in test),
    100 * sum(r['_r'] > 0 for r in dev) / len(dev), 100 * sum(r['_r'] > 0 for r in test) / len(test)))
cell = lambda xs: ('%+.2fR %3.0f%% n=%3d' % (statistics.mean(x['_r'] for x in xs), 100 * sum(x['_r'] > 0 for x in xs) / len(xs), len(xs))) if xs else '        n/a      '
keys = [k for k in rows[0] if not k.startswith('_')]
print('\n%-40s %-26s | %-22s %-22s %-22s' % ('feature (terciles cut on DEV)', 'cut points', 'low third', 'mid third', 'high third'))
for k in keys:
    vals = sorted(r[k] for r in dev if r[k] is not None)
    if len(set(vals)) <= 7:   # categorical
        cats = sorted(set(r[k] for r in rows if r[k] is not None))
        print('%-40s' % k)
        for c in cats:
            print('    %-36s dev %s | test %s' % (c, cell([r for r in dev if r[k] == c]), cell([r for r in test if r[k] == c])))
        continue
    q1, q2 = vals[len(vals) // 3], vals[2 * len(vals) // 3]
    b = lambda xs, lo, hi: [r for r in xs if r[k] is not None and lo <= r[k] < hi]
    inf = float('inf')
    print('%-40s %-26s | dev  %s %s %s' % (k, '<%.2f | <%.2f | >=' % (q1, q2), cell(b(dev, -inf, q1)), cell(b(dev, q1, q2)), cell(b(dev, q2, inf))))
    print('%-40s %-26s | test %s %s %s' % ('', '', cell(b(test, -inf, q1)), cell(b(test, q1, q2)), cell(b(test, q2, inf))))
import json
json.dump(rows, open('/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad/feat_rows_%d.json' % DON, 'w'))
