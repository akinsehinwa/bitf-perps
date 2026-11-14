import sys; sys.path.insert(0, '/home/user/bitf-perps/research')
import bb_lab as B
from ifvg_lab import report
base = dict(bias='ema4h', key='hz')
for kw in (dict(n_bb=17), dict(n_bb=21), dict(n_bb=25), dict(n_bb=30), dict(n_bb=20, k_bb=2.5), dict(n_bb=20, tgt=2.0),
           dict(n_bb=20, key='none'), dict(n_bb=20, pat=('engulf',)), dict(n_bb=20, pat=('pin',))):
    report(B.book(**dict(base, **kw)), str(kw))
report(B.book(B.OTHER, **dict(base, n_bb=20)), 'n_bb 20 other 3 coins')
