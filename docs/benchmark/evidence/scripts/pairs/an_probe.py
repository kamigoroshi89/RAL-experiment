import json, sys
from collections import Counter, defaultdict
rows=[json.loads(l) for l in open(sys.argv[1])]
TAU={'double_take_vs_bounce':'count','bounce_vs_forged_dispense':'count','nonresponse_vs_falsified_dispense':'resp','refusal_vs_robot_missed':'sched'}
TICK={}
res=defaultdict(Counter)
for r in rows:
    g=r['group']; tau=TAU[g]
    kk=[]
    for m in ('A','B'):
        al=[a for a in r[m]['alerts'] if a[0]==tau and a[3]=='violated']
        if g=='nonresponse_vs_falsified_dispense':
            tick = 25200000 if r['dose']==0 else 75600000
            al=[a for a in al if a[1]==f"resp@{tick}"]
        if g=='refusal_vs_robot_missed':
            ticks=[22500000,29700000,51300000,72900000,80100000]
            al=[a for a in al if a[1]==f"sched@{ticks[r['tick_idx']]}"]
        kk.append(al[0][2] if al else "NOALERT")
    res[(g,r['variant'])][tuple(kk)]+=1
for (g,v),c in res.items():
    print(g,v,sum(c.values()),dict(c))
