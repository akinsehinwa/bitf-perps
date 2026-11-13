exec(open('dz.py').read().split('# ---- book')[0])
sys.path.insert(0,'/home/user/bitfunded-perps/research'); import h3_regime as h3
PQ=pickle.load(open(S+'/book_trades.pkl','rb'))['Q']
print('pickle Q avg %.3f  regen Q avg %.3f' % (statistics.mean(t['r'] for t in PQ), statistics.mean(t['r'] for t in Q)))
bysym=collections.defaultdict(list)
for g in sigs: bysym[g['sym']].append(g['close'])
P2=[]
for t in PQ:
    cs=[c for c in bysym[t['sym']] if c<=t['t_in']<=c+8*H]
    if not cs: continue
    c=max(cs); v,dz=regime(c)
    P2.append(dict(t,close=c,vexp=v,dz=dz))
print('pickle Q mapped to signal',len(P2),'/',len(PQ))
for lbl,a,b in (('first2y',START,START+730*D),('lastyr',START+730*D,END)):
    xs=[t for t in P2 if a<=t['close']<b]
    print('pickle',lbl,'dz',st([t['r'] for t in xs if t['dz']]),'else',st([t['r'] for t in xs if not t['dz']]))
RISK={'Qx':2.5,'Qc':1.25,'Cx':1.5,'Cc':0.5}
def tag(bk,variant,qv):
    out=[]
    for t in bk:
        if t['tag']=='Q':
            if variant=='dz' and t['dz']: continue
            out.append(dict(t,tag='Qx' if (variant=='dz' or qv(t)) else 'Qc'))
        else: out.append(dict(t,tag='Cx' if t['vexp'] else 'Cc'))
    return out
t0=START+10*D; t1=START+1005*D
sets={}
for name,QQ,qv in (('regen15m',Q,lambda t:t['vexp']),('pickle-sigtime',P2,lambda t:t['vexp']),('pickle-h3fill',P2,lambda t:bool(h3.vol_state(t['t_in'])[0]))):
    bk=book2.book(QQ+C)
    b=tag(bk,'base',qv); d=tag(bk,'dz',qv)
    print(name,'base',book2.fmt(book2.sim(b,RISK,t0,t1))); print(name,'dz  ',book2.fmt(book2.sim(d,RISK,t0,t1)))
    sets[name]=(b,d)
def mc(tr,n=3000,seed=7,weeks_per=60):
    rnd=random.Random(seed); W=7*D; wk=collections.defaultdict(list)
    for t in tr:
        if t0<=t['t_in']<t1: wk[(t['t_in']-t0)//W].append(t)
    keys=list(range(int((t1-t0)//W))); ok=0; days=[]; f=0
    for _ in range(n):
        seq=[]
        for j in range(weeks_per):
            w=rnd.choice(keys)
            for t in wk.get(w,[]):
                off=t0+w*W; seq.append(dict(t,t_in=t['t_in']-off+j*W+t0,t_out=t['t_out']-off+j*W+t0))
        r=book2.sim(seq,RISK,t0,t0+1)
        if r['pass']>0: ok+=1; days.append(r['med'])
        elif r['f1']>0 or r['f2']>0: f+=1
    days.sort(); return 100*ok/n, 100*f/n, days[len(days)//2]
for name,(b,d) in sets.items():
    print('MC',name,'base pass %.1f%% fail %.1f%% med %.0fd' % mc(b),'| dz pass %.1f%% fail %.1f%% med %.0fd' % mc(d))
