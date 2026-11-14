"""Money per year across the whole account cycle (user question 2026-11-14): eval at 1.75% -> pass -> funded at risk X
with 15-day payouts (80% split, $399 refunded on the 3rd payout) -> when the funded account blows or gets stuck near
the floor, buy a new eval immediately -> repeat. A failed eval also means buying a new one. One account at a time.
2-year horizon from each start date (every 3 days through the first year of data). Book = live rules: Q + CRT on the
new core 10 with skip days, swing on all 72 at half risk. Net = payouts - eval fees."""
import sys, pickle, statistics
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps, risk_opt as ro, core_swap as cs
D = 86_400_000
SP = '/tmp/claude-0/-home-user-bitf-perps/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad/'
S = pickle.load(open(SP + 'swing_chk.pkl', 'rb'))
for t in S:
    t.update(tag='B', prio=2, rex=True)
CORE = ['BTC', 'ETH', 'BNB', 'XRP', 'SOL', 'ADA', 'UNI', 'LINK', 'AVAX', 'LTC']
wd = lambda t: perps.local_dt(t, 8).strftime('%a')
q = [t for t in cs.Q if t['sym'] in CORE and wd(t.get('sig_close', t['t_in'])) not in ('Mon', 'Sat', 'Sun')]
c = [t for t in cs.C if t['sym'] in CORE and wd(t['dec']) not in ('Fri', 'Sat')]
book = sorted(q + c + S, key=lambda t: (t['t_in'], t.get('prio', 1)))
END = max(t['t_out'] for t in book)
EV = dict(guard=4.25, buffer=1.0, open_cap=4.5, max_open=3, mpos=30, mtot=60, q=1.75, cmult=0.5, crt=0.75, dd_cut=True,
          finish=False, abandon=True, bb=0.5)
FD = dict(guard=4.5, buffer=0.25, open_cap=6.0, max_open=3, mpos=30, mtot=60, cmult=0.5, crt=0.75, abandon=True, bb=0.5)
HOR = 730
START = int(perps.dt.datetime(2023, 11, 22, tzinfo=perps.UTC).timestamp() * 1000)


def chain(start, fcfg):
    t, end_h = start, start + HOR * D
    paid = fees = 0.0; n_funded = 0; funded_days = 0.0; evals = 0
    while t < end_h - 5 * D:
        fees += 399; evals += 1
        res, d = ro.simulate(book, EV, t, end_h)
        if res == 'open':
            break
        if res == 'fail':
            t += max(1, d) * D; continue
        t += (d + 1) * D; n_funded += 1
        p, blown, life, npay = ro.funded(book, fcfg, t, horizon_days=max(1, (end_h - t) / D), payout_every=15)
        paid += p; funded_days += life; t += (life + 1) * D
    return paid - fees, paid, fees, n_funded, funded_days, evals


if __name__ == '__main__':
    starts = list(range(START, END - HOR * D, 3 * D))
    print('%d start dates, 2-year chains. Eval risk 1.75%%.' % len(starts))
    print('%-14s | %9s %9s %9s %9s | %7s %8s %7s %9s' % ('funded risk', 'net/yr', 'median', 'worst10%', 'best10%', 'evals', 'funded#', '%time', 'fees/yr'))
    for r in (0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0):
        res = [chain(s, dict(FD, q=r)) for s in starts]
        net = sorted(x[0] / 2 for x in res)
        q_ = lambda p: net[int(p * (len(net) - 1))]
        print('%-14s | %9.0f %9.0f %9.0f %9.0f | %7.1f %8.1f %6.0f%% %9.0f' % (
            '%.2f%%' % r, statistics.mean(net), q_(.5), q_(.1), q_(.9), statistics.mean(x[5] for x in res) / 2,
            statistics.mean(x[3] for x in res) / 2, 100 * statistics.mean(x[4] for x in res) / HOR, statistics.mean(x[2] for x in res) / 2), flush=True)
