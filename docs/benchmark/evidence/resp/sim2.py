import numpy as np, math, json
from scipy.stats import norm
exec(open('/tmp/research/resp/sim.py').read().split("# ---------- 1. current RESP")[0])  # reuse helpers/constants
rng=np.random.default_rng(7)
res={}
# --- A. extra post-dose readings under the CURRENT template (max rule), SS persistent NR vs responder, circadian known, observed noise
sw=3.2569743337681163
N=400000
for k in (1,2,3,4):
    # pre exact? no: pre noisy; k post readings independent noise; effect swing sw each
    pre=rng.normal(0,SD_R,N); posts=rng.normal(0,SD_R,(N,k))
    Dr=pre[:,None]-(posts-sw)   # responder: post lower by sw => drop = pre - post, y_post = base - eff => drop = (pre_noise - post_noise)+sw
    Dn=pre[:,None]-posts
    mr=Dr.max(1); mn=Dn.max(1)
    pr=(mr<DELTA).mean(); pn=(mn<DELTA).mean()
    # AUC of -max
    from scipy.stats import rankdata
    allv=np.concatenate([-mr[:100000],-mn[:100000]]); rk=rankdata(allv)
    n1=100000; auc=(rk[n1:].sum()-n1*(n1+1)/2)/(n1*n1)   # P(score_NR > score_R)
    res[f"max_rule_k{k}"]=dict(p_viol_resp=float(pr),p_viol_nr=float(pn),auc=float(auc))
    print("max rule k=%d P(viol|R)=%.3f P(viol|NR)=%.3f AUC=%.3f"%(k,pr,pn,auc))
# ceiling: pre known exactly, post mean of k
for k in (1,4,10**6):
    d=sw/(SD_R/math.sqrt(k)); print("ceiling pre exact, k post mean:",k,"d'",d,"AUC",norm.cdf(d/math.sqrt(2)))
    res[f"ceiling_k{k}"]=dict(dprime=d,auc=float(norm.cdf(d/math.sqrt(2))))
# --- B. R1 MC: library of effect profiles with adherence
def adherent_intakes(nd,rng):
    its=[]
    for d in range(nd):
        for t in DOSE:
            u=rng.random()
            if u<.057: continue
            dl=0
            if u<.057+.081: dl=min(rng.exponential(20*MIN),6*H)
            its.append(int(d*DAY+t+dl+5000))
    return sorted(its)
LIB=np.array([eff(range(16),adherent_intakes(16,rng)) for _ in range(800)])  # (800,16,5)
res["lib_mean_by_day"]=LIB.mean((0,2)).tolist()
def mc(m,n,delta,scale,NP=40000,latent=False):
    """run-in m untreated days, then n treated days with Emax scale `scale` for all intakes (effect = scale*profile, exact for equal scales)."""
    sd=SD_AR if latent else SD_R
    idx=rng.integers(0,LIB.shape[0],NP)
    prof=LIB[idx][:,:n,:]*scale          # NP,n,5
    base_noise=rng.normal(0,sd,(NP,m,5)); tr_noise=rng.normal(0,sd,(NP,n,5))
    ref=base_noise.mean((1,2)); tr=(-prof+tr_noise).mean((1,2))
    drop=ref-tr
    return drop
rows={}
for m,n in ((3,3),(3,5),(5,3),(5,5),(5,7),(7,5),(7,7)):
    row={}
    dr=mc(m,n,0,1.0); dn=mc(m,n,0,0.0)
    mu=float(dr.mean()); d=mu/2
    for tag,sdn in (("obs",False),("lat",True)):
        a=mc(m,n,0,1.0,latent=sdn); b=mc(m,n,0,0.0,latent=sdn); c5=mc(m,n,0,0.5,latent=sdn); c75=mc(m,n,0,0.25,latent=sdn)
        thr=a.mean()/2
        row[tag]=dict(thr=float(thr),p_viol_resp=float((a<thr).mean()),p_viol_nr0=float((b<thr).mean()),p_viol_s05=float((c5<thr).mean()),p_viol_s025=float((c75<thr).mean()),sd_resp=float(a.std()))
    rows[f"m{m}_n{n}"]=row
    print(m,n,json.dumps(row["obs"]),"\n    ",json.dumps(row["lat"]))
res["R1_mc"]=rows
# --- C. CUSUM on daily means for loss of response at day d0=6 (record: stationary treated, washout profile), m=5 reference days estimated
# profile of the effect shortfall (persistent NR from day 6) from sim_out
so=json.load(open('/tmp/research/resp/sim_out.json'))
short=np.array(so["loss_shortfall"]); short=np.concatenate([short,np.full(20-len(short),short[-1])])
SIGD=so["daily"]["sig_d"]; mu1=9.4
def cusum_alarm(h,k,nd=20,NP=20000,m=5,d0=6,null=False):
    # daily mean of drop-from-ref: x_t = ref - y_t... use standardized shortfall relative to mean of first m days
    noise=rng.normal(0,SIGD,(NP,nd))
    eff_short=np.zeros(nd) if null else short[:nd]
    x=-(-eff_short)+noise   # shortfall + noise (positive shortfall means pressure higher than treated)
    ref=x[:,:m].mean(1,keepdims=True)
    z=x-ref
    S=np.zeros(NP); alarm=np.full(NP,np.inf)
    for t in range(m,nd):
        S=np.maximum(0,S+z[:,t]-k)
        newly=(S>h)&np.isinf(alarm)
        alarm[newly]=t
    return alarm
k=mu1/2
# choose h so that P(false alarm within 14 post-ref days) ~ 5%
for h in np.arange(4,40,1.0):
    a=cusum_alarm(h,k,nd=20,null=True)
    if np.isfinite(a).mean()<=0.05: break
print("CUSUM h",h,"k",k,"false alarm prob over days 5..19 (15 days):",np.isfinite(a).mean())
a1=cusum_alarm(h,k)
lag=a1-6
print("loss at day 6: P(alarm by day t) :",[(t,float(np.mean(a1<=t))) for t in range(6,14)])
res["cusum"]=dict(h=float(h),k=float(k),fa=float(np.isfinite(a).mean()),detect=[(t,float(np.mean(a1<=t))) for t in range(6,16)])
# compare fixed window m=5,n=5 (5%/ power) already in R1 MC
json.dump(res,open('/tmp/research/resp/sim2_out.json','w'),indent=1)
