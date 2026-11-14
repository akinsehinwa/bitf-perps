import sys; sys.path.insert(0, '/home/user/bitf-perps/research')
import ifvg2 as V
from ifvg_lab import report
for kw in (dict(G=6.0), dict(G=7.0), dict(G=10.0), dict(G=6.0, look=240), dict(G=8.0, look=240),
           dict(G=8.0, stop='origin'), dict(G=6.0, look=240, stop='origin'), dict(G=8.0, tgt=2.0)):
    report(V.book(**kw), str(kw))
tl = V.book(G=8.0)
for t in tl:
    import datetime as d
    print('   %s %-5s %s %+.2fR %s' % (d.datetime.utcfromtimestamp(t['t_in'] / 1000).date(), t['sym'], 'L' if t['side'] == 1 else 'S', t['r'], t['exit']))
report(V.book(V.OTHER, G=8.0), 'G8 other 3 coins')
