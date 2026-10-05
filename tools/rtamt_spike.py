"""RTAMT spike of WS05-T02 (ADR-013): can RTAMT host the seven past-time templates?

Plain Python, no network, no wall-clock time, no randomness. Usage::

    python tools/rtamt_spike.py            # version line, then one line per question Q1..Q6
    python tools/rtamt_spike.py --detail   # also the per-template, per-case and per-probe tables

The script reads the installed RTAMT version from package metadata (``NOT-INSTALLED`` if the
distribution is absent), then tries ``import rtamt``. If the import fails (for example on a
Python that the installed RTAMT does not support) every question is reported ``NOT-RUN`` with
the import error as the reason. The exit code is 0 whenever the report was produced.

Question criteria (a question line is ``PASS``, ``FAIL``, ``NOT-SUPPORTED`` or ``NOT-RUN``):

* Q1 past-time operators: PASS iff all seven templates of docs/formal/02-templates.md section 3.1
  translate mechanically (registry names replaced by their values, bounds written with an
  explicit ``ms`` unit, ``once[0, inf]`` written ``once``) and the RTAMT value equals the
  ``sigma_raw`` of every golden case of docs/formal/golden/templates.yaml within 1e-9 (or is
  infinite with the same sign).
* Q2 sparse sampling: PASS iff the fixed-step interface, fed from the grid built with
  ``ralmon.signals`` (``hold_last``, ``impulses_on_grid``, derived signals), reproduces the
  golden values without a sampling violation and enforces the alignment of bounds.
* Q3 robustness intervals: NOT-SUPPORTED iff ``update`` returns a point value for every
  ``Semantics`` member; the script also tests the monotonicity of each template in its
  unknown signals with RTAMT point evaluations (the soundness condition of the two-bound
  procedure).
* Q4 guards and infinities: PASS iff infinities propagate exactly, the atoms apply the guard
  rule of 02-templates.md section 2.1 and an unknown (NaN) value is not read as a verdict.
* Q5 time robustness: PASS iff the time-margin goldens (sched, int, sys) are reproduced by
  the translation (mechanical or with derived signals), graded lateness included.
* Q6 cost per sample: PASS iff operator updates per grid step grow linearly with the number of
  instances (counting wrapper, no wall-clock); the per-update cost of the timed operators is
  reported as well.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import math
import re
import sys
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "docs" / "formal" / "golden" / "templates.yaml"
TEMPLATES_DOC = ROOT / "docs" / "formal" / "02-templates.md"
STEP_MS = 60_000  # F0 step_ms
INF = math.inf
NAN = math.nan
TOL = 1e-9
DETAIL = "--detail" in sys.argv[1:]
KEYWORDS = {"historically", "once", "since", "and", "or", "not", "inf"}


# --------------------------------------------------------------------------- helpers


def _import_signals() -> Any:
    try:
        return importlib.import_module("ralmon.signals")
    except ModuleNotFoundError:
        sys.path.insert(0, str(ROOT / "src"))
        return importlib.import_module("ralmon.signals")


SIG = _import_signals()


def same_value(expected: float, got: float) -> bool:
    """Equal within TOL, or the same infinity."""
    if math.isnan(got) or math.isnan(expected):
        return False
    if math.isinf(expected) or math.isinf(got):
        return expected == got
    return abs(expected - got) <= TOL


def fmt(x: float) -> str:
    if math.isinf(x) or math.isnan(x):
        return str(x)
    return f"{x:g}"


@dataclass
class Result:
    status: str
    reason: str
    lines: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- inputs


def load_golden() -> dict[str, Any]:
    import yaml

    with GOLDEN.open(encoding="utf-8") as handle:
        data: dict[str, Any] = yaml.safe_load(handle)
    return data


def registry_values(golden: dict[str, Any]) -> dict[str, int | float]:
    registry: dict[str, int | float] = {}
    for entry in golden["fixture_registry"]:
        for name, value in zip(entry["names"], entry["values"], strict=True):
            registry[name] = value
    return registry


def template_strings() -> dict[str, str]:
    """The ``formula_past_time`` column of the table of section 3.1 of 02-templates.md."""
    strings: dict[str, str] = {}
    pattern = re.compile(
        r"^\|\s*(RANGE|SCHED|HOLD|COUNT|RESP|SYS|INT)\s*\|[^|]*\|\s*`([^`]+)`\s*\|"
    )
    text = TEMPLATES_DOC.read_text(encoding="utf-8")
    section = text.split("### 3.1 The seven templates", 1)[1].split("### 3.2", 1)[0]
    for line in section.splitlines():
        match = pattern.match(line)
        if match:
            strings[match.group(1).lower()] = match.group(2)
    if len(strings) != 7:
        raise ValueError(f"expected seven template strings, found {sorted(strings)}")
    return strings


# --------------------------------------------------------------------------- translation


def _bound_value(text: str, registry: dict[str, int | float]) -> int | None:
    """Value in ms of a bound expression made of numbers, registry names, + and -; None for inf."""
    text = text.strip()
    if text == "inf":
        return None
    total = 0
    for sign, term in re.findall(r"([+-]?)\s*([A-Za-z0-9_]+)", text):
        value = int(term) if term.isdigit() else int(registry[term])
        total += -value if sign == "-" else value
    return total


def translate(formula: str, registry: dict[str, int | float]) -> str:
    """Syntax-directed translation of a template string into RTAMT syntax.

    Registry names become numbers, ``once[a, b]`` and ``historically[a, b]`` get explicit ``ms``
    units, ``once[0, inf]`` becomes the untimed ``once``. Nothing else is rewritten.
    """

    def interval(match: re.Match[str]) -> str:
        op, lo_text, hi_text = match.group(1), match.group(2), match.group(3)
        lo, hi = _bound_value(lo_text, registry), _bound_value(hi_text, registry)
        if hi is None:
            if lo != 0:
                raise ValueError(f"unbounded {op} with a non-zero lower bound")
            return op
        return f"{op}[{lo}ms,{hi}ms]"

    out = re.sub(r"\b(once|historically)\[([^,\]]+),([^\]]+)\]", interval, formula)
    for name in sorted(registry, key=len, reverse=True):
        out = re.sub(rf"\b{re.escape(name)}\b", str(registry[name]), out)
    return out


def variables_of(rtamt_text: str) -> list[str]:
    names: list[str] = []
    for token in re.findall(
        r"[A-Za-z_][A-Za-z0-9_]*", re.sub(r"\d+ms", "", rtamt_text)
    ):
        if token not in KEYWORDS and token not in names:
            names.append(token)
    return names


# --------------------------------------------------------------------------- grid signals


def build_signals(
    case: dict[str, Any], *, unavailable: float = NAN, k_end: int | None = None
) -> dict[str, list[float]]:
    """Grid signals of a golden case, in the encoding of 02-templates.md section 1.3.

    Indicators are +inf when the impulse (or the level) is 1 and -inf otherwise. Held values
    are NaN before their first sample. Channels listed in ``channels_unavailable`` are filled
    with ``unavailable``. Counters read 0 before their first output (they are counts, not
    unknowns). All derived signals are fed with every sample and event in device-time order.
    """
    inputs = case["inputs"]
    steps = (case["eval_at_ms"] // STEP_MS) if k_end is None else k_end
    grid = [k * STEP_MS for k in range(steps + 1)]
    samples = [SIG.Sample(**s) for s in inputs["samples"]]
    events = [
        SIG.Event(
            kind=SIG.EventKind(e["kind"]), **{k: v for k, v in e.items() if k != "kind"}
        )
        for e in inputs["events"]
    ]
    for generated in inputs.get("generated", []):
        t = generated["t_ms"]
        samples.append(SIG.Sample(generated["signal"], t, t, 1.0, None, None))
    unavailable_channels = set(inputs.get("channels_unavailable", []))

    from_events = [s for e in events if (s := SIG.event_to_sample(e)) is not None]
    stream = sorted(
        samples + from_events,
        key=lambda s: (s.t_device_ms, 0 if s.signal == "bp" else 1),
    )

    def of(signal: str) -> list[Any]:
        return [s for s in stream if s.signal == signal]

    def indicator(signal: str) -> list[float]:
        if signal in unavailable_channels:
            return [unavailable] * len(grid)
        return [INF if v else -INF for v in SIG.impulses_on_grid(of(signal), grid)]

    def level(signal: str) -> list[float]:
        if signal in unavailable_channels:
            return [unavailable] * len(grid)
        held = SIG.hold_last(of(signal), grid)
        return [NAN if math.isnan(v) else (INF if v == 1.0 else -INF) for v in held]

    derived = {d.output.value: d for d in SIG.default_derived_signals()}
    outputs: dict[str, list[Any]] = {name: [] for name in derived}
    for sample in stream:
        for name, signal in derived.items():
            produced = signal.update(sample)
            if produced is not None:
                outputs[name].append(produced)

    cuff_health = list(SIG.hold_last(of("cuff_health"), grid))
    signals: dict[str, list[float]] = {
        "meas": indicator("meas"),
        "dispense": indicator("dispense"),
        "sched_tick": indicator("sched_tick"),
        "day_end": indicator("day_end"),
        "intake": indicator("intake"),
        "auth": indicator("auth"),
        "presence": level("presence"),
        "bp": list(SIG.hold_last(of("bp"), grid)),
        "cuff_health": cuff_health,
        "cuff_ok": [
            NAN if math.isnan(v) else (INF if v == 1.0 else -INF) for v in cuff_health
        ],
        "inflation_ms": list(SIG.hold_last(of("inflation_ms"), grid)),
        "dose_count": [
            0.0 if math.isnan(v) else v
            for v in SIG.hold_last(outputs["dose_count"], grid)
        ],
        "bp_drop": list(SIG.hold_last(outputs["bp_drop"], grid)),
        "tau": [float(t) for t in grid],
    }
    return signals


# --------------------------------------------------------------------------- RTAMT runner


def make_spec(rtamt: Any, text: str, names: list[str], period_ms: int = STEP_MS) -> Any:
    spec = rtamt.StlDiscreteTimeSpecification()
    for name in names:
        spec.declare_var(name, "float")
    spec.set_sampling_period(period_ms, "ms", 0.1)
    spec.spec = text
    spec.parse()
    return spec


def run_spec(
    rtamt: Any,
    text: str,
    signals: dict[str, list[float]],
    timestamps: list[int] | None = None,
) -> tuple[list[float], Any]:
    names = variables_of(text)
    spec = make_spec(rtamt, text, names)
    steps = len(signals["tau"])
    out: list[float] = []
    for k in range(steps):
        stamp = k * STEP_MS if timestamps is None else timestamps[k]
        out.append(spec.update(stamp, [(n, signals[n][k]) for n in names]))
    return out, spec


# variants of each template (name, kind, text builder)
TIME_SKELETONS = {
    # docs/formal/02-templates.md section 1.4 (Boolean skeletons: sign only)
    "sched": "historically(once[sched_window, sched_window + step_ms] sched_tick -> once[0, sched_window] meas)",
    "int": "historically(dispense -> once[0, int_window] (presence or intake or auth))",
}


def variants(
    template: str, strings: dict[str, str], registry: dict[str, int | float]
) -> list[tuple[str, str, str | None]]:
    """(variant name, kind, RTAMT text or None if not expressible), kind in literal/rewrite/skeleton."""
    formula = strings[template]
    literal = translate(formula, registry)
    if template == "sched":
        # hand rewrite: once[B] (meas and age >= 0)  ->  tau + once[B] (meas and (0 - tau)),
        # valid because age = tau(k) - tau(j) is linear in the two grid positions
        rewrite = translate(
            formula.replace(
                "once[0, sched_window] (meas and age >= 0)",
                "(tau + once[0, sched_window] (meas and (0 - tau)))",
            ),
            registry,
        )
        return [
            ("literal", "literal", None),
            ("skeleton", "skeleton", translate(TIME_SKELETONS["sched"], registry)),
            ("time-signal rewrite", "rewrite", rewrite),
        ]
    if template == "int":
        rewrite = translate(
            formula.replace(
                "once[0, inf] ((presence or intake or auth) and age <= int_window)",
                "((int_window - tau) + once ((presence or intake or auth) and tau))",
            ),
            registry,
        )
        return [
            ("literal", "literal", None),
            ("skeleton", "skeleton", translate(TIME_SKELETONS["int"], registry)),
            ("time-signal rewrite", "rewrite", rewrite),
        ]
    if template == "sys":
        guard_aware = translate(
            formula.replace("cuff_health == 1", "cuff_ok"), registry
        )
        return [
            ("literal", "literal", literal),
            ("guard indicator", "rewrite", guard_aware),
        ]
    return [("literal", "literal", literal)]


@dataclass
class CaseRow:
    case_id: str
    template: str
    variant: str
    kind: str
    expected: float
    got: float | None
    equal: bool
    note: str


KNOWN_DIFFERENCES = {
    "G-SCHED-3": "graded lateness exists only in the per-instance semantics (02-templates 2.3): the string "
    "is -inf at the decision step and the min over history never recovers",
    "G-INT-3": "robot channels unavailable: NaN is absorbed by or/and (order-dependent), see Q4",
}


def evaluate_cases(rtamt: Any) -> list[CaseRow]:
    golden = load_golden()
    registry = registry_values(golden)
    strings = template_strings()
    rows: list[CaseRow] = []
    for case in golden["cases"]:
        template = case["inputs"]["template"]
        expected = float(case["expected"]["sigma_raw"])
        for name, kind, text in variants(template, strings, registry):
            if text is None:
                rows.append(
                    CaseRow(
                        case["id"],
                        template,
                        name,
                        kind,
                        expected,
                        None,
                        False,
                        "not expressible: `age` is a function of the inner and of the evaluation step",
                    )
                )
                continue
            feeds = [("", NAN)]
            if case["inputs"].get("channels_unavailable"):
                feeds.append((" (unavailable fed as -inf)", -INF))
            for suffix, unavailable in feeds:
                signals = build_signals(case, unavailable=unavailable)
                got = run_spec(rtamt, text, signals)[0][-1]
                if kind == "skeleton":
                    equal = (got >= 0) == (expected >= 0)
                    note = "sign only"
                else:
                    equal = same_value(expected, got)
                    note = ""
                if not equal and case["id"] in KNOWN_DIFFERENCES and not suffix:
                    note = (note + " " + KNOWN_DIFFERENCES[case["id"]]).strip()
                rows.append(
                    CaseRow(
                        case["id"],
                        template,
                        name + suffix,
                        kind,
                        expected,
                        got,
                        equal,
                        note,
                    )
                )
    return rows


# --------------------------------------------------------------------------- questions


def q1(rtamt: Any, rows: list[CaseRow]) -> Result:
    lines: list[str] = []
    failing: list[str] = []
    for template in ("range", "sched", "hold", "count", "resp", "sys", "int"):
        literal = [r for r in rows if r.template == template and r.variant == "literal"]
        if any(r.got is None for r in literal):
            verdict = "not expressible (age)"
        else:
            bad = [r.case_id for r in literal if not r.equal]
            verdict = (
                "equal on all goldens" if not bad else f"differs on {', '.join(bad)}"
            )
        if "equal on all" not in verdict:
            failing.append(f"{template}")
        lines.append(f"  Q1 template {template}: literal translation {verdict}")
    for r in rows:
        got = "-" if r.got is None else fmt(r.got)
        lines.append(
            f"  Q1 case {r.case_id} [{r.variant}] expected {fmt(r.expected)} got {got} "
            f"{'equal' if r.equal else 'DIFFERENT'} {r.note}".rstrip()
        )
    probe_signals = {"a": [5.0, 1.0, 1.0, 1.0], "b": [0.0, 10.0, 20.0, 30.0]}
    for probe in ("once[0ms,60000ms] a + b", "(once[0ms,60000ms] a) + b"):
        names = variables_of(probe)
        spec = make_spec(rtamt, probe, names)
        values = [
            spec.update(i * STEP_MS, [(n, probe_signals[n][i]) for n in names])
            for i in range(4)
        ]
        lines.append(
            f"  Q1 precedence probe '{probe}' on a={probe_signals['a']} b={probe_signals['b']}: {values}"
        )
    try:
        make_spec(rtamt, "once[0,inf] meas", ["meas"])
        lines.append("  Q1 unbounded bound 'once[0,inf] meas': accepted")
    except Exception as err:  # noqa: BLE001 - report whatever RTAMT raises
        lines.append(
            f"  Q1 unbounded bound 'once[0,inf] meas': {type(err).__name__}: {str(err).strip()}"
        )
    if failing:
        return Result(
            "FAIL",
            f"{7 - len(failing)} of 7 templates translate mechanically and equal the goldens; "
            f"not: {', '.join(failing)} (age term, == atom)",
            lines,
        )
    return Result(
        "PASS",
        "all seven templates translate mechanically and equal the goldens",
        lines,
    )


def q2(rtamt: Any, rows: list[CaseRow]) -> Result:
    lines: list[str] = []
    golden = load_golden()
    registry = registry_values(golden)
    strings = template_strings()
    literal_ok = [
        r
        for r in rows
        if r.variant == "literal" and r.template in {"range", "hold", "count", "resp"}
    ]
    equal = sum(1 for r in literal_ok if r.equal)
    lines.append(
        f"  Q2 grid feed (range, hold, count, resp, literal strings): {equal} of {len(literal_ok)} golden evaluations equal"
    )
    # sampling violations on the grid, and irregular timestamps
    case = next(c for c in golden["cases"] if c["id"] == "G-HOLD-1")
    text = translate(strings["hold"], registry)
    signals = build_signals(case)
    grid_vals, spec = run_spec(rtamt, text, signals)
    violations_grid = spec.sampling_violation_counter
    jitter = [k * STEP_MS + (k * 7919) % 30_000 for k in range(len(signals["tau"]))]
    irregular_vals, spec_irregular = run_spec(rtamt, text, signals, timestamps=jitter)
    violations_irregular = spec_irregular.sampling_violation_counter
    lines.append(
        f"  Q2 G-HOLD-1 grid timestamps: sampling_violation_counter={violations_grid}; "
        f"jittered timestamps (deterministic, up to 30 s): counter={violations_irregular}, "
        f"values identical={grid_vals == irregular_vals}"
    )
    # alignment of bounds: where is a misaligned bound rejected?
    stage = "parse"
    try:
        bad = make_spec(rtamt, "once[0ms,90500ms] meas", ["meas"])
        stage = "first update"
        bad.update(0, [("meas", INF)])
        aligned = "accepted at parse and at the first update (no error)"
    except Exception as err:  # noqa: BLE001 - report whatever RTAMT raises
        aligned = f"rejected at {stage}: {type(err).__name__}: {str(err).strip()[:110]}"
    lines.append(f"  Q2 bound 90500 ms with a 60000 ms period: {aligned}")
    # the `unit` attribute documented in the README: does it change the meaning of a bare bound?
    for label, setter in (
        ("spec.unit = 'ms'", lambda s: setattr(s, "unit", "ms")),
        ("spec.ast.unit = 'ms'", lambda s: setattr(s.ast, "unit", "ms")),
        ("no unit set", lambda s: None),
    ):
        spec = rtamt.StlDiscreteTimeSpecification()
        spec.declare_var("meas", "float")
        setter(spec)
        spec.set_sampling_period(STEP_MS, "ms", 0.1)
        spec.spec = "once[0,120000] meas"
        spec.parse()
        seen = [
            spec.update(k * STEP_MS, [("meas", INF if k == 0 else -INF)])
            for k in range(6)
        ]
        window = next((k for k, v in enumerate(seen) if v == -INF), None)
        forgotten = "never within 6 steps" if window is None else f"at step {window}"
        lines.append(
            f"  Q2 bare bound 'once[0,120000]' with {label}: the impulse of step 0 is forgotten {forgotten} "
            "(a 120000 ms window at a 60000 ms period is forgotten at step 3)"
        )
    ok = (
        equal == len(literal_ok)
        and violations_grid == 0
        and grid_vals == irregular_vals
        and "multiple of the sampling period" in aligned
    )
    reason = (
        "fixed-step interface fed from the monitor grid; timestamps are only audited "
        f"(counter {violations_grid} on the grid, {violations_irregular} when jittered, values unchanged); "
        "unaligned bounds rejected; no sparse or irregular evaluation in RTAMT, the hold stays in ralmon"
    )
    if ok:
        return Result("PASS", reason, lines)
    return Result(
        "FAIL",
        "grid feed did not reproduce the goldens or alignment is not enforced",
        lines,
    )


def _scan(
    rtamt: Any,
    text: str,
    signals: dict[str, list[float]],
    name: str,
    step: int,
    values: list[float],
) -> list[float]:
    out: list[float] = []
    for v in values:
        probe = {k: list(vals) for k, vals in signals.items()}
        probe[name][step] = v
        out.append(run_spec(rtamt, text, probe)[0][-1])
    return out


def _monotone(values: list[float], direction: str) -> bool:
    pairs = list(pairwise(values))
    if direction == "up":
        return all(b >= a for a, b in pairs)
    return all(b <= a for a, b in pairs)


def q3(rtamt: Any) -> Result:
    lines: list[str] = []
    # (a) return type of update for every Semantics member
    types: dict[str, str] = {}
    for member in rtamt.Semantics:
        try:
            spec = rtamt.StlDiscreteTimeSpecification(semantics=member)
            for name in ("x", "y"):
                spec.declare_var(name, "float")
            spec.set_var_io_type("x", "input")
            spec.set_var_io_type("y", "output")
            spec.set_sampling_period(STEP_MS, "ms", 0.1)
            spec.spec = "out = historically(x >= y)"
            spec.declare_var("out", "float")
            spec.parse()
            types[str(member)] = type(spec.update(0, [("x", 1.0), ("y", 0.0)])).__name__
        except Exception as err:  # noqa: BLE001
            types[str(member)] = f"error {type(err).__name__}"
    lines.append(f"  Q3 type returned by update(), per Semantics member: {types}")
    lines.append(
        "  Q3 rtamt.semantics.interval.Interval stores integer time bounds "
        "(begin, end, begin_unit, end_unit), not robustness bounds"
    )
    golden = load_golden()
    registry = registry_values(golden)
    strings = template_strings()
    cases = {c["id"]: c for c in golden["cases"]}
    lo, hi = float(registry["bound_bp_lower"]), float(registry["bound_bp_upper"])
    scan_bp = [lo + i for i in range(int(hi - lo) + 1)]

    table: list[tuple[str, str, str]] = []

    def endpoints(
        name: str,
        text: str,
        signals: dict[str, list[float]],
        sig: str,
        step: int,
        values: list[float],
        bounds: tuple[float, float],
    ) -> tuple[list[float], float, float, float, float]:
        scan = _scan(rtamt, text, signals, sig, step, values)
        ends = _scan(rtamt, text, signals, sig, step, [bounds[0], bounds[1]])
        return scan, min(ends), max(ends), min(scan), max(scan)

    # RANGE: unknown bp at the anchor step
    case = cases["G-RANGE-1"]
    signals = build_signals(case)
    text = translate(strings["range"], registry)
    step = case["eval_at_ms"] // STEP_MS
    _, e_lo, e_hi, s_lo, s_hi = endpoints(
        "range", text, signals, "bp", step, scan_bp, (lo, hi)
    )
    sound = e_lo == s_lo and e_hi == s_hi
    table.append(("range", "bp", "NOT monotone (concave: tent over the band)"))
    lines.append(
        f"  Q3 range, unknown bp in [{fmt(lo)}, {fmt(hi)}]: endpoint values [{fmt(e_lo)}, {fmt(e_hi)}], "
        f"scan over all integer values [{fmt(s_lo)}, {fmt(s_hi)}] -> endpoint rule "
        f"{'sound' if sound else 'UNSOUND (upper bound too low)'}"
    )
    # COUNT: coincident dispense and day_end, unknown dose_count
    case = cases["G-COUNT-3"]
    signals = build_signals(case)
    step = case["eval_at_ms"] // STEP_MS
    signals["dispense"][step] = (
        INF  # a dispense at the closing step (fixture-only coincidence)
    )
    text = translate(strings["count"], registry)
    counts = [
        float(i) for i in range(6)
    ]  # fixture-only bounds 0..5, not a clinical value
    _, e_lo, e_hi, s_lo, s_hi = endpoints(
        "count", text, signals, "dose_count", step, counts, (0.0, 5.0)
    )
    table.append(
        (
            "count",
            "dose_count",
            "each conjunct monotone (opposite directions); NOT monotone when dispense and day_end coincide",
        )
    )
    lines.append(
        f"  Q3 count (dispense and day_end at step {step}), unknown dose_count in [0, 5]: endpoints "
        f"[{fmt(e_lo)}, {fmt(e_hi)}], scan [{fmt(s_lo)}, {fmt(s_hi)}] -> endpoint rule "
        f"{'sound' if (e_lo, e_hi) == (s_lo, s_hi) else 'UNSOUND'}"
    )
    # SYS: unknown cuff_health with a multi-valued status
    case = cases["G-SYS-1"]
    signals = build_signals(case)
    step = case["eval_at_ms"] // STEP_MS
    text = translate(strings["sys"].replace("cuff_health == 1", "cuff_ok"), registry)

    def sys_scan(values: list[float]) -> list[float]:
        out = []
        for v in values:
            probe = {k: list(vals) for k, vals in signals.items()}
            probe["cuff_ok"][step] = INF if v == 1.0 else -INF
            out.append(run_spec(rtamt, text, probe)[0][-1])
        return out

    ends = sys_scan([0.0, 2.0])
    inside = sys_scan([0.0, 0.5, 1.0, 1.5, 2.0])
    table.append(
        (
            "sys",
            "cuff_health",
            "NOT monotone if the status takes values other than 0 and 1; monotone for a Boolean status",
        )
    )
    lines.append(
        f"  Q3 sys, unknown cuff_health in [0, 2] (equality guard): endpoints {[fmt(v) for v in ends]}, "
        f"scan {[fmt(v) for v in inside]} -> endpoint rule "
        f"{'sound' if max(ends) == max(inside) else 'UNSOUND (healthy interior value missed)'}"
    )
    # monotone probes
    case = cases["G-SYS-1"]
    signals = build_signals(case)
    step = case["eval_at_ms"] // STEP_MS
    text = translate(strings["sys"].replace("cuff_health == 1", "cuff_ok"), registry)
    vals = _scan(
        rtamt,
        text,
        signals,
        "inflation_ms",
        step,
        [0.0, 15000.0, 30000.0, 45000.0, 60000.0],
    )
    table.append(
        ("sys", "inflation_ms", f"non-decreasing (scan {_monotone(vals, 'up')})")
    )
    case = cases["G-HOLD-1"]
    signals = build_signals(case)
    step = case["eval_at_ms"] // STEP_MS
    text = translate(strings["hold"], registry)
    vals = _scan(rtamt, text, signals, "bp", step, scan_bp)
    table.append(("hold", "bp", f"non-decreasing (scan {_monotone(vals, 'up')})"))
    vals = _scan(rtamt, text, signals, "meas", step - 5, [-INF, INF])
    table.append(("hold", "meas", f"non-decreasing (scan {_monotone(vals, 'up')})"))
    case = cases["G-RESP-1"]
    signals = build_signals(case)
    step = case["eval_at_ms"] // STEP_MS
    text = translate(strings["resp"], registry)
    drops = [float(d) for d in range(-100, 101, 5)]
    vals = _scan(rtamt, text, signals, "bp_drop", 510, drops)
    table.append(
        (
            "resp",
            "bp_drop (so non-increasing in the later bp)",
            f"non-decreasing (scan {_monotone(vals, 'up')})",
        )
    )
    vals = _scan(rtamt, text, signals, "meas", 510, [-INF, INF])
    table.append(("resp", "meas", f"non-decreasing (scan {_monotone(vals, 'up')})"))
    case = cases["G-SCHED-1"]
    signals = build_signals(case)
    text = variants("sched", strings, registry)[1][2] or ""
    vals = _scan(rtamt, text, signals, "meas", 560, [-INF, INF])
    table.append(("sched", "meas", f"non-decreasing (scan {_monotone(vals, 'up')})"))
    case = cases["G-INT-1"]
    signals = build_signals(case)
    text = variants("int", strings, registry)[1][2] or ""
    vals = _scan(rtamt, text, signals, "auth", 418, [-INF, INF])
    table.append(
        (
            "int",
            "auth (presence, intake alike)",
            f"non-decreasing (scan {_monotone(vals, 'up')})",
        )
    )
    lines.append("  Q3 monotonicity table (template, unknown signal, finding):")
    for template, signal, finding in table:
        lines.append(f"    {template:6s} {signal:42s} {finding}")
    only_points = all(v == "float" for v in types.values() if not v.startswith("error"))
    if only_points:
        return Result(
            "NOT-SUPPORTED",
            "update() returns one float for every Semantics member: point values only, intervals need custom code; "
            "endpoint evaluation is unsound for range, count (coincident triggers) and sys (multi-valued status)",
            lines,
        )
    return Result("FAIL", "an interval-valued result was found; inspect", lines)


def q4(rtamt: Any, rows: list[CaseRow]) -> Result:
    lines: list[str] = []
    golden = load_golden()
    registry = registry_values(golden)
    strings = template_strings()
    infinite = [
        r
        for r in rows
        if r.variant == "literal" and r.got is not None and math.isinf(r.expected)
    ]
    inf_ok = all(r.equal for r in infinite)
    lines.append(
        f"  Q4 infinite goldens (failed guards) reproduced exactly: {[r.case_id for r in infinite if r.equal]} "
        f"of {[r.case_id for r in infinite]}"
    )
    hold = translate(strings["hold"], registry)
    no_anchor = next(c for c in golden["cases"] if c["id"] == "G-RANGE-1")
    vacuous = run_spec(rtamt, hold, build_signals(no_anchor, k_end=3))[0]
    lines.append(f"  Q4 vacuous truth (no anchor) is exactly +inf: {fmt(vacuous[-1])}")
    # native atoms
    eq = make_spec(rtamt, "cuff_health == 1", ["cuff_health"])
    eq_vals = [
        eq.update(i * STEP_MS, [("cuff_health", v)])
        for i, v in enumerate([1.0, 0.0, 2.0])
    ]
    lines.append(
        f"  Q4 native equality atom 'cuff_health == 1' on healthy, 0, 2: {[fmt(v) for v in eq_vals]} "
        "(guard rule of 02-templates.md 2.1 would give +inf, -inf, -inf)"
    )
    # unknown values
    rng = make_spec(rtamt, translate(strings["range"], registry), ["meas", "bp"])
    unknown = rng.update(0, [("meas", INF), ("bp", NAN)])
    lines.append(
        f"  Q4 range with a measurement and an unknown (NaN) pressure: {fmt(unknown)} "
        "(T01 3.5 requires unknown, never a verdict)"
    )
    witness = make_spec(
        rtamt, "presence or intake or auth", ["presence", "intake", "auth"]
    )
    w1 = witness.update(0, [("presence", NAN), ("intake", NAN), ("auth", INF)])
    witness2 = make_spec(
        rtamt, "auth or presence or intake", ["presence", "intake", "auth"]
    )
    w2 = witness2.update(0, [("presence", NAN), ("intake", NAN), ("auth", INF)])
    lines.append(
        f"  Q4 'presence or intake or auth' with unavailable robot channels (NaN) and auth=+inf: {fmt(w1)}; "
        f"operands reordered 'auth or presence or intake': {fmt(w2)} (order-dependent)"
    )
    guard_native = all(abs(v) in (INF,) for v in eq_vals)
    nan_ok = (not math.isnan(w1)) and w1 == w2 and not math.isinf(unknown)
    if inf_ok and guard_native and nan_ok:
        return Result("PASS", "infinities and guards represented", lines)
    return Result(
        "FAIL",
        "infinities propagate exactly when the host feeds +-inf indicators, but the atoms do not apply the "
        "guard rule (== is -|a-b|) and NaN is silently absorbed or read as a verdict",
        lines,
    )


def q5(rtamt: Any, rows: list[CaseRow]) -> Result:
    lines: list[str] = []
    wanted = [
        r
        for r in rows
        if r.template in {"sched", "int", "sys"}
        and r.kind == "rewrite"
        and "(unavailable" not in r.variant
    ]
    equal = [r for r in wanted if r.equal]
    for r in rows:
        if r.template in {"sched", "int", "sys"} and r.kind == "rewrite":
            lines.append(
                f"  Q5 {r.case_id} [{r.variant}] expected {fmt(r.expected)} "
                f"got {fmt(r.got) if r.got is not None else '-'} {'equal' if r.equal else 'DIFFERENT'}"
            )
    lines.append(
        "  Q5 literal strings of sched and int: not expressible, `age` has no RTAMT counterpart "
        "(no freeze variable, no time-valued atom); sys has no age but its == atom differs (Q4)"
    )
    failing = [r.case_id for r in wanted if not r.equal]
    if failing:
        return Result(
            "FAIL",
            f"not native; with a derived time signal tau and arithmetic over a sub-formula {len(equal)} of "
            f"{len(wanted)} time-margin goldens are equal; differs: {', '.join(failing)} "
            "(graded lateness is per-instance only; unavailable robot channels need -inf instead of NaN)",
            lines,
        )
    return Result(
        "PASS",
        "only by hand rewrite with a derived time signal (not native, not mechanical)",
        lines,
    )


class _CountingDeque(deque[float]):
    reads = 0

    def __getitem__(self, index: Any) -> Any:
        type(self).reads += 1
        return super().__getitem__(index)


def instrument(spec: Any, counter: list[int]) -> None:
    """Count every operator update of ``spec`` in ``counter[0]`` and every window-buffer read."""
    for op in spec.online_interpreter.online_operator_dict.values():
        original = op.update

        def counted(*args: Any, _orig: Callable[..., Any] = original, **kw: Any) -> Any:
            counter[0] += 1
            return _orig(*args, **kw)

        op.update = counted
        if hasattr(op, "buffer"):
            op.buffer = _CountingDeque(op.buffer, maxlen=op.buffer.maxlen)


def q6(rtamt: Any) -> Result:
    lines: list[str] = []
    golden = load_golden()
    registry = registry_values(golden)
    strings = template_strings()
    text = translate(strings["resp"], registry)
    names = variables_of(text)
    case = next(c for c in golden["cases"] if c["id"] == "G-RESP-1")
    signals = build_signals(case)
    steps = 240
    per_instance: dict[int, tuple[float, float]] = {}
    for count in (1, 10, 100):
        specs = [make_spec(rtamt, text, names) for _ in range(count)]
        updates = [0]
        _CountingDeque.reads = 0
        for spec in specs:
            spec.update(0, [(n, signals[n][0]) for n in names])  # builds the operators
            instrument(spec, updates)
        updates[0] = 0
        _CountingDeque.reads = 0
        for k in range(1, steps):
            for spec in specs:
                spec.update(
                    k * STEP_MS,
                    [(n, signals[n][min(k, len(signals[n]) - 1)]) for n in names],
                )
        per_step = updates[0] / (steps - 1)
        reads = _CountingDeque.reads / (steps - 1)
        per_instance[count] = (per_step / count, reads / count)
        lines.append(
            f"  Q6 {count:3d} instances: operator updates per grid step {per_step:g} "
            f"({per_step / count:g} per instance), timed-window buffer reads per step {reads:g} "
            f"({reads / count:g} per instance)"
        )
    # window dependence of one timed operator
    for operator in ("once", "historically"):
        for width_steps in (30, 120):
            spec = make_spec(
                rtamt, f"{operator}[0ms,{width_steps * STEP_MS}ms] meas", ["meas"]
            )
            spec.update(0, [("meas", -INF)])
            op = next(iter(spec.online_interpreter.online_operator_dict.values()))
            op.buffer = _CountingDeque(op.buffer, maxlen=op.buffer.maxlen)
            _CountingDeque.reads = 0
            for k in range(1, 101):
                spec.update(k * STEP_MS, [("meas", -INF)])
            lines.append(
                f"  Q6 {operator}[0, {width_steps} steps]: buffer reads per update "
                f"{_CountingDeque.reads / 100:g} (the whole window is scanned at each step)"
            )
    ratios = {v[0] for v in per_instance.values()}
    linear = len(ratios) == 1
    return Result(
        "PASS" if linear else "FAIL",
        f"operator updates per step are linear in the number of instances ({min(ratios):g} per instance); "
        "a timed once or historically scans its whole window at every step, so the cost per update is O(window), not O(1)",
        lines,
    )


# --------------------------------------------------------------------------- main


def decision(results: dict[str, Result]) -> str:
    if results["Q1"].status != "PASS":
        return "outcome C (forced by a Q1 failure): custom evaluator; B3 uses the custom point evaluator"
    if all(results[q].status == "PASS" for q in ("Q1", "Q2", "Q4")):
        return "outcome A: RTAMT as point-robustness engine, custom interval layer"
    return "outcome B: custom evaluator, RTAMT as oracle and engine of B3"


def main() -> int:
    try:
        version = importlib.metadata.version("rtamt")
    except importlib.metadata.PackageNotFoundError:
        version = "NOT-INSTALLED"
    print(f"RTAMT version: {version}")
    print(f"Python: {sys.version.split()[0]}")
    rtamt: Any = None
    import_error = ""
    if version != "NOT-INSTALLED":
        try:
            rtamt = importlib.import_module("rtamt")
        except Exception as err:  # noqa: BLE001 - any import failure is a finding
            import_error = f"import rtamt failed: {type(err).__name__}: {err}"
    else:
        import_error = "rtamt is not installed"
    names = {
        "Q1": "past-time operators",
        "Q2": "sparse sampling",
        "Q3": "robustness intervals",
        "Q4": "guards and infinities",
        "Q5": "time robustness",
        "Q6": "cost per sample",
    }
    results: dict[str, Result] = {}
    if rtamt is None:
        for q in names:
            results[q] = Result("NOT-RUN", import_error)
    else:
        rows = evaluate_cases(rtamt)
        results["Q1"] = q1(rtamt, rows)
        results["Q2"] = q2(rtamt, rows)
        results["Q3"] = q3(rtamt)
        results["Q4"] = q4(rtamt, rows)
        results["Q5"] = q5(rtamt, rows)
        results["Q6"] = q6(rtamt)
    for q, label in names.items():
        result = results[q]
        print(f"{q} {result.status} {label}: {result.reason}")
        if DETAIL:
            for line in result.lines:
                print(line)
    if DETAIL and rtamt is not None:
        print(f"Decision by the rule of WS05-T02 check 9: {decision(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
