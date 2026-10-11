"""Why does the hierarchical rule not reach C1 even when diagnostics are emitted? Decision rows and missing fields for the
matched alerts of C1 members (pairs), and class frequencies of the fields (pairs and main population)."""
import sys, collections
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import pairlib as P, mainlib as M, common, likelihood_attr as L
from ralmon.attribution.rule import HierarchicalRule
reg, tpl, cfg = common.load()
rule = HierarchicalRule(reg)
rows = P.load("p40", 1)
out = []; pr = lambda *a: out.append(" ".join(str(x) for x in a))
pr("### 7.1 Old rule on the matched alerts of C1 members of the pairs, diagnostics emitted (decision row, abstention reason, fields missing for the exclusion)")
pr("| template | row | reason | missing fields (exclusion set) | n |"); pr("|---|---|---|---|---|")
c = collections.Counter()
for r in rows:
    P.match_pair(r)
    for m in "AB":
        if r["cause"][m] != "C1" or not r["own"][m]: continue
        a = r["own"][m]
        d = rule.decide(a["record"], a["ev_on"])
        c[(a["template"], d.row, d.reason.value if d.reason else "-", tuple(x.split(".")[-1] for x in d.missing))] += 1
for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
    pr(f"| {k[0]} | {k[1]} | {k[2]} | {', '.join(k[3]) or '-'} | {v} |")
pr()
# field class frequencies in matched alerts by truth cause, pairs, profile ON
pr("### 7.2 Reading classes of the fields at the matched alerts of the pairs (profile with diagnostics), by truth cause: A / D / U / other counts")
cnt = collections.defaultdict(collections.Counter)
for r in rows:
    for m in "AB":
        a = r["own"][m]
        if not a: continue
        rd = L.classes_from_rule(L.LikelihoodAttributor(reg).rule, a["ev_on"], a["record"].template)
        for f, cl in rd.items():
            if cl == "U" and f not in L._READS_BY_NAME[a["template"]]: continue
            cnt[(r["cause"][m], f)][cl] += 1
pr("| cause | field | classes |"); pr("|---|---|---|")
for (cause, f), v in sorted(cnt.items()):
    pr(f"| {cause} | {f} | {dict(v)} |")
open(f"{common.ROOT}/out/structural.md", "w").write("\n".join(out))
print("\n".join(out))
