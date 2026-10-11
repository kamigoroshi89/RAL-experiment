"""Item 2: why the main-population log score is worse with driver diagnostics (0.901 against 0.894)."""
import sys, math, collections
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import common, likelihood_attr as L, mainlib as M
from dataclasses import replace
from main_report import labelled, post, REF, CL
H = 3600 * 1000
items = labelled("m120", "injected", 24 * H)
DIAG = "system.diagnostics_ok"
out = []; pr = lambda *a: out.append(" ".join(str(x) for x in a))
tot = collections.defaultdict(lambda: [0, 0.0])   # (template, truth, class) -> n, sum delta
cls_counts = collections.Counter()
N = 0; sON = sOFF = 0.0
bytarget = collections.Counter()
for it in items:
    if it["truth"] not in CL: continue
    a = it["alert"]
    rOn = post(a, REF, "ev_on"); rOff = post(a, REF, "ev_off")
    if rOn is None or rOff is None: continue
    t = a["template"]
    lOn = -math.log(max(rOn.posterior[it["truth"]], 1e-12)); lOff = -math.log(max(rOff.posterior[it["truth"]], 1e-12))
    rd = L.classes_from_rule(L.LikelihoodAttributor(common.load()[0]).rule, a["ev_on"], a["record"].template) if False else None
    dcls = {True: "D", False: "A", None: "U"}[a["ev_on"].system.diagnostics_ok]
    cls_counts[(it["truth"], dcls)] += 1
    k = (t, it["truth"], dcls)
    tot[k][0] += 1; tot[k][1] += lOn - lOff
    N += 1; sON += lOn; sOFF += lOff
pr(f"alerts scored {N}; mean log score with diagnostics {sON/N:.4f}, without {sOFF/N:.4f}; difference (with minus without) {sON/N - sOFF/N:+.4f} nats per alert, total {sON - sOFF:+.1f} nats")
pr()
pr("#### 9.2.1 Change of the log score caused by the diagnostics field, by template, true cause and reading class (sum of the per-alert differences; positive = worse with diagnostics)")
pr("| template | truth | DIAG class | alerts | sum of change (nats) | mean change |"); pr("|---|---|---|---|---|---|")
for k, (n, s) in sorted(tot.items()):
    pr(f"| {k[0]} | {k[1]} | {k[2]} | {n} | {s:+.2f} | {s/n:+.4f} |")
pr()
by_t = collections.defaultdict(float); by_c = collections.defaultdict(float); by_cl = collections.defaultdict(float)
for (t, c, d), (n, s) in tot.items(): by_t[t] += s; by_c[c] += s; by_cl[d] += s
pr("By template: " + ", ".join(f"{t} {v:+.1f}" for t, v in sorted(by_t.items())))
pr("By true cause: " + ", ".join(f"{c} {v:+.1f}" for c, v in sorted(by_c.items())))
pr("By reading class: " + ", ".join(f"{c} {v:+.1f}" for c, v in sorted(by_cl.items())))
pr()
# model cell against empirical rate
pr("#### 9.2.2 The cell P(DIAG = A | cause) against the empirical rate of A among the alerts of that cause (diagnostic only, not used to fit)")
pr("| template | cause | model P(A) | empirical A | empirical A or D | alerts |"); pr("|---|---|---|---|---|---|")
emp = collections.defaultdict(lambda: [0, 0, 0])
for it in items:
    if it["truth"] not in CL: continue
    cl = it["alert"]["ev_on"].system.diagnostics_ok
    e = emp[(it["alert"]["template"], it["truth"])]
    e[2] += 1
    if cl is not None: e[1] += 1
    if cl is False: e[0] += 1
for (t, c), (a_, ad, n) in sorted(emp.items()):
    cell = L.cell(c, t, DIAG, REF)
    pr(f"| {t} | {c} | {'-' if cell is None else f'{cell:.3f}'} | {a_/ad:.3f} ({a_}/{ad}) | {ad} | {n} |" if ad else f"| {t} | {c} | - | - | 0 | {n} |")
pr()
# ble_dropout alerts: A or D, by target
pr("#### 9.2.3 Alerts matched to a ble_dropout: reading class of DIAG by dropout target")
cnt = collections.Counter()
for d in M.load("m120"):
    for a, comp in M.label_alerts(d):
        t, e = M.truth_of(comp, "injected")
        if t == "C2" and e and e[1] == "ble_dropout":
            tg = [l["params"].get("target") for l in d["log"] if l["subtype"] == "ble_dropout" and l["onset_ms"] == e[3]]
            cl = {True: "D", False: "A", None: "U"}[a["ev_on"].system.diagnostics_ok]
            cnt[(tg[0] if tg else "?", a["template"], cl)] += 1
pr("| target | template | DIAG | alerts |"); pr("|---|---|---|---|")
for k, v in sorted(cnt.items(), key=str): pr(f"| {k[0]} | {k[1]} | {k[2]} | {v} |")
open(f"{common.ROOT}/out/diag_decomp.md", "w").write("\n".join(out))
print("\n".join(out))
