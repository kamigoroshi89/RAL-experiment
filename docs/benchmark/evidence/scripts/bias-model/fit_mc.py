import sys, json
sys.path.insert(0,"/tmp/research/obs3")
from fits import *
import numpy as np
def surf(path,case,key):
    R=json.load(open(path)); S={}
    for kk,v in R.items():
        c,m,k=kk.split("|")
        if c==case: S[(float(m),int(k))]=v[key]/v["n"]
    return S
out=[]
for label,path,case,key in (("B1 model O (MC 10000/cell)","/tmp/research/obs3/part2_b1.json","O_iid","cov"),
                            ("B1 model L (MC 10000/cell)","/tmp/research/obs3/part2_b1.json","L_iid","cov"),
                            ("B3 O_s20 day (MC)","/tmp/research/obs3/part2_b3.json","O_s20","b3")):
    try: S=surf(path,case,key)
    except Exception as e: print(label,"missing",e); continue
    print("==",label)
    if label.startswith("B1"):
        Sa=surface_analytic("L" if "model L" in label else "O")
        print("   MC vs analytic: max |diff|",max(abs(S[c]-Sa[c]) for c in S),"RMSE",np.sqrt(np.mean([(S[c]-Sa[c])**2 for c in S])))
    for r in run_protocols(S): print("  ",r[0],f"{r[1]:22s} RMSE {r[2]:.4f} max {r[3]:.4f} at {r[4]}",np.round(r[5],3))
