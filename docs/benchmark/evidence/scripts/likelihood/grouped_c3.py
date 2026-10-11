"""Members whose old kappa is C3 (diagnostics emitted): table outcome by independence assumption."""
import sys, collections
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import common, likelihood_attr as L
from dataclasses import replace
from sweeps import members, post, REF
for grp in ("none", "g1", "g2"):
    c = collections.Counter()
    for m in members:
        a = m["alert"]
        if a["old_on"] != "C3": continue
        r = post(a, replace(REF, group=grp), "on")
        c[(m["truth"], r.argmax(), r.kappa(.8))] += 1
    print("group", grp, dict(c))
