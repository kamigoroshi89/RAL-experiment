# Evidence of the benchmark design decisions (2026-10-10 and 2026-10-11)

Reports and scripts produced by research and analysis agents for the decisions ADR-068, ADR-070, ADR-071, ADR-072 and ADR-073 of `docs/plan/03-decisions.md`. They are analyses, not results of the paper: every figure comes from the generator, the monitor and the baselines of this repository as they were at the commits named in the decisions, with the empty design rows replaced by labelled sensitivity ranges (a range is not a proposal). Nothing here has been reviewed by a clinician, and the sources quoted in `group1-ble-cuff.md` were opened by the research agent and not by gab (`verified_by` stays null in the registry of values).

The decisions cite these files under `/tmp/research/...`; the copies here are the durable ones:

| File | Decision that rests on it | Original path |
|---|---|---|
| `group1-ble-cuff.md` | Group 1 values (blocks 1 and 2) | `/tmp/research/group1-ble-cuff.md` |
| `group1-observability.md` | ADR-070 (readings per window, realised share, `device_bias` defect) | `/tmp/research/group1-observability.md` |
| `group1-design-options.md` | ADR-070 (anchoring to k readings, bias grid, sample size, `stuck_at` carry-over) | `/tmp/research/group1-design-options.md` |
| `group1-bias-model.md` | ADR-070 (f) (zero-offset row, model on amplitude and k) | `/tmp/research/group1-bias-model.md` |
| `benchmark-size-all-subtypes.md` | benchmark size D (provisional), ADR-071 | `/tmp/research/benchmark-size-all-subtypes.md` |
| `fault-free-diagnostic.md` | ADR-071 (fault-free day, decomposition, sensitivity) | `/tmp/research/fault-free-diagnostic.md` |
| `nonadditivity.md` | ADR-071 (d)(2), ADR-073 | `/tmp/research/nonadditivity.md` |
| `resp/evidence.md` and `resp/*.py` | ADR-072 (RESP reformulations) | `/tmp/research/resp/` |
| `scripts/` | diagnostic experiments (`exp*.py`), `bias-model/`, the single-injection additivity test | `/tmp/research/diag/`, `/tmp/research/obs3/`, `/tmp/research/nonadd/` |

The scripts ran on a copy of the repository (`git archive HEAD`) with `PYTHONPATH` set to that copy and with temporary override files for the prior and design rows; to rerun one, adapt the paths first. They are kept as the record of the method and are not part of the test suite (`tests/` does not import them).

Added 2026-10-11 (ADR-074, pairs):

| File | Decision that rests on it | Original path |
|---|---|---|
| `likelihood-attribution.md` and `scripts/likelihood/` | ADR-074 (likelihood table, recompute of the 2160 pair members, sensitivity); the prototype `likelihood_attr.py` is research code, not the implementation of WS05-T12 | `/tmp/research/likelihood-attribution.md`, `/tmp/research/likelihood/` (46 MB of raw output not copied) |
| `pairs-allocation.md`, `scripts/pairs/`, `pairs/*.patch` | pairs ADR (fourth group `bounce_vs_forged_dispense`, strata, number of pairs); the patches add the fourth group (`g4_confounders.patch`) and an optional informed-attacker copy of `content_change` (`g4_inject_c3_optional.patch`) | `/tmp/research/pairs-allocation.md`, `/tmp/research/pairs/` |
