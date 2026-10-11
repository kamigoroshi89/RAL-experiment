"""Build a FIXTURE benchmark and dump the reading-ledger tally of the anchored cuff faults (WS04-T16, item 2 of the fix round).

FIXTURE-ONLY: the fixture prior and registry F0 of tests/benchmark/test_builder.py, rates c1 = c3 = 0 so that only
the C2 faults act. No clinical meaning. Usage (repository root, project venv):

    PYTHONPATH=. .venv/bin/python docs/benchmark/evidence/scripts/anchored_loss_build.py N_PATIENTS C2_RATE OUT.json

OUT.json gets the `settings.anchored_cuff_faults`, `plan_skipped`, `plan_unrealised` blocks of the manifest and the
patient/day counts. `anchored_loss_report.py` turns such files into the table with Wilson intervals.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from tests.benchmark.test_builder import build


def main(argv: list[str]) -> int:
    n_patients, rate, out = int(argv[1]), float(argv[2]), Path(argv[3])
    tmp = Path(tempfile.mkdtemp(prefix="anchored-loss-", dir=Path("outputs") if Path("outputs").is_dir() else None))
    try:
        _, manifest = build(
            tmp, "bench", pairs=0, variants=[], n_patients=n_patients, n_days=7,
            rates=(0.0, rate, 0.0),
        )  # fmt: skip
        s = manifest.settings
        out.write_text(
            json.dumps(
                {
                    "n_patients": n_patients,
                    "c2_rate": rate,
                    "n_patient_days": s["n_patient_days"],
                    "anchored_cuff_faults": s["anchored_cuff_faults"],
                    "plan_skipped": s["plan_skipped"],
                    "plan_unrealised": s["plan_unrealised"],
                    "n_measurement_ticks": len(s["schedule"]["measurement_ticks_ms"]),
                },
                indent=1,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
