"""3-year backtest of the user's P50-T2 bot using ITS OWN functions (engine.py / p50.py, unmodified),
fed with our cached Binance USDT-M 15m bars. Offline, read-only.
  mode=faithful : the bot's order of operations (update leg on the bar, then test the fill on that same bar;
                  target allowed on the fill bar via _fill_p50's same-bar check)
  mode=strict   : fill tested against the limit as it stood BEFORE the bar (then the leg updates), and no
                  target on the fill bar (stop still checked)
Rules taken from p50.py: 4H from 15m, 2-each-side fractals, BOS close, 50% limit that trails the leg,
stop origin -/+ 0.1 ATR(14,4H) tick-rounded, after-fee 2R target, cancel at 1.618 / 12 4H bars / opposite BOS,
10-day max hold, 0.04% fee per side, one ticket or position per coin.
Book eligibility: source 4H candle opened 08:00 or 20:00 SGT (sess=1). Filters at the BOS close (+2 min):
crt=1 BTC daily CRT carry-forward bias; ema=1 BTC daily EMA20/50 trend (the bot's functions)."""
import sys, statistics, collections
from datetime import timedelta
S = '/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad'
sys.path.insert(0, S + '/tf'); sys.path.insert(0, '/home/user/bitfunded-perps'); sys.path.insert(0, S)
import engine as E, p50
import perps
P = dict(a.split('=') for a in sys.argv[1:] if '=' in a)
MODE = P.get('mode', 'faithful')
SYMS = P.get('syms', 'BTC,SOL,ZEC,HYPE,UNI,ADA,NEAR').split(',')
START = int(perps.dt.datetime(2023, 11, 12, tzinfo=perps.UTC).timestamp() * 1000)
M15 = 15 * 60_000; H4 = 4 * 3600_000


def to_dicts(rows):
    return [{"open_time": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5],
             "close_time": r[0] + M15 - 1} for r in rows]


def fast_pre(h4):
    """Same outputs as p50.precompute_symbol, O(n): latest strict 2-each-side fractal confirmed by bar i."""
    n = len(h4); atrs = E.wilder_atr(h4, 14)
    hi = [b["high"] for b in h4]; lo = [b["low"] for b in h4]
    fh = [False] * n; fl = [False] * n
    for p in range(2, n - 2):
        fh[p] = all(hi[p] > hi[j] for j in (p - 2, p - 1, p + 1, p + 2))
        fl[p] = all(lo[p] < lo[j] for j in (p - 2, p - 1, p + 1, p + 2))
    last_sh = [None] * n; last_sl = [None] * n
    sh = sl = None
    bos_long = [False] * n; bos_short = [False] * n; olow = [None] * n; ohigh = [None] * n
    for i in range(n):
        p = i - 2
        if p >= 2:
            if fh[p]: sh = {"kind": "high", "index": p, "price": hi[p]}
            if fl[p]: sl = {"kind": "low", "index": p, "price": lo[p]}
        last_sh[i], last_sl[i] = sh, sl
        if sh and h4[i]["close"] > sh["price"] and not (i > 0 and h4[i - 1]["close"] > sh["price"]):
            bos_long[i] = True; olow[i] = min(lo[sh["index"]:i + 1])
        if sl and h4[i]["close"] < sl["price"] and not (i > 0 and h4[i - 1]["close"] < sl["price"]):
            bos_short[i] = True; ohigh[i] = max(hi[sl["index"]:i + 1])
    return {"h4": h4, "atr": atrs, "bos_long": bos_long, "bos_short": bos_short,
            "origin_low": olow, "origin_high": ohigh}


def btc_filters():
    b15 = to_dicts(perps.load_json(perps.cache_file('BTC', '4h'), []))
    # dailies from 4h bars (00:00 UTC = 08:00 SGT open), closed only
    days = collections.OrderedDict()
    for b in perps.load_json(perps.cache_file('BTC', '4h'), []):
        k = b[0] // 86_400_000
        d = days.get(k)
        if d is None:
            days[k] = {"open_time": k * 86_400_000, "open": b[1], "high": b[2], "low": b[3], "close": b[4],
                       "close_time": k * 86_400_000 + 86_400_000 - 1, "n": 1}
        else:
            d["high"] = max(d["high"], b[2]); d["low"] = min(d["low"], b[3]); d["close"] = b[4]; d["n"] += 1
    daily = [d for d in days.values() if d["n"] == 6]
    return p50.build_crt_filter_events(daily), p50.build_ema_trend_rows(daily)


CRT_EV, EMA_ROWS = btc_filters()


def run(sym):
    name = sym + 'USDT'
    tick = (E.DEFAULT_FILTERS.get(name) or {"tick": 1e-6})["tick"]
    m15 = to_dicts(perps.load_json(perps.cache_file(sym, '15m'), []))
    if len(m15) < 5000:
        return []
    h4 = p50.build_4h_from_15m(m15)
    pre = fast_pre(h4)
    h4idx = {b["open_time"]: k for k, b in enumerate(h4)}
    i15 = {b["open_time"]: k for k, b in enumerate(m15)}
    out, busy = [], 0
    stats = collections.Counter()
    for i in range(30, len(h4) - 1):
        for direction in ("long", "short"):
            if not (pre["bos_long"][i] if direction == "long" else pre["bos_short"][i]):
                continue
            close_ms = h4[i]["open_time"] + H4
            if close_ms < START or close_ms < busy:
                continue
            src_hour = E.ms_to_sgt(h4[i]["open_time"]).hour
            if P.get('sess', '1') == '1' and src_hour not in (8, 20):
                stats['off_session'] += 1; continue
            when = E.ms_to_sgt(close_ms) + timedelta(minutes=2)
            if P.get('crt', '0') == '1' and not p50.crt_aligned(direction, p50.crt_filter_bias_at(CRT_EV, when)):
                stats['crt_block'] += 1; continue
            if P.get('ema', '0') == '1' and not p50.ema_aligned(direction, p50.ema_trend_at(EMA_ROWS, when)):
                stats['ema_block'] += 1; continue
            atr = pre["atr"][i]
            origin = pre["origin_low"][i] if direction == "long" else pre["origin_high"][i]
            extreme = h4[i]["high"] if direction == "long" else h4[i]["low"]
            leg0 = (extreme - origin) if direction == "long" else (origin - extreme)
            if not atr or leg0 <= 0:
                continue
            tkt = {"direction": direction, "fib": p50.FIB, "origin": origin, "extreme": extreme, "leg0": leg0,
                   "atr": atr, "limit": p50.fib_limit(direction, origin, extreme),
                   "stop": p50.round_stop((origin - 0.1 * atr) if direction == "long" else (origin + 0.1 * atr), direction, tick)}
            n0 = i15.get(close_ms)
            if n0 is None:
                continue
            expire_ms = close_ms + 12 * H4
            filled = None
            m = n0
            while m < len(m15):
                bar = m15[m]
                if bar["open_time"] >= expire_ms:
                    stats['expired'] += 1; break
                # opposite BOS at a 4H close
                if bar["open_time"] % H4 == 0 and bar["open_time"] > close_ms:
                    k = h4idx.get(bar["open_time"] - H4)
                    if k is not None:
                        if (direction == "long" and pre["bos_short"][k]) or (direction == "short" and pre["bos_long"][k]):
                            stats['opposite_bos'] += 1; break
                if MODE == 'strict' and p50.hits_limit(direction, tkt["limit"], bar):
                    filled = (m, tkt["limit"], tkt["stop"]); break
                p50.update_pullback_leg(tkt, bar, tick)
                if tkt.get("cancel_now") or tkt.get("ext_and_fill"):
                    stats['ext_1.618'] += 1; break
                if MODE != 'strict' and p50.hits_limit(direction, tkt["limit"], bar):
                    filled = (m, tkt["limit"], tkt["stop"]); break
                m += 1
            if not filled:
                busy = m15[min(m, len(m15) - 1)]["open_time"]
                continue
            m, e, stop = filled
            if (direction == "long" and stop >= e) or (direction == "short" and stop <= e):
                continue
            tgt = p50.after_fee_target(e, stop, direction, 2.0)
            px = why = None
            opened = m15[m]["open_time"]
            for q in range(m, len(m15)):
                bar = m15[q]
                hs = p50.hits_stop(direction, stop, bar)
                ht = p50.hits_target(direction, tgt, bar) and not (MODE == 'strict' and q == m)
                if hs:
                    px, why = stop, 'stop'
                elif ht:
                    px, why = tgt, 'target'
                elif bar["open_time"] + M15 >= opened + 10 * 86_400_000:
                    px, why = bar["close"], 'max_hold'
                if px is not None:
                    break
            if px is None:
                break
            side = 1 if direction == "long" else -1
            d = abs(e - stop)
            r = (side * (px - e) / e - 2 * E.FEE_RATE) / (d / e + E.FEE_RT)
            out.append({'sym': sym, 't_in': opened, 't_out': bar["open_time"] + M15, 'r': r, 'exit': why, 'side': side})
            stats['filled'] += 1
            busy = bar["open_time"] + M15
    run.stats[sym] = stats
    return out


run.stats = {}

if __name__ == '__main__':
    import family as F
    trades = sorted([t for s in SYMS for t in run(s)], key=lambda t: t['t_in'])
    rs = [t['r'] for t in trades]
    tot = collections.Counter()
    for c in run.stats.values():
        tot.update(c)
    ex = collections.Counter(t['exit'] for t in trades)
    label = ' '.join(sys.argv[1:]) or 'mode=faithful sess=1'
    print('%-34s %+.3fR win %2.0f%% pf %.2f %4.1f/mo %+5.1fR/mo | %s' % (
        label, statistics.mean(rs), 100 * sum(x > 0 for x in rs) / len(rs),
        sum(x for x in rs if x > 0) / -sum(x for x in rs if x <= 0), len(rs) / 36.5, sum(rs) / 36.5, F.yr(trades)))
    print('      exits %s | not filled: %s' % (dict(ex), {k: v for k, v in tot.items() if k != 'filled'}))
    if P.get('sim'):
        b = F.book(trades)
        for r in (1.25, 1.75):
            print('      book, risk %.2f%%: %s' % (r, F.sim(b, r)))
