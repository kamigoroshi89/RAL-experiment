"""Write a complete builder configuration under /tmp/research/likelihood/runs/<name>/ from the committed files
(snapshot of HEAD in /tmp/research/pairs/repo).  Every awaiting row gets a PLACEHOLDER (labelled in source_ref)."""
import copy, hashlib, json, sys
from pathlib import Path
import yaml
import numpy as np

REPO = Path("/tmp/research/likelihood/repo")
REPO_G4 = Path("/tmp/research/likelihood/repo")
HOUR = 3_600_000
MIN = 60_000
DAY = 86_400_000

def mk(name, *, durations=None, rates=(0.3, 0.3, 0.2), n_patients=100, n_days=7, seed=0, pairs=0,
       vitals_ms=MIN, mags=None, noise_seg=True, mean_delay_ms=30*MIN, dwell_ms=10*MIN, bpm_bounds=(40.0,180.0),
       dur_by_subtype=None, g4=False, repo=None):
    """durations: dict level->ms applied to every duration row; dur_by_subtype: subtype -> dict level->ms (override)."""
    REPO_ = REPO_G4 if g4 else REPO
    root = Path("/tmp/research/likelihood/runs") / name
    if root.exists():
        import shutil; shutil.rmtree(root)
    (root / "configs").mkdir(parents=True)
    import shutil
    for d in ("benchmark", "registry", "priors", "templates"):
        shutil.copytree(REPO_ / "configs" / d, root / "configs" / d)
    shutil.copy(REPO_ / "configs" / "diagnosability.yaml", root / "configs")
    PH = "PLACEHOLDER FOR SENSITIVITY ONLY (research run, not a proposal)"
    # --- generator design
    gd = root / "configs/benchmark/generator_design.yaml"
    doc = yaml.safe_load(gd.read_text())
    vals = {"circadian_peak_clock_ms": 14*HOUR, "intake_lag_ms": 5_000, "double_take_gap_ms": 2*MIN,
            "robot_dwell_ms": dwell_ms, "vitals_period_ms": vitals_ms}
    for r in doc["parameters"]:
        if r["status"] == "awaiting_human_value":
            r.update(value=vals[r["parameter"]], status="filled", source_ref=PH, rationale=PH, verified_by=None)
    gd.write_text(yaml.safe_dump(doc, sort_keys=False))
    # --- prior
    pp = root / "configs/priors/literature_hypertension.yaml"
    doc = yaml.safe_load(pp.read_text())
    for r in doc["parameters"]:
        if r["status"] == "awaiting_human_value":
            r.update(value=mean_delay_ms, status="filled", source_ref=PH, rationale=PH, verified_by=None)
    pp.write_text(yaml.safe_dump(doc, sort_keys=False))
    # --- injections
    ij = root / "configs/benchmark/injections.yaml"
    doc = yaml.safe_load(ij.read_text())
    durations = durations or {"short": HOUR, "medium": 4*HOUR, "long": 12*HOUR}
    M = {"cuff_silent_bias_magnitude_low": 1.0, "cuff_silent_bias_magnitude_medium": 1.5, "cuff_silent_bias_magnitude_high": 2.5,
         "ecg_noise_magnitude_low": 1.0, "ecg_noise_magnitude_medium": 2.0, "ecg_noise_magnitude_high": 3.0,
         "dispenser_bounce_magnitude_nominal": 500, "dispenser_bounce_magnitude_stress_low": 5000, "dispenser_bounce_magnitude_stress_high": 20000,
         "nav_delay_magnitude_low": 0.5, "nav_delay_magnitude_medium": 1.0, "nav_delay_magnitude_high": 2.0,
         "hypertensive_spike_magnitude_below": 0.5, "hypertensive_spike_magnitude_near": 1.0, "hypertensive_spike_magnitude_above": 2.0,
         "hypotension_below_hold_magnitude_below": 0.5, "hypotension_below_hold_magnitude_near": 1.0, "hypotension_below_hold_magnitude_above": 2.0,
         "drug_nonresponse_magnitude_partial": 0.5, "drug_nonresponse_magnitude_mild": 0.9,
         "injection_naive_pulse_lower_bpm": bpm_bounds[0], "injection_naive_pulse_upper_bpm": bpm_bounds[1]}
    M.update(mags or {})
    fixed = {"injection_rate_c1": rates[0], "injection_rate_c2": rates[1], "injection_rate_c3": rates[2],
             "confounder_pairs_per_variant": pairs}
    for r in doc["parameters"]:
        n = r["parameter"]
        if n in fixed:
            r.update(value=fixed[n], status="filled")
        elif r["status"] == "awaiting_human_value" or n in M:
            if "_duration_" in n:
                sub, lev = n.split("_duration_")
                v = (dur_by_subtype or {}).get(sub, durations)[lev]
            else:
                v = M[n]
            r.update(value=v, status="filled", source_ref=PH, rationale=PH, verified_by=None)
    if g4:
        grp = {"members": {"A": {"class": "C2", "subtype": "dispenser_bounce"}, "B": {"class": "C3", "subtype": "dispense_forgery"}},
               "matrix_rows": ["prototype"], "added_by": "prototype (research copy)", "variants": {}}
        for att in ("naive", "informed"):
            for auth in (True, False):
                for cont in (True, False):
                    vid = f"{att}_{'auth' if auth else 'noauth'}_{'content' if cont else 'nocontent'}"
                    wh = ([] if auth else ["verification"]) + ([] if cont else ["content_change"])
                    exp = (att == "informed") and (not auth) and (not cont)
                    grp["variants"][vid] = {"attacker": att, "withheld": wh, "expected_indistinguishable": exp,
                        "source_type": "design_choice", "source_ref": "prototype (research copy)", "rationale": "prototype"}
        doc["confounders"]["groups"]["bounce_vs_forged_dispense"] = grp
    ij.write_text(yaml.safe_dump(doc, sort_keys=False))
    # --- segments (inline, FIXTURE-ONLY)
    seg = root / "segments"; seg.mkdir()
    entries = []
    rng = np.random.default_rng(1)
    for kind, base, spread, unit, period, n in (
        ("hr_clean", 70.0, 30, "bpm", MIN, DAY // MIN),
        ("spo2_clean", 95.0, 4, "%", MIN, DAY // MIN),
        ("hr_error_ecg_noise", 0.0, 0, "bpm", 1000, 7200),
    ):
        if kind == "hr_error_ecg_noise":
            if not noise_seg: continue
            values = [float(x) for x in rng.normal(0, 3.0, n)]
        else:
            values = [base + i % spread for i in range(n)]
        data = json.dumps({"values": values}, sort_keys=True).encode()
        (seg / f"{kind}.json").write_bytes(data)
        entries.append({"segment_id": f"{kind}-1", "dataset": "inline-fixture", "record_id": f"{kind}-1", "kind": kind,
                        "sample_period_ms": period, "n_samples": len(values), "unit": unit, "path": f"{kind}.json",
                        "sha256": hashlib.sha256(data).hexdigest(), "licence": "fixture-only"})
    (seg / "index.json").write_text(json.dumps({"schema_version": "0.1.0", "segments": entries}))
    # --- default.yaml
    dc = root / "configs/benchmark/default.yaml"
    doc = yaml.safe_load(dc.read_text())
    doc["paths"]["segments"] = str(seg)
    for r in doc["parameters"]:
        if r["parameter"] == "n_patients": r["value"] = n_patients
        if r["parameter"] == "n_days": r["value"] = n_days
        if r["parameter"] == "generation_seed": r["value"] = seed
    dc.write_text(yaml.safe_dump(doc, sort_keys=False))
    return dc

if __name__ == "__main__":
    print(mk("smoke", n_patients=4))
