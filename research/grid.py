import sys, itertools, statistics, pickle
sys.path.insert(0,'/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad')
import qlab
D=qlab.D; START=qlab.START
WARM=START-365*D   # signals from a year earlier so walk-forward has a first training window
res={}
for don, body in itertools.product((40,55,70),(0.75,1.0,1.25)):
    st=dict(qlab.ST, donchian=don, min_body_atr=body)
    sig=qlab.signals(st=st, start=WARM)
    for lim, tr, sk in itertools.product((0.4,0.5,0.6,0.75),(2.0,2.5,3.0),(1.75,2.0,2.25)):
        out=[]
        for g in sig:
            r=qlab.execute(g, 'atr:%s'%lim, stop='sig:%s'%sk, tr=tr, pen=0.05)
            if r and r.get('filled'): out.append((g['close'], r['r']))
        res[(don,body,lim,tr,sk)]=out
    print('done', don, body, flush=True)
pickle.dump(res, open('/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad/grid.pkl','wb'))
