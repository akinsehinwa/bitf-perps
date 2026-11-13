exec(open('dz.py').read().split('# ---- Monte Carlo')[0].split('res={}')[0])
import itertools
bt=pickle.load(open(S+'/book_trades.pkl','rb'))
PQ=bt['Q']
mine={(t['sym'],t['t_in']):t for t in Q}
print('pickle Q matched in regenerated:',sum((t['sym'],t['t_in']) in mine and abs(mine[(t['sym'],t['t_in'])]['r']-t['r'])<1e-9 for t in PQ),'/',len(PQ))
print('BTC 4h first bar',perps.local_dt(B4[0][0],0))
sys.path.insert(0,'/home/user/bitfunded-perps/research'); import h3_regime as h3
def tagq(t, how):
    if how=='h3': v,_=h3.vol_state(t['t_in']); return bool(v)
    return t['vexp']
for msd,qsrc,how,crt in itertools.product((None,2),('pickle','regen'),('sig','h3'),('tilt','flat1')):
    QQ=PQ if qsrc=='pickle' else Q
    QQ=[dict(t,vexp=mine.get((t['sym'],t['t_in']),{}).get('vexp')) if qsrc=='pickle' else t for t in QQ]
    bk=book2.book(QQ+C,max_same_dir=msd)
    out=[]
    for t in bk:
        if t['tag']=='Q': out.append(dict(t,tag='Qx' if tagq(t,how) else 'Qc'))
        else: out.append(dict(t,tag=('Cx' if t['vexp'] else 'Cc') if crt=='tilt' else 'C'))
    for a,b,lbl in ((START+10*D,START+1005*D,'desk'),(START,START+(1096-120)*D,'h3win')):
        r=book2.sim(out,{'Qx':2.5,'Qc':1.25,'Cx':1.5,'Cc':0.5,'C':1.0},a,b)
        print(msd,qsrc,how,crt,lbl,book2.fmt(r))
