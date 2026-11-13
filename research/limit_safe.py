"""Risk vs the hard limits: per-trade cap chosen so stop-outs (with 25% stop slippage) cannot breach 5% daily / 8% total.
Eval (both stages) and funded (180d, 15d payouts). lossx = losing trades cost 1.25x their planned risk (gaps/slippage)."""
import sys, statistics
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import risk_opt as ro
Q, C = ro.build_trades(); tr = sorted(Q + C, key=lambda t: (t['t_in'], t.get('prio', 1)))
START = int(ro.perps.dt.datetime(2023, 11, 12, tzinfo=ro.perps.UTC).timestamp() * 1000); D = ro.D
end = max(t['t_out'] for t in tr)
def ev(cfg):
    res = []; s = START + 10 * D
    while s < START + 1005 * D:
        res.append(ro.simulate(tr, cfg, s, end)); s += 2 * D
    n = len(res); ps = sorted(d for r, d in res if r == 'pass'); p = len(ps) / n
    return 100 * p, ps[len(ps) // 2], statistics.mean(d for _, d in res) / p, 399 / p
def fd(cfg, H=180):
    res = []; s = START + 10 * D
    while s < end - H * D:
        res.append(ro.funded(tr, cfg, s, H, 15)); s += 2 * D
    paid = [r[0] for r in res]; life = statistics.mean(r[2] for r in res)
    return statistics.mean(paid), sorted(paid)[len(paid) // 10], 100 * statistics.mean(r[1] for r in res), life, statistics.mean(paid) / life
print('%-34s | %5s %5s %6s %6s | %7s %6s %6s %5s %6s' % ('profile', 'pass', 'med', 'Edays', 'Efees', 'fund$', 'p10$', 'blown', 'life', '$/day'))
for name, q, guard, oc, mo in [('safe 1.5% (current research)', 1.5, 4.25, 5.0, 3),
                               ('2% cap, 2 open', 2.0, 3.75, 4.0, 2), ('2.5% cap, 2 open', 2.5, 3.75, 4.0, 2),
                               ('2% x up to 3 open', 2.0, 3.75, 4.0, 3), ('3% single, 1 open', 3.0, 3.75, 3.0, 1),
                               ('5% (last reply)', 5.0, 4.9, 8.0, 4)]:
    cfg = dict(abandon=True, guard=guard, buffer=0.5, open_cap=oc, max_open=mo, mpos=32.5, mtot=64, q=q,
               cmult=0.5 if q <= 1.5 else 1.0, crt=0.75 if q <= 1.5 else 1.0, dd_cut=False, finish=True, lossx=float(sys.argv[1]) if len(sys.argv) > 1 else 1.25)
    e = ev(cfg); f = fd(cfg)
    print('%-34s | %4.0f%% %5.0f %6.0f %6.0f | %7.0f %6.0f %5.0f%% %5.0f %6.1f' % ((name,) + e + f))
