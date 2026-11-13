import sys, os, math, bisect, statistics, pickle, json, random, collections
S = '/tmp/claude-0/-home-user/c8fa9696-dfb6-57b3-8da3-7ff0497b037c/scratchpad'
sys.path.insert(0, S); sys.path.insert(0, '/home/user/bitfunded-perps'); os.chdir('/home/user/bitfunded-perps')
import perps, qlab, book2
H=3600_000; H4=4*H; D=86_400_000; START=qlab.START
load=qlab.load
B4=load('BTC','4h'); BT=[b[0]+H4 for b in B4]
LR=[None]+[math.log(B4[k][4]/B4[k-1][4]) for k in range(1,len(B4))]
SD=[None]*len(B4)
for k in range(43,len(B4)): SD[k]=statistics.pstdev(LR[k-41:k+1])
def vexp(t):  # bars closed at or before t
    k=bisect.bisect_right(BT,t)-1
    if k<90 or SD[k-42] is None: return None
    return SD[k]>SD[k-42]
DV=json.load(open('trader/perps/cache/DVOL-BTC-1h.json')); DT=[r[0] for r in DV]; DM={r[0]:r[4] for r in DV}
def dfall(t):
    k=bisect.bisect_right(DT,t-H)-1   # last row with t_open+1h<=t
    if k<0: return None
    t0=DT[k]; p=DM.get(t0-168*H)
    if p is None:
        j=bisect.bisect_right(DT,t0-168*H)-1; p=DV[j][4] if j>=0 else None
    return None if p is None else DV[k][4]-p<0
def regime(t):
    v=vexp(t); f=dfall(t)
    return v, (None if v is None or f is None else (not v) and f)
# ---- Q trades, signal-time regime
sigs=qlab.signals(); Q=[]
for g in sigs:
    r=qlab.execute(g,'atr:0.5',pen=0.05)
    if not r or not r.get('filled'): continue
    v,dz=regime(g['close']); v2,dz2=regime((r['t_in']//H4)*H4)
    Q.append(dict(sym=r['sym'],t_in=r['t_in'],t_out=r['t_out'],r=r['r'],side=r['side'],tag='Q',prio=0,close=g['close'],vexp=v,dz=dz,dz_fill=dz2,vexp_fill=v2))
END=START+1096*D
Q=[t for t in Q if START<=t['t_in']<END]
C=[dict(t) for t in pickle.load(open(S+'/book_trades.pkl','rb'))['C']]
for t in C:
    dec=((t['t_in']-H4)//H4)*H4; t['vexp'],t['dz']=regime(dec); t['vexp_fill'],_=regime((t['t_in']//H4)*H4)
print('Q fills',len(Q),'missing dz',sum(t['dz'] is None for t in Q),'C',len(C),'missing',sum(t['vexp'] is None for t in C))
print('Q dz signal vs fill disagree:',sum(t['dz']!=t['dz_fill'] for t in Q),' vexp disagree:',sum(t['vexp']!=t['vexp_fill'] for t in Q))
P=[('Y1',START,START+365*D),('Y2',START+365*D,START+730*D),('Y3',START+730*D,END),('first2y',START,START+730*D),('lastyr',START+730*D,END),
   ('IS',START,qlab.START+(perps.dt.datetime(2025,12,18,tzinfo=perps.UTC).timestamp()*1000-START)),]
SPLIT=int(perps.dt.datetime(2025,12,18,tzinfo=perps.UTC).timestamp()*1000)
P[-1]=('IS',START,SPLIT); P.append(('OS',SPLIT,END))
def st(xs):
    return '%3d %+.2f' % (len(xs), statistics.mean(xs)) if xs else '  0   n/a'
for key in ('dz','dz_fill'):
    print('\nQ (all fills, no caps) by %s:  period | dead zone n avgR | elsewhere n avgR | contracting&DVOL-up n avgR' % key)
    for lbl,a,b in P:
        xs=[t for t in Q if a<=t['close']<b and t[key] is not None]
        vk='vexp' if key=='dz' else 'vexp_fill'
        print('%-8s | %s | %s | %s' % (lbl, st([t['r'] for t in xs if t[key]]), st([t['r'] for t in xs if not t[key]]),
              st([t['r'] for t in xs if not t[key] and not t[vk]])))
# ---- book
t0=START+10*D; t1=START+1005*D
def tagged(bk, variant):
    out=[]
    for t in bk:
        if t['tag']=='Q':
            if variant=='dz' and t['dz']: continue
            tag='Qx' if (variant=='dz' or t['vexp']) else 'Qc'
        else:
            tag='Cx' if t['vexp'] else 'Cc'
        out.append(dict(t,tag=tag))
    return out
RISK={'Qx':2.5,'Qc':1.25,'Cx':1.5,'Cc':0.5}
def run(msd, fill_time=False, skip_before_book=False):
    QQ=Q
    if fill_time: QQ=[dict(t,dz=t['dz_fill'],vexp=t['vexp_fill']) for t in Q]
    CC=C if not fill_time else [dict(t,vexp=t['vexp_fill']) for t in C]
    bk=book2.book(QQ+CC,max_same_dir=msd)
    base=tagged(bk,'base')
    if skip_before_book:   # skipped Q tickets free their slot
        bk2=book2.book([t for t in QQ if not t['dz']]+CC,max_same_dir=msd); dz=tagged(bk2,'dz')
    else: dz=tagged(bk,'dz')
    return base,dz
res={}
for msd in (None,2):
  for ft in (False,True):
    for sb in (True,False):
        base,dz=run(msd,ft,sb)
        rb=book2.sim(base,RISK,t0,t1); rd=book2.sim(dz,RISK,t0,t1)
        print('msd=%s regime@%s skip_frees_slot=%s | base %s\n%42s dz   %s' % (msd,'fill' if ft else 'signal',sb,book2.fmt(rb),'',book2.fmt(rd)))
        res[(msd,ft,sb)]=(base,dz)
# also house-rule baseline CRT flat 1%
base,_=res[(None,False,True)]
print('house baseline Q tilt + C 1%:',book2.fmt(book2.sim([dict(t,tag=t['tag'] if t['tag'][0]=='Q' else 'C') for t in base],{'Qx':2.5,'Qc':1.25,'C':1.0},t0,t1)))
# by-half R/month in book
def rpm(tr,a,b):
    xs=[t for t in tr if a<=t['t_in']<b]; return sum(t['r']*RISK[t['tag']] for t in xs)/((b-a)/D/30.4)
for k in ((None,False,True),):
    base,dz=res[k]
    for lbl,a,b in (('IS',START,SPLIT),('OS',SPLIT,END)):
        print(lbl,'%%/mo base %.2f dz %.2f' % (rpm(base,a,b),rpm(dz,a,b)))
# ---- Monte Carlo: weekly blocks
def mc(tr, n=3000, seed=7):
    rnd=random.Random(seed); W=7*D
    weeks=collections.defaultdict(list)
    for t in tr: weeks[(t['t_in']-START)//W].append(t)
    nw=int((END-START)//W); keys=list(range(nw))
    passes=0; days=[]
    for _ in range(n):
        seq=[]; 
        for j in range(30):   # 30 weeks per path
            w=rnd.choice(keys)
            for t in weeks.get(w,[]): seq.append(dict(t,t_in=t['t_in']-w*W+j*W+START,t_out=t['t_out']-w*W+j*W+START))
        r=book2.sim(seq,RISK,START,START+1)
        passes+=r['pass']>0
        if r['pass']>0: days.append(r['med'])
    days.sort()
    return 100*passes/n, days[len(days)//2] if days else float('nan')
for k in ((None,False,True),(None,False,False)):
    base,dz=res[k]
    print('MC',k,'base pass %.1f%% med %.0fd' % mc(base), '| dz pass %.1f%% med %.0fd' % mc(dz))
