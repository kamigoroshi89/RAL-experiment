import json, sys
from collections import Counter, defaultdict
rows=[json.loads(l) for l in open(sys.argv[1])]
res=defaultdict(lambda: Counter())
for r in rows:
    key=(r['group'],r['variant']); c=res[key]; c['n']+=1
    for m in ('A','B'):
        al=[a for a in r[m]['alerts'] if a[0]!='range' and a[3]=='violated']
        ks={a[2] for a in al}
        c[m+'_any_nonrange']+= bool(al)
        for k in ('C1','C2','C3'): c[f'{m}_{k}']+= (k in ks)
# group-level summary
print("variant | n | A:any,C1,C2,C3 | B:any,C1,C2,C3  (non-RANGE violated alerts of the day, n=40/variant)")
for (g,v),c in res.items():
    n=c['n']
    f=lambda m:",".join(str(c[f'{m}_{k}']) for k in ('any_nonrange','C1','C2','C3'))
    print(f"{g[:12]} | {v} | {n} | {f('A')} | {f('B')}")
