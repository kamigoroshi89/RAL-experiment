import sys, json, time
sys.path.insert(0,"/tmp/research/obs3")
from mcsim import *
if __name__=="__main__":
    which=sys.argv[1]; res={}
    t0=time.time()
    with Pool(26) as pool:
        if which=="b1":
            for case in CASES:
                for m in (0.0,1.0,1.5,2.5):
                    for k in (1,2,3):
                        N=60000 if m==0 else 20000
                        o=run_cell(pool,case,m,k,N,hash((case,m,k))%100000*100,False)
                        res[f"{case}|{m}|{k}"]=dict(n=len(o),cov_with=int(o[:,0].sum()),cov_without=int(o[:,1].sum()),
                              day_with=int(o[:,2].sum()),day_without=int(o[:,3].sum()),
                              cov_new=int(((o[:,0]==1)&(o[:,1]==0)).sum()),cov_lost=int(((o[:,0]==0)&(o[:,1]==1)).sum()))
                        print(case,m,k,res[f"{case}|{m}|{k}"],round(time.time()-t0),flush=True)
        else:
            N=int(sys.argv[2])
            for case in sys.argv[3].split(','):
                for m in (0.0,1.0,1.5,2.5):
                    for k in (1,2,3):
                        if case in ("O_iid","L_iid") and not ((m==0.0 and k==1) or (m==1.5 and k==2)): continue
                        o=run_cell(pool,case,m,k,N,hash((case,m,k,"b3"))%100000*100+7,2,chunk=25)
                        res[f"{case}|{m}|{k}"]=dict(n=len(o),b3_with=int(o[:,4].sum()),b3_without=int(o[:,5].sum()),
                              b3_new=int(((o[:,4]==1)&(o[:,5]==0)).sum()),day_with=int(o[:,2].sum()),
                              day_without=int(o[:,3].sum()),first=[int((o[:,6]==j).sum()) for j in range(5)],
                              b3_with_by_first=[int(o[(o[:,6]==j),4].sum()) for j in range(5)])
                        print(case,m,k,res[f"{case}|{m}|{k}"]["b3_with"],res[f"{case}|{m}|{k}"]["b3_without"],round(time.time()-t0),flush=True)
    json.dump(res,open(f"/tmp/research/obs3/part1_{which}.json","w"),indent=1)
