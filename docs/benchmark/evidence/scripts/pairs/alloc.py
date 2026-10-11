import json, math, sys
import numpy as np
from collections import defaultdict
rows=[json.loads(l) for l in open('/tmp/research/pairs/rows_k1.jsonl')]+[json.loads(l) for l in open('/tmp/research/pairs/rows_g4.jsonl')]
MECH={'double_take_vs_bounce':(('C1','double_take'),('C2','dispenser_bounce')),
 'nonresponse_vs_falsified_dispense':(('C1','drug_nonresponse'),('C3','dispense_forgery')),
 'refusal_vs_robot_missed':(('C1','measurement_refusal'),('C2','manipulation_failure')),
 'bounce_vs_forged_dispense':(('C2','dispenser_bounce'),('C3','dispense_forgery'))}
def pos(r, later=False):
    ma,mb=MECH[r['group']]
    a=any((e[0],e[1])==ma for e in r['A']['inj_events'])
    if later and not a: a=any((x[0],x[1])==ma and x[5]>0 for x in r['A']['records'])
    b=any((x[0],x[1])==mb and x[2] for x in r['B']['records']) and any((e[0],e[1])==mb for e in r['B']['inj_events'])
    return a and b
GR=['double_take_vs_bounce','nonresponse_vs_falsified_dispense','refusal_vs_robot_missed','bounce_vs_forged_dispense']
by=defaultdict(list)
for r in rows: by[(r['group'],r['variant'])].append(r)
stats={}
for (g,v),rs in by.items():
    n=len(rs)
    for later in (False,True):
        d=sum(pos(r,later) and not r['flag'] for r in rs)/n   # distinguishable and positive
        i=sum(pos(r,later) and r['flag'] for r in rs)/n       # indistinguishable and positive
        allp=sum(pos(r,later) for r in rs)/n
        stats[(g,v,later)]=(d,i,allp,n,rs[0]['expected'])
# print per-variant table (day0)
print("PER VARIANT (day0 positives): n, expected_indist, share pos&dist, share pos&indist, share pos, MC se(pos)")
for g in GR:
    for (gg,v,l),(d,i,a,n,e) in stats.items():
        if gg==g and not l:
            dl=stats[(g,v,True)]
            print(f"{g[:14]} {v:28s} n={n} exp_ind={e} dist={d:.3f} ind={i:.3f} pos={a:.3f} se={math.sqrt(a*(1-a)/n):.3f} pos_incl_closing={dl[2]:.3f}")
def pb_cdf(ps):
    """Poisson-binomial pmf by convolution"""
    pmf=np.array([1.0])
    for p in ps:
        pmf=np.convolve(pmf,[1-p,p])
    return pmf
def need(ps_per_variant_unit, share, target, use_p5, vlist):
    """smallest n per variant (equal) s.t. mean>=target (and P5>=target)"""
    for n in range(1,5000):
        ps=[]
        for s in vlist: ps += [share*s]*n
        mean=sum(ps)
        if mean<target: continue
        if not use_p5: return n,mean,None
        pmf=pb_cdf(ps); cdf=np.cumsum(pmf)
        # P5 = smallest k with cdf(k)>=0.05
        p5=int(np.searchsorted(cdf,0.05))
        if p5>=target: return n,mean,p5
    return None
def group_alloc(g, share=0.25, target=56, later=False):
    dist_v=[v for (gg,v,l),(d,i,a,n,e) in stats.items() if gg==g and not l and not e]
    ind_v=[v for (gg,v,l),(d,i,a,n,e) in stats.items() if gg==g and not l and e]
    sd=[stats[(g,v,later)][0] for v in dist_v]
    return dist_v, ind_v, sd
print()
out={}
for later in (False,True):
  print("== positives incl. closing-step events:", later)
  for g in GR:
    dist_v,ind_v,sd=group_alloc(g,later=later)
    m,mu,_=need(None,0.25,56,False,sd); n5,mu5,p5=need(None,0.25,56,True,sd)
    print(f"{g}: d_g={len(dist_v)} mean s_dist={np.mean(sd):.3f}  n/variant(mean>=56)={m} (E={mu:.1f}) ; n/variant(P5>=56)={n5} (E={mu5:.1f}, P5={p5}) -> pairs {n5*len(dist_v)}")
    out[(g,later)]=(len(dist_v),m,n5)

print("\n==== ALLOCATION (day0 positives) ====")
Z=1.959964
def m_for(h): return math.ceil(Z*Z*0.25/(h*h))
HS=(0.10,0.15,0.20)
print("test pairs needed for 95% half-width (worst case p=.5, normal approx):", {h:m_for(h) for h in HS}, {h:round(Z*Z*0.25/(h*h),2) for h in HS})
def ind_need(g, share, m, use_p5, n_dist_per_variant, later=False):
    dist_v,ind_v,sd=group_alloc(g,later=later)
    # incidental indistinguishable positives inside designed-distinguishable variants (per pair)
    inc=[stats[(g,v,later)][1] for v in dist_v]
    base=[]
    for s in inc: base += [share*s]*n_dist_per_variant
    s_ind=[stats[(g,v,later)][1] for v in ind_v]
    for n in range(0,6000):
        ps=list(base)
        for s in s_ind: ps += [share*s]*n
        mean=sum(ps)
        if mean<m: continue
        if not use_p5: return n, mean, None
        cdf=np.cumsum(pb_cdf(ps)); p5=int(np.searchsorted(cdf,0.05))
        if p5>=m: return n, mean, p5
    return None
def totals(share=0.25, target=56, use_p5=True, later=False, h=0.10, verbose=False):
    tot=0; rec={}
    for g in GR:
        dist_v,ind_v,sd=group_alloc(g,later=later)
        nd=need(None,share,target,use_p5,sd)[0]
        ni=ind_need(g,share,m_for(h),use_p5,nd,later)[0]
        rec[g]=(len(dist_v),nd,len(ind_v),ni,nd*len(dist_v)+ni*len(ind_v))
        tot+=rec[g][4]
    return tot,rec
for use_p5 in (False,True):
  for h in HS:
    tot,rec=totals(use_p5=use_p5,h=h)
    print(f"P5={use_p5} h={h}: total pairs={tot}  ", {g[:10]:r for g,r in rec.items()})

print("\n==== SENSITIVITY: test share (P5 rule, equal pairs per variant) ====")
for share in (0.20,0.25,0.30,1/3,0.5):
    row=[]
    for h in (0.10,0.15,0.20):
        tot,rec=totals(share=share,use_p5=True,h=h)
        row.append(tot)
    tot0,rec0=totals(share=share,use_p5=True,h=0.15)
    dist_only=sum(r[1]*r[0] for r in rec0.values())
    print(f"share={share:.3f}: total pairs h=.10/.15/.20 = {row}; distinguishable-stratum-only pairs = {dist_only}")
print("mean-only rule:")
for share in (0.20,0.25,0.30,1/3,0.5):
    row=[totals(share=share,use_p5=False,h=h)[0] for h in (0.10,0.15,0.20)]
    print(f"share={share:.3f}: {row}")

print("\n==== hypergeometric vs binomial (actual split: fixed test size over all units) ====")
rng=np.random.default_rng(0)
tot,rec=totals(use_p5=True,h=0.15)
npairs=tot; Ntot=200+npairs; ntest=round(0.25*Ntot)
print("N units",Ntot,"n_test",ntest,"pairs",npairs)
# build unit list with per-group, per-variant probability of dist-positive and ind-positive
units=[]  # (group, p_dist, p_ind)
for g,(dg,nd,ig,ni,t) in rec.items():
    dist_v,ind_v,sd=group_alloc(g)
    for v in dist_v:
        d,i,a,n,e=stats[(g,v,False)]
        for _ in range(nd): units.append((g,d,i))
    for v in ind_v:
        d,i,a,n,e=stats[(g,v,False)]
        for _ in range(ni): units.append((g,d,i))
units_g=np.array([GR.index(u[0]) for u in units]); pd=np.array([u[1] for u in units]); pi=np.array([u[2] for u in units])
M=20000
res_dist=np.zeros((M,4),int); res_ind=np.zeros((M,4),int)
Ndec=len(units)
for k in range(M):
    # draw positives once, then test membership by a random subset of ntest among Ntot units (200 are virtual)
    sel=rng.choice(Ntot,size=ntest,replace=False)
    sel=sel[sel<Ndec]   # first Ndec indices are pair units
    u=rng.random(len(sel))
    isd=u<pd[sel]; isi=(~isd)&(u<pd[sel]+pi[sel])
    for gi in range(4):
        m=units_g[sel]==gi
        res_dist[k,gi]=(isd&m).sum(); res_ind[k,gi]=(isi&m).sum()
for gi,g in enumerate(GR):
    print(g, "dist-stratum test positives: mean %.1f P5 %d P1 %d min %d | ind-stratum: mean %.1f P5 %d"%(res_dist[:,gi].mean(),np.percentile(res_dist[:,gi],5),np.percentile(res_dist[:,gi],1),res_dist[:,gi].min(),res_ind[:,gi].mean(),np.percentile(res_ind[:,gi],5)))
