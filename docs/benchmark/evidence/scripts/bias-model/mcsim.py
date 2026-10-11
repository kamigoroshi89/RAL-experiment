"""Monte Carlo of the real B1 / B3 classes on the hand-built day (obs2 stream). Paired: same latent and noise with and
without the offset.  Offsets added directly to the covered readings (equivalent to the injector: checked in check_inj.py)."""
import sys, json, time
sys.path.insert(0,"/tmp/research/obs3")
from common import *
from multiprocessing import Pool
CASES={"O_iid":(None,0,False),"L_iid":(None,0,True),"O_s10":("s",10,False),"O_s20":("s",20,False),
       "L_s10":("s",10,True),"L_s20":("s",20,True)}
def latent_vals(rng,case):
    kind,d,noise=CASES[case]
    if kind is None: return rng.uniform(A,B,5), noise
    r0=rng.uniform(A+d,B); r3=rng.uniform(A+d,B)
    return np.array([r0,r0-d,rng.uniform(A,B),r3,r3-d]), noise
def work(args):
    case,m,k,n,seed,b3=args
    rng=np.random.default_rng(seed)
    out=np.zeros((n,8),dtype=np.int8)  # b1cov_with,b1cov_without,b1day_with,b1day_without,b3_with,b3_without,first,sign
    for t in range(n):
        lat,noise=latent_vals(rng,case)
        v0=lat+(rng.normal(0,SIG,5) if noise else 0.0)
        i=int(rng.integers(0,5-k+1)); sign=rng.choice((-1.0,1.0))
        v1=v0.copy(); v1[i:i+k]+=sign*m*SIG
        res=[]
        for v in (v1,v0):
            d=detect_b1(v)
            cov=sum(len(covered_time(j,d)) for j in range(i,i+k))>0
            res.append((cov,len(d)>0))
        out[t,0]=res[0][0]; out[t,1]=res[1][0]; out[t,2]=res[0][1]; out[t,3]=res[1][1]
        if b3:
            out[t,4]=len(detect_b3(v1))>0
            if b3==1: out[t,5]=len(detect_b3(v0))>0
        out[t,6]=i; out[t,7]=sign
    return out
def run_cell(pool,case,m,k,N,seed0,b3,chunk=2500):
    jobs=[]; left=N; s=seed0
    while left>0:
        c=min(chunk,left); jobs.append((case,m,k,c,s,b3)); left-=c; s+=1
    return np.concatenate(pool.map(work,jobs))
