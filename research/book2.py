"""Portfolio book with per-strategy risk and caps, plus the R-based challenge sim (risk per trade by tag)."""
import collections, statistics
import perps
D = 86_400_000


def book(trades, max_open=3, per_day=3, per_scan_tag=None, max_same_dir=None):
    out, openp, pd, ps = [], [], collections.Counter(), collections.Counter()
    for t in sorted(trades, key=lambda t: (t['t_in'], t.get('prio', 1))):
        openp = [p for p in openp if p['t_out'] > t['t_in']]
        k = perps.day_key(t['t_in'], 8)
        if len(openp) >= max_open or pd[k] >= per_day or any(p['sym'] == t['sym'] for p in openp):
            continue
        if per_scan_tag and t['tag'] in per_scan_tag and ps[(t['tag'], t['t_in'] // (4 * 3600_000))] >= per_scan_tag[t['tag']]:
            continue
        if max_same_dir and sum(1 for p in openp if p['side'] == t['side']) >= max_same_dir:
            continue
        out.append(t); openp.append(t); pd[k] += 1; ps[(t['tag'], t['t_in'] // (4 * 3600_000))] += 1
    return out


def sim(tr, risk, start, end):
    """risk: dict tag -> % per trade. Stage 1 +8/-10, stage 2 +5/-8, daily -5, halve risk below -3%."""
    ev = sorted(tr, key=lambda t: t['t_out'])
    res, s = [], start
    while s < end:
        t, out = s, []
        for tgt, mx in ((8, 10), (5, 8)):
            bal, day, dp, done = 0.0, None, 0.0, None
            for x in ev:
                if x['t_in'] < t:
                    continue
                k = x['t_out'] // D
                if k != day:
                    day, dp = k, 0.0
                rk = risk[x['tag']] * (0.5 if bal < -3 else 1)
                bal += x['r'] * rk; dp += x['r'] * rk
                if -dp >= 5 or -bal >= mx:
                    done = ('fail', x['t_out']); break
                if bal >= tgt:
                    done = ('pass', x['t_out']); break
            done = done or ('open', None); out.append(done)
            if done[0] != 'pass':
                break
            t = done[1] + 30 * 60_000
        res.append((s, out)); s += D
    n = len(res)
    f1 = sum(o[0][0] == 'fail' for _, o in res)
    f2 = sum(len(o) > 1 and o[1][0] == 'fail' for _, o in res)
    both = sorted((o[1][1] - s) / D for s, o in res if len(o) > 1 and o[1][0] == 'pass')
    pc = lambda q: both[int(q * len(both))] if both else float('nan')
    return {'pass': 100 * len(both) / n, 'f1': 100 * f1 / n, 'f2': 100 * f2 / n, 'med': pc(.5), 'p75': pc(.75),
            'w30': 100 * sum(x <= 30 for x in both) / n, 'w60': 100 * sum(x <= 60 for x in both) / n}


def fmt(r):
    return 'both pass %3.0f%% | fail S1 %2.0f%% S2 %2.0f%% | median %3.0f d, 75%% %3.0f d | within 30d %2.0f%%, 60d %2.0f%%' % (
        r['pass'], r['f1'], r['f2'], r['med'], r['p75'], r['w30'], r['w60'])
