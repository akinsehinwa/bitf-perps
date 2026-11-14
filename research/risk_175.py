"""Eval at 1.5% vs 1.75% base risk (Q+CRT new core 10 with skip days, swing all 72 x0.5), and funded at 1% vs 1.5%."""
import sys, pickle
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps, risk_opt as ro, core_swap as cs
SP = '/tmp/claude-0/-home-user-bitf-perps/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad/'
S = pickle.load(open(SP + 'swing_chk.pkl', 'rb'))
for t in S:
    t.update(tag='B', prio=2, rex=True)
CORE = ['BTC', 'ETH', 'BNB', 'XRP', 'SOL', 'ADA', 'UNI', 'LINK', 'AVAX', 'LTC']
wd = lambda t: perps.local_dt(t, 8).strftime('%a')
q = [t for t in cs.Q if t['sym'] in CORE and wd(t.get('sig_close', t['t_in'])) not in ('Mon', 'Sat', 'Sun')]
c = [t for t in cs.C if t['sym'] in CORE and wd(t['dec']) not in ('Fri', 'Sat')]
book = sorted(q + c + S, key=lambda t: (t['t_in'], t.get('prio', 1)))
ev = dict(guard=4.25, buffer=1.0, open_cap=4.5, max_open=3, mpos=30, mtot=60, cmult=0.5, crt=0.75, dd_cut=True, finish=False, abandon=True, bb=0.5)
print('EVAL            pass  fail |  med  Edays  w90')
for qq in (1.5, 1.75, 2.0):
    r = ro.evaluate(book, dict(ev, q=qq), step_days=2)
    print('  %.2f%%       %4.0f%% %4.0f%% | %4.0f %5.0f %4.0f%%' % (qq, r['pass'], r['fail'], r['med'], r['e_days'], r['w90']))
fd = dict(guard=4.5, buffer=0.25, open_cap=4.5, max_open=3, mpos=30, mtot=60, cmult=0.5, crt=0.75, abandon=True, bb=0.5)
print('FUNDED (1 year, 15-day payouts, your 80%)')
for qq in (1.0, 1.25, 1.5):
    f = ro.evaluate_funded(book, dict(fd, q=qq), 365)
    print('  %.2f%%   mean $%6.0f  median $%6.0f  worst10%% $%6.0f  blown %3.0f%%' % (qq, f['mean'], f['med'], f['p10'], f['blown']))
