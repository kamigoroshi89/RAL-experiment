import sys, json, time
sys.path.insert(0,"/tmp/research/obs3")
from mcsim import *
if __name__=="__main__":
    which=sys.argv[1]; N=int(sys.argv[2]); cases=sys.argv[3].split(","); res={}
    t0=time.time(); grid=[round(0.25*i,2) for i in range(13)]
    with Pool(26) as pool:
        for case in cases:
            for m in grid:
                for k in (1,2,3):
                    o=run_cell(pool,case,m,k,N,abs(hash((case,m,k,which)))%100000*100+3,2 if which=="b3" else False,chunk=(20 if which=="b3" else 2500))
                    res[f"{case}|{m}|{k}"]=dict(n=len(o),cov=int(o[:,0].sum()),day=int(o[:,2].sum()),b3=int(o[:,4].sum()),
                        b3_by_first=[[int((o[:,6]==j).sum()),int(o[(o[:,6]==j),4].sum())] for j in range(5)])
            print(case,"done",round(time.time()-t0),flush=True)
    json.dump(res,open(f"/tmp/research/obs3/part2_{which}.json","w"),indent=1)
