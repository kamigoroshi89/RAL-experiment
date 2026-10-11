"""RESP reformulations: exact/Monte-Carlo quantification with the real pkpd + circadian of the repo copy.
Run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/research/resp/repo/src python3 sim.py
Assumptions (stated): ticks 06:15 08:15 14:15 20:15 22:15; doses 07:00, 21:00; perfect adherence unless said;
AR sd 8.8 phi .22/30min -> readings >=2 h apart independent (0.22^4=.0023); cuff sd 8, bias 0; circadian A~N(13.2,6.1)>=0, peak 14:00 (FIXTURE, unknown);
Emax 17.3 for every patient (no spread in the committed prior); observation at the tick (no robot delay)."""
import numpy as np, math, json
from scipy.stats import norm
from ralmon.benchmark.pkpd import OneCompartmentEmax, PkpdParams
from ralmon.benchmark.latent import circadian
H=3_600_000; MIN=60_000; DAY=86_400_000
P=PkpdParams(17.3,0.76,2.3,0.0815); EFF=OneCompartmentEmax()
TICKS=[375,495,855,1215,1335]; DOSE=[7*H,21*H]
SD_AR,SD_CUFF=8.8,8.0; SD_R=math.hypot(SD_AR,SD_CUFF)  # 11.9 per observed reading
DELTA=7.5; Z95=norm.ppf(.95); Z80=norm.ppf(.8)
out={}
def eff(days, intakes, scales=None, which=None):
    grid=[d*DAY+m*MIN for d in days for m in TICKS]
    e=np.array(EFF.effect_mmhg(P,intakes,grid,scales)).reshape(len(days),5)
    return e
def intakes_for(nd, start=0, mult=1):
    return sorted([d*DAY+t for d in range(start,nd) for t in DOSE for _ in range(mult)])
# circadian offsets at the 5 ticks (A=13.2 mean)
circ=circadian(np.array([m*MIN for m in TICKS]),13.2,14*H)
print("circ",np.round(circ,2))
# ---------- 1. current RESP, per dose ----------
rows={}
def pair_stats(name, e_pre, e_post, circ_pre, circ_post, sd_obs=math.sqrt(2)*SD_R, sd_lat=math.sqrt(2)*SD_AR, amp_sd=6.1):
    mu_c=circ_pre-circ_post
    # patient amplitude spread: circ diff scales with A (A~N(13.2,6.1) trunc>=0): sd of diff = |mu_c|*6.1/13.2
    sd_c=abs(mu_c)*amp_sd/13.2
    res={}
    for tag,sd in (("obs",math.sqrt(sd_obs**2+sd_c**2)),("lat",math.sqrt(sd_lat**2+sd_c**2))):
        mu=mu_c+(e_post-e_pre)
        res[tag]=dict(mu=mu,sd=sd,p_viol=float(norm.cdf((DELTA-mu)/sd)))
    return res
def scen(name, e_r, e_n, slot):  # e_r,e_n: (pre,post) effects
    (pi,po)=((0,1) if slot=="am" else (3,4))
    cp,cq=circ[pi],circ[po]
    r=pair_stats(name,e_r[0],e_r[1],cp,cq); n=pair_stats(name,e_n[0],e_n[1],cp,cq)
    rows[name]=dict(responder=r,nonresp=n)
    for tag in ("obs","lat"):
        d=(r[tag]["mu"]-n[tag]["mu"])
        sd=r[tag]["sd"]
        rows[name][f"auc1_{tag}"]=float(norm.cdf(d/(sd*math.sqrt(2))))
        rows[name][f"dprime_{tag}"]=d/sd
# steady state (day 5)
E=eff(range(8),intakes_for(8)); ss=E[6]
for slot,(a,b) in (("am",(0,1)),("pm",(3,4))):
    scen(f"SS_{slot}_persistent_NR",(ss[a],ss[b]),(0.0,0.0),slot)
# window injection: only this dose (07:00 or 21:00 of day 6) scaled to 0, other doses normal
for slot,(a,b),idx in (("am",(0,1),0),("pm",(3,4),1)):
    its=intakes_for(8); sc=[1.0]*len(its)
    t=6*DAY+DOSE[idx]; sc[its.index(t)]=0.0
    Ei=eff(range(8),its,sc)[6]
    scen(f"SS_{slot}_window_dose_scaled0",(ss[a],ss[b]),(Ei[a],Ei[b]),slot)
    rows[f"SS_{slot}_window_dose_scaled0"]["eff_nr"]=[float(Ei[a]),float(Ei[b])]
# first dose day 0
E0=E[0]
scen("FIRST_am",(E0[0],E0[1]),(0.0,0.0),"am")
scen("FIRST_pm_day0",(E0[3],E0[4]),(0.0,0.0),"pm")
out["current_resp"]=rows
for k,v in rows.items():
    print(k, "R mu_obs %.2f p_obs %.3f p_lat %.3f | NR mu_obs %.2f p_obs %.3f p_lat %.3f | AUC1 obs %.3f lat %.3f"%(v["responder"]["obs"]["mu"],v["responder"]["obs"]["p_viol"],v["responder"]["lat"]["p_viol"],v["nonresp"]["obs"]["mu"],v["nonresp"]["obs"]["p_viol"],v["nonresp"]["lat"]["p_viol"],v["auc1_obs"],v["auc1_lat"]))
# natural fault-free rates (responder, SS) per day check vs diag 1.15
pa=rows["SS_am_persistent_NR"]["responder"]["lat"]["p_viol"]; pp=rows["SS_pm_persistent_NR"]["responder"]["lat"]["p_viol"]
print("check latent SS violation per day (x.945):",pa,pp,(pa+pp)*.945)
# pooled n doses AUC and doses needed (SS persistent NR; circadian cancels in am+pm pairs)
dsw=[]  # mean over am+pm of swing
sw_am=ss[1]-ss[0]; sw_pm=ss[4]-ss[3]
print("SS swings am,pm",sw_am,sw_pm,"mean",(sw_am+sw_pm)/2)
sdD=math.sqrt(2)*SD_R
sw=(sw_am+sw_pm)/2
pool={}
for n in (1,2,4,14,28):
    pool[n]=dict(auc=float(norm.cdf(sw*math.sqrt(n)/(sdD*math.sqrt(2)))), se=sdD/math.sqrt(n))
n_need=((Z95+Z80)*sdD/sw)**2
print("pooled-pair statistic SS: auc",pool,"doses for 5%/80%:",n_need,"days",n_need/2)
out["pooled_pair_SS"]=dict(swing=sw,auc=pool,doses_needed=n_need,days_needed=n_need/2)
# first dose pooled? only one per patient
# ---------- 2. R1: level statistic ----------
# daily-mean effect by day since start, and its variation from adherence (iid slots: omit .057, delay .081 exp mean 20 min, double ignored)
rng=np.random.default_rng(20261011)
def adherent_intakes(nd,rng,start=0):
    its=[]
    for d in range(start,nd):
        for t in DOSE:
            u=rng.random()
            if u<.057: continue
            dl=0
            if u<.057+.081: dl=min(rng.exponential(20*MIN), 6*H)
            its.append(int(d*DAY+t+dl+5000))
    return sorted(its)
NS=600
daymeans=np.zeros((NS,10))
for s in range(NS):
    its=adherent_intakes(10,rng)
    e=eff(range(10),its)
    daymeans[s]=e.mean(1)
sig_eff=daymeans[:,3:].std(0).mean()
mean_ss=daymeans[:,3:].mean()
print("daily-mean effect by day:",np.round(daymeans.mean(0),2),"sd across patients/days (steady)",sig_eff)
SIG_D=math.sqrt(SD_R**2/5+sig_eff**2)
print("SD of a daily mean (5 readings, noise+adherence):",SIG_D)
out["daily"]=dict(mean_by_day=daymeans.mean(0).tolist(),sig_eff=sig_eff,sig_d=SIG_D,mean_ss=float(mean_ss))
bm=daymeans.mean(0)  # mean effect by day index since start
def dm(n,skip=0): return float(bm[skip:skip+n].mean())
SD_BASE=8.7
R1={}
def analysis(delta_mu, sd):
    return dict(dprime=delta_mu/sd, auc=float(norm.cdf(delta_mu/(sd*math.sqrt(2)))), power_at_5pct=float(1-norm.cdf(Z95-delta_mu/sd)))
# (a) population reference
for n in (1,3,7,14):
    mu=dm(n); sd=math.sqrt(SD_BASE**2+SIG_D**2/n)
    R1[f"pop_n{n}"]=dict(mu=mu,sd=sd,**analysis(mu,sd))
mu_inf=float(mean_ss); R1["pop_inf"]=dict(mu=mu_inf,sd=SD_BASE,**analysis(mu_inf,SD_BASE))
# (b) run-in m days then n treated days
def days_needed(mu_fn, m):
    for n in range(1,200):
        sd=SIG_D*math.sqrt(1/n+(1/m if m else 0)) if m else None
        if m and mu_fn(n)/sd>=Z95+Z80: return n
    return None
for m in (1,2,3,5,7):
    for n in (1,2,3,5,7):
        mu=dm(n); sd=SIG_D*math.sqrt(1/n+1/m)
        R1[f"runin_m{m}_n{n}"]=dict(mu=mu,sd=sd,**analysis(mu,sd))
    R1[f"runin_m{m}_n_needed"]=days_needed(dm,m)
# note run-in with infinite m: sd=SIG_D/sqrt(n)
def n_inf():
    for n in range(1,50):
        if dm(n)/(SIG_D/math.sqrt(n))>=Z95+Z80: return n
R1["runin_minf_n_needed"]=n_inf()
# (c) loss of response: previous m treated days (steady) vs n days after switch to scale 0 for all intakes from day d0
d0=6
its=intakes_for(14); sc=[0.0 if t>=d0*DAY else 1.0 for t in its]
Eloss=eff(range(14),its,sc).mean(1)
print("daily-mean effect around a persistent switch to scale 0 at day 6:",np.round(Eloss,2))
out["loss_profile"]=Eloss.tolist()
# shortfall relative to the responder profile
resp_profile=eff(range(14),its).mean(1)
short=resp_profile-Eloss
print("shortfall by day",np.round(short,2))
out["loss_shortfall"]=short.tolist()
def loss_stat(m,n,gap=0):
    base=resp_profile[d0-m:d0].mean()  # treated before
    mu=(resp_profile[d0+gap:d0+gap+n]-Eloss[d0+gap:d0+gap+n]).mean()
    sd=SIG_D*math.sqrt(1/n+1/m)
    return mu,sd
for m in (3,5):
    for n in (1,2,3,5,7):
        mu,sd=loss_stat(m,n); R1[f"loss_m{m}_n{n}"]=dict(mu=float(mu),sd=sd,**analysis(mu,sd))
out["R1"]=R1
for k,v in R1.items():
    if isinstance(v,dict): print(k,"mu %.2f sd %.2f d' %.2f AUC %.3f pow5 %.2f"%(v["mu"],v["sd"],v["dprime"],v["auc"],v["power_at_5pct"]))
    else: print(k,v)
# ---------- 3. R2: first dose / first 24 h / dose change ----------
R2={}
# first dose pair (current statistic) circadian-known: D mean = 9.27, sd 16.8
for tag,mu_c in (("circ_fixture",circ[0]-circ[1]),("circ_known",0.0)):
    mu=E0[1]-E0[0]+mu_c; sd=math.sqrt(2)*SD_R if tag=="circ_known" else math.hypot(math.sqrt(2)*SD_R,abs(mu_c)*6.1/13.2)
    R2[f"first_pair_{tag}"]=dict(mu_resp=float(mu),mu_nr=float(mu_c),sd=sd,p_viol_resp=float(norm.cdf((DELTA-mu)/sd)),p_viol_nr=float(norm.cdf((DELTA-mu_c)/sd)),auc=float(norm.cdf((mu-mu_c)/(sd*math.sqrt(2)))))
# first-24h: mean of the 4 post-first-dose readings vs 1 pre reading (circadian known) / vs m-day slot-matched run-in
post=E0[1:].mean()
R2["first24h_post_mean_effect"]=float(post)
for m in (0,1,2,3):
    if m==0: sd=SD_R*math.sqrt(1/4+1)
    else: sd=SD_R*math.sqrt(1/4+1/(4*m))
    R2[f"first24h_m{m}"]=dict(mu=float(post),sd=sd,**analysis(post,sd))
# first 48h
post48=np.concatenate([E[0][1:],E[1]]).mean()
for m in (0,2,3):
    n=9
    sd=SD_R*math.sqrt(1/n+(1 if m==0 else 1/(5*m)))   # m=0: single pre reading
    R2[f"first48h_m{m}"]=dict(mu=float(post48),sd=sd,**analysis(post48,sd))
# dose change: doubling (12.5->25 mg: two intakes at each dose time); halving reverse
for mult_from,mult_to in ((1,2),(2,3)):
    pass
E1x=eff(range(10),intakes_for(10,mult=1))[8]; E2x=eff(range(10),intakes_for(10,mult=2))[8]
dchg=(E2x-E1x).mean()
print("dose doubling steady-state effect change by slot",np.round(E2x-E1x,2),"mean",dchg)
R2["dose_doubling_effect_change"]=float(dchg)
R2["dose_doubling_by_slot"]=(E2x-E1x).tolist()
for m in (3,5,7):
    # days needed after change
    for n in range(1,400):
        if dchg/(SIG_D*math.sqrt(1/n+1/m))>=Z95+Z80: R2[f"dose_doubling_n_needed_m{m}"]=n; break
# single-pair statistic for dose change (pre = steady 1x, post = after the dose on 2x): swing change
sw1=E1x[1]-E1x[0]
R2["dose_doubling_single_pair_extra_swing_am"]=float((E2x[1]-E2x[0])-(E1x[1]-E1x[0]))
# omission contrast: omit the 21:00 dose on day 7, effect next day slots vs taken
its_full=intakes_for(10); its_om=[t for t in its_full if t!=7*DAY+21*H]
Ef=eff(range(10),its_full); Eo=eff(range(10),its_om)
om=(Ef-Eo)[8]   # day 8 slots: shortfall after omission on day 7 evening
om7=(Ef-Eo)[7]
print("omitted 21:00 dose day 7: shortfall day7 slots",np.round(om7,2)," day 8 slots",np.round(om,2))
R2["omission_shortfall_day7"]=om7.tolist(); R2["omission_shortfall_day8"]=om.tolist()
# window injection (current drug_nonresponse): one day fully scaled 0 (both doses) at SS: shortfall on that day vs next
its=intakes_for(12); sc=[0.0 if (7*DAY<=t<8*DAY) else 1.0 for t in its]
Ew=eff(range(12),its,sc); Er=eff(range(12),its)
wd=(Er-Ew)
print("one-day NR (both doses day 7) shortfall by day:",np.round(wd.mean(1),2))
R2["oneday_NR_shortfall_by_day"]=wd.mean(1).tolist()
out["R2"]=R2
for k,v in R2.items(): print(k,v)
json.dump(out,open("/tmp/research/resp/sim_out.json","w"),indent=1,default=float)
