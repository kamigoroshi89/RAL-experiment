import sys, time, os, shutil, json, subprocess
sys.path.insert(0, "/tmp/research/pairs/scripts")
import mkcfg
npat=int(sys.argv[1]); pairs=int(sys.argv[2]); tag=sys.argv[3]
cfg = mkcfg.mk(f"cost_{tag}", n_patients=npat, pairs=pairs, g4=True)
sys.path.insert(0, "/tmp/research/pairs/repo_g4/src")
from ralmon.benchmark.builder import BuildContext
t=time.time()
ctx = BuildContext.create(cfg, allow_fixture_only=True)
out=f"/tmp/research/pairs/out_{tag}"
shutil.rmtree(out, ignore_errors=True)
m = ctx.generate(out, git_rev="research")
dt=time.time()-t
size=int(subprocess.run(["du","-sb",out],capture_output=True,text=True).stdout.split()[0])
by={}
for sub in ("days","truth","generator","plans"):
    by[sub]=int(subprocess.run(["du","-sb",f"{out}/{sub}"],capture_output=True,text=True).stdout.split()[0])
nfiles=sum(len(f) for _,_,f in os.walk(out))
print(tag, "secs",round(dt,1),"bytes",size,"files",nfiles,by)
