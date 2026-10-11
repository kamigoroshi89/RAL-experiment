import json, sys, math
sys.path.insert(0,"/tmp/research/obs3")
from analytic import *
R=json.load(open("/tmp/research/obs3/part1_b1.json"))
def ci(x,n): 
    p=x/n; se=math.sqrt(max(p*(1-p),1e-12)/n); return p,1.96*se
def fmt(x,n): p,h=ci(x,n); return f"{p:.3f}±{h:.3f}"
for case in ("O_iid","L_iid","O_s10","O_s20","L_s10","L_s20"):
    print("==",case)
    print("m  k | covered-readings alarm WITH | WITHOUT (same draws) | excess | new alarms(without->with) | lost | day-level WITH | day WITHOUT | analytic L/O")
    for m in (0.0,1.0,1.5,2.5):
        for k in (1,2,3):
            c=R[f"{case}|{m}|{k}"]; n=c["n"]
            pw,hw=ci(c["cov_with"],n); p0,h0=ci(c["cov_without"],n)
            an=Pk(p_out_L(m),k) if case.startswith("L") else Pk(p_out_O(m),k)
            share=(p0/pw if pw>0 else float('nan'))
            print(f"{m:3} {k} | {fmt(c['cov_with'],n)} | {fmt(c['cov_without'],n)} | {pw-p0:+.3f} | {c['cov_new']/n:.3f} | {c['cov_lost']/n:.3f} | {fmt(c['day_with'],n)} | {fmt(c['day_without'],n)} | {an:.3f} | share_at_zero {share:.2f} | N={n}")
