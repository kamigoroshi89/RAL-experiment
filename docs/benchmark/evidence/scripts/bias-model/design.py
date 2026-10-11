import sys; sys.path.insert(0,"/tmp/research/obs3")
from analytic import *
import numpy as np
from scipy.optimize import minimize
rng=np.random.default_rng(2026)
sig=lambda x:1/(1+np.exp(-x))
print("== linear interpolation error of the analytic B1 curve on m in [1,2.5] with n equally spaced levels (max abs error)")
mm=np.linspace(1,2.5,601)
for model,f in (("L",p_out_L),("O",p_out_O)):
    for name,fun in (("k=1",lambda m:Pk(f(m),1)),("k=2",lambda m:Pk(f(m),2)),("k=3",lambda m:Pk(f(m),3)),("mean over k",lambda m:np.mean([Pk(f(m),k) for k in (1,2,3)],axis=0))):
        row=[]
        for n in (2,3,4,5,7):
            nodes=np.linspace(1,2.5,n); y=np.array([fun(x) for x in nodes]); ip=np.interp(mm,nodes,y)
            row.append(np.abs(ip-np.array([fun(x) for x in mm])).max())
        print(model,name,"n=2,3,4,5,7:",[round(float(x),4) for x in row])
    # quadratic through the 3 grid levels 1,1.5,2.5
    for name,fun in (("k=1",lambda m:Pk(f(m),1)),("k=3",lambda m:Pk(f(m),3))):
        nodes=np.array([1,1.5,2.5]); c=np.polyfit(nodes,[fun(x) for x in nodes],2)
        print(model,name,"quadratic through 1,1.5,2.5, max err on [1,2.5]:",round(float(np.abs(np.polyval(c,mm)-np.array([fun(x) for x in mm])).max()),4))
# --- sample size
def P_of(model): 
    f=p_out_L if model=="L" else p_out_O
    return lambda m,k: Pk(f(m),k)
def nll_ii(th,m,k,y):
    p=1-(1-sig(th[0]+th[1]*m))**k; p=np.clip(p,1e-9,1-1e-9)
    return -(y*np.log(p)+(1-y)*np.log(1-p)).sum()
def nll_logit(th,m,y):
    z=th[0]+th[1]*m; return (np.logaddexp(0,z)-y*z).sum()
def sim(model,n=100,reps=1500):
    Pf=P_of(model); m0=1.5
    target_k={k:Pf(m0,k) for k in (1,2,3)}; target=np.mean(list(target_k.values()))
    out={"A_3level_cell":[], "B_3level_logit":[], "C_cont_logit":[], "D_cont_model_ii":[], "E_9cells_cell(k=2)":[], "F_cont_model_ii(k=2)":[]}
    for r in range(reps):
        # 3-level design: m in {1,1.5,2.5}, k uniform
        lev=rng.choice([1.0,1.5,2.5],size=n); k=rng.integers(1,4,size=n)
        y=(rng.random(n)<np.array([Pf(a,b) for a,b in zip(lev,k)])).astype(float)
        out["A_3level_cell"].append(y[lev==1.5].mean() if (lev==1.5).any() else np.nan)
        th=minimize(nll_logit,[-1,1],args=(lev,y),method="BFGS").x; out["B_3level_logit"].append(sig(th[0]+th[1]*1.5))
        # 9 cells: cell (1.5,2)
        sel=(lev==1.5)&(k==2); out["E_9cells_cell(k=2)"].append(y[sel].mean() if sel.any() else np.nan)
        # continuous
        m=rng.uniform(1,2.5,size=n); k=rng.integers(1,4,size=n)
        y=(rng.random(n)<np.array([Pf(a,b) for a,b in zip(m,k)])).astype(float)
        th=minimize(nll_logit,[-1,1],args=(m,y),method="BFGS").x; out["C_cont_logit"].append(sig(th[0]+th[1]*1.5))
        th=minimize(nll_ii,[-1.5,1],args=(m,k,y),method="Nelder-Mead").x
        pk=lambda kk:1-(1-sig(th[0]+th[1]*1.5))**kk
        out["D_cont_model_ii"].append(np.mean([pk(1),pk(2),pk(3)])); out["F_cont_model_ii(k=2)"].append(pk(2))
    res={}
    for key,v in out.items():
        v=np.array(v,float); tg=target_k[2] if "k=2" in key else target
        res[key]=(float(np.nanmean(v)-tg),float(np.nanstd(v)),float(np.mean(np.isnan(v))))
    return target,target_k,res
for model in ("L","O"):
    t,tk,res=sim(model)
    print(f"== model {model}: true pooled P(1.5)={t:.3f}; per k {[round(x,3) for x in tk.values()]}; n=100 injections")
    for key,(b,s,nan) in res.items(): print(f"   {key:24s} bias {b:+.3f} SD {s:.3f} (share of runs with empty cell {nan:.3f})")
    p=t; print("   binomial SD of a 3-level cell with n=33:",round(np.sqrt(p*(1-p)/33),3),"; n needed per cell for the continuous-fit SD (cont_logit):",
          int(np.ceil(p*(1-p)/res["C_cont_logit"][1]**2)),"; n for SD .05 / .03 / .02:",[int(np.ceil(p*(1-p)/s**2)) for s in (.05,.03,.02)])
