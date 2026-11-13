import urllib.request,json,time,sys
START=1682899200000  # 2023-05-01 UTC
out='/home/user/bitfunded-perps/trader/perps/cache/DVOL-%s-1h.json'
for cur in ('BTC','ETH'):
    end=int(time.time()*1000); rows={}
    while True:
        u=f'https://www.deribit.com/api/v2/public/get_volatility_index_data?currency={cur}&start_timestamp={START}&end_timestamp={end}&resolution=3600'
        for a in range(5):
            try: d=json.load(urllib.request.urlopen(u,timeout=30)); break
            except Exception as e: print('retry',e); time.sleep(2*(a+1))
        r=d['result']
        for x in r['data']: rows[x[0]]=x
        c=r.get('continuation')
        if not r['data'] or c is None or c<START: break
        end=c; time.sleep(0.3)
    L=[rows[k] for k in sorted(rows) if k>=START]
    json.dump(L,open(out%cur,'w'))
    gaps=[(L[i-1][0],L[i][0]) for i in range(1,len(L)) if L[i][0]-L[i-1][0]!=3600000]
    import datetime as dt
    f=lambda t:dt.datetime.utcfromtimestamp(t/1000).strftime('%Y-%m-%d %H:%M')
    print(cur,len(L),f(L[0][0]),f(L[-1][0]),'gaps',len(gaps),'missing_hours',sum((b-a)//3600000-1 for a,b in gaps))
    for a,b in sorted(gaps,key=lambda g:g[0]-g[1])[:8]: print('  ',f(a),'->',f(b),(b-a)//3600000-1,'h missing')
