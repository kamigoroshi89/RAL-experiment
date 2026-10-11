import sys, json
sys.path.insert(0,"/tmp/research/obs3")
import numpy as np
from scipy.optimize import least_squares
from scipy.stats import norm
from analytic import *
sig=lambda x:1/(1+np.exp(-x))
GRID=[round(0.25*i,2) for i in range(13)]; KS=(1,2,3)
def surface_analytic(model):
    f=p_out_L if model=="L" else p_out_O
    return {(m,k):Pk(f(m),k) for m in GRID for k in KS}
MODELS={}
def reg(name,npar,x0s):
    def deco(f): MODELS[name]=(f,npar,x0s); return f
    return deco
@reg("i_logit_z",2,[(-3,1.5),(-1,1),(0,2)])
def _(th,m,k): return sig(th[0]+th[1]*m*np.sqrt(k))
@reg("i_probit_z",2,[(-1.5,0.8),(-0.5,0.5),(0,1)])
def _(th,m,k): return norm.cdf(th[0]+th[1]*m*np.sqrt(k))
@reg("ii_geo_0par",0,[()])
def _(th,m,k): return 1-(1-np.minimum(1,m*SIG/W))**k
@reg("ii_geo_1par",1,[(1.0,),(0.5,),(2.0,)])
def _(th,m,k): return 1-(1-np.minimum(1,th[0]*m*SIG/W))**k
@reg("ii_logit_m_k",2,[(-2,1.5),(-1,1),(0,2)])
def _(th,m,k): return 1-(1-sig(th[0]+th[1]*m))**k
@reg("iii_logit_logm_logk",3,[(0,1,0.5),(-1,2,1),(0.5,0.5,0.2)])
def _(th,m,k): return sig(th[0]+th[1]*np.log(np.maximum(m,1e-9))+th[2]*np.log(k))
def fit(name,cells,S):
    f,npar,x0s=MODELS[name]
    if npar==0: return ()
    m=np.array([c[0] for c in cells]); k=np.array([c[1] for c in cells]); y=np.array([S[c] for c in cells])
    best=None
    for x0 in x0s:
        r=least_squares(lambda th:f(th,m,k)-y,x0)
        if best is None or r.cost<best.cost: best=r
    return tuple(best.x)
def evaluate(name,th,cells,S):
    f=MODELS[name][0]
    m=np.array([c[0] for c in cells]); k=np.array([c[1] for c in cells]); y=np.array([S[c] for c in cells])
    e=f(th,m,k)-y; return float(np.sqrt(np.mean(e**2))), float(np.abs(e).max()), cells[int(np.abs(e).argmax())]
PROTOCOLS={
 "P1 interp (train m in .25,.75,1.25,1.75,2.25,2.75,3 [+0]; test .5,1,1.5,2,2.5)":
   (lambda m,k: m in (0,0.25,0.75,1.25,1.75,2.25,2.75,3.0), lambda m,k: m in (0.5,1.0,1.5,2.0,2.5)),
 "P2 nine grid cells (m in 1,1.5,2.5 x k); test the other 30 cells with m>0":
   (lambda m,k: m in (1.0,1.5,2.5), lambda m,k: m not in (0,1.0,1.5,2.5)),
 "P3 k extrapolation (train k=1,2; test k=3, m>0)":
   (lambda m,k: k in (1,2), lambda m,k: k==3 and m>0),
}
def run_protocols(S,names=None,out=None):
    rows=[]
    for pn,(trf,tef) in PROTOCOLS.items():
        for name in (names or MODELS):
            tr=[c for c in S if trf(*c)]; te=[c for c in S if tef(*c)]
            if name.startswith("iii"): tr=[c for c in tr if c[0]>0]
            th=fit(name,tr,S); rmse,mx,at=evaluate(name,th,te,S)
            rows.append((pn.split(" ")[0],name,rmse,mx,at,th))
    return rows
if __name__=="__main__":
    for model in ("L","O"):
        S=surface_analytic(model)
        print("== analytic B1, model",model)
        for r in run_protocols(S): print(r[0],f"{r[1]:22s} RMSE {r[2]:.4f} max {r[3]:.4f} at {r[4]}",np.round(r[5],3))
