import sys; sys.path.insert(0,'/tmp/research/resp')
from lib2 import *
N=int(sys.argv[1])
ctx=make_ctx("real2",n_patients=N,n_days=7)
M=[];LM=[]
for idx in range(N):
    params=ctx.draw_patient(idx); bp=ctx.build_patient(params,idx)
    row=[];lrow=[]
    for d in bp.days:
        if d.tail: continue
        o=d.observed; meas=[s.value for s in o.samples if s.signal=="bp"]
        row.append(np.mean(meas) if len(meas)==5 else np.nan)
        lat=[s for s in d.truth.latent.samples if s.signal=="bp"]
        lt=[s.t_device_ms for s in lat]; lv=[s.value for s in lat]
        mt=[s.t_device_ms for s in o.samples if s.signal=="bp"]
        lrow.append(np.mean([lv[bisect.bisect_right(lt,t)-1] for t in mt]) if len(mt)==5 else np.nan)
    M.append(row);LM.append(lrow)
M=np.array(M);LM=np.array(LM)
np.save("real2_M.npy",M);np.save("real2_LM.npy",LM)
ss=M[:,1:]
dev=ss-np.nanmean(ss,1,keepdims=True)
n=np.sum(~np.isnan(ss),1,keepdims=True)
# unbiased within-patient SD of daily means (days 1..6)
w=np.nansum(dev**2,1)/(n[:,0]-1)
print("within-patient SD of observed daily mean (days>=1):",np.sqrt(np.nanmean(w)))
ldev=LM[:,1:]-np.nanmean(LM[:,1:],1,keepdims=True)
wl=np.nansum(ldev**2,1)/(n[:,0]-1)
print("within-patient SD of latent daily mean (at observed instants):",np.sqrt(np.nanmean(wl)))
print("mean by day obs:",np.round(np.nanmean(M,0),2))
print("mean by day latent:",np.round(np.nanmean(LM,0),2))
print("day-0 minus mean(days1-6) per patient: mean %.2f sd %.2f"%(np.nanmean(M[:,0]-np.nanmean(M[:,1:],1)),np.nanstd(M[:,0]-np.nanmean(M[:,1:],1))))
