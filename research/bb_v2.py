import sys; sys.path.insert(0, '/home/user/bitf-perps/research')
import bb_lab as B
from ifvg_lab import report
for kw in (dict(bias='ema4h', key='hz'), dict(bias='struct', key='hz'), dict(bias='ema4h', key='none'),
           dict(bias='ema4h', key='hz', touches=2), dict(bias='ema4h', key='hz', touches=4),
           dict(bias='ema4h', key='hz', tol=0.15), dict(bias='ema4h', key='hz', tol=0.4),
           dict(bias='ema4h', key='hz', pat=('ifvg',)), dict(bias='ema4h', key='hz', buf=0.5),
           dict(bias='ema4h', key='hz', tgt=1.0), dict(bias='ema4h', key='hz', tgt=2.0), dict(bias='ema4h', key='hz', n_bb=20)):
    report(B.book(**kw), str(kw))
tl = B.book(bias='ema4h', key='hz')
for s in B.COINS:
    report([t for t in tl if t['sym'] == s], '  ema4h+hz ' + s)
report(B.book(B.OTHER, bias='ema4h', key='hz'), 'ema4h+hz other 3 coins')
