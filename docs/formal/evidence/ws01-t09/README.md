# WS01-T09 evidence: VitalDB cuff against arterial line

Supplementary estimate of the cuff error for `cuff_error_sd` (WS01-T09; decision of gab of 2026-10-08 recorded with ADR-027). Written by a research agent on 2026-10-08 and kept here so that the numbers in `docs/formal/parameter-literature-proposal.md` can be reproduced; a rerun on 2026-10-08 gave a byte-identical output. Not part of `ralmon`, not linted, not tested.

- `cuff_vs_art.py`: pairs each `Solar8000/NIBP_SBP` reading with the median `Solar8000/ART_SBP` within ±30 s (sensitivity variants inside), on the 30 VitalDB 1.0.0 cases under `data/raw/vitaldb/vital_files` (PhysioNet copy, CC BY 4.0; data never committed). Needs the `vitaldb` package in a throwaway environment (not a project dependency). Run from the repository root, or set `VITALDB_DIR`.
- `cuff_vs_art.out`: output of the run (main result: 38 pairs from 9 cases, mean -10.0 mmHg, SD 17.3 mmHg).
- `posthoc.py`, `posthoc.out`: post-hoc check without the single +77 mmHg pair (SD 9.5 mmHg).

Caveats: intraoperative patients under anaesthesia; an arterial line is not the reference of ISO 81060-2; 30 cases only.
