"""Background data pull: 1h perp candles for all Bitfunded crypto coins (36 months), funding-rate history
(monthly archives, 38 months) for the same coins, and 5-minute 'metrics' (open interest, long/short and
taker ratios) for the 10 watchlist coins (daily archives, ~3 years)."""
import sys, io, zipfile, csv, json, os
sys.path.insert(0, '/home/user/bitfunded-perps'); import perps
from concurrent.futures import ThreadPoolExecutor
mk = perps.load_markets()
crypto = [k for k, v in mk.items() if v['type'] == 'crypto' and v.get('binance')]
def one_1h(n):
    try: return n, len(perps.download(n, '1h', 36)[0])
    except Exception as e: return n, 'ERR %s' % e
with ThreadPoolExecutor(12) as ex:
    res = list(ex.map(one_1h, crypto))
print('1h done:', len(res), 'coins', flush=True)
# funding
F = "https://data.binance.vision/data/futures/um/monthly/fundingRate/%sUSDT/%sUSDT-fundingRate-%s.zip"
months = []
d = perps.now_utc().date().replace(day=1)
for m in range(38, 0, -1):
    y, mo = d.year, d.month - m
    while mo <= 0: y, mo = y - 1, mo + 12
    months.append('%04d-%02d' % (y, mo))
def one_fund(n):
    b = mk[n]['binance']; rows = []
    for tag in months:
        blob = perps.fetch(F % (b, b, tag))
        if not blob: continue
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for name in z.namelist():
                for r in csv.reader(io.TextIOWrapper(z.open(name), 'utf-8')):
                    if r and r[0].strip().isdigit():
                        rows.append([int(r[0]), float(r[2])])
    perps.save_json(perps.path('cache', '%s-funding.json' % n), sorted(rows))
    return n, len(rows)
with ThreadPoolExecutor(12) as ex:
    res = list(ex.map(one_fund, crypto))
print('funding done:', sum(1 for _, k in res if k), 'coins', flush=True)
# metrics (5m) for the 10 watchlist coins, last ~36 months, daily files
M = "https://data.binance.vision/data/futures/um/daily/metrics/%sUSDT/%sUSDT-metrics-%s.zip"
import datetime as dt
days = [(perps.now_utc().date() - dt.timedelta(days=k)).isoformat() for k in range(1, 1100)]
def one_day(args):
    n, day = args
    blob = perps.fetch(M % (n, n, day))
    out = []
    if blob:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for name in z.namelist():
                for r in csv.reader(io.TextIOWrapper(z.open(name), 'utf-8')):
                    if r and r[0][:2] == '20':
                        try:
                            t = int(dt.datetime.strptime(r[0], '%Y-%m-%d %H:%M:%S').replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
                            out.append([t, float(r[2] or 0), float(r[3] or 0), float(r[4] or 0), float(r[5] or 0), float(r[6] or 0), float(r[7] or 0)])
                        except ValueError:
                            pass
    return out
for n in ['BTC', 'ETH', 'BNB', 'XRP', 'SOL', 'HYPE', 'ZEC', 'ADA', 'UNI', 'LINK']:
    with ThreadPoolExecutor(16) as ex:
        rows = [r for part in ex.map(one_day, [(n, d_) for d_ in days]) for r in part]
    perps.save_json(perps.path('cache', '%s-metrics.json' % n), sorted(rows))
    print('metrics', n, len(rows), flush=True)
print('ALL DONE', flush=True)
