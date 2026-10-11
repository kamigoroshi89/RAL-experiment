"""B1 and B3 on FAULT-FREE days of the real generator (literature prior + stand-in mean_delay + fixture design rows)."""
import os, sys, pathlib, json
sys.dont_write_bytecode=True
ROOT=pathlib.Path("/home/gab/Desktop/RAL experiment"); sys.path.insert(0,str(ROOT))
import yaml, numpy as np
import tests.benchmark.test_builder as tb
tb.INJECTIONS_FILE=pathlib.Path("/tmp/research/obs3/injections_HEAD.yaml")
from ralmon.benchmark.builder import BuildContext, load_config
from ralmon.benchmark.priors import LiteraturePriorSource
from ralmon.baselines import B1StaticThresholds, B3PlainSTL
from ralmon.baselines.base import TimingConfig
from ralmon.spec import load_registry, load_templates
from multiprocessing import Pool
N0,N1=int(sys.argv[1]),int(sys.argv[2])
tmp=pathlib.Path(f"/tmp/research/obs3/gen_tmp_{N0}"); tmp.mkdir(exist_ok=True)
def setup():
    doc=yaml.safe_load((ROOT/"configs/priors/literature_hypertension.yaml").read_text())
    for r in doc["parameters"]:
        if r["parameter"]=="mean_delay_ms":
            r.update(value=1_200_000,status="filled",source_ref="STAND-IN",source_type="design_choice",rationale="stand-in",verified_by=None)
    pp=tmp/"prior_standin.yaml"; pp.write_text(yaml.safe_dump(doc,sort_keys=False))
    cd=tb.config_document(tmp,prior=pp,n_patients=400,n_days=7,pairs=0,variants=[],rates=(0.0,0.0,0.0))
    cd["paths"]["registry"]=str(ROOT/"configs/registry/hypertension.yaml")
    cfg=load_config(tb.write_config(tmp,cd))
    prior=LiteraturePriorSource(pp,strict=False,allow_fixture_only=True)
    return BuildContext.create(cfg,prior,allow_fixture_only=True)
ctx=setup()
reg=ctx.registry
T=TimingConfig(60000,0,3_600_000)
def one(idx):
    b1=B1StaticThresholds(timing=T,registry=reg); b1.fit([],[])
    b3=B3PlainSTL(tuple(ctx.templates),reg,timing=T); b3.fit([],[])
    params=ctx.draw_patient(idx); bp=ctx.build_patient(params,idx)
    out=[]
    for d in bp.days:
        if d.tail: continue
        o=d.observed
        bpv=[s.value for s in o.samples if s.signal=="bp"]
        nout=sum((x<110) or (x>140) for x in bpv)
        d1=b1.run(o,bp.plan); d3=b3.run(o,bp.plan)
        out.append((idx,o.day_index,len(bpv),nout,len(d1),len(d3)))
    return out
if __name__=="__main__":
    with Pool(24) as p: res=p.map(one,range(N0,N1))
    arr=np.array([r for x in res for r in x]); np.save(f"/tmp/research/obs3/real_baselines_{N0}.npy",arr)
    print(arr.shape, "days; P(B1 alarm)",(arr[:,4]>0).mean(),"P(B3 alarm)",(arr[:,5]>0).mean(),"P(any out)",(arr[:,3]>0).mean(),
          "mean B1 n",arr[:,4].mean(),"B3 n",arr[:,5].mean(),"readings/day",arr[:,2].mean())
