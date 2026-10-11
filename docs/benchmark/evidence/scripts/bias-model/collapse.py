import sys; sys.path.insert(0,"/tmp/research/obs3")
from analytic import *
import numpy as np
from scipy.stats import norm
print("== collapse test: B1 P(detect) at equal z=m*sqrt(k)")
print("z   | model L: k=1  k=2  k=3  spread | model O: k=1 k=2 k=3 spread | mean-offset z-test power one-sided 5% (sigma 8)")
for z in (1.0,1.5,2.0,2.5,3.0):
    row=[]
    for f in (p_out_L,p_out_O):
        v=[Pk(f(z/np.sqrt(k)),k) for k in (1,2,3)]; row.append((v,max(v)-min(v)))
    pw=norm.cdf(z-1.645)
    print(f"{z:.1f} | "+" ".join(f"{x:.3f}" for x in row[0][0])+f" {row[0][1]:.3f} | "+" ".join(f"{x:.3f}" for x in row[1][0])+f" {row[1][1]:.3f} | {pw:.3f}")
print("== mean-offset test power for the grid cells (known sign one-sided 5%; unknown sign two-sided 5%); sigma 8 and sigma_eff 11.9")
for m in (1.0,1.5,2.5):
    for se in (8.0,11.9):
        r=[]
        for k in (1,2,3):
            z=m*8.0*np.sqrt(k)/se
            r.append((norm.cdf(z-1.645),norm.cdf(z-1.96)+norm.cdf(-z-1.96)))
        print(f"m={m} sigma_eff={se}: z={[round(m*8*np.sqrt(k)/se,2) for k in (1,2,3)]} one-sided={[round(a,3) for a,b in r]} two-sided={[round(b,3) for a,b in r]}")
print("z for power .5/.8/.9 one-sided:",1.645,1.645+norm.ppf(.8),1.645+norm.ppf(.9))
print("== B1 analytic per cell (L, O) and zero row")
for m in (0,1.0,1.5,2.5):
    print(m,"L p=",round(p_out_L(m),4),[round(Pk(p_out_L(m),k),3) for k in (1,2,3)],"O p=",round(p_out_O(m),4),[round(Pk(p_out_O(m),k),3) for k in (1,2,3)])
print("zero row L per day (5 readings):",1-(1-p_out_L(0))**5)
# sensitivity: band occupancy (latent density), B1 per reading p(0), p(1), p(1.5), p(2.5)
cases={"uniform in band U[110,140]":(lambda x:1/30,110,140),
       "centre N(125,5)":(lambda x:norm.pdf(x,125,5),90,160),
       "wide N(135,10)":(lambda x:norm.pdf(x,135,10),80,200),
       "tail U[110,150] (25% above band)":(lambda x:1/40,110,150),
       "N(149.3,9) (the prior baseline mean, no drug/circadian)":(lambda x:norm.pdf(x,149.3,9),100,200)}
print("== sensitivity of per-reading out-of-band probability to the latent distribution (cuff noise 8 added, fair sign)")
for n,(f,lo,hi) in cases.items():
    ps=[p_out_density(f,lo,hi,m) for m in (0,1.0,1.5,2.5)]
    print(f"{n:55s}",[round(p,3) for p in ps],"excess over zero:",[round(p-ps[0],3) for p in ps[1:]], "share of alarm already at zero:",[round(ps[0]/p,2) for p in ps[1:]])
