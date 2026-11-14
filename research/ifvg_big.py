import sys; sys.path.insert(0, '/home/user/bitf-perps/research')
import ifvg_lab as L
for k in (2.5, 3.0, 4.0):
    for G in (6.0, 8.0, 10.0):
        L.report(L.book(L.USER, k=k, G=G), 'k %.1f G %.0f' % (k, G))
for kw in (dict(stop='leg'), dict(arm=0.618), dict(btc=True), dict(tgt=3.0), dict(tgt=1.5), dict(inv=1.0)):
    L.report(L.book(L.USER, k=3.0, G=8.0, **kw), 'k3 G8 ' + str(kw))
tl = L.book(L.USER, k=3.0, G=8.0)
for s in L.USER:
    L.report([t for t in tl if t['sym'] == s], '  k3G8 ' + s)
L.report(L.book(L.OTHER, k=3.0, G=8.0), 'k3G8 other 4 coins')
