"""Eval impact of adding the swing check-in ticket (ifvg2 G7, CHK 08/12/16/20, all 72 coins) to Q + CRT (new core 10)."""
import sys, pickle, os
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps, ifvg2, risk_opt as ro, core_swap as cs
SP = '/tmp/claude-0/-home-user-bitf-perps/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad/swing_chk.pkl'
if os.path.exists(SP):
    S = pickle.load(open(SP, 'rb'))
else:
    mk = perps.load_markets(); CR = [k for k, v in mk.items() if v['type'] == 'crypto' and v.get('binance')]
    S = [t for s in CR for t in ifvg2.run(s, G=7.0, CHK={8, 12, 16, 20})]; pickle.dump(S, open(SP, 'wb'))
for t in S:
    t.update(tag='B', prio=2, rex=True)
CORE = ['BTC', 'ETH', 'BNB', 'XRP', 'SOL', 'ADA', 'UNI', 'LINK', 'AVAX', 'LTC']
base = [t for t in cs.Q + cs.C if t['sym'] in CORE]
ev = dict(guard=4.25, buffer=1.0, open_cap=4.5, max_open=3, mpos=30, mtot=60, q=1.5, cmult=0.5, crt=0.75, dd_cut=True, finish=False, abandon=True)
print('%-40s %5s %5s | %4s %4s | %4s %4s | %6s' % ('book', 'pass', 'fail', 'p25', 'med', 'w60', 'w90', 'Edays'))
for name, extra, mult, mo in (('Q+CRT core 10 (live)', [], 0, 3), ('+ swing all 72 x0.5', S, 0.5, 3), ('+ swing all 72 x1.0', S, 1.0, 3),
                              ('+ swing x0.5, max 4 open', S, 0.5, 4), ('+ swing core 10 only x1.0', [t for t in S if t['sym'] in CORE], 1.0, 3)):
    tl = sorted(base + extra, key=lambda t: (t['t_in'], t.get('prio', 1)))
    r = ro.evaluate(tl, dict(ev, bb=mult, max_open=mo), step_days=2)
    print('%-40s %4.0f%% %4.0f%% | %4.0f %4.0f | %3.0f%% %3.0f%% | %6.0f' % (name, r['pass'], r['fail'], r['p25'], r['med'], r['w60'], r['w90'], r['e_days']))
