import sys; sys.path.insert(0, '/home/user/bitf-perps/research')
import bb_lab as B
from ifvg_lab import report
base = dict(bias='ema4h', key='hz', pat=('engulf',))
for kw in (dict(n_bb=17), dict(n_bb=23), dict(n_bb=25), dict(n_bb=20, k_bb=2.5), dict(n_bb=20, key='none')):
    report(B.book(**dict(base, **kw)), 'engulf ' + str(kw))
tl = B.book(**dict(base, n_bb=20))
for s in B.COINS:
    report([t for t in tl if t['sym'] == s], '  engulf n20 ' + s)
report(B.book(B.OTHER, **dict(base, n_bb=20)), 'engulf n20 other 3 coins')
report(B.book(B.OTHER, bias='ema4h', key='hz', n_bb=25), 'n25 other 3 coins')
