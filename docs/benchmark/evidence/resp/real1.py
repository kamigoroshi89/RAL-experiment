import sys; sys.path.insert(0,'/tmp/research/resp')
from lib2 import *
import collections
ctx=make_ctx("real1",n_patients=int(sys.argv[1]),n_days=7)
cnt=collections.Counter(); ndays=collections.Counter(); sl=collections.Counter()
for idx in range(int(sys.argv[1])):
    params=ctx.draw_patient(idx); bp=ctx.build_patient(params,idx)
    for d in bp.days:
        if d.tail: continue
        di=d.observed.day_index
        ndays[di]+=1
        for e in d.truth.ground_truth:
            if e.subtype=="spontaneous_resp":
                cnt[di]+=1
                hour=(e.onset_ms%86_400_000)/3.6e6
                sl[(di==0, "am" if hour<12 else "pm")]+=1
print("patients",sys.argv[1])
for di in sorted(ndays): print("day",di,"spont_resp per patient-day %.3f"%(cnt[di]/ndays[di]))
print("slots (day0?, am/pm):",{k:round(v/(ndays[0] if k[0] else sum(ndays[i] for i in ndays if i>0)),3) for k,v in sl.items()})
