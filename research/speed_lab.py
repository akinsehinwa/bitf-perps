"""Speed lab: can trade management (lower targets, break-even, partials) or a looser Q signal set
(more trades) shorten the time to pass?  Part A: Q management grid on the live signals.
Part B: looser signal sets.  Results cached in the scratchpad.  House rules: pen 0.05 limit fills,
0.04% fee/side, stop first, no target on the fill bar, 70/30 split at 2025-12-18."""
import sys, statistics, pickle, itertools, os
sys.path.insert(0, '/home/user/bitf-perps/research'); sys.path.insert(0, '/home/user/bitfunded-perps')
import perps, qlab
D = 86_400_000
SPLIT = int(perps.dt.datetime(2025, 12, 18, tzinfo=perps.UTC).timestamp() * 1000)
S = '/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad/'
MONTHS = 36.0


def stats(rs_t):
    rs = [t['r'] for t in rs_t]
    if not rs:
        return None
    eq = pk = dd = 0
    for t in sorted(rs_t, key=lambda t: t['t_out']):
        eq += t['r']; pk = max(pk, eq); dd = max(dd, pk - eq)
    isr = [t['r'] for t in rs_t if t['t_in'] < SPLIT]; osr = [t['r'] for t in rs_t if t['t_in'] >= SPLIT]
    return dict(n=len(rs), mo=len(rs) / MONTHS, win=100 * sum(r > 0 for r in rs) / len(rs), avg=statistics.mean(rs),
                rmo=sum(rs) / MONTHS, dd=dd, IS=statistics.mean(isr) if isr else 0, OS=statistics.mean(osr) if osr else 0,
                sd=statistics.pstdev(rs))


def run(sigs, **kw):
    out = []
    for g in sigs:
        r = qlab.execute(g, 'atr:0.5', pen=0.05, **kw)
        if r and r.get('filled'):
            out.append(dict(r, sig_close=g['close']))
    return out


def line(label, s):
    print('%-38s n=%4d %4.1f/mo win %3.0f%% avg %+.3fR sd %.2f %+5.2fR/mo dd %4.1fR | IS %+.2f OS %+.2f' % (
        label, s['n'], s['mo'], s['win'], s['avg'], s['sd'], s['rmo'], s['dd'], s['IS'], s['OS']))


if __name__ == '__main__':
    part = sys.argv[1] if len(sys.argv) > 1 else 'A'
    if part == 'A':
        sigs = qlab.signals()
        print('live Q signals:', len(sigs))
        res = {}
        for tr, be, pt in itertools.product((0.5, 0.75, 1.0, 1.5, 2.0, 3.0), (0, 0.5, 1.0), (0, 1)):
            if pt and tr <= 1.0:
                continue
            s = stats(run(sigs, tr=tr, be=be, part=pt)); res[(tr, be, pt)] = s
            line('tr %.2f be %.1f part %d' % (tr, be, pt), s)
        pickle.dump(res, open(S + 'speed_A.pkl', 'wb'))
    else:
        ST, SCH = qlab.ST, qlab.SCH
        allh = dict(SCH, scan_hours=[0, 4, 8, 12, 16, 20])
        variants = {
            'live': (ST, SCH),
            'mon on': (ST, dict(SCH, skip_days=[])),
            'all 6 scans': (ST, dict(allh)),
            'all scans + mon': (ST, dict(allh, skip_days=[])),
            'body 0.75': (dict(ST, min_body_atr=0.75), SCH),
            'body 0.5': (dict(ST, min_body_atr=0.5), SCH),
            'donch 30': (dict(ST, donchian=30), SCH),
            'donch 20': (dict(ST, donchian=20), SCH),
            'no regime': (dict(ST, regime_filter=False), SCH),
            'loose: 6sc+mon+body.75': (dict(ST, min_body_atr=0.75), dict(allh, skip_days=[])),
            'loose: 6sc+mon+body.75+d30': (dict(ST, min_body_atr=0.75, donchian=30), dict(allh, skip_days=[])),
        }
        trs = [(2.0, 0, 0), (1.0, 0, 0), (1.5, 0, 0)]
        keep = {}
        for name, (st, sch) in variants.items():
            sigs = qlab.signals(st, sch)
            for tr, be, pt in trs:
                tl = run(sigs, tr=tr, be=be, part=pt)
                s = stats(tl); line('%s tr%.1f' % (name, tr), s)
                keep[(name, tr)] = tl
        pickle.dump(keep, open(S + 'speed_B.pkl', 'wb'))
