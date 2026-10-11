"""Checks of the prototype (run: python3 test_likelihood.py). Fixed data, no network, no wall clock."""
import sys, math, pickle, itertools
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import common, likelihood_attr as L
from dataclasses import replace
from ralmon.attribution.rule import A, D, U, F, G, K
from ralmon.attribution.evidence import NON_PROVENANCE_PATHS
reg, tpl, cfg = common.load()
P0 = L.Params()
def rd(**kw):
    base = {f: U for f in NON_PROVENANCE_PATHS}
    for k, v in kw.items(): base[k] = v
    return base
FQ = {"diag": "system.diagnostics_ok", "life": "system.node_lifecycle", "ble": "system.ble_link_quality", "seq": "crypto_temporal.seq_gap_or_replay",
      "auth": "crypto_temporal.authenticated", "manip": "system.manip_task_failed", "qos": "system.qos_deadline_missed", "live": "system.liveliness_ok"}
def R(t, p=P0, **kw):
    return L.posterior_from_readings(rd(**{FQ[k]: v for k, v in kw.items()}), t, p)
n = 0
def ok(c, msg):
    global n; n += 1
    assert c, msg
# 1 posterior is a distribution
for t in ("range", "sched", "hold", "count", "resp", "sys", "int"):
    r = R(t, diag=D, life=D, seq=A)
    ok(abs(sum(r.posterior.values()) - 1) < 1e-12, "sums to 1")
# 2 unavailable contributes factor 1: adding a U field changes nothing
r1 = R("resp", diag=D); r2 = R("resp", diag=D, manip=U, auth=U)
ok(r1.posterior == r2.posterior and r1.loglik == r2.loglik, "U is factor 1")
# 3 mask == unavailable
r3 = L.posterior_from_readings(rd(**{FQ["manip"]: A, FQ["diag"]: D}), "resp", replace(P0, mask=frozenset({FQ["manip"]})))
ok(r3.loglik == R("resp", diag=D).loglik, "masked field = unavailable")
# 4 K treated as unavailable
r4 = L.posterior_from_readings(rd(**{FQ["life"]: K}), "resp", P0)
ok(r4.loglik == R("resp").loglik, "K = unavailable")
# 5 diagnostics ok does not zero a silent fault: P(D | C2, hold) > 0 and log-lik finite
r5 = R("hold", diag=D)
ok(math.isfinite(r5.loglik["C2"]) and L.cell("C2", "hold", FQ["diag"], P0) > P0.eps, "P(diag A | C2) > eps")
# 6 range: C2 has only silent components -> all cells eps -> LLR(C1,C2) = 0 on any reading
r6 = R("range", diag=D, life=D, live=D, qos=D, ble=D)
ok(abs(r6.llr("C1", "C2")) < 1e-12, "range: C1 and C2 indistinguishable on the cuff-path system fields")
# 7 an asserted authentication failure pushes to C3; denied pushes away
ra = R("resp", auth=A); rd_ = R("resp", auth=D)
ok(ra.posterior["C3"] > 0.9 and rd_.posterior["C3"] < R("resp").posterior["C3"], "auth direction")
# 8 monotone in eps for a structural zero: smaller eps -> larger LR for a raised field
l = [R("sched", replace(P0, eps=e), manip=A).llr("C2", "C1") for e in (0.1, 0.05, 0.01, 0.001)]
ok(all(a < b for a, b in zip(l, l[1:])), "LR grows as eps shrinks")
# 9 prior-free: LLR does not depend on the prior
ok(all(abs(R("resp", replace(P0, prior=pn), manip=A).llr("C2", "C1") - R("resp", manip=A).llr("C2", "C1")) < 1e-12 for pn in L.PRIORS), "LLR prior-free")
# 10 posterior scales with the prior as Bayes says
a = R("resp", replace(P0, prior="c1_heavy"), diag=D); b = R("resp", diag=D)
for c1, c2 in itertools.combinations(L.CAUSES, 2):
    lhs = math.log(a.posterior[c1] / a.posterior[c2]) - math.log(b.posterior[c1] / b.posterior[c2])
    rhs = math.log(L.PRIORS["c1_heavy"][c1] / L.PRIORS["c1_heavy"][c2]) - math.log(L.PRIORS["uniform"][c1] / L.PRIORS["uniform"][c2])
    ok(abs(lhs - rhs) < 1e-9, "Bayes")
# 11 unsupported cause has probability 0 (sys has no C1)
ok(R("sys", diag=D).posterior["C1"] == 0.0 and "C1" not in L.support("sys", P0), "support")
# 12 G1: a repeated sequence value (seq asserted, ratio complete) favours C3; a gap (seq asserted, degraded link) favours C2
p1 = replace(P0, group="g1")
rep = L.posterior_from_readings(rd(**{FQ["seq"]: A, FQ["ble"]: F}), "sched", p1)
gap = L.posterior_from_readings(rd(**{FQ["seq"]: A, FQ["ble"]: A}), "sched", p1)
ok(rep.posterior["C3"] > rep.posterior["C2"] and gap.posterior["C2"] > gap.posterior["C3"], "G1 repeat vs gap")
# 13 identical readings give identical results (determinism)
ok(R("resp", diag=D, seq=A).posterior == R("resp", diag=D, seq=A).posterior, "deterministic")
# 14 the attributor does not read the record: violated may be None (tested on a stored vector)
pairs_rows = pickle.load(open(f"{common.ROOT}/out/pairs_p40_sw1.pkl", "rb"))
a0 = pairs_rows[0]["A"]["alerts"][0]
att = L.LikelihoodAttributor(reg, P0)
ok(att.posterior(None, a0["ev_on"]).posterior == att.posterior(a0["record"], a0["ev_on"]).posterior, "record not read")
print("all", n, "checks passed")
