"""Command line of the benchmark builder (WS04-T11): ``python -m ralmon.benchmark build | verify | validate``.

``build --config PATH --out DIR [--seed N] [--prior PATH] [--allow-fixture-only] [--git-rev REV] [--n-patients N]
[--n-days N]`` builds a benchmark version; ``verify DIR`` checks every file of the manifest against its sha256 and
that no observed file names latent or truth data; ``validate DIR`` is completed by WS04-T12 and is a placeholder here.

Exit codes. 0: done. 1: ``verify`` found a problem. 2: configuration error (a malformed or incomplete configuration,
an unusable design file or segment library, an output directory that is not empty, a placeholder command). 3: provenance
error (a fixture-only prior or registry without ``--allow-fixture-only``, a prior or design row that is still
``awaiting_human_value``, a value without a source). The revision recorded in the manifest is read from ``git`` here,
never by the library: ``git rev-parse HEAD``, with ``-dirty`` appended when the working tree has changes.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from ralmon.benchmark.builder import (
    BenchmarkConfigError,
    generate_benchmark,
    load_config,
    verify_benchmark,
)
from ralmon.benchmark.injection import InjectionError
from ralmon.benchmark.priors import (
    FixtureOnlyPriorError,
    MissingProvenanceError,
    PriorConfigError,
    UnfilledParameterError,
)
from ralmon.benchmark.segments import SegmentError
from ralmon.benchmark.trace import TraceError

EXIT_OK = 0
EXIT_VERIFY = 1
EXIT_CONFIG = 2
EXIT_PROVENANCE = 3  # algorithmic: the exit code of a provenance error


def git_revision(cwd: Path | None = None) -> str:
    """``git rev-parse HEAD`` of the working tree; ``-dirty`` is appended if the generator may have changed.

    Dirty means: a tracked file has changes, or an untracked file lies under ``src/`` or ``configs/`` (a new module
    or configuration can change the output). Untracked files elsewhere (scratch notes) do not count. ``unknown``
    without git.
    """

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True, cwd=cwd
        ).stdout.strip()

    try:
        rev = git("rev-parse", "HEAD")
        tracked = git("status", "--porcelain", "--untracked-files=no")
        untracked = git(
            "status", "--porcelain", "--untracked-files=all", "--", ":/src", ":/configs"
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{rev}-dirty" if tracked or untracked else rev


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ralmon.benchmark",
        description="Build, verify and validate a semi-synthetic benchmark version (pre-clinical, no real patient).",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="generate a benchmark version")
    build.add_argument(
        "--config",
        type=Path,
        required=True,
        help="configuration file (configs/benchmark/default.yaml)",
    )
    build.add_argument(
        "--out", type=Path, required=True, help="output directory (new or empty)"
    )
    build.add_argument(
        "--seed",
        type=int,
        default=None,
        help="generation seed (overrides generation_seed)",
    )
    build.add_argument(
        "--prior", type=Path, default=None, help="prior file of the single cohort"
    )
    build.add_argument(
        "--allow-fixture-only",
        action="store_true",
        help="accept fixture-only inputs (tests)",
    )
    build.add_argument(
        "--git-rev",
        default=None,
        help="generator revision to record (default: git rev-parse HEAD)",
    )
    build.add_argument(
        "--n-patients",
        type=int,
        default=None,
        help="virtual patients of the single cohort",
    )
    build.add_argument(
        "--n-days",
        type=int,
        default=None,
        help="scored days per patient (the tail day is extra)",
    )
    verify = commands.add_parser(
        "verify", help="check the files of a benchmark against its manifest"
    )
    verify.add_argument("directory", type=Path)
    validate = commands.add_parser("validate", help="validation report (WS04-T12)")
    validate.add_argument("directory", type=Path)
    return parser


def _build(args: argparse.Namespace) -> int:
    config = load_config(args.config).with_overrides(
        n_patients=args.n_patients,
        n_days=args.n_days,
        generation_seed=args.seed,
        prior=args.prior,
    )
    revision = (
        args.git_rev
        if args.git_rev is not None
        else git_revision(Path(__file__).resolve().parent)
    )
    manifest = generate_benchmark(
        config,
        None,
        args.out,
        allow_fixture_only=args.allow_fixture_only,
        git_rev=revision,
    )
    settings = manifest.settings
    twin_counts = settings["twin_event_counts"]
    assert isinstance(twin_counts, dict)
    print(f"built {args.out}")
    print(
        f"  benchmark version {manifest.benchmark_version}, generation seed {manifest.generation_seed}, "
        f"revision {manifest.generator_git_rev}"
    )
    print(
        f"  virtual patients {settings['n_patients']}, scored patient-days {settings['n_patient_days']}, "
        f"tail days {settings['n_patients']} (unscored, ADR-066)"
    )
    print(
        f"  twin patients {settings['n_twin_patients']}, scored twin days {settings['n_twin_patient_days']}, "
        f"tail days {settings['n_twin_patients']} (unscored); the twins are not in the headline counts"
    )
    print(
        f"  files {len(manifest.files)}; ground-truth events on scored days of the virtual patients "
        f"{sum(manifest.event_counts.values())}; events of the twins "
        f"{sum(twin_counts.values())}"  # type: ignore[arg-type]
    )
    print(
        f"  prior {manifest.prior_source_name}: fixture_only {str(manifest.fixture_only).lower()}, "
        f"n_unfilled {manifest.n_unfilled}, n_unverified {manifest.n_unverified}"
    )
    return EXIT_OK


def _verify(args: argparse.Namespace) -> int:
    try:
        count = verify_benchmark(args.directory)
    except (TraceError, OSError) as exc:  # ManifestError is a TraceError
        print(f"verify failed: {exc}", file=sys.stderr)
        return EXIT_VERIFY
    print(
        f"verified {count} files of {args.directory}: hashes match the manifest, no unlisted file, every observed day parses strictly and names no truth"
    )
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            return _build(args)
        if args.command == "verify":
            return _verify(args)
        print("validate: provided by WS04-T12")
        return EXIT_CONFIG
    except (
        FixtureOnlyPriorError,
        UnfilledParameterError,
        MissingProvenanceError,
    ) as exc:
        print(f"provenance error: {exc}", file=sys.stderr)
        return EXIT_PROVENANCE
    except (
        BenchmarkConfigError,
        PriorConfigError,
        InjectionError,
        SegmentError,
        TraceError,
        OSError,
    ) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG


if __name__ == "__main__":
    raise SystemExit(main())
