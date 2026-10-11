import numpy as np, math, json
from scipy.stats import norm
exec(open('/tmp/research/resp/sim.py').read().split("# ---------- 1. current RESP")[0])
E=eff(range(8),intakes_for(8)); ss=E[6]
print("SS responder effects",np.round(ss,2))
for s in (0.0,0.25,0.5,0.75,1.0):
    row=[]
    for slot,(a,b),idx in (("am",(0,1),0),("pm",(3,4),1)):
        its=intakes_for(8); sc=[1.0]*len(its); sc[its.index(6*DAY+DOSE[idx])]=s
        Ei=eff(range(8),its,sc)[6]
        mu_c=circ[a]-circ[b]; sdc=abs(mu_c)*6.1/13.2
        mu=mu_c+Ei[b]-Ei[a]
        pl=norm.cdf((DELTA-mu)/math.hypot(math.sqrt(2)*SD_AR,sdc)); po=norm.cdf((DELTA-mu)/math.hypot(math.sqrt(2)*SD_R,sdc))
        row.append((slot,round(float(Ei[a]),2),round(float(Ei[b]),2),round(float(pl),3),round(float(po),3)))
    print("scale",s,row)
# both doses of day 6 scaled (a day-long window): labelled events per day
for s in (0.0,):
    its=intakes_for(8); sc=[s if (6*DAY<=t<7*DAY) else 1.0 for t in its]
    Ei=eff(range(8),its,sc)[6]; print("day-window scale",s,np.round(Ei,2))
# first dose, latent / observed per slot for scale 0 vs 1 (circ fixture) already in sim
# realised label for day-0 first-dose pair (latent) :
mu_c=circ[0]-circ[1]; sdc=abs(mu_c)*6.1/13.2
for tag,mu in (("resp",mu_c+E[0][1]-E[0][0]),("nr",mu_c)):
    print("first dose latent P(viol)",tag,norm.cdf((DELTA-mu)/math.hypot(math.sqrt(2)*SD_AR,sdc)))
# R1 latent label prob s=0.75 for m5 n5, analytic from MC: mean drop 
