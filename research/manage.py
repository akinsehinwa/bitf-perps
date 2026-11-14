"""Trade management lab: does one consistent management action beat "set 2R and walk away"?

Trades (same entries as the house backtests): Q (live, 15m), CRT (live, 15m), iFVG retrace (user's rules,
base and big-leg k3/G8, 1h). Each trade is re-walked from its fill with a management rule:
  tgt x      full exit at after-fee x R
  be x       stop moved to ENTRY (Bitfunded will not let a stop go past entry) once price reaches x R
  part f@x   close fraction f at x R (separate TP order), rest rides to the target
  +be        after the partial fills, stop to entry
House rules: stop first if a bar touches both; nothing but the stop on the fill bar; a BE/partial set on a bar is
active from the next bar; 0.04% fee per side on every piece; weekend flat at Sat 04:00 SGT; max hold as the strategy.
Also reports MFE: of the trades that hit the full stop, how far into profit they got first."""
import sys, statistics, collections, pickle, os
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps
FRT = 0.0008; H = 3600_000
SCH = perps.load_config()['schedule']
CACHE = '/tmp/claude-0/-home-user-bitf-perps/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad/manage_trades.pkl'
_bars = {}


def bars(sym, iv):
    if (sym, iv) not in _bars:
        rows = perps.load_json(perps.cache_file(sym, iv), [])
        _bars[(sym, iv)] = (rows, {r[0]: k for k, r in enumerate(rows)})
    return _bars[(sym, iv)]


def trades():
    if os.path.exists(CACHE):
        return pickle.load(open(CACHE, 'rb'))
    import qlab, cycle2_crt, ifvg_lab
    out = {}
    out['Q'] = [dict(r, iv='15m', hold=48) for g in qlab.signals() for r in [qlab.execute(g, 'atr:0.5', pen=0.05)]
                if r and r.get('filled')]
    out['CRT'] = [dict(t, iv='15m', hold=24) for t in cycle2_crt.crt(fill='touch', slip=0.05, dfilt=True, hours={8, 12, 16, 20})]
    out['iFVG rules'] = [dict(t, iv='1h', hold=72) for t in ifvg_lab.book(ifvg_lab.USER)]
    out['iFVG big legs'] = [dict(t, iv='1h', hold=72) for t in ifvg_lab.book(ifvg_lab.USER, k=3.0, G=8.0)]
    pickle.dump(out, open(CACHE, 'wb'))
    return out


def walk(t, tgt=2.0, be=None, part=None, be_after_part=False):
    rows, idx = bars(t['sym'], t['iv'])
    n = idx.get(t['t_in'])
    if n is None:
        return None
    s, e, stp = t['side'], t['e'], t['stp']
    d = abs(e - stp)
    lvl = lambda x: e + s * (x * (d + FRT * e) + FRT * e)
    R = lambda px: (s * (px - e) / e - FRT) / (d / e + FRT)
    step = 4 if t['iv'] == '15m' else 1
    flat = perps.next_weekend_stop(rows[n][0], SCH)
    left = 1.0; got = 0.0; cur = stp; mfe = 0.0; part_done = False; pend_stop = None
    tp = lvl(tgt)
    for m in range(n, min(len(rows), n + t['hold'] * step)):
        o, h, l = rows[m][1], rows[m][2], rows[m][3]
        if pend_stop is not None:
            cur = pend_stop; pend_stop = None
        if rows[m][0] >= flat:
            return got + left * R(o), mfe, 'weekend'
        if (s == 1 and l <= cur) or (s == -1 and h >= cur):
            px = (min(o, cur) if s == 1 else max(o, cur)) if m > n else cur
            return got + left * R(px), mfe, 'stop' if cur == stp else 'be'
        fav = h if s == 1 else l
        if m > n:
            mfe = max(mfe, (s * (fav - e) / e - FRT) / (d / e + FRT))
            if part and not part_done and (fav - lvl(part[1])) * s >= 0:
                got += part[0] * part[1]; left -= part[0]; part_done = True
                if be_after_part:
                    pend_stop = e
            if (fav - tp) * s >= 0:
                return got + left * tgt, mfe, 'target'
            if be is not None and (fav - lvl(be)) * s >= 0 and cur == stp:
                pend_stop = e
    return got + left * R(rows[m][4]), mfe, 'time'


RULES = [('2R, hands off (baseline)', dict()),
         ('target 1R', dict(tgt=1.0)), ('target 1.5R', dict(tgt=1.5)),
         ('BE at 0.5R', dict(be=0.5)), ('BE at 0.75R', dict(be=0.75)), ('BE at 1R', dict(be=1.0)), ('BE at 1.5R', dict(be=1.5)),
         ('half off at 0.5R', dict(part=(0.5, 0.5))), ('half off at 0.5R + BE', dict(part=(0.5, 0.5), be_after_part=True)),
         ('half off at 1R', dict(part=(0.5, 1.0))), ('half off at 1R + BE', dict(part=(0.5, 1.0), be_after_part=True)),
         ('third off at 1R + BE', dict(part=(1 / 3, 1.0), be_after_part=True)),
         ('3R, hands off', dict(tgt=3.0)), ('half off at 1R + BE, rest 3R', dict(tgt=3.0, part=(0.5, 1.0), be_after_part=True))]

if __name__ == '__main__':
    T = trades()
    for name, tl in T.items():
        base = [walk(t) for t in tl]; ok = [(t, b) for t, b in zip(tl, base) if b]
        print('\n== %s: %d trades' % (name, len(ok)))
        stopped = [b for _, b in ok if b[2] == 'stop']
        if stopped:
            print('   full-stop losers: %d. Before stopping out they reached: +0.5R %.0f%% | +1R %.0f%% | +1.5R %.0f%%' % (
                len(stopped), *[100 * sum(b[1] >= x for b in stopped) / len(stopped) for x in (0.5, 1.0, 1.5)]))
        print('   %-32s %5s %6s %7s %6s %6s' % ('rule', 'win', 'avg R', 'total R', 'maxDD', 'worst10'))
        for rn, kw in RULES:
            rs = [r for t in [t for t, _ in ok] for r in [walk(t, **kw)] if r]
            vals = [r[0] for r in rs]
            eq = pk = dd = 0
            for v in vals:
                eq += v; pk = max(pk, eq); dd = max(dd, pk - eq)
            roll = min(sum(vals[i:i + 10]) for i in range(len(vals) - 9))
            print('   %-32s %4.0f%% %+6.3f %+7.1f %6.1f %+6.1f' % (rn, 100 * sum(v > 0 for v in vals) / len(vals),
                  statistics.mean(vals), sum(vals), dd, roll))
