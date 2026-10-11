"""Fault-free observed BP readings from the REAL latent patient model + measurement process, with the committed
literature prior (patient and device rows filled; mean_delay_ms is unfilled -> stand-in) and fixture-only design rows.
Run the builder's own build_patient with injection rates 0 (no faults), no confounder pairs."""
import os, sys, pathlib, json, copy
os.environ["PYTHONDONTWRITEBYTECODE"]="1"
sys.dont_write_bytecode=True
ROOT=pathlib.Path("/home/gab/Desktop/RAL experiment")
sys.path.insert(0,str(ROOT))
import yaml, numpy as np
import tests.benchmark.test_builder as tb
tb.INJECTIONS_FILE=pathlib.Path("/tmp/research/obs3/injections_HEAD.yaml")
from ralmon.benchmark.builder import BuildContext, load_config
from ralmon.benchmark.priors import LiteraturePriorSource
N=int(sys.argv[1]); out=pathlib.Path(sys.argv[2]); tmp=pathlib.Path("/tmp/research/obs3/gen_tmp"); tmp.mkdir(exist_ok=True)
# prior: committed literature prior + stand-in mean_delay_ms (the only unfilled row)
doc=yaml.safe_load((ROOT/"configs/priors/literature_hypertension.yaml").read_text())
for r in doc["parameters"]:
    if r["parameter"]=="mean_delay_ms":
        r.update(value=1_200_000,status="filled",source_ref="STAND-IN for the unfilled row (research script, 20 min)",
                 source_type="design_choice",rationale="stand-in",verified_by=None)
pp=tmp/"prior_standin.yaml"; pp.write_text(yaml.safe_dump(doc,sort_keys=False))
cd=tb.config_document(tmp,prior=pp,n_patients=N,n_days=7,pairs=0,variants=[],rates=(0.0,0.0,0.0))
cd["paths"]["registry"]=str(ROOT/"configs/registry/hypertension.yaml")
cfg=load_config(tb.write_config(tmp,cd))
prior=LiteraturePriorSource(pp,strict=False,allow_fixture_only=True)
ctx=BuildContext.create(cfg,prior,allow_fixture_only=True)
rows=[]  # patient, day, k, t_ms, value, baseline latent at time
for idx in range(N):
    params=ctx.draw_patient(idx)
    bp=ctx.build_patient(params,idx)
    for d in bp.days:
        if d.tail: continue
        obs=d.observed
        n=0
        meas=[s for s in obs.samples if s.signal=="bp"]
        # latent value at the measurement: truth side latent bp at nearest grid step (for diagnosis only)
        for s in meas:
            rows.append((idx,obs.day_index,n,s.t_device_ms%86_400_000,s.value)); n+=1
arr=np.array(rows,dtype=float)
np.save(out,arr)
print(arr.shape, "patients",N)
