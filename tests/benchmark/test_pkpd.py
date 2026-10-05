"""PK/PD response model and onset window of the latent patient (WS04-T04).

Every number below is arithmetic and FIXTURE-ONLY (ka 2 per h, ke 1 per h, Emax 20 mmHg,
EC50 0.25 of a unit-dose-normalised concentration): none is a clinical value, none comes from
a drug, and none enters a prior file. Expected values are hand-computed in the comments.
No test builds a per-millisecond array of a day; the largest grids are about 15 000 points.
The committed configuration files are never read here (their rows are awaiting a human); a
file is needed only in tmp_path, built by the fixture-only prior builder.
"""

from __future__ import annotations

import ast
import dataclasses
import math
from collections.abc import Sequence
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ralmon.benchmark import LiteraturePriorSource, PatientParams
from ralmon.benchmark import pkpd as pkpd_module
from ralmon.benchmark.latent import LatentPressure, simulate_baseline_sbp
from ralmon.benchmark.pkpd import (
    MAX_EVALUATIONS,
    MAX_GRID_LEN,
    MAX_INTAKES,
    RATE_LIMIT_TOLERANCE,
    OneCompartmentEmax,
    PkpdModelError,
    PkpdParams,
    ResponseModel,
    apply_drug_response,
    bateman_concentration,
    compose_latent_sbp,
    derive_onset_window,
    effect_concentration,
    emax_effect_mmhg,
    intake_times_from_events,
    t_max_hours,
    window_overlap,
)
from ralmon.benchmark.rng import StreamPurpose, stream
from ralmon.signals import Event, EventKind

from .conftest import make_fixture_prior
from .test_priorsource import parameter_literals

ROOT = Path(__file__).resolve().parents[2]
PKPD_FILE = ROOT / "src" / "ralmon" / "benchmark" / "pkpd.py"

HOUR = 3_600_000
KA, KE, EMAX, EC50 = 2.0, 1.0, 20.0, 0.25  # FIXTURE-ONLY
PARAMS = PkpdParams(
    emax_mmhg=EMAX, ec50=EC50, absorption_rate_per_h=KA, elimination_rate_per_h=KE
)
MODEL = OneCompartmentEmax()
T_MAX_H = math.log(2.0)  # ln(ka / ke) / (ka - ke) for ka 2, ke 1
T_MAX_MS = round(T_MAX_H * HOUR)  # 2 495 330 ms
INT64_MAX = 2**63 - 1
NAN, INF = float("nan"), float("inf")


def effect_at(params: PkpdParams, t_ms: int) -> float:
    """Single-intake effect at ``t_ms`` after an intake at 0, through the public model."""
    return float(MODEL.effect_mmhg(params, [0], [t_ms])[0])


def reference_bateman(ka: float, ke: float, tau_h: float) -> float:
    """Bateman function with 60 digits (exact binary inputs): immune to ka-ke cancellation."""
    with localcontext() as context:
        context.prec = 60
        a, k, t = Decimal(ka), Decimal(ke), Decimal(tau_h)
        if a == k:
            return float(k * t * (-k * t).exp())
        return float(a / (a - k) * ((-k * t).exp() - (-a * t).exp()))


# ---------------------------------------------------------------------------
# Hand values (tests 1 to 9 of the task)
# ---------------------------------------------------------------------------


def test_bateman_concentration_hand_values() -> None:
    # C(1 h) = 2 / (2 - 1) * (exp(-1) - exp(-2)) = 2 * (0.367879441 - 0.135335283)
    #        = 0.465088316
    assert bateman_concentration(KA, KE, 1.0) == pytest.approx(0.465088316, rel=1e-9)
    # at ln 2: exp(-ln 2) = 1/2 and exp(-2 ln 2) = 1/4, so C = 2 * (1/2 - 1/4) = 1/2
    assert bateman_concentration(KA, KE, T_MAX_H) == pytest.approx(0.5, rel=1e-9)
    # ka below ke: C(ln 2; ka 1, ke 2) = 1 / (1 - 2) * (exp(-2 ln 2) - exp(-ln 2))
    #            = -(1/4 - 1/2) = 1/4
    assert bateman_concentration(1.0, 2.0, T_MAX_H) == pytest.approx(0.25, rel=1e-9)


def test_tmax_closed_form() -> None:
    assert t_max_hours(KA, KE) == pytest.approx(0.693147, abs=1e-6)
    grid = list(range(0, 3 * HOUR, 1_000))  # 10 800 points, one second apart
    conc = effect_concentration(PARAMS, [0], grid)
    argmax_ms = grid[int(np.argmax(conc))]
    assert abs(argmax_ms - T_MAX_H * HOUR) <= 1_000  # within one grid step
    # swapping ka and ke gives the same peak time (the function is symmetric)
    assert t_max_hours(KE, KA) == pytest.approx(t_max_hours(KA, KE), rel=1e-12)


def test_bateman_ka_equals_ke_limit() -> None:
    assert bateman_concentration(1.0, 1.0, 1.0) == pytest.approx(
        math.exp(-1.0), rel=1e-9
    )
    near = bateman_concentration(1.0 + 1e-9, 1.0, 1.0)
    assert near == pytest.approx(0.367879441, rel=1e-6)
    assert t_max_hours(1.0, 1.0) == pytest.approx(1.0, rel=1e-12)


def test_concentration_zero_before_intake_and_nonnegative() -> None:
    assert bateman_concentration(KA, KE, -1.0) == 0.0
    assert bateman_concentration(KA, KE, -1e300) == 0.0
    assert bateman_concentration(KA, KE, 0.0) == 0.0
    conc = effect_concentration(PARAMS, [HOUR], [0, HOUR - 1, HOUR, HOUR + 1, 5 * HOUR])
    assert conc[:3] == (0.0, 0.0, 0.0)  # before and at the instant of the intake
    assert conc[3] > 0.0 and conc[4] > 0.0
    assert all(c >= 0.0 for c in conc)


def test_emax_hand_values() -> None:
    assert emax_effect_mmhg(PARAMS, 0.0) == 0.0
    assert emax_effect_mmhg(PARAMS, EC50) == pytest.approx(10.0, rel=1e-12)
    # 20 * 0.5 / (0.25 + 0.5) = 13.3333333
    assert emax_effect_mmhg(PARAMS, 0.5) == pytest.approx(13.3333333, rel=1e-7)
    previous = -1.0
    for c in (0.0, 1e-6, 0.01, 0.1, 0.25, 0.5, 1.0, 10.0, 1e3, 1e6):
        effect = emax_effect_mmhg(PARAMS, c)
        assert previous < effect < EMAX or c == 0.0
        previous = effect


def test_superposition_is_linear() -> None:
    # intakes at 0 and 12 h: the concentration at 13 h is C(13 h) + C(1 h)
    got = effect_concentration(PARAMS, [0, 12 * HOUR], [13 * HOUR])[0]
    expected = bateman_concentration(KA, KE, 13.0) + bateman_concentration(KA, KE, 1.0)
    assert got == pytest.approx(expected, rel=1e-12)
    assert expected == pytest.approx(0.465088316, abs=1e-5)  # C(13 h) is below 5e-6
    # order of the intakes does not matter
    swapped = effect_concentration(PARAMS, [12 * HOUR, 0], [13 * HOUR])[0]
    assert swapped == pytest.approx(got, rel=1e-12)


def test_double_intake_doubles_concentration_before_emax() -> None:
    grid = [0, T_MAX_MS, HOUR, 5 * HOUR]
    single = effect_concentration(PARAMS, [0], grid)
    double = effect_concentration(PARAMS, [0, 0], grid)
    for one, two in zip(single, double, strict=True):
        assert two == pytest.approx(2.0 * one, rel=1e-12)
    # at t_max the concentration is 2 * 0.5 = 1.0 and E(1.0) = 20 * 1 / 1.25 = 16
    effect = MODEL.effect_mmhg(PARAMS, [0, 0], [T_MAX_MS])
    assert effect[0] == pytest.approx(16.0, rel=1e-9)


def test_intake_scales_scale_emax_per_intake() -> None:
    # a scale of 0.5 halves the Emax of that intake: 0.5 * 13.3333333 = 6.6666667
    effect = MODEL.effect_mmhg(PARAMS, [0], [T_MAX_MS], intake_scales=[0.5])
    assert effect[0] == pytest.approx(6.6666667, rel=1e-7)
    # scale 0 is a non-response, scale 1 equals no scales at all
    assert MODEL.effect_mmhg(PARAMS, [0], [T_MAX_MS], intake_scales=[0.0])[0] == 0.0
    assert MODEL.effect_mmhg(PARAMS, [0], [T_MAX_MS], intake_scales=[1]) == (
        MODEL.effect_mmhg(PARAMS, [0], [T_MAX_MS])
    )
    # two simultaneous intakes with scales 1 and 0: the concentration is doubled (saturation
    # sees both) but only the first intake's share of the effect is produced:
    # 20 * 0.5 / (0.25 + 1.0) = 8
    mixed = MODEL.effect_mmhg(PARAMS, [0, 0], [T_MAX_MS], intake_scales=[1.0, 0.0])
    assert mixed[0] == pytest.approx(8.0, rel=1e-8)
    # only the sum of the scales of simultaneous intakes matters at one instant: 0.25 + 0.75
    # gives the same effect as 1 + 0 (the saturation term sees both intakes)
    split = MODEL.effect_mmhg(PARAMS, [0, 0], [T_MAX_MS], intake_scales=[0.25, 0.75])
    assert split[0] == pytest.approx(8.0, rel=1e-8)
    # scales 1 and 1 are the unscaled double intake: 20 * 1.0 / 1.25 = 16
    both = MODEL.effect_mmhg(PARAMS, [0, 0], [T_MAX_MS], intake_scales=[1.0, 1.0])
    assert both[0] == pytest.approx(16.0, rel=1e-8)
    # a scale belongs to its own intake, not to the sorted position
    # (the first listed intake, at 12 h, has scale 1 and the second, at 0, has scale 0)
    late = MODEL.effect_mmhg(
        PARAMS, [12 * HOUR, 0], [13 * HOUR], intake_scales=[1.0, 0.0]
    )
    c_both = bateman_concentration(KA, KE, 13.0) + bateman_concentration(KA, KE, 1.0)
    assert late[0] == pytest.approx(
        EMAX * bateman_concentration(KA, KE, 1.0) / (EC50 + c_both), rel=1e-9
    )
    assert (
        late[0] > 10.0
    )  # the scale of the sorted position (0 at the later time) would give ~0


def test_no_intake_means_zero_effect_and_unchanged_trace() -> None:
    baseline = simulate_baseline_sbp(
        PatientParams(
            patient_id="p0000",
            baseline_sbp_mmhg=130.0,
            circadian_amplitude_mmhg=10.0,
            ar_noise_sd_mmhg=8.0,
            ar_noise_phi=0.6,
            emax_mmhg=EMAX,
            ec50=EC50,
            absorption_rate_per_h=KA,
            elimination_rate_per_h=KE,
            onset_delay_range_ms=(HOUR, 2 * HOUR),
        ),
        900_000,
        1,
        12 * HOUR,
        900_000,
        stream(0, 0, None, StreamPurpose.LATENT_AR),
    )
    effect = MODEL.effect_mmhg(PARAMS, [], baseline.t_ms)
    assert len(effect) == 96 and all(e == 0.0 for e in effect)
    composed = compose_latent_sbp(baseline.sbp_mmhg, effect)
    assert composed.tobytes() == baseline.sbp_mmhg.tobytes()  # bit for bit
    assert apply_drug_response(MODEL, PARAMS, baseline, []).tobytes() == (
        baseline.sbp_mmhg.tobytes()
    )
    # scales may be given for no intake, as the empty list
    assert MODEL.effect_mmhg(PARAMS, [], [0, 5], intake_scales=[]) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# Onset window (tests 10 to 13)
# ---------------------------------------------------------------------------


def test_onset_window_two_crossings_closed_form() -> None:
    # delta 10 needs C = 0.25; with u = exp(-t): u^2 - u + 0.125 = 0, so
    # t = -ln((1 +- sqrt(0.5)) / 2) = 0.158347 h and 1.921094 h.
    lo_h = -math.log((1 + math.sqrt(0.5)) / 2)
    hi_h = -math.log((1 - math.sqrt(0.5)) / 2)
    assert (lo_h, hi_h) == (
        pytest.approx(0.158347, abs=1e-6),
        pytest.approx(1.921094, abs=1e-6),
    )
    assert derive_onset_window(PARAMS, 10.0) == (570_050, 6_915_939)  # rounded inward


def test_onset_window_empty_when_peak_effect_below_delta() -> None:
    assert derive_onset_window(PARAMS, 14.0) is None  # the peak effect is 13.3333
    assert derive_onset_window(PARAMS, 13.4) is None
    assert derive_onset_window(PARAMS, 1e300) is None
    # a patient who cannot respond: Emax 0
    assert derive_onset_window(dataclasses.replace(PARAMS, emax_mmhg=0.0), 1.0) is None


def test_onset_window_contains_tmax_for_delta_just_below_peak() -> None:
    window = derive_onset_window(PARAMS, 13.0)
    assert window is not None
    lo, hi = window
    assert lo < T_MAX_H * HOUR < hi
    assert lo <= T_MAX_MS <= hi
    # a delta barely below the peak: a window of a few ms around t_max
    narrow = derive_onset_window(PARAMS, 13.333)
    assert narrow is not None and narrow[0] <= T_MAX_MS <= narrow[1]
    assert narrow[1] - narrow[0] < 120_000
    wide = derive_onset_window(PARAMS, 10.0)
    assert wide is not None and wide[0] < lo and hi < wide[1]  # a lower delta widens it


def test_window_contains_the_better_integer_neighbour_of_the_peak() -> None:
    # delta equal to the larger of the two integer neighbours of the peak: the window is not
    # empty, whichever neighbour (floor or ceil of t_max in ms) is the larger
    floors = ceils = 0
    for ka in (1.3, 1.7, 2.3, 2.9, 3.1, 4.7):
        for ke in (0.4, 0.55, 0.9, 1.1):
            params = PkpdParams(EMAX, EC50, ka, ke)
            below = math.floor(t_max_hours(ka, ke) * HOUR)
            e0, e1 = effect_at(params, below), effect_at(params, below + 1)
            floors, ceils = floors + (e0 >= e1), ceils + (e1 > e0)
            window = derive_onset_window(params, max(e0, e1))
            assert window is not None and window[0] <= below + (e1 > e0) <= window[1]
            above = math.nextafter(max(e0, e1), INF)
            assert derive_onset_window(params, above) is None
    assert floors > 0 and ceils > 0  # the fixture grid exercises both branches


def test_onset_window_at_delta_equal_to_an_attained_effect() -> None:
    # delta equal (as a float) to the effect at an integer instant on the rising side: that
    # instant is the first of the window (>=, not >), and the previous millisecond is not.
    t0 = 1_000_000
    delta = effect_at(PARAMS, t0)
    window = derive_onset_window(PARAMS, delta)
    assert window is not None and window[0] == t0
    # the same on the falling side: the last instant of the window
    t1 = 5_000_000
    delta = effect_at(PARAMS, t1)
    window = derive_onset_window(PARAMS, delta)
    assert window is not None and window[1] == t1
    # delta equal to the best integer neighbour of the peak: the window is not empty
    delta = max(effect_at(PARAMS, T_MAX_MS - 1), effect_at(PARAMS, T_MAX_MS))
    window = derive_onset_window(PARAMS, delta)
    assert window is not None and window[0] <= T_MAX_MS <= window[1]
    # one ulp above the best attained effect: no instant reaches it
    above = math.nextafter(delta, INF)
    assert effect_at(PARAMS, T_MAX_MS) < above
    assert derive_onset_window(PARAMS, above) is None


def test_window_overlap_with_registry_window() -> None:
    window = (570_050, 6_915_939)
    assert window_overlap(window, 3_600_000, 7_200_000) == (3_600_000, 6_915_939)
    assert window_overlap(window, 7_200_000, 10_800_000) is None
    # a registry window inside the onset window, and an onset window inside the registry's
    assert window_overlap(window, 1_000_000, 2_000_000) == (1_000_000, 2_000_000)
    assert window_overlap(window, 0, 10_800_000) == window
    # closed intervals: touching at one instant is an overlap, one ms apart is none
    assert window_overlap(window, 6_915_939, 7_200_000) == (6_915_939, 6_915_939)
    assert window_overlap(window, 6_915_940, 7_200_000) is None
    assert window_overlap(window, 0, 570_050) == (570_050, 570_050)
    assert window_overlap(window, 0, 570_049) is None
    assert window_overlap((5, 5), 5, 5) == (5, 5)  # all degenerate
    assert window_overlap((0, 0), 0, 0) == (0, 0)


# ---------------------------------------------------------------------------
# Protocol, validation, delta (tests 14 to 16)
# ---------------------------------------------------------------------------


class ConstantEffectModel:
    """A stub engine: a constant effect, ignoring everything (what a Pulse adapter replaces)."""

    def __init__(self, value: float) -> None:
        self.value = value
        self.calls: list[tuple[Any, ...]] = []

    def effect_mmhg(
        self,
        params: PkpdParams | PatientParams,
        intake_times_ms: Sequence[int],
        t_grid_ms: Sequence[int],
        intake_scales: Sequence[float] | None = None,
    ) -> Sequence[float]:
        self.calls.append(
            (params, tuple(intake_times_ms), tuple(t_grid_ms), intake_scales)
        )
        return [self.value] * len(t_grid_ms)


def _baseline(n: int = 4) -> LatentPressure:
    t = np.arange(n, dtype=np.int64) * 900_000
    flat = np.full(n, 130.0)
    zeros = np.zeros(n)
    return LatentPressure(
        t_ms=t, circadian_mmhg=zeros, ar_noise_mmhg=zeros, sbp_mmhg=flat
    )


def test_response_model_protocol_swappable() -> None:
    stub = ConstantEffectModel(7.5)
    assert isinstance(stub, ResponseModel) and isinstance(MODEL, ResponseModel)
    baseline = _baseline()
    out = apply_drug_response(stub, PARAMS, baseline, [0], [0.5])
    assert out.tolist() == [122.5] * 4  # baseline - effect
    assert len(stub.calls) == 1 and stub.calls[0][1:] == (
        (0,),
        tuple(baseline.t_ms),
        [0.5],
    )
    # the composer accepts either engine through the same call
    real = apply_drug_response(MODEL, PARAMS, baseline, [0])
    assert real.shape == (4,) and np.all(real <= baseline.sbp_mmhg)
    assert real[0] == 130.0  # nothing at the instant of the intake


@pytest.mark.parametrize(
    "field", ["emax_mmhg", "ec50", "absorption_rate_per_h", "elimination_rate_per_h"]
)
def test_parameters_validated(field: str) -> None:
    bad = [NAN, INF, -INF, 10**400, -(10**400), None, True, False, "1", b"1", [1.0], 1j]
    bad += [-1.0, -1e-300] if field == "emax_mmhg" else [0.0, -0.0, 0, -1.0, -1e-300]
    for value in bad:
        with pytest.raises(PkpdModelError):
            dataclasses.replace(PARAMS, **{field: value})
    # the boundary: Emax 0 is allowed (a non-responder), a rate or EC50 of 0 is not
    if field == "emax_mmhg":
        assert dataclasses.replace(PARAMS, **{field: 0.0}).emax_mmhg == 0.0
        assert dataclasses.replace(PARAMS, **{field: 0}).emax_mmhg == 0.0
    tiny = dataclasses.replace(PARAMS, **{field: 5e-324})
    assert getattr(tiny, field) == 5e-324


def test_params_from_a_patient_and_from_a_fixture_prior(tmp_path: Path) -> None:
    prior = LiteraturePriorSource(make_fixture_prior(tmp_path), allow_fixture_only=True)
    patient = prior.sample_patient(stream(0, 3, None, StreamPurpose.PATIENT), 3)
    params = PkpdParams.from_patient(patient)
    assert params == PkpdParams(
        emax_mmhg=patient.emax_mmhg,
        ec50=patient.ec50,
        absorption_rate_per_h=patient.absorption_rate_per_h,
        elimination_rate_per_h=patient.elimination_rate_per_h,
    )
    # the fixture file rows are 20, 1, 2, 0.5: a unit-dose Emax model on the fixture rows
    assert (params.emax_mmhg, params.ec50) == (20.0, 1.0)
    assert (params.absorption_rate_per_h, params.elimination_rate_per_h) == (2.0, 0.5)
    # a PatientParams is accepted wherever PkpdParams is
    grid = [0, HOUR, 2 * HOUR]
    assert MODEL.effect_mmhg(patient, [0], grid) == MODEL.effect_mmhg(params, [0], grid)
    assert derive_onset_window(patient, 5.0) == derive_onset_window(params, 5.0)
    with pytest.raises(PkpdModelError):
        PkpdParams.from_patient(None)  # type: ignore[arg-type]
    with pytest.raises(PkpdModelError):
        PkpdParams.from_patient(dataclasses.replace(patient, ec50=0.0))


def test_delta_is_an_argument_not_a_constant() -> None:
    with pytest.raises(TypeError):
        derive_onset_window(PARAMS)  # type: ignore[call-arg]
    # the threshold must be given, and different deltas give different windows
    assert derive_onset_window(PARAMS, 5.0) != derive_onset_window(PARAMS, 10.0)
    source = PKPD_FILE.read_text(encoding="utf-8")
    assert (
        parameter_literals(source) == []
    )  # no unannotated numeric literal in the module


def test_module_hygiene() -> None:
    tree = ast.parse(PKPD_FILE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not any(n.startswith(("ralmon.spec", "ralmon.monitor")) for n in imported)
    assert not {"yaml", "pathlib", "os", "random", "time", "datetime"} & imported
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    # ground truth discipline: the response model is part of the generator and never reads
    # the ground-truth types (and takes no DISPENSE as an intake)
    assert not {"LatentDay", "GroundTruthEvent", "ObservedDay"} & names
    import ralmon.benchmark as root

    for name in (
        "OneCompartmentEmax",
        "ResponseModel",
        "PkpdParams",
        "derive_onset_window",
    ):
        assert name not in root.__all__ and not hasattr(root, name)


def _scan_window(params: PkpdParams, delta: float, best: int) -> tuple[int, int]:
    """Oracle: the contiguous integer-ms run around ``best`` with effect >= delta, by scan."""
    lo = hi = best
    while lo > 1 and effect_at(params, lo - 1) >= delta:
        lo -= 1
    while effect_at(params, hi + 1) >= delta:
        hi += 1
    return lo, hi


def _best_integer_peak() -> int:
    around = range(T_MAX_MS - 3, T_MAX_MS + 4)
    return max(around, key=lambda t: (effect_at(PARAMS, t), -t))


@pytest.mark.parametrize("step", [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048])
def test_window_end_at_delta_equal_to_the_effect_at_an_exponential_probe(
    step: int,
) -> None:
    # The falling side probes best + 1, + 2, + 4, ...: a delta exactly equal to the effect at
    # one of those instants must keep that instant inside the window (>=, not >).
    best = _best_integer_peak()
    assert (
        1 <= best - (T_MAX_MS - 3) + 1 <= 7
    )  # the oracle really looked around the peak
    delta = effect_at(PARAMS, best + step)
    window = derive_onset_window(PARAMS, delta)
    assert window is not None
    lo, hi = _scan_window(PARAMS, delta, best)
    assert hi >= best + step  # the probe instant itself attains delta
    assert window == (lo, hi)


@pytest.mark.parametrize("k", range(1, 16))
def test_window_start_at_delta_equal_to_the_effect_at_a_bisection_instant(
    k: int,
) -> None:
    # The rising side bisects [0, best]: its middles are dyadic fractions of best. A delta
    # equal to the effect at such an instant (or a neighbour) keeps that instant inside.
    best = _best_integer_peak()
    for t0 in ((best * k) // 16 - 1, (best * k) // 16, (best * k) // 16 + 1):
        delta = effect_at(PARAMS, t0)
        window = derive_onset_window(PARAMS, delta)
        assert window is not None
        # on the rising side the effect is strictly increasing here: the window starts at t0
        assert effect_at(PARAMS, t0 - 1) < delta
        assert window[0] == t0
        assert effect_at(PARAMS, window[1]) >= delta > effect_at(PARAMS, window[1] + 1)


@pytest.mark.parametrize("offset", [1, 2, 3, 5, 100, 1_000, 3_000, 70_001])
def test_window_end_at_delta_equal_to_the_effect_at_a_falling_instant(
    offset: int,
) -> None:
    # the falling-side bisection: the end of the window is the instant whose effect is delta
    best = _best_integer_peak()
    t1 = best + offset
    delta = effect_at(PARAMS, t1)
    window = derive_onset_window(PARAMS, delta)
    assert window is not None
    assert effect_at(PARAMS, t1 + 1) < delta  # strictly decreasing there
    assert window[1] == t1
    if offset <= 100:  # a scan of the whole run is affordable for the near instants
        assert window == _scan_window(PARAMS, delta, best)


def test_a_peak_at_the_int64_boundary_is_a_defined_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No float hours value gives peak_ms == 2**63 exactly (hours * 3 600 000 skips it), so
    # the two float neighbours of the boundary are used: 2**63 - 1024 is below the int64
    # maximum (effect 0 there, no window); 2**63 + 2048 is above it and must be a
    # PkpdModelError, never a raw OverflowError from the int64 conversion of the probe grid.
    boundary = float(2**63)
    below_hours = boundary / pkpd_module.MS_PER_HOUR  # peak_ms is 2**63 - 1024
    above_hours = math.nextafter(below_hours, INF)  # peak_ms is 2**63 + 2048
    assert below_hours * pkpd_module.MS_PER_HOUR < boundary
    assert above_hours * pkpd_module.MS_PER_HOUR > boundary
    monkeypatch.setattr(pkpd_module, "_t_max", lambda ka, ke: below_hours)
    assert derive_onset_window(PARAMS, 1.0) is None
    monkeypatch.setattr(pkpd_module, "_t_max", lambda ka, ke: above_hours)
    with pytest.raises(PkpdModelError):
        derive_onset_window(PARAMS, 1.0)


# ---------------------------------------------------------------------------
# Only true intakes drive the model
# ---------------------------------------------------------------------------


def _event(kind: EventKind, t_ms: int) -> Event:
    return Event(kind, t_ms, t_ms, "x", {}, None)


def test_only_intake_events_drive_the_model() -> None:
    events = [
        _event(EventKind.DISPENSE, 0),
        _event(EventKind.INTAKE, 60_000),
        _event(EventKind.DISPENSE, 10 * HOUR),  # dispensed, never taken: no effect
        _event(EventKind.MEASUREMENT, 5 * HOUR),
        _event(EventKind.INTAKE, 12 * HOUR),
    ]
    assert intake_times_from_events(events) == (60_000, 12 * HOUR)
    assert intake_times_from_events([_event(EventKind.DISPENSE, 5)]) == ()
    assert intake_times_from_events([]) == ()
    effect = MODEL.effect_mmhg(PARAMS, intake_times_from_events(events[:1]), [HOUR])
    assert effect == (0.0,)  # a DISPENSE alone has no effect
    for bad in (None, 5, "x", [None], [1], [("intake", 1)], {1: 2}):
        with pytest.raises(PkpdModelError):
            intake_times_from_events(bad)  # type: ignore[arg-type]
    with pytest.raises(PkpdModelError):
        intake_times_from_events([_event(EventKind.INTAKE, -1)])


def test_intake_times_use_the_device_clock_not_the_reception_clock() -> None:
    # t_rx_ms differs from t_device_ms (a late, or an early, reception): the latent intake
    # time is the device time of the event
    events = [
        Event(EventKind.INTAKE, 1_000, 5_000, "x", {}, None),
        Event(EventKind.INTAKE, 9_000, 2_000, "x", {}, None),
        Event(EventKind.DISPENSE, 3_000, 4_000, "x", {}, None),
    ]
    assert intake_times_from_events(events) == (1_000, 9_000)
    # a negative reception time does not matter either; a negative device time does
    assert intake_times_from_events(
        [Event(EventKind.INTAKE, 7, -3, "x", {}, None)]
    ) == (7,)
    with pytest.raises(PkpdModelError):
        intake_times_from_events([Event(EventKind.INTAKE, -1, 5, "x", {}, None)])


# ---------------------------------------------------------------------------
# Numerics: ka close to ke, extreme times, no NaN, nonnegative
# ---------------------------------------------------------------------------

REL_DIFFS = (
    0.0,
    1e-15,
    1e-13,
    RATE_LIMIT_TOLERANCE / 2,
    RATE_LIMIT_TOLERANCE,
    RATE_LIMIT_TOLERANCE * 2,
    1e-9,
    1e-6,
    1e-3,
    -1e-13,
    -RATE_LIMIT_TOLERANCE,
    -RATE_LIMIT_TOLERANCE * 2,
    -1e-9,
    -1e-6,
    -1e-3,
)


@pytest.mark.parametrize("rel", REL_DIFFS)
@pytest.mark.parametrize("ke", [0.25, 1.0, 40.0])
def test_bateman_near_the_limit_matches_a_high_precision_reference(
    rel: float, ke: float
) -> None:
    ka = ke * (1.0 + rel)
    for tau in (1e-6, 0.05, 1.0, 7.5, 30.0, 100.0):
        got = bateman_concentration(ka, ke, tau)
        want = reference_bateman(ka, ke, tau)
        assert got >= 0.0
        assert got == pytest.approx(want, rel=1e-12, abs=1e-300), (rel, tau)


@pytest.mark.parametrize("rel", [1e-12, 1e-9, 1e-6])
def test_bateman_is_continuous_across_the_limit_branch(rel: float) -> None:
    # ka = ke (1 + rel) just below and above the tolerance, against the exact limit
    for tau in (0.5, 2.0, 10.0):
        limit = reference_bateman(1.0, 1.0, tau)
        assert bateman_concentration(1.0 + rel, 1.0, tau) == pytest.approx(
            limit, rel=10 * rel * (1 + tau)
        )
        assert bateman_concentration(1.0, 1.0 + rel, tau) == pytest.approx(
            limit, rel=10 * rel * (1 + tau)
        )


def test_bateman_ka_and_ke_exactly_equal_uses_the_limit_not_a_division() -> None:
    for rate in (1e-300, 1e-9, 0.7, 40.0, 1e300):
        for tau in (0.0, 1e-9, 1.0, 1e3, 1e300):
            value = bateman_concentration(rate, rate, tau)
            assert 0.0 <= value <= 1.0 and math.isfinite(value)
    assert bateman_concentration(0.7, 0.7, 1.0) == pytest.approx(
        0.7 * math.exp(-0.7), rel=1e-12
    )


def test_bateman_large_tau_underflows_to_zero_without_nan() -> None:
    for tau in (800.0, 1e6, 1e300, 1e308, 2.0**62):
        assert bateman_concentration(2.0, 1.0, tau) == 0.0
        assert bateman_concentration(1.0, 2.0, tau) == 0.0
        assert bateman_concentration(1.0, 1.0, tau) == 0.0
        assert bateman_concentration(1.0 + 1e-13, 1.0, tau) == 0.0
    # extreme rates: finite, within [0, 1], never NaN or an exception
    rates = (5e-324, 1e-300, 1e-9, 1.0, 1e9, 1e300, 1.7e308)
    for ka in rates:
        for ke in rates:
            for tau in (0.0, 1e-300, 1e-9, 1.0, 1e9, 1e300):
                value = bateman_concentration(ka, ke, tau)
                assert math.isfinite(value) and 0.0 <= value <= 1.0 + 1e-12


def test_concentration_is_nonnegative_and_bounded_over_a_sweep() -> None:
    grid = list(range(0, 40 * HOUR, 5 * 60_000))  # 480 points
    for ke in (0.25, 1.0, 3.0):
        for rel in (0.0, 1e-13, 1e-9, 1e-6, 0.01, 1.0, 9.0, -1e-9, -0.5, -0.99):
            params = dataclasses.replace(
                PARAMS,
                absorption_rate_per_h=ke * (1.0 + rel),
                elimination_rate_per_h=ke,
            )
            conc = effect_concentration(params, [0, 7 * HOUR], grid)
            assert all(math.isfinite(c) and c >= 0.0 for c in conc)
            effect = MODEL.effect_mmhg(params, [0, 7 * HOUR], grid)
            assert all(0.0 <= e < EMAX for e in effect)


def test_far_away_grid_times_give_zero_not_nan() -> None:
    far = INT64_MAX
    assert effect_concentration(PARAMS, [0], [far]) == (0.0,)
    assert effect_concentration(PARAMS, [far], [far]) == (0.0,)
    assert MODEL.effect_mmhg(PARAMS, [0, far], [far - 1, far]) == (0.0, 0.0)
    slow = dataclasses.replace(
        PARAMS, absorption_rate_per_h=1e-12, elimination_rate_per_h=1e-12
    )
    effect = MODEL.effect_mmhg(slow, [0], [far])
    assert math.isfinite(effect[0]) and 0.0 <= effect[0] <= EMAX


def test_t_max_numerics() -> None:
    for rel in REL_DIFFS:
        ka = 1.0 + rel
        got = t_max_hours(ka, 1.0)
        r = ka - 1.0
        assert abs(got - (1.0 - r / 2.0)) <= r * r + 1e-15, rel
    # the same away from ke = 1 (log(ka) - log(ke) would lose digits there): with
    # r = (ka - ke) / ke the peak time is ln(1 + r) / (ke r) = (1 - r/2 + r^2/3 - r^3/4 ...) / ke
    for ke in (0.25, 40.0, 1e6):
        for rel in (*REL_DIFFS, 1e-2, -1e-2, 0.3, -0.3):
            ka = ke * (1.0 + rel)
            r = (ka - ke) / ke
            series = (
                1.0 - r / 2.0 + r**2 / 3.0 - r**3 / 4.0 + r**4 / 5.0 - r**5 / 6.0
            ) / ke
            if abs(r) < 0.1:
                assert t_max_hours(ka, ke) == pytest.approx(series, rel=1e-11), (
                    ke,
                    rel,
                )
            if abs(rel) >= 1e-2:
                direct = math.log(ka / ke) / (ka - ke)
                assert t_max_hours(ka, ke) == pytest.approx(direct, rel=1e-9)
    assert t_max_hours(1.7e308, 5e-324) > 0.0  # no overflow of ka / ke
    assert t_max_hours(5e-324, 1.7e308) > 0.0
    assert math.isfinite(t_max_hours(1e-300, 1e300))
    # two denormal rates: the peak time (about 2e323 h) is not representable
    with pytest.raises(PkpdModelError):
        t_max_hours(5e-324, 5e-324)


# ---------------------------------------------------------------------------
# Onset window: integer milliseconds, rounded inward, verified (property tests)
# ---------------------------------------------------------------------------


def _check_window(params: PkpdParams, delta: float) -> tuple[int, int] | None:
    window = derive_onset_window(params, delta)
    if window is None:
        # no integer instant next to the peak reaches delta
        peak_ms = (
            t_max_hours(params.absorption_rate_per_h, params.elimination_rate_per_h)
            * HOUR
        )
        around = (math.floor(peak_ms), math.floor(peak_ms) + 1)
        assert all(effect_at(params, t) < delta for t in around)
        return None
    lo, hi = window
    assert isinstance(lo, int) and isinstance(hi, int) and 1 <= lo <= hi
    assert effect_at(params, lo) >= delta and effect_at(params, hi) >= delta
    assert effect_at(params, lo - 1) < delta  # one ms outside is below delta
    assert effect_at(params, hi + 1) < delta
    return window


@settings(max_examples=40, deadline=None)
@given(
    ka=st.floats(0.5, 6.0),
    ke=st.floats(0.25, 2.0),
    emax=st.floats(5.0, 40.0),
    ec50=st.floats(0.05, 2.0),
    fraction=st.floats(0.02, 1.2),
)
def test_window_bounds_are_attained_and_tight(
    ka: float, ke: float, emax: float, ec50: float, fraction: float
) -> None:
    params = PkpdParams(emax, ec50, ka, ke)
    peak_c = bateman_concentration(ka, ke, t_max_hours(ka, ke))
    peak_effect = emax * peak_c / (ec50 + peak_c)
    delta = max(fraction * peak_effect, 1e-6)
    window = _check_window(params, delta)
    if fraction > 1.0 + 1e-9:
        assert window is None
    if fraction < 0.99 and delta > 1e-3:
        assert window is not None


@settings(max_examples=15, deadline=None)
@given(
    ka=st.floats(0.5, 6.0),
    ke=st.floats(0.25, 2.0),
    fraction=st.floats(0.1, 0.99),
)
def test_window_matches_the_set_where_the_effect_reaches_delta(
    ka: float, ke: float, fraction: float
) -> None:
    params = PkpdParams(EMAX, EC50, ka, ke)
    peak_c = bateman_concentration(ka, ke, t_max_hours(ka, ke))
    delta = fraction * EMAX * peak_c / (EC50 + peak_c)
    window = derive_onset_window(params, delta)
    assert window is not None
    grid = list(range(10_000, 60 * HOUR, 20_000))  # 10 800 points
    effect = MODEL.effect_mmhg(params, [0], grid)
    for t, e in zip(grid, effect, strict=True):
        assert (e >= delta) == (window[0] <= t <= window[1]), (t, e, delta, window)


@pytest.mark.parametrize("rel", [0.0, 1e-13, 1e-9, 1e-6, -1e-9, -1e-6])
def test_window_with_ka_close_to_ke(rel: float) -> None:
    params = dataclasses.replace(PARAMS, absorption_rate_per_h=KE * (1.0 + rel))
    # the limit curve: C = ke t exp(-ke t), peak C = exp(-1) at t = 1 h, effect 20 c / (c + .25)
    peak_effect = EMAX * math.exp(-1.0) / (EC50 + math.exp(-1.0))
    for fraction in (0.5, 0.9, 0.999):
        window = _check_window(params, fraction * peak_effect)
        assert window is not None and window[0] < HOUR < window[1]
    assert _check_window(params, peak_effect * 1.001) is None


def test_window_is_deterministic_and_pure() -> None:
    first = derive_onset_window(PARAMS, 10.0)
    assert [derive_onset_window(PARAMS, 10.0) for _ in range(3)] == [first] * 3
    # numpy scalars and ints are accepted as delta; a float and its int agree
    assert derive_onset_window(PARAMS, np.float64(10.0)) == first
    assert derive_onset_window(PARAMS, 10) == first


def test_window_of_a_tiny_delta_starts_at_the_first_millisecond() -> None:
    # effect(0) = 0 and effect(1 ms) is about 4e-5 mmHg: a delta below it starts at 1 ms
    first = effect_at(PARAMS, 1)
    assert 0.0 < first < 1e-3
    window = derive_onset_window(PARAMS, first)
    assert window is not None and window[0] == 1
    below = derive_onset_window(PARAMS, first / 2)
    assert below is not None and below[0] == 1
    assert derive_onset_window(PARAMS, math.nextafter(first, INF)) != window


def test_a_window_ending_beyond_the_int64_range_is_a_defined_error() -> None:
    # the peak (2.6e11 h) is representable, but the effect is still above delta at int64 max
    slow = PkpdParams(EMAX, EC50, 1e-11, 1e-12)
    peak_ms = t_max_hours(1e-11, 1e-12) * HOUR
    assert peak_ms < INT64_MAX
    assert effect_at(slow, INT64_MAX) > 1e-6
    with pytest.raises(PkpdModelError):
        derive_onset_window(slow, 1e-6)


def test_window_that_leaves_the_int64_range_is_a_defined_error() -> None:
    slow = PkpdParams(EMAX, EC50, 1e-14, 1e-15)  # a peak at about 1e14 h
    with pytest.raises(PkpdModelError):
        derive_onset_window(slow, 1.0)
    # a curve so fast that no integer millisecond reaches delta: None, not an error
    fast = PkpdParams(EMAX, EC50, 1e300, 1e299)
    assert derive_onset_window(fast, 1.0) is None


# ---------------------------------------------------------------------------
# Robustness against extreme inputs (every public function: PkpdModelError only)
# ---------------------------------------------------------------------------

BAD_NUMBERS: list[Any] = [
    NAN,
    INF,
    -INF,
    10**400,
    -(10**400),
    None,
    True,
    False,
    "1",
    b"1",
    [1.0],
    1j,
    object(),
]
BAD_TIME_SEQUENCES: list[Any] = [
    None,
    5,
    1.5,
    "ab",
    b"ab",
    {1},
    {1: 2},
    (x for x in [1]),
    [1.5],
    [True],
    [None],
    ["1"],
    [-1],
    [INT64_MAX + 1],
    [10**400],
    [NAN],
    [[1]],
    [np.float64(1.0)],
    np.array([1.5]),
    np.array([True]),
    np.array([-1]),
    np.array([[1, 2]]),
    np.array([INT64_MAX + 1], dtype=np.uint64),
    np.array(["a"]),
]
BAD_GRIDS: list[Any] = [
    *BAD_TIME_SEQUENCES,
    [],
    (),
    range(0),
    [2, 1],
    [1, 1],
    [0, 5, 5],
    [3, 2, 1],
]
BAD_SCALES: list[Any] = [
    [NAN],
    [INF],
    [-0.5],
    [-1e-300],
    [True],
    [None],
    ["1"],
    [10**400],
    [0.5, 0.5],  # length mismatch with one intake
    [],
    0.5,
    "a",
    b"a",
    {0.5},
    {0: 0.5},
    [[0.5]],
    object(),
    (x for x in [0.5]),
    np.array([0.5, 0.5]),
    np.array([[0.5]]),
    np.array([True]),
    np.array(["a"]),
]
BAD_PARAMS: list[Any] = [
    None,
    5,
    "p",
    {"emax_mmhg": 20.0},
    object(),
    (20.0, 0.25, 2.0, 1.0),
]


@pytest.mark.parametrize("bad", BAD_NUMBERS + [0.0, -1.0, -0.0, 0])
def test_bateman_rejects_bad_rates(bad: Any) -> None:
    with pytest.raises(PkpdModelError):
        bateman_concentration(bad, KE, 1.0)
    with pytest.raises(PkpdModelError):
        bateman_concentration(KA, bad, 1.0)
    with pytest.raises(PkpdModelError):
        t_max_hours(bad, KE)
    with pytest.raises(PkpdModelError):
        t_max_hours(KA, bad)


@pytest.mark.parametrize("bad", BAD_NUMBERS)
def test_bateman_rejects_bad_tau(bad: Any) -> None:
    with pytest.raises(PkpdModelError):
        bateman_concentration(KA, KE, bad)


@pytest.mark.parametrize("bad", [*BAD_NUMBERS, -1.0, -1e-300, -(10**3)])
def test_emax_effect_rejects_bad_concentrations(bad: Any) -> None:
    with pytest.raises(PkpdModelError):
        emax_effect_mmhg(PARAMS, bad)
    with pytest.raises(PkpdModelError):
        emax_effect_mmhg(bad, 0.5)  # a bad parameter set


@pytest.mark.parametrize("bad", BAD_PARAMS)
def test_every_function_rejects_bad_params(bad: Any) -> None:
    with pytest.raises(PkpdModelError):
        MODEL.effect_mmhg(bad, [0], [1])
    with pytest.raises(PkpdModelError):
        effect_concentration(bad, [0], [1])
    with pytest.raises(PkpdModelError):
        derive_onset_window(bad, 1.0)
    with pytest.raises(PkpdModelError):
        apply_drug_response(MODEL, bad, _baseline(), [0])


@pytest.mark.parametrize("bad", BAD_TIME_SEQUENCES)
def test_effect_rejects_bad_intake_times(bad: Any) -> None:
    with pytest.raises(PkpdModelError):
        MODEL.effect_mmhg(PARAMS, bad, [0, 1])
    with pytest.raises(PkpdModelError):
        effect_concentration(PARAMS, bad, [0, 1])


@pytest.mark.parametrize("bad", BAD_GRIDS)
def test_effect_rejects_bad_grids(bad: Any) -> None:
    with pytest.raises(PkpdModelError):
        MODEL.effect_mmhg(PARAMS, [0], bad)
    with pytest.raises(PkpdModelError):
        effect_concentration(PARAMS, [0], bad)


@pytest.mark.parametrize("bad", BAD_SCALES)
def test_effect_rejects_bad_scales(bad: Any) -> None:
    with pytest.raises(PkpdModelError):
        MODEL.effect_mmhg(PARAMS, [0], [1, 2], intake_scales=bad)


def test_effect_scale_overflow_is_a_defined_error() -> None:
    with pytest.raises(PkpdModelError):
        MODEL.effect_mmhg(PARAMS, [0], [T_MAX_MS], intake_scales=[1.7e308])
    huge = dataclasses.replace(PARAMS, emax_mmhg=1.7e308)
    with pytest.raises(PkpdModelError):
        MODEL.effect_mmhg(huge, [0, 0], [T_MAX_MS], intake_scales=[10.0, 10.0])


def test_effect_accepts_the_usual_sequence_types() -> None:
    expected = MODEL.effect_mmhg(PARAMS, [0, 12 * HOUR], [HOUR, 13 * HOUR])
    assert len(expected) == 2
    forms: list[tuple[Any, Any]] = [
        ((0, 12 * HOUR), (HOUR, 13 * HOUR)),
        (np.array([0, 12 * HOUR]), np.array([HOUR, 13 * HOUR])),
        (
            np.array([0, 12 * HOUR], dtype=np.int32),
            np.array([HOUR, 13 * HOUR], dtype=np.int32),
        ),
        ([np.int64(0), np.int64(12 * HOUR)], [np.int64(HOUR), np.int64(13 * HOUR)]),
    ]
    for intakes, grid in forms:
        assert MODEL.effect_mmhg(PARAMS, intakes, grid) == expected
    assert MODEL.effect_mmhg(PARAMS, [0], range(0, 3 * HOUR, HOUR)) == (
        MODEL.effect_mmhg(PARAMS, [0], [0, HOUR, 2 * HOUR])
    )
    # a boundary instant: time 0 and the largest int64 are valid times
    assert MODEL.effect_mmhg(PARAMS, [0], [0]) == (0.0,)
    assert MODEL.effect_mmhg(PARAMS, [INT64_MAX], [INT64_MAX]) == (0.0,)
    assert MODEL.effect_mmhg(PARAMS, [0], [INT64_MAX]) == (0.0,)


@pytest.mark.parametrize("bad", [*BAD_NUMBERS, 0.0, -1.0, -1e-300, 0, -1, "a"])
def test_derive_rejects_bad_delta(bad: Any) -> None:
    with pytest.raises(PkpdModelError):
        derive_onset_window(PARAMS, bad)


BAD_WINDOWS: list[Any] = [
    None,
    5,
    "ab",
    (1,),
    (1, 2, 3),
    (2, 1),
    (1.5, 2),
    (1, 2.5),
    (True, 2),
    (None, 2),
    (-1, 5),
    (1, INT64_MAX + 1),
    (10**400, 10**400),
    [1, 2, 3],
    {1: 2},
    ("a", "b"),
]


@pytest.mark.parametrize("bad", BAD_WINDOWS)
def test_overlap_rejects_bad_windows(bad: Any) -> None:
    with pytest.raises(PkpdModelError):
        window_overlap(bad, 0, 10)


@pytest.mark.parametrize(
    "d1, d2",
    [
        (None, 5),
        (1, None),
        (1.5, 5),
        (1, 5.5),
        (True, 5),
        (-1, 5),
        (6, 5),
        (0, 10**400),
        (10**400, 10**400),
        (NAN, 5),
        ("1", 5),
        (INT64_MAX + 1, INT64_MAX + 1),
    ],
)
def test_overlap_rejects_bad_registry_window(d1: Any, d2: Any) -> None:
    with pytest.raises(PkpdModelError):
        window_overlap((1, 2), d1, d2)


@pytest.mark.parametrize(
    "bad_baseline",
    [None, 5, "ab", [], [[1.0]], [NAN], [INF], ["a"], [True], [None], [10**400]],
)
def test_compose_rejects_bad_baseline(bad_baseline: Any) -> None:
    with pytest.raises(PkpdModelError):
        compose_latent_sbp(bad_baseline, [1.0])


@pytest.mark.parametrize(
    "bad_effect",
    [
        None,
        5,
        "ab",
        [],
        [[1.0]],
        [NAN],
        [INF],
        [-INF],
        [-1.0],
        [-1e-300],
        ["a"],
        [True],
        [None],
        [10**400],
        [1.0, 2.0],
    ],
)
def test_compose_rejects_bad_effect(bad_effect: Any) -> None:
    with pytest.raises(PkpdModelError):
        compose_latent_sbp([130.0], bad_effect)


@pytest.mark.parametrize("empty", [[], (), range(0), np.array([])])
def test_compose_rejects_two_empty_vectors(empty: Any) -> None:
    # both empty: the size check must fire, not a raw reduction error on an empty array
    with pytest.raises(PkpdModelError):
        compose_latent_sbp(empty, empty)
    with pytest.raises(PkpdModelError):
        compose_latent_sbp([], [])


def test_effect_rejects_an_empty_grid_with_no_intakes() -> None:
    # no intake and no grid point: the (valid) empty intake list does not excuse the grid
    for empty_grid in ([], (), range(0), np.array([], dtype=np.int64)):
        with pytest.raises(PkpdModelError):
            MODEL.effect_mmhg(PARAMS, [], empty_grid)
        with pytest.raises(PkpdModelError):
            effect_concentration(PARAMS, [], empty_grid)
        with pytest.raises(PkpdModelError):
            MODEL.effect_mmhg(PARAMS, (), empty_grid, intake_scales=[])


def test_compose_arithmetic_and_read_only_result() -> None:
    out = compose_latent_sbp([130.0, 131.5, 129.0], [0.0, 1.5, 20.0])
    assert out.tolist() == [130.0, 130.0, 109.0]  # baseline - effect
    assert out.dtype == np.float64 and not out.flags.writeable
    again = compose_latent_sbp(np.array([130.0, 131.5, 129.0]), (0.0, 1.5, 20.0))
    assert again.tolist() == out.tolist()
    # a drug can push the pressure below zero: the composer does not clip (the validation
    # report decides what is physiological)
    assert compose_latent_sbp([5.0], [20.0]).tolist() == [-15.0]
    # the result does not alias the baseline
    base = np.array([130.0, 129.0])
    out2 = compose_latent_sbp(base, [0.0, 0.0])
    base[0] = 1.0
    assert out2[0] == 130.0


@pytest.mark.parametrize(
    "model",
    [None, 5, "m", object()],
)
def test_apply_rejects_bad_models(model: Any) -> None:
    with pytest.raises(PkpdModelError):
        apply_drug_response(model, PARAMS, _baseline(), [0])


@pytest.mark.parametrize("bad", [None, 5, "b", [1.0], np.zeros(3)])
def test_apply_rejects_bad_baseline(bad: Any) -> None:
    with pytest.raises(PkpdModelError):
        apply_drug_response(MODEL, PARAMS, bad, [0])


@pytest.mark.parametrize(
    "returned",
    [[1.0], [1.0] * 5, [NAN] * 4, [-1.0] * 4, [INF] * 4, None, 5, "abcd", [None] * 4],
)
def test_apply_rejects_a_misbehaving_engine(returned: Any) -> None:
    class Broken:
        def effect_mmhg(self, *args: Any, **kwargs: Any) -> Any:
            return returned

    with pytest.raises(PkpdModelError):
        apply_drug_response(Broken(), PARAMS, _baseline(), [0])  # type: ignore[arg-type]


def test_apply_passes_the_latent_grid_and_intakes_to_the_engine() -> None:
    stub = ConstantEffectModel(0.0)
    baseline = _baseline(3)
    out = apply_drug_response(stub, PARAMS, baseline, [5, 6])
    assert out.tolist() == [130.0] * 3
    assert stub.calls[0][1] == (5, 6) and stub.calls[0][2] == (0, 900_000, 1_800_000)
    assert stub.calls[0][3] is None


# ---------------------------------------------------------------------------
# Size bounds: nothing hangs, nothing exhausts memory
# ---------------------------------------------------------------------------


def test_size_constants_are_positive_ints() -> None:
    for value in (MAX_INTAKES, MAX_GRID_LEN, MAX_EVALUATIONS):
        assert isinstance(value, int) and value > 0
    assert MAX_EVALUATIONS >= MAX_GRID_LEN  # a whole day grid of one intake is allowed


def test_too_many_intakes_or_grid_points_are_refused_before_any_allocation() -> None:
    # ``range`` objects have a length without a memory cost, so nothing is built
    with pytest.raises(PkpdModelError):
        MODEL.effect_mmhg(PARAMS, range(MAX_INTAKES + 1), [0])
    with pytest.raises(PkpdModelError):
        MODEL.effect_mmhg(PARAMS, [0], range(MAX_GRID_LEN + 1))
    with pytest.raises(PkpdModelError):
        effect_concentration(PARAMS, range(MAX_INTAKES + 1), [0])
    with pytest.raises(PkpdModelError):
        effect_concentration(PARAMS, [0], range(MAX_GRID_LEN + 1))
    too_many = MAX_EVALUATIONS // MAX_GRID_LEN + 1
    with pytest.raises(PkpdModelError):
        MODEL.effect_mmhg(PARAMS, range(too_many), range(MAX_GRID_LEN))


def test_size_bounds_hold_exactly_at_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pkpd_module, "MAX_INTAKES", 3)
    monkeypatch.setattr(pkpd_module, "MAX_GRID_LEN", 4)
    monkeypatch.setattr(pkpd_module, "MAX_EVALUATIONS", 8)
    assert (
        len(MODEL.effect_mmhg(PARAMS, [0, 1, 2], [1, 2])) == 2
    )  # 3 intakes (limit), 6 evals
    assert (
        len(MODEL.effect_mmhg(PARAMS, [0, 1], [1, 2, 3, 4])) == 4
    )  # 4 points, 8 evals (limit)
    with pytest.raises(PkpdModelError):
        MODEL.effect_mmhg(PARAMS, [0, 1, 2, 3], [1])  # 4 intakes
    with pytest.raises(PkpdModelError):
        MODEL.effect_mmhg(PARAMS, [0], [1, 2, 3, 4, 5])  # 5 points
    with pytest.raises(PkpdModelError):
        MODEL.effect_mmhg(PARAMS, [0, 1, 2], [1, 2, 3])  # 9 evaluations


def test_a_realistic_week_is_fast_and_small() -> None:
    # 7 days at a 15 min grid with 3 intakes a day: 672 points, 21 intakes
    grid = np.arange(7 * 96, dtype=np.int64) * 900_000
    intakes = [d * 24 * HOUR + h * HOUR for d in range(7) for h in (8, 14, 20)]
    effect = MODEL.effect_mmhg(PARAMS, intakes, grid)
    assert len(effect) == 672 and all(0.0 <= e < EMAX * 3 for e in effect)
    # the effect before the first intake is zero
    assert effect[: 8 * 4] == (0.0,) * 32
