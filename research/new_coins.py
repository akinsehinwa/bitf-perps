"""PYTH, ONDO, PENDLE on the house strategies (Q, CRT, BB20-engulf, iFVG v2 big legs), same rules as the main book."""
import sys, pickle
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import qlab, cycle2_crt, bb_lab as B, ifvg2 as V
from ifvg_lab import report
NEW = ['PYTH', 'ONDO', 'PENDLE']
out = {}
q = [dict(r, tag='Q', prio=0, sig_close=g['close']) for g in qlab.signals(syms=NEW) for r in [qlab.execute(g, 'atr:0.5', pen=0.05)] if r and r.get('filled')]
c = sorted([dict(t) for s in NEW for t in cycle2_crt.run(s, fill='touch', slip=0.05, dfilt=True, hours={8, 12, 16, 20})], key=lambda t: t['t_in'])
b = B.book(NEW, bias='ema4h', key='hz', pat=('engulf',), n_bb=20)
v = V.book(NEW, G=7.0)
for name, tl in (('Q', q), ('CRT', c), ('BB20 engulf', b), ('iFVG v2 big legs (G7)', v)):
    report(tl, '%s - 3 new coins' % name)
    for s in NEW:
        report([t for t in tl if t['sym'] == s], '    ' + s)
    out[name] = tl
pickle.dump(out, open('/tmp/claude-0/-home-user-bitf-perps/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad/new_coins.pkl', 'wb'))
