import json, sys, math
from collections import defaultdict, Counter
rows=[json.loads(l) for l in open(sys.argv[1])]
by=defaultdict(list)
for r in rows: by[(r['group'],r['variant'])].append(r)
def wilson(k,n,z=1.96):
    p=k/n; d=1+z*z/n; c=p+z*z/(2*n); h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))
    return (c-h)/d,(c+h)/d
out=[]
print("group | variant | n | exp | flag_rate | separated_by (counts) | A_pos(day0) | A_pos(+later) | B_real | pos(day0)")
for (g,v),rs in by.items():
    n=len(rs)
    flag=sum(r['flag'] for r in rs)
    sep=Counter(tuple(r['separated_by']) for r in rs)
    exp=rs[0]['expected']
    # A positive: injected truth event of A's class/mechanism in day0
    mech={'double_take_vs_bounce':('C1','double_take'),'nonresponse_vs_falsified_dispense':('C1','drug_nonresponse'),'refusal_vs_robot_missed':('C1','measurement_refusal'),'bounce_vs_forged_dispense':('C2','dispenser_bounce')}[g]
    mechB={'double_take_vs_bounce':('C2','dispenser_bounce'),'nonresponse_vs_falsified_dispense':('C3','dispense_forgery'),'refusal_vs_robot_missed':('C2','manipulation_failure'),'bounce_vs_forged_dispense':('C3','dispense_forgery')}[g]
    def apos(r):
        return any((e[0],e[1])==mech for e in r['A']['inj_events'])
    def apos_later(r):
        return apos(r) or any((x[0],x[1])==mech and x[5]>0 for x in r['A']['records'])
    def breal(r):
        return any((x[0],x[1])==mechB and x[2] for x in r['B']['records']) and any((e[0],e[1])==mechB for e in r['B']['inj_events'])
    ap=sum(apos(r) for r in rs); apl=sum(apos_later(r) for r in rs); br=sum(breal(r) for r in rs)
    pos=sum(apos(r) and breal(r) for r in rs)
    print(f"{g} | {v} | {n} | {exp} | {flag/n:.3f} | {dict(sep)} | {ap/n:.3f} | {apl/n:.3f} | {br/n:.3f} | {pos/n:.3f}")
