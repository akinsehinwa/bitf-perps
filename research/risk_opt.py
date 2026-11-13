"""Risk optimisation for Q + CRT under the Bitfunded 50K two-step rules.

Event-driven challenge simulator (more faithful than book2.sim): trades enter in time order and are sized AT
ENTRY against every limit, then booked at their exit.
  per-trade risk = base % (Q when BTC 7d vol expanding) x contracting multiplier x (CRT ratio for CRT)
                   x 0.5 while realized P&L < -dd_cut % (if enabled), capped by "finish line" sizing (if enabled)
  capped by: daily guard  (guard - realized loss today - open risk)
             max-loss room (firm max loss - buffer + realized - open risk)
             open-risk cap (cap - open risk)
             margin: notional = risk / (stop distance + 0.08% fees); margin = notional / 5 (5x);
                     per-position margin <= mpos %, total margin <= mtot % (Bitfunded: total < 65%)
  max open positions, one position per coin, max 3 new a day (SGT day).
  Fail: realized loss in an SGT day >= 5% or total realized loss >= 10% (stage 1) / 8% (stage 2).
  (Floating loss is covered because open risk counts inside the guards; stops gap rarely on 4h perps.)
  Pass: realized >= +8% (stage 1) / +5% (stage 2) with no open positions; stage 2 starts 30 min later.
Starts every day from START+10d to START+1005d (START = 2023-11-12 UTC); a stage still running at the data end
is "open". Expected days / fees per funded account treat a failure as a restart with a new $399 challenge
(renewal: E[days] = mean attempt length / P(pass), E[fees] = $399 / P(pass))."""
import sys, collections, statistics, pickle, itertools
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps

D = 86_400_000
CACHE = '/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad/risk_opt_trades.pkl'


def build_trades():
    try:
        return pickle.load(open(CACHE, 'rb'))
    except Exception:
        pass
    import qlab, cycle2_crt
    Q = []
    for g in qlab.signals():
        r = qlab.execute(g, 'atr:0.5', pen=0.05)
        if r and r.get('filled'):
            Q.append(dict(r, tag='Q', prio=0, sig_close=g['close']))
    import bisect, math
    b4 = perps.load_json(perps.cache_file('BTC', '4h'), [])
    ts = [b[0] for b in b4]; c = [b[4] for b in b4]
    lr = [0] + [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
    exp = {ts[i]: statistics.pstdev(lr[i - 41:i + 1]) > statistics.pstdev(lr[i - 83:i - 41]) for i in range(84, len(c))}
    for t in Q:
        t['rex'] = exp.get(ts[bisect.bisect_right(ts, t['sig_close'] - 4 * 3600_000) - 1])
    C = cycle2_crt.crt(fill='touch', slip=0.05, dfilt=True, hours={8, 12, 16, 20})
    for t in C:
        t['tag'] = 'C'
    pickle.dump((Q, C), open(CACHE, 'wb'))
    return Q, C


def simulate(trades, cfg, start, end_data):
    """One challenge (both stages) from `start`. Returns (result, days)."""
    acct = 100.0  # work in % of the account
    ev = [t for t in trades if t['t_in'] >= start]
    i = 0
    t_stage = start
    for tgt, mx in ((8.0, 10.0), (5.0, 8.0)):
        realized = 0.0; day = None; dpnl = 0.0
        openp = []; per_day = collections.Counter()
        result = None; losses_row = wins_row = 0
        while i < len(ev) or openp:
            nxt_in = ev[i]['t_in'] if i < len(ev) else None
            nxt_out = min(p['t_out'] for p in openp) if openp else None
            if nxt_out is not None and (nxt_in is None or nxt_out <= nxt_in):
                p = min(openp, key=lambda p: p['t_out']); openp.remove(p)
                k = perps.day_key(p['t_out'], 8)
                if k != day:
                    day, dpnl = k, 0.0
                realized += p['pnl']; dpnl += p['pnl']
                if p['pnl'] > 0:
                    wins_row += 1; losses_row = 0
                else:
                    losses_row += 1; wins_row = 0
                if -dpnl >= 5.0 or -realized >= mx:
                    return 'fail', (p['t_out'] - start) / D
                if realized >= tgt and not openp:
                    result = p['t_out']; break
                continue
            t = ev[i]; i += 1
            if t['t_in'] < t_stage:
                continue
            if realized >= tgt:
                continue
            k = perps.day_key(t['t_in'], 8)
            if k != day:
                day, dpnl = k, 0.0
            if len(openp) >= cfg['max_open'] or per_day[k] >= 3 or any(p['sym'] == t['sym'] for p in openp):
                continue
            pct = cfg['q'] * (1.0 if t['rex'] else cfg['cmult'])
            if t['tag'] == 'C':
                pct *= cfg['crt']
            if cfg['dd_cut'] and realized < -3.0:
                pct *= 0.5
            if cfg.get('ramp') and realized < cfg['ramp'][0]:
                pct *= cfg['ramp'][1]                  # start small until a cushion is banked
            if cfg.get('streak') and losses_row >= cfg['streak'][0]:
                pct *= cfg['streak'][1]                # cut size after N losses in a row
            if cfg.get('hot') and wins_row >= cfg['hot'][0]:
                pct *= cfg['hot'][1]                   # press after N wins in a row
            if cfg['finish']:
                need = (tgt - realized) / 2.0 * 1.15
                pct = min(pct, max(0.25, need))
            o_risk = sum(p['risk'] for p in openp)
            room = min(cfg['guard'] - max(0.0, -dpnl) - o_risk,
                       mx - cfg['buffer'] + realized - o_risk,
                       cfg['open_cap'] - o_risk)
            risk = min(pct, room)
            if risk < 0.2:
                if cfg.get('abandon') and realized < 0 and mx - cfg['buffer'] + realized - o_risk < 0.2 and not openp:
                    return 'fail', (t['t_in'] - start) / D   # stuck at the floor: abandon, buy a new eval
                continue
            cost = t['stop_frac'] + 0.0008
            notional = risk / cost                 # % of account
            mpos = cfg['mpos'] * 5; mtot = cfg['mtot'] * 5 - sum(p['notional'] for p in openp)
            if notional > min(mpos, mtot):
                notional = max(0.0, min(mpos, mtot)); risk = notional * cost
                if risk < 0.2:
                    continue
            openp.append({'sym': t['sym'], 't_out': t['t_out'], 'risk': risk, 'notional': notional, 'pnl': t['r'] * risk * (cfg.get('lossx', 1.0) if t['r'] < 0 else 1.0)})
            per_day[k] += 1
        if result is None:
            return 'open', (end_data - start) / D
        t_stage = result + 30 * 60_000
        while i < len(ev) and ev[i]['t_in'] < t_stage:
            i += 1
    return 'pass', (result - start) / D


def evaluate(trades, cfg, step_days=1):
    START = int(perps.dt.datetime(2023, 11, 12, tzinfo=perps.UTC).timestamp() * 1000)
    t0, t1 = START + 10 * D, START + 1005 * D
    end_data = max(t['t_out'] for t in trades)
    res = []
    s = t0
    while s < t1:
        res.append(simulate(trades, cfg, s, end_data)); s += step_days * D
    n = len(res)
    passed = sorted(d for r, d in res if r == 'pass')
    fails = [d for r, d in res if r == 'fail']
    p = len(passed) / n
    mean_attempt = statistics.mean([d for _, d in res])
    q = lambda a, x: a[int(x * (len(a) - 1))] if a else float('nan')
    return {'pass': 100 * p, 'fail': 100 * len(fails) / n, 'open': 100 * sum(r == 'open' for r, _ in res) / n,
            'med': q(passed, .5), 'p25': q(passed, .25), 'p75': q(passed, .75),
            'w60': 100 * sum(d <= 60 for d in passed) / n, 'w90': 100 * sum(d <= 90 for d in passed) / n,
            'e_days': mean_attempt / p if p else float('inf'), 'e_fees': 399 / p if p else float('inf')}


GUARDS = {
    'current': dict(guard=3.5, buffer=1.5, open_cap=3.0, max_open=3, mpos=25, mtot=50),
    'wider':   dict(guard=4.0, buffer=1.0, open_cap=4.5, max_open=3, mpos=30, mtot=60),
    'max':     dict(guard=4.5, buffer=0.5, open_cap=6.0, max_open=4, mpos=32.5, mtot=64),
}

if __name__ == '__main__':
    Q, C = build_trades()
    trades = sorted(Q + C, key=lambda t: (t['t_in'], t.get('prio', 1)))
    print('trades: Q %d (avg %+.2fR), CRT %d (avg %+.2fR)' % (len(Q), statistics.mean(t['r'] for t in Q), len(C), statistics.mean(t['r'] for t in C)))
    rows = []
    for g, q, cm, crt, dd, fin in itertools.product(GUARDS, (1.5, 2.0, 2.5, 3.0, 4.0, 5.0), (0.5, 0.75), (0.5, 1.0), (True, False), (True, False)):
        cfg = dict(GUARDS[g], q=q, cmult=cm, crt=crt, dd_cut=dd, finish=fin)
        r = evaluate(trades, cfg, step_days=2)
        rows.append((r, g, q, cm, crt, dd, fin))
    rows.sort(key=lambda x: x[0]['e_days'])
    hdr = '%-8s %4s %4s %4s %3s %3s | %5s %5s %5s | %4s %4s %4s | %4s %4s | %6s %6s'
    print(hdr % ('guards', 'Q%', 'cmul', 'crt', 'dd', 'fin', 'pass', 'fail', 'open', 'p25', 'med', 'p75', 'w60', 'w90', 'Edays', 'Efees'))
    fmt = '%-8s %4.1f %4.2f %4.1f %3s %3s | %4.0f%% %4.0f%% %4.0f%% | %4.0f %4.0f %4.0f | %3.0f%% %3.0f%% | %6.0f %6.0f'
    for r, g, q, cm, crt, dd, fin in rows[:20]:
        print(fmt % (g, q, cm, crt, 'y' if dd else 'n', 'y' if fin else 'n', r['pass'], r['fail'], r['open'], r['p25'], r['med'], r['p75'], r['w60'], r['w90'], r['e_days'], r['e_fees']))
    print('...current live setting:')
    for r, g, q, cm, crt, dd, fin in rows:
        if g == 'current' and q == 2.0 and cm == 0.5 and crt == 0.5 and dd and fin:
            print(fmt % (g, q, cm, crt, 'y', 'y', r['pass'], r['fail'], r['open'], r['p25'], r['med'], r['p75'], r['w60'], r['w90'], r['e_days'], r['e_fees']))
    pickle.dump(rows, open('/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad/risk_opt_rows.pkl', 'wb'))


def funded(trades, cfg, start, horizon_days=365, payout_every=15):
    """Funded (Trader Stage) account from `start`: static floor at -8% of the 50K start, -5% daily loss,
    withdraw realized profit every `payout_every` days if > 0 (balance back to 50K; floor unchanged),
    a payout date in a loss moves 7 days later. Trader keeps 80%; the $399 fee is refunded with the 3rd
    payout. Returns (trader_usd, blown, days_alive, n_payouts)."""
    end = start + horizon_days * D
    ev = [t for t in trades if start <= t['t_in'] < end]
    bal = 0.0; day = None; dpnl = 0.0; openp = []; per_day = collections.Counter()
    next_pay = start + payout_every * D; paid = 0.0; n_pay = 0
    wins_row = 0
    i = 0
    while i < len(ev) or openp:
        nxt_in = ev[i]['t_in'] if i < len(ev) else None
        nxt_out = min(p['t_out'] for p in openp) if openp else None
        tnext = nxt_out if nxt_out is not None and (nxt_in is None or nxt_out <= nxt_in) else nxt_in
        while next_pay <= tnext and next_pay < end:
            if bal > 0:
                paid += bal * 500 * 0.8; n_pay += 1          # % of 50K -> USD, 80% split
                if n_pay == 3:
                    paid += 399
                bal = 0.0; next_pay += payout_every * D
            else:
                next_pay += 7 * D
        if nxt_out is not None and (nxt_in is None or nxt_out <= nxt_in):
            p = min(openp, key=lambda p: p['t_out']); openp.remove(p)
            k = perps.day_key(p['t_out'], 8)
            if k != day:
                day, dpnl = k, 0.0
            bal += p['pnl']; dpnl += p['pnl']
            wins_row = wins_row + 1 if p['pnl'] > 0 else 0
            if -dpnl >= 5.0 or bal <= -8.0:
                return paid, True, (p['t_out'] - start) / D, n_pay
            continue
        t = ev[i]; i += 1
        k = perps.day_key(t['t_in'], 8)
        if k != day:
            day, dpnl = k, 0.0
        if len(openp) >= cfg['max_open'] or per_day[k] >= 3 or any(p['sym'] == t['sym'] for p in openp):
            continue
        pct = cfg['q'] * (1.0 if t['rex'] else cfg['cmult']) * (cfg['crt'] if t['tag'] == 'C' else 1.0)
        if cfg.get('hot') and wins_row >= cfg['hot'][0]:
            pct *= cfg['hot'][1]
        o_risk = sum(p['risk'] for p in openp)
        room = min(cfg['guard'] - max(0.0, -dpnl) - o_risk, 8.0 - cfg['buffer'] + bal - o_risk, cfg['open_cap'] - o_risk)
        risk = min(pct, room)
        if risk < 0.2:
            if cfg.get('abandon') and bal < 0 and 8.0 - cfg['buffer'] + bal - o_risk < 0.2 and not openp:
                return paid, True, (t['t_in'] - start) / D, n_pay   # stuck at the floor: walk away
            continue
        cost = t['stop_frac'] + 0.0008
        notional = risk / cost
        cap = min(cfg['mpos'] * 5, cfg['mtot'] * 5 - sum(p['notional'] for p in openp))
        if notional > cap:
            notional = max(0.0, cap); risk = notional * cost
            if risk < 0.2:
                continue
        openp.append({'sym': t['sym'], 't_out': t['t_out'], 'risk': risk, 'notional': notional, 'pnl': t['r'] * risk * (cfg.get('lossx', 1.0) if t['r'] < 0 else 1.0)})
        per_day[k] += 1
    if bal > 0:
        paid += bal * 500 * 0.8; n_pay += 1
    return paid, False, horizon_days, n_pay


def evaluate_funded(trades, cfg, horizon_days=365, step_days=2):
    START = int(perps.dt.datetime(2023, 11, 12, tzinfo=perps.UTC).timestamp() * 1000)
    t0 = START + 10 * D; t1 = max(t['t_out'] for t in trades) - horizon_days * D
    res = []; s = t0
    while s < t1:
        res.append(funded(trades, cfg, s, horizon_days)); s += step_days * D
    paid = sorted(r[0] for r in res)
    q = lambda x: paid[int(x * (len(paid) - 1))]
    return {'mean': statistics.mean(paid), 'med': q(.5), 'p10': q(.1), 'p90': q(.9),
            'blown': 100 * sum(r[1] for r in res) / len(res),
            'life': statistics.median(r[2] for r in res), 'pays': statistics.mean(r[3] for r in res), 'n': len(res)}
