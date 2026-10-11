import sys
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import common, likelihood_attr as L
from ralmon.attribution.rule import _READS
from ralmon.attribution.evidence import NON_PROVENANCE_PATHS
out = []; pr = lambda *a: out.append(" ".join(str(x) for x in a))
pr("#### 1.2 Component catalogue (the sub-causes whose mixture makes a cell)")
pr("| cause | component | templates it can violate | raises (R by construction, C conditional) | tags | source of the row |")
pr("|---|---|---|---|---|---|")
for c in L.COMPS:
    rs = ", ".join(f"{f.split('.')[-1]}:{v}" for f, v in c.raises.items()) or "none (silent)" if c.cause != "C1" else "none"
    pr(f"| {c.cause} | {c.name} | {' '.join(sorted(c.templates))} | {rs} | {' '.join(sorted(c.tags))} | {c.source} |")
pr()
pr("#### 1.3 Cell structure per field and cause (over the whole catalogue; 'structural 0' = eps, 'structural 1' = 1 - eps, 'mixture' = declared weights, 'cond.' = involves qc)")
pr("| field | C1 | C2 | C3 | what has to be decided and by whom |")
pr("|---|---|---|---|---|")
def struct(cause, f):
    cs = [c for c in L.COMPS if c.cause == cause]
    r = [c.name for c in cs if c.raises.get(f) == "R"]; cc = [c.name for c in cs if c.raises.get(f) == "C"]; d = [c.name for c in cs if c.raises.get(f) == "D"]
    if not r and not cc and not d: return "structural 0 (eps)"
    parts = []
    if r: parts.append("R: " + ", ".join(r))
    if cc: parts.append("C: " + ", ".join(cc))
    if d: parts.append("divert share delta")
    return "mixture; " + "; ".join(parts)
need = {
 "system.diagnostics_ok": "driver profile: which faults make the driver report stale (design, WS07-T03) - GAB; mixture weights - GAB",
 "crypto_temporal.authenticated": "deployment property (device authenticates); None otherwise. Cell = share of C3 classes that synthesise or rewrite a message - GAB (mixture)",
 "witness.intake_observed": "delta (C1 diverted dose, 0 in the benchmark adherence model) - GAB; qc for the forgery with a co-located robot - GAB",
 "witness.identity_confirmed": "D-6 of evidence-channels: how identity is checked; C3 naive spoof only - GAB",
}
for f in NON_PROVENANCE_PATHS:
    if f in ("system.battery_low", "witness.robot_present"): continue
    pr(f"| {f} | {struct('C1', f)} | {struct('C2', f)} | {struct('C3', f)} | {need.get(f, 'fault-model/threat-model row; qc and mixture weights - GAB')} |")
pr(f"| {L.XSHORT} (EXTENSION, ADR-032 proposed) | structural 0 (eps) | mixture; C: dispenser_bounce | structural 0 (eps) (timing chosen by the attacker is not modelled) | T_b (registry name dispense_bounce_interval_ms, unverified) - GAB |")
pr(f"| {L.XZERO} (EXTENSION) | structural 0 (eps) | mixture; C: dispenser_bounce | structural 0 (eps) (a forged DISPENSE has no payload: U) | content-sensing sign convention (ADR-032 note) - GAB |")
pr()
pr("#### 1.4 Numeric cells P(A | cause) at the reference point of the grid (eps .01, qc .5, uniform mixtures, fault-model family); `-` = the cause has no component for the template (impossible)")
for t in ("range", "sched", "hold", "count", "resp", "sys", "int"):
    pr(f"**{t}** (support: {', '.join(L.support(t, L.Params())) })")
    pr("| field | C1 | C2 | C3 |"); pr("|---|---|---|---|")
    fs = [f for f in NON_PROVENANCE_PATHS if f in {k for k in L._READS_BY_NAME[t]}]
    if t in L.EXT_TEMPLATES: fs += list(L.EXT_FIELDS)
    for f in fs:
        v = [L.cell(c, t, f, L.Params()) for c in L.CAUSES]
        pr(f"| {f} | " + " | ".join("-" if x is None else f"{x:.3f}" for x in v) + " |")
    pr()
pr("#### 1.5 Parameters of the model (none is a proposal; every number is a grid value)")
pr("| parameter | role | grid values used | where its value would have to come from | awaiting gab |")
pr("|---|---|---|---|---|")
for row in (
 ("eps", "leak of every structural cell: 1-eps if a cause raises the field by construction, eps if not (reading noise, an unmodelled cause)", "0.001, 0.01, 0.05, 0.1", "device specification and literature on the false-alert rate of each channel (none collected); design choice meanwhile", "yes"),
 ("qc", "probability that a conditional raise (LC, SEQ, D-5 conditions) holds", "0.25, 0.5, 0.75", "fault-model conditions LC/SEQ with the device lease, deadline and sequence provision of the real deployment (WS07-T03/EC-OP-18)", "yes"),
 ("component weights (family)", "which sub-causes are in each cause's mixture and with which weights (uniform over those that can violate the template)", "uniform over the fault-model/threat-model catalogue; uniform over the 8+5 subtypes injected by benchmark v1", "design choice; ward incident statistics would be the literature source (none identified)", "yes"),
 ("silent_share", "total within-C2 weight of {stuck_at, cuff_silent_bias, dispenser_bounce}", "uniform, 0.05, 0.25, 0.5, 0.75", "design choice (declared limit of analisi 4.8); device failure statistics", "yes"),
 ("informed_share", "total within-C3 weight of the informed-level attacks", "uniform, 0.25, 0.75", "threat model (attacker capability levels); design choice", "yes"),
 ("divert", "share of C1 in which a dispensed dose is not taken (witness intake False)", "0, 0.1, 0.25", "adherence literature (diversion/pocketing); 0 in the benchmark adherence model (declared simplification)", "yes"),
 ("prior_t(c)", "prior over causes for the template", "uniform; c1_heavy (.6/.3/.1), c2_heavy (.3/.6/.1), c3_rare (.45/.5/.05), c3_heavy (.2/.2/.6): ILLUSTRATIVE", "literature on alert aetiology on wards or a declared design choice; never the injection rates", "yes"),
 ("tau", "abstention threshold: UNDETERMINED if max posterior < tau", "0.5, 0.67, 0.8, 0.9, 0.95, 0.99", "design choice (clinical cost of a wrong cause vs an abstention)", "yes"),
 ("T_b (extension)", "interval under which two openings are a bounce", "1 s, 10 s, 30 s, 60 s, 180 s", "dispenser specification; registry name proposed in ADR-032", "yes"),
 ("profile", "which channels exist: diagnostics reports, authentication, content sensing, robot witness", "with / without diagnostics; authenticating or not; content sensing or not", "device specification; ADR-036", "decided per run"),
):
    pr("| " + " | ".join(row) + " |")
open(f"{common.ROOT}/out/cells_tables.md", "w").write("\n".join(out))
print("\n".join(out))
