"""Strategy R: previous-day high/low liquidity sweep fade (Roboquant template), adapted to our 10 coins.
Signal candles: sig= 30m (default) / 1h / 15m, built from 15m bars. Entry and exits walk 15m bars.
Roboquant defaults: prior day = full ET calendar day; short when a bearish signal candle trades above PDH
and closes back below it inside the prior-day range (long mirrors at PDL); no engulf filter; max 1 trade a
day per coin; entries 09:45-13:00 ET; stop = 0.3 x daily ATR(14); target = 0.1 x daily ATR(14).
Market entry at the next candle's open. 0.04% fee per side, no slippage. Last 3 years only.
usage: rq.py key=val ...   (sig= slm= tpm= first= last= window=rq|all engulf= btc= maxday=)"""
import sys, statistics, collections
from zoneinfo import ZoneInfo
sys.path.insert(0, '/home/user/bitfunded-perps')
import perps

H = perps.HOUR_MS; D = 86_400_000; M15 = 15 * 60_000
cfg = perps.load_config(); sch = cfg['schedule']
FEE = float(dict(a.split('=') for a in sys.argv[1:] if '=' in a).get('fee', cfg['firm']['fee_pct_per_side'])) / 100
P = dict(a.split('=') for a in sys.argv[1:] if '=' in a)
num = lambda k, d: float(P.get(k, d))
SYMS = P.get('syms', 'BTC,ETH,BNB,XRP,SOL,HYPE,ZEC,ADA,UNI,LINK').split(',')
ET = ZoneInfo('America/New_York')
START = int(perps.dt.datetime(2023, 11, 12, tzinfo=perps.UTC).timestamp() * 1000)
REG = perps.btc_regime(perps.load_json(perps.cache_file('BTC', '4h'), []), cfg['strategy'])
SIG_MS = {'15m': M15, '30m': 2 * M15, '1h': 4 * M15}


def et_day(t):
    return perps.dt.datetime.fromtimestamp(t / 1000, ET).toordinal()


def aggregate(b15, ms):
    out = []
    for x in b15:
        k = x[0] // ms * ms
        if out and out[-1][0] == k:
            o = out[-1]; o[2] = max(o[2], x[2]); o[3] = min(o[3], x[3]); o[4] = x[4]
        else:
            out.append([k, x[1], x[2], x[3], x[4]])
    return out


def walk(b, n, side, e, stop, tgt, end_ms):
    flat = perps.next_weekend_stop(b[n][0], sch)
    m = n
    for m in range(n, len(b)):
        o, h, l = b[m][1], b[m][2], b[m][3]
        if b[m][0] >= min(flat, end_ms):
            return o, 'eod' if b[m][0] >= end_ms else 'weekend', b[m][0]
        if (side == 1 and l <= stop) or (side == -1 and h >= stop):
            return ((min(o, stop) if side == 1 else max(o, stop)) if m > n else stop), 'stop', b[m][0] + M15
        if m > n and ((side == 1 and h >= tgt) or (side == -1 and l <= tgt)):
            return tgt, 'target', b[m][0] + M15
    return b[m][4], 'time', b[m][0] + M15


def strat(sym):
    b15 = perps.load_json(perps.cache_file(sym, '15m'), [])
    if len(b15) < 2000:
        return []
    i15 = {x[0]: k for k, x in enumerate(b15)}
    sms = SIG_MS[P.get('sig', '30m')]
    b = aggregate(b15, sms)
    # ET-day ranges and daily ATR(14) known at the start of each day
    days = collections.OrderedDict()
    for x in b15:
        k = et_day(x[0])
        if k not in days:
            days[k] = [x[2], x[3], x[4], x[0]]
        else:
            d = days[k]; d[0] = max(d[0], x[2]); d[1] = min(d[1], x[3]); d[2] = x[4]
    dk = list(days)
    prev, datr, nxt, trs = {}, {}, {}, []
    for j in range(1, len(dk)):
        hi, lo, cl, _ = days[dk[j - 1]]
        pc = days[dk[j - 2]][2] if j >= 2 else None
        trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)) if pc else hi - lo)
        prev[dk[j]] = (hi, lo)
        if len(trs) >= 14:
            datr[dk[j]] = statistics.mean(trs[-14:])
        if j + 1 < len(dk):
            nxt[dk[j]] = days[dk[j + 1]][3]
    per_day = collections.Counter()
    out, busy = [], 0
    for i in range(1, len(b) - 1):
        t = b[i][0]; tc = t + sms
        if tc < START or tc < busy:
            continue
        k = et_day(t)
        if k not in prev or k not in datr or k not in nxt or per_day[k] >= int(num('maxday', 1)):
            continue
        if P.get('window', 'rq') == 'rq':
            et = perps.dt.datetime.fromtimestamp(tc / 1000, ET)
            hm = et.hour * 100 + et.minute
            if not (int(num('first', 945)) <= hm <= int(num('last', 1300))):
                continue
        if perps.in_weekend(tc, sch):
            continue
        PDH, PDL = prev[k]
        o, h, l, c = b[i][1:5]
        side = -1 if (h > PDH and PDL < c < PDH and c < o) else 1 if (l < PDL and PDL < c < PDH and c > o) else 0
        if not side:
            continue
        if P.get('engulf', '0') == '1':
            po, pc = b[i - 1][1], b[i - 1][4]
            if not (max(o, c) >= max(po, pc) and min(o, c) <= min(po, pc)):
                continue
        if P.get('btc', '0') == '1':
            r = REG.get((tc // (4 * H)) * 4 * H - 4 * H)
            if r is None or (r > 0) != (side == 1):
                continue
        n = i15.get(tc)
        if n is None:
            continue
        per_day[k] += 1
        e = b15[n][1]
        a = datr[k]
        stop = e - side * num('slm', 0.3) * a
        tgt = e + side * num('tpm', 0.1) * a
        if P.get('tgt') == 'opp':
            tgt = PDL if side == -1 else PDH
        if (tgt - e) * side <= 0:
            continue
        end = nxt[k] if P.get('eod', '1') == '1' else t + 48 * H
        px, why, to = walk(b15, n, side, e, stop, tgt, end)
        d = abs(stop - e)
        r = (side * (px - e) / e - 2 * FEE) / (d / e + 2 * FEE)
        out.append({'sym': sym, 'side': side, 't_in': b15[n][0], 't_out': to, 'r': r, 'exit': why,
                    'stop_pct': d / e * 100, 'tgt_pct': abs(tgt - e) / e * 100})
        busy = to
    return out


def table(trades, label):
    rs = [t['r'] for t in trades]
    if not rs:
        print(label, 'no trades'); return
    Y = [START, START + 365 * D, START + 730 * D, START + 1100 * D]
    cells = []
    for y in range(3):
        xs = [t['r'] for t in trades if Y[y] <= t['t_in'] < Y[y + 1]]
        cells.append('%+.3fR %2.0f%% n=%3d' % (statistics.mean(xs), 100 * sum(x > 0 for x in xs) / len(xs), len(xs)) if xs else 'n/a')
    gw = sum(x for x in rs if x > 0); gl = -sum(x for x in rs if x <= 0)
    print('%-34s %+.3fR win %2.0f%% pf %.2f %4.1f/mo %+5.1fR/mo | %s | stop %.2f%% tgt %.2f%%' % (
        label, statistics.mean(rs), 100 * sum(x > 0 for x in rs) / len(rs), gw / gl if gl else 9, len(rs) / 36.5,
        sum(rs) / 36.5, ' | '.join(cells), statistics.median(t['stop_pct'] for t in trades), statistics.median(t['tgt_pct'] for t in trades)))


if __name__ == '__main__':
    trades = sorted([t for s in SYMS for t in strat(s)], key=lambda t: t['t_in'])
    table(trades, ' '.join(sys.argv[1:]) or 'Roboquant defaults, 30m')
