import sys, pickle, math
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import common, pairlib as P
out = pickle.load(open(f"{common.ROOT}/out/sweeps.pkl", "rb"))
G = P.GROUPS
def f(x, nd=2):
    return "nan" if x is None or (isinstance(x, float) and math.isnan(x)) else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))
lines = []
pr = lambda *a: lines.append(" ".join(str(x) for x in a))
pr("### 6.1 One-at-a-time sweeps from the reference point (eps .01, qc .5, uniform prior, fm family, uniform mixtures, no grouping, tau .8)")
pr("Columns. Pairs (distinguishable, primary template): D>0 rate per group g1 double_take_vs_bounce / g2 nonresponse / g3 refusal / g4 bounce_vs_forged; mean Lambda_A of the indistinguishable stratum per group (lean toward c_A, nats). Members (1879 matched, own match): argmax = truth, UND / confident right / confident wrong at the row's tau, confident C1 for a member whose truth is not C1, confident-C1 bounce members (of 618). Main population (m120): log score, Brier, silent-fault alerts with confident C1 / with argmax C1 (of n).")
pr()
pr("| parameter | value | D>0 g1/g2/g3/g4 | indist mean Lambda_A g1/g2/g3/g4 | argmax=truth /1879 | UND / right / wrong | conf. C1 for non-C1 | bounce members with conf. C1 (of 618: g1 B + g4 A) | main log / Brier | silent conf C1 / argmax C1 (of n) |")
pr("|---|---|---|---|---|---|---|---|---|---|")
for k, v, h in out["one_at_a_time"]:
    d = h["D_pos_by_group"]; l = h["indist_meanLambdaA"]
    pr(f"| {k} | {v} | " + "/".join(f(d.get(g, float('nan'))) for g in G) + " | " + "/".join(f(l.get(g, float('nan'))) for g in G) +
       f" | {h['argmax_ok']} | {h['und']} / {h['right']} / {h['wrong']} | {h['conf_C1_not_C1']} | {h['bounce_conf_C1']}/{h['bounce_n']} | {h['main_log']:.3f} / {h['main_brier']:.3f} | {h['sil_conf_C1']} / {h['sil_argmax_C1']} (of {h['sil_n']}) |")
pr()
pr("### 6.2 Variants of the evidence set at the reference point")
pr("| variant | D>0 g1/g2/g3/g4 | argmax=truth | UND / right / wrong | main log / Brier |")
pr("|---|---|---|---|---|")
for n, h in out["variants"]:
    d = h["D_pos_by_group"]
    pr(f"| {n} | " + "/".join(f(d.get(g, float('nan'))) for g in G) + f" | {h['argmax_ok']} | {h['und']} / {h['right']} / {h['wrong']} | {h['main_log']:.3f} / {h['main_brier']:.3f} |")
pr()
fa = out["factorial"]
pr(f"### 6.3 Full factorial over eps x qc x prior x silent_share x grouping ({len(fa)} combinations): range of the headline quantities")
def rng(fn, label, fmt="{:.3f}"):
    vals = [(fn(h), p) for p, h in fa]
    lo = min(vals, key=lambda x: x[0]); hi = max(vals, key=lambda x: x[0])
    pr(f"| {label} | {fmt.format(lo[0])} | {fmt.format(hi[0])} | min at eps={lo[1].eps} qc={lo[1].qc} prior={lo[1].prior} silent={lo[1].silent_share} group={lo[1].group}; max at eps={hi[1].eps} qc={hi[1].qc} prior={hi[1].prior} silent={hi[1].silent_share} group={hi[1].group} |")
pr("| quantity | min | max | where |"); pr("|---|---|---|---|")
for i, g in enumerate(G):
    rng(lambda h, g=g: h["D_pos_by_group"].get(g, float("nan")), f"D>0 rate, {g}")
rng(lambda h: h["D_pos"] / h["pairs_dist_n"], "D>0 rate, all distinguishable pairs")
rng(lambda h: h["both"] / h["pairs_dist_n"], "both-correct-direction, all distinguishable pairs")
rng(lambda h: h["argmax_ok"], "members with argmax = truth (of 1879)", "{:.0f}")
rng(lambda h: h["right"], "confident right members @ tau .8", "{:.0f}")
rng(lambda h: h["wrong"], "confident wrong members @ tau .8", "{:.0f}")
rng(lambda h: h["conf_C1_not_C1"], "confident C1 for members whose truth is not C1 @ .8", "{:.0f}")
rng(lambda h: h["bounce_conf_C1"], "bounce members (618) with confident C1 @ .8", "{:.0f}")
rng(lambda h: h["main_log"], "main log score (nats)")
rng(lambda h: h["main_brier"], "main Brier")
rng(lambda h: h["sil_conf_C1"] / max(1, h["sil_n"]), "silent-fault alerts with confident C1 @ .8 (share)")
rng(lambda h: h["sil_argmax_C1"] / max(1, h["sil_n"]), "silent-fault alerts with argmax C1 (share)")
pr()
# silent share x eps table for silent faults
pr("### 6.4 Silent-fault alerts of the main population (stuck_at, cuff_silent_bias, dispenser_bounce): share with confident C1 at tau .8 and with argmax C1, by eps and silent share (uniform prior, qc .5, no grouping)")
pr("| eps | silent share | confident C1 | argmax C1 | n |"); pr("|---|---|---|---|---|")
for p, h in fa:
    if p.qc == 0.5 and p.prior == "uniform" and p.group == "none":
        pr(f"| {p.eps} | {p.silent_share} | {h['sil_conf_C1']} | {h['sil_argmax_C1']} | {h['sil_n']} |")
pr()
pr("### 6.5 The same with the C1-heavy illustrative prior (0.6/0.3/0.1)")
pr("| eps | silent share | confident C1 | argmax C1 | n |"); pr("|---|---|---|---|---|")
for p, h in fa:
    if p.qc == 0.5 and p.prior == "c1_heavy" and p.group == "none":
        pr(f"| {p.eps} | {p.silent_share} | {h['sil_conf_C1']} | {h['sil_argmax_C1']} | {h['sil_n']} |")
open(f"{common.ROOT}/out/sweeps_tables.md", "w").write("\n".join(lines))
print("\n".join(lines))
