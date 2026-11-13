import sys, itertools, statistics, json
sys.path.insert(0, '/home/user/bitfunded-perps')
import perps
cfg = perps.load_config()
fee = cfg['firm']['fee_pct_per_side']/100; slip = cfg['strategy']['slippage_pct_per_side']/100
data = {s: perps.load_json(perps.cache_file(s, '4h'), []) for s in cfg['symbols']}
t0 = min(b[0][0] for b in data.values()) + 40*perps.DAY_MS; t1 = max(b[-1][0] for b in data.values())
q = [t0 + (t1-t0)*k/4 for k in range(5)]
days = (t1-t0)/perps.DAY_MS
res = []
for hours, setups, don, ast, tr, be, mh in itertools.product(
        ([8,16,20,0],[16,20],[8,16,20]), (['breakout'],['pullback'],['breakout','pullback']),
        (20,55), (1.5,2.5,3.5), (1.5,2.0,3.0), (0,1.0), (12,30)):
    if setups==['pullback'] and don==55: continue
    sch = dict(cfg['schedule'], scan_hours=hours)
    st = dict(cfg['strategy'], setups=setups, donchian=don, atr_stop=ast, target_r=tr, be_at_r=be, max_hold_bars=mh)
    trades = [t for s,b in data.items() for t in perps.gen_trades(s, b, st, sch) if t['t_in']>=t0]
    qs = []
    for k in range(4):
        rs = [perps.trade_r(t, fee, slip) for t in trades if q[k] <= t['t_in'] < q[k+1]]
        qs.append(statistics.mean(rs) if rs else 0)
    rs = [perps.trade_r(t, fee, slip) for t in trades]
    win = sum(r>0 for r in rs)/len(rs)
    res.append((sum(x>0 for x in qs), statistics.mean(qs), min(qs), qs, len(rs)/days, win, hours, '+'.join(setups), don, ast, tr, be, mh))
res.sort(key=lambda r: (r[0] >= 4, r[0] >= 3, r[2], r[1]), reverse=True)
print("pos/4 meanR  minQ   quarters                     tr/day win  hours  setup don stop tgt be hold")
for r in res[:25]:
    print("%d   %+.3f %+.3f  %s  %.2f  %2.0f%% %-12s %-17s %d %.1f %.1f %.0f %d" % (r[0], r[1], r[2], ' '.join('%+.2f'%x for x in r[3]), r[4], 100*r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12]))
print('combos', len(res), ' all-4-positive:', sum(r[0]==4 for r in res), ' 3+:', sum(r[0]>=3 for r in res))
json.dump([list(r[:2])+[r[3]]+list(r[4:]) for r in res[:40]], open('/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad/wf.json','w'))
