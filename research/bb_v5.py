import sys; sys.path.insert(0, '/home/user/bitf-perps/research')
import bb_lab as B
from ifvg_lab import report
for pat in (('engulf',), ('engulf', 'pin', 'ifvg')):
    for kw in (dict(n_bb=20), dict(n_bb=20, lv_tf='2h'), dict(n_bb=20, lv_tf='2h', touches=4), dict(n_bb=20, lv_tf='2h', tol=0.15),
               dict(n_bb=13, lv_tf='2h'), dict(n_bb=25, lv_tf='2h')):
        report(B.book(bias='ema4h', key='hz', pat=pat, **kw), '%s %s' % ('engulf' if len(pat) == 1 else 'any', kw))
