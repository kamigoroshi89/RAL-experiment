import sys, os, dataclasses, random, math
sys.dont_write_bytecode=True
sys.path.insert(0,"/tmp/research/obs2")
from dets import *   # B1,B3,PLAN,detect,with_values,make_stream,run,spec,finalize_observed,TICKS,DOSES,DAY
from anchored import onset_grid,end_grid,STEP
import numpy as np
from scipy.stats import norm
SIG=8.0; A,B=110.0,140.0; W=B-A
BASE=make_stream(30_000)
SAMPLE_IDX=[i for i,x in enumerate(BASE.samples) if x.signal=="bp"]
TK=[t+30_000 for t in TICKS]
def stream_with(vals):
    out=list(BASE.samples)
    for i in SAMPLE_IDX:
        x=out[i]; k=TK.index(x.t_device_ms); out[i]=dataclasses.replace(x,value=float(vals[k]))
    return dataclasses.replace(BASE,samples=tuple(out))
def detect_b1(vals):
    day=finalize_observed(stream_with(vals)); return B1.run(day,PLAN)
def detect_b3(vals):
    day=finalize_observed(stream_with(vals)); return B3.run(day,PLAN)
def covered_time(k_idx,dets):
    t0=TK[k_idx]; return [d for d in dets if t0 < d.t_ms <= t0+60_000+STEP]
