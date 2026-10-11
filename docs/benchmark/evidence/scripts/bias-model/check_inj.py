import sys; sys.path.insert(0,"/tmp/research/obs3")
from common import *
rng=np.random.default_rng(1); bad=0
for t in range(200):
    k=int(rng.integers(1,4)); i=int(rng.integers(0,5-k+1)); m=float(rng.choice([1,1.5,2.5])); sign=rng.choice((-1.,1.))
    v0=rng.uniform(A,B,5)
    O=onset_grid(i); E=end_grid(i+k-1); o=int(rng.choice(O))*STEP; e=int(rng.choice(E))*STEP
    inj=run(stream_with(v0),[spec("cuff_silent_bias",o,e-o,sign*m*SIG,"mmHg")])
    got=[x.value for x in inj.stream.samples if x.signal=="bp"]
    v1=v0.copy(); v1[i:i+k]+=sign*m*SIG
    # compare with direct (order of bp samples = reading order)
    if not np.allclose(got,v1): bad+=1
print("mismatches injector vs direct offset:",bad,"of 200")
