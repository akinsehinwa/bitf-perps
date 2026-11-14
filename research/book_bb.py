"""Adding the BB20-engulf strategy (B) to the Q + CRT book: overlap/confluence and eval pass-rate impact.
B = bb_lab(bias='ema4h', key='hz', pat=('engulf',), n_bb=20) on the user's 9 coins (and a variant without LINK/HYPE).
Eval sim = risk_opt.simulate (both stages, rolling daily starts, one position per coin, max 3 open, 3 new/day)."""
import sys, statistics, pickle, os, collections
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import risk_opt as ro, bb_lab as B
from ifvg_lab import report
S = '/tmp/claude-0/-home-user-bitf-perps/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad/bb_trades.pkl'
Q, C = ro.build_trades()
if os.path.exists(S):
    BB = pickle.load(open(S, 'rb'))
else:
    BB = B.book(bias='ema4h', key='hz', pat=('engulf',), n_bb=20); pickle.dump(BB, open(S, 'wb'))
for t in BB:
    t.update(tag='B', prio=2, rex=True)
H = 3600_000
# --- confluence: B trade within 24h of a Q/CRT entry on the same coin and side
qc = Q + C
def near(t, pool, w=24 * H):
    return [u for u in pool if u['sym'] == t['sym'] and u['side'] == t['side'] and abs(u['t_in'] - t['t_in']) <= w]
conf = [t for t in BB if near(t, qc)]
alone = [t for t in BB if not near(t, qc)]
opp = [t for t in BB if [u for u in qc if u['sym'] == t['sym'] and u['side'] != t['side'] and abs(u['t_in'] - t['t_in']) <= 24 * H]]
print('B trades %d | Q %d | CRT %d' % (len(BB), len(Q), len(C)))
report(conf, 'B agreeing with Q/CRT (same coin+side, 24h)')
report(alone, 'B alone')
report(opp, 'B opposite to a Q/CRT trade')
qconf = [u for u in qc if near(u, BB)]
report(qconf, 'Q/CRT trades confirmed by B')
report([u for u in qc if not near(u, BB)], 'Q/CRT trades without B')
# monthly R correlation
def monthly(tl):
    m = collections.Counter()
    for t in tl:
        m[t['t_in'] // (30 * 86400_000)] += t['r']
    return m
mq, mb = monthly(qc), monthly(BB); ks = sorted(set(mq) | set(mb))
print('monthly R correlation (Q+CRT vs B): %.2f' % statistics.correlation([mq[k] for k in ks], [mb[k] for k in ks]))
# --- eval impact
safe = dict(guard=4.25, buffer=1.0, open_cap=5, max_open=3, mpos=30, mtot=60, q=1.5, cmult=0.5, crt=0.75, dd_cut=True, finish=False, abandon=True)
fast = dict(guard=3.75, buffer=0.5, open_cap=3.0, max_open=1, mpos=32.5, mtot=64, q=3.0, cmult=1.0, crt=1.0, dd_cut=False, finish=True, abandon=True, lossx=1.05)
noLH = [t for t in BB if t['sym'] not in ('LINK', 'HYPE')]
print('\n%-44s %5s %5s | %4s %4s | %4s %4s | %6s %6s' % ('book / sizing', 'pass', 'fail', 'p25', 'med', 'w60', 'w90', 'Edays', 'Efees'))
for prof, base in (('safe 1.5%', safe), ('fast 3% single', fast)):
    for name, tl, bb in (('Q+CRT', [], 0), ('Q+CRT+B x0.5', BB, 0.5), ('Q+CRT+B x0.75', BB, 0.75), ('Q+CRT+B x1.0', BB, 1.0),
                         ('Q+CRT+B(no LINK/HYPE) x0.75', noLH, 0.75)):
        trades = sorted(Q + C + tl, key=lambda t: (t['t_in'], t.get('prio', 1)))
        r = ro.evaluate(trades, dict(base, bb=bb), step_days=2)
        print('%-44s %4.0f%% %4.0f%% | %4.0f %4.0f | %3.0f%% %3.0f%% | %6.0f %6.0f' % (prof + ': ' + name, r['pass'], r['fail'], r['p25'], r['med'], r['w60'], r['w90'], r['e_days'], r['e_fees']))
