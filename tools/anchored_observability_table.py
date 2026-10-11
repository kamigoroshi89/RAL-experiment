"""Generate (or check) the observability table of the anchored cuff faults in docs/benchmark/builder.md.

WS04-T16, ADR-070 (a). The table is the exact enumeration of the placement rule of
``ralmon.benchmark.anchoring`` on the default day: the readings come from the care-plan schedule under the registry
of the configuration (each reading is its tick plus ``inflation_ms_nominal`` of the generator design, no jitter),
the numbers of readings k from the duration rows of ``injections.yaml``, the grid from the configuration. No number
is typed here.

Usage (from the repository root, with the virtual environment)::

    python tools/anchored_observability_table.py            # print the table
    python tools/anchored_observability_table.py --write    # rewrite the marked block of the document
    python tools/anchored_observability_table.py --check    # exit 1 if the block of the document is stale

Exit codes: 0 done (or current), 1 the table of the document is stale, 2 a file is missing, unreadable or
the document has no marked block. This script lives in ``tools/`` because ``ralmon.benchmark`` must not import
the specification (``tests/benchmark/test_ground_truth.py::test_import_boundaries``).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "benchmark" / "default.yaml"
DEFAULT_DOC = ROOT / "docs" / "benchmark" / "builder.md"


def default_day(config_path: Path) -> tuple[list[int], int, tuple[int, ...]]:
    """``(reading instants, grid step, the k of the duration rows)`` of a fault-free default day."""
    from ralmon.benchmark.anchoring import ANCHORED_SUBTYPES
    from ralmon.benchmark.builder import BenchmarkConfigError, load_config
    from ralmon.benchmark.injection import load_injection_design
    from ralmon.benchmark.schedule import load_filled_rows, load_schedule
    from ralmon.spec.registry import load_registry

    config = load_config(config_path)
    if config.arrival_jitter_path is not None:
        raise BenchmarkConfigError(
            "the observability table assumes no arrival jitter: this configuration has a jitter model"
        )
    registry = load_registry(config.registry_path, step_ms=config.monitor_step_ms)
    windows = {
        f"{name}_ms": int(registry.get(name).value)
        for name in ("hold_lookback", "delta1", "delta2", "sched_window")
    }
    schedule = load_schedule(config.care_plans_path, **windows)
    inflation = int(
        load_filled_rows(config.generator_design_path, ("inflation_ms_nominal",))[
            "inflation_ms_nominal"
        ]
    )
    design = load_injection_design(config.injections_path, section="c2")
    values: set[int] = set()
    for subtype in ANCHORED_SUBTYPES:
        block = design[subtype].duration
        assert block is not None
        for level in block.levels:
            if level.value is None:
                raise BenchmarkConfigError(f"row {level.name!r} is awaiting a value")
            values.add(int(level.value))
    readings = [t + inflation for t in schedule.measurement_ticks_ms]
    return readings, config.latent_step_ms, tuple(sorted(values))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python tools/anchored_observability_table.py"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="rewrite the marked block")
    mode.add_argument(
        "--check", action="store_true", help="exit 1 if the block is stale"
    )
    args = parser.parse_args(argv)

    from ralmon.benchmark.anchoring import find_block, observability_table, render_block

    try:
        readings, step, ks = default_day(args.config)
    except Exception as exc:  # noqa: BLE001  any loader error (configuration, registry, design) is reported plainly
        print(f"cannot derive the default day: {exc}", file=sys.stderr)
        return 2
    table = observability_table(readings, step_ms=step, ks=ks)
    if not (args.write or args.check):
        print(table)
        return 0
    try:
        document = args.doc.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"cannot read {args.doc}: {exc}", file=sys.stderr)
        return 2
    found = find_block(document)
    if found is None:
        print(f"{args.doc} has no observability-table block", file=sys.stderr)
        return 2
    if args.check:
        if found.group(1).strip("\n") == table.strip("\n"):
            return 0
        print(
            f"the observability table of {args.doc} is stale: "
            "run python tools/anchored_observability_table.py --write",
            file=sys.stderr,
        )
        return 1
    updated = document[: found.start()] + render_block(table) + document[found.end() :]
    args.doc.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
