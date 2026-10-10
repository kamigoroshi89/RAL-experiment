"""Group 1 values (BLE link and cuff), blocks 1 and 2: seven rows entered as proposals (VAL-G1).

The rows are read from the committed configuration files. They are device quantities with a
source (block 1, literature-anchored, weak) and a BLE-link design choice (block 2), accepted by
gab on 2026-10-10 as PROPOSALS, not reviewed: ``verified_by`` stays null. The tests pin the
values, units, kinds, the constraints the loaders enforce and the set of rows that still wait.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ralmon.benchmark.__main__ import EXIT_PROVENANCE
from ralmon.benchmark.__main__ import main as benchmark_main
from ralmon.benchmark.measurement import T_DAY_MS
from ralmon.benchmark.priors import (
    LiteraturePriorSource,
    UnfilledParameterError,
    collect_parameter_files,
    load_design_file,
    load_prior_file,
)
from ralmon.spec.registry import load_registry

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ROOT / "configs"
PRIOR_FILE = CONFIGS / "priors" / "literature_hypertension.yaml"
DESIGN_FILE = CONFIGS / "benchmark" / "generator_design.yaml"
INJECTIONS_FILE = CONFIGS / "benchmark" / "injections.yaml"
REGISTRY_FILE = CONFIGS / "registry" / "hypertension.yaml"
STEP_MS = 60_000

BLOCK1 = {
    "inflation_ms_nominal": ("ms", 30000),
    "inflation_ms_sd": ("ms", 3000),
    "pulse_error_sd_bpm": ("bpm", 2.1),
}
BLOCK2_PRIOR = {"ble_dropout_rate_per_h": ("1/h", 0.0104)}
BLOCK2_DURATIONS = {
    "ble_dropout_duration_short": ("ms", 120000),
    "ble_dropout_duration_medium": ("ms", 900000),
    "ble_dropout_duration_long": ("ms", 3600000),
}

MARK_PROPOSAL = "proposal accepted by gab 2026-10-10, not reviewed"
MARK_SOURCE = "source opened by the research agent, not by gab"
MARK_DECISION = "gab, 2026-10-10, accepted as a proposal, not reviewed"

# Block 3 (ADR-070 (c)): bias magnitudes, multiples of cuff_error_sd_mmhg (8 mmHg in the prior file).
BIAS_LEVELS = {
    "cuff_silent_bias_magnitude_low": (
        1.0,
        8,
        "1.00 / 1.41 / 1.73",
        "0.26 / 0.45 / 0.60",
    ),
    "cuff_silent_bias_magnitude_medium": (
        1.5,
        12,
        "1.50 / 2.12 / 2.60",
        "0.40 / 0.66 / 0.79",
    ),
    "cuff_silent_bias_magnitude_high": (
        2.5,
        20,
        "2.50 / 3.54 / 4.33",
        "0.69 / 0.89 / 0.97",
    ),
}

# The 55 rows that still wait for a human value, by file.
AWAITING_PRIOR = ["mean_delay_ms"]
AWAITING_DESIGN = [
    "circadian_peak_clock_ms",
    "intake_lag_ms",
    "double_take_gap_ms",
    "robot_dwell_ms",
    "vitals_period_ms",
]
FILLED_NOW = 39
AWAITING_NOW = 55


def flat(text: str | None) -> str:
    assert text is not None
    return " ".join(text.split())


def prior_rows() -> dict[str, object]:
    return {r.parameter: r for r in load_prior_file(PRIOR_FILE).rows}


def design_rows() -> dict[str, object]:
    return {r.parameter: r for r in load_design_file(DESIGN_FILE).rows}


def injection_rows() -> dict[str, object]:
    return {r.parameter: r for r in load_design_file(INJECTIONS_FILE).rows}


def all_seven() -> list[tuple[str, object, str, float, str]]:
    out: list[tuple[str, object, str, float, str]] = []
    for name, (unit, value) in BLOCK1.items():
        out.append((name, design_rows()[name], unit, value, "published_literature"))
    for name, (unit, value) in BLOCK2_PRIOR.items():
        out.append((name, prior_rows()[name], unit, value, "design_choice"))
    for name, (unit, value) in BLOCK2_DURATIONS.items():
        out.append((name, injection_rows()[name], unit, value, "design_choice"))
    return out


@pytest.mark.parametrize(
    ("name", "row", "unit", "value", "source_type"),
    all_seven(),
    ids=lambda x: str(x)[:40],
)
def test_row_loads_as_filled_with_the_stated_value(
    name: str, row: object, unit: str, value: float, source_type: str
) -> None:
    assert row.status == "filled", name
    assert row.filled, name
    assert row.unit == unit, name
    assert row.value == value, name
    assert row.distribution is None, name
    assert row.source_type == source_type, name


@pytest.mark.parametrize(
    ("name", "row", "unit", "value", "source_type"),
    all_seven(),
    ids=lambda x: str(x)[:40],
)
def test_row_is_a_proposal_not_reviewed(
    name: str, row: object, unit: str, value: float, source_type: str
) -> None:
    assert row.verified_by is None, name
    rationale = flat(row.rationale)
    assert MARK_PROPOSAL in rationale, name
    assert row.source_ref and row.source_ref.strip(), name
    if source_type == "published_literature":
        assert MARK_SOURCE in rationale, name
        assert "doi:" in row.source_ref, name
    else:
        assert MARK_DECISION in flat(row.source_ref), name
        assert "design choice" in rationale.lower(), name


def test_integer_rows_are_integers() -> None:
    rows = design_rows()
    assert isinstance(rows["inflation_ms_nominal"].value, int)
    assert not isinstance(rows["inflation_ms_nominal"].value, bool)
    for name in BLOCK2_DURATIONS:
        value = injection_rows()[name].value
        assert isinstance(value, int) and not isinstance(value, bool), name
        assert 1 <= value <= T_DAY_MS, name
    # real-valued rows (the loader accepts an int literal such as 3000 for a float field)
    assert isinstance(rows["inflation_ms_sd"].value, int | float)
    assert isinstance(rows["pulse_error_sd_bpm"].value, float)
    assert isinstance(prior_rows()["ble_dropout_rate_per_h"].value, float)


def test_block1_constraints() -> None:
    rows = design_rows()
    registry = load_registry(REGISTRY_FILE, step_ms=STEP_MS)
    nominal = rows["inflation_ms_nominal"].value
    assert 0 <= nominal <= T_DAY_MS
    assert nominal >= registry.get("cuff_inflation_min").value
    assert nominal <= registry.get("bound_inflation_ms_upper").value
    assert rows["inflation_ms_sd"].value >= 0
    assert rows["pulse_error_sd_bpm"].value >= 0
    # the rationale of the cycle: in this generator 'inflation' is the arrival-to-reading cycle
    assert "arrival-to-reading cycle" in flat(rows["inflation_ms_nominal"].rationale)


def test_block1_sensitivities_are_in_the_rationale_only() -> None:
    rows = design_rows()
    assert "14000" in flat(rows["inflation_ms_sd"].rationale)
    assert "5.9" in flat(rows["pulse_error_sd_bpm"].rationale)
    assert "30 - 45 sec (on deflation)" in flat(rows["inflation_ms_nominal"].rationale)
    assert "zoll.com" in flat(rows["inflation_ms_nominal"].source_ref)


def test_ble_rate_is_a_design_choice_with_its_envelope() -> None:
    row = prior_rows()["ble_dropout_rate_per_h"]
    rationale = flat(row.rationale)
    assert row.value >= 0
    assert 0.25 / 24 == pytest.approx(row.value, abs=5e-5)
    assert "0.25 windows per device-day" in rationale
    assert "not a measurement" in rationale
    for number in ("0.0417", "0.167"):
        assert number in rationale
    assert (
        "Nunes" in flat(row.source_ref)
        and "10.1007/s11517-024-03155-3" in row.source_ref
    )


def test_ble_durations_are_ordered_and_tied_to_the_window() -> None:
    rows = injection_rows()
    short, medium, long_ = (
        rows[f"ble_dropout_duration_{level}"].value
        for level in ("short", "medium", "long")
    )
    assert short < medium < long_
    registry = load_registry(REGISTRY_FILE, step_ms=STEP_MS)
    window = int(registry.get("sched_window").value)
    assert window == 1_800_000
    assert medium * 2 == window
    assert long_ == 2 * window
    assert short % STEP_MS == 0 and short > 32_000
    for level in ("short", "medium", "long"):
        row = rows[f"ble_dropout_duration_{level}"]
        text = flat(row.rationale) + " " + flat(row.source_ref)
        assert "5.4" in text and "Breteler" in text, level
        assert "ADR-068" in text, level


def test_cuff_duration_rows_and_device_bias_stay_untouched() -> None:
    """The duration rows wait for WS04-T16 (unit change); the device_bias level is a definition."""
    rows = injection_rows()
    for family in ("stuck_at", "cuff_silent_bias", "cuff_detached"):
        for level in ("short", "medium", "long"):
            assert rows[f"{family}_duration_{level}"].status == "awaiting_human_value"
    assert rows["cuff_silent_bias_magnitude_device_bias"].value == 1.0
    assert rows["cuff_silent_bias_magnitude_device_bias"].unit == "x cuff_bias_mmhg"
    assert rows["cuff_silent_bias_magnitude_device_bias"].status == "filled"


def test_awaiting_rows_are_exactly_the_other_55() -> None:
    expected_injections = {
        name
        for name, row in injection_rows().items()
        if row.status == "awaiting_human_value"
    }
    assert len(expected_injections) == 49
    assert not (expected_injections & set(BLOCK2_DURATIONS))
    assert not (expected_injections & set(BIAS_LEVELS))
    files = {f.path.name: f for f in collect_parameter_files(ROOT)}
    awaiting = {
        name: [r.parameter for r in f.rows if r.status == "awaiting_human_value"]
        for name, f in files.items()
    }
    assert awaiting["literature_hypertension.yaml"] == AWAITING_PRIOR
    assert awaiting["generator_design.yaml"] == AWAITING_DESIGN
    assert awaiting["care_plans.yaml"] == []
    assert awaiting["default.yaml"] == []
    assert set(awaiting["injections.yaml"]) == expected_injections
    assert sum(len(v) for v in awaiting.values()) == AWAITING_NOW
    rows = [r for f in files.values() for r in f.rows]
    assert sum(1 for r in rows if r.status == "filled") == FILLED_NOW
    assert len(rows) == FILLED_NOW + AWAITING_NOW


def test_strict_prior_load_no_longer_names_the_ble_rate() -> None:
    with pytest.raises(UnfilledParameterError) as info:
        LiteraturePriorSource(PRIOR_FILE)
    message = str(info.value)
    assert "mean_delay_ms" in message
    assert "ble_dropout_rate_per_h" not in message
    source = LiteraturePriorSource(PRIOR_FILE, strict=False)
    assert source.unfilled_names() == ("mean_delay_ms",) or list(
        source.unfilled_names()
    ) == ["mean_delay_ms"]


def test_default_build_error_does_not_name_the_ble_rate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = benchmark_main(
        [
            "build",
            "--config",
            str(CONFIGS / "benchmark" / "default.yaml"),
            "--out",
            str(tmp_path / "out"),
            "--allow-fixture-only",
            "--git-rev",
            "test",
        ]
    )
    err = capsys.readouterr().err
    assert code == EXIT_PROVENANCE
    assert "mean_delay_ms" in err
    assert "ble_dropout_rate_per_h" not in err


STALE_NOTE_PHRASES = (
    "no value has been chosen by an agent",
    "no value chosen by an agent",
    "the human supplies the value",
    "agent-proposed grid point for confirmation",
)
NOTE_ACCEPTED = "proposal accepted by gab on 2026-10-10 and not reviewed"
NOTE_SOURCES = "sources opened by the research agent, not by gab"


@pytest.mark.parametrize(
    ("name", "row", "unit", "value", "source_type"),
    all_seven(),
    ids=lambda x: str(x)[:40],
)
def test_note_of_a_filled_row_is_true(
    name: str, row: object, unit: str, value: float, source_type: str
) -> None:
    note = flat(row.note)
    lowered = note.lower()
    for phrase in STALE_NOTE_PHRASES:
        assert phrase not in lowered, (name, phrase)
    assert NOTE_ACCEPTED in note, name
    if source_type == "published_literature":
        assert NOTE_SOURCES in note, name
    # the meaning part of the note survives
    assert len(note) > 120, name


def test_stale_sentence_stays_only_on_awaiting_rows_of_the_design_file() -> None:
    """The awaiting rows are unchanged: their note still says that no value has been chosen."""
    for name, row in design_rows().items():
        if name in AWAITING_DESIGN:
            assert row.status == "awaiting_human_value", name
            assert "chosen by an agent" in flat(row.note), name


def test_bias_magnitudes_load_as_filled_with_the_stated_values() -> None:
    rows = injection_rows()
    for name, (value, _mmhg, _z, _p) in BIAS_LEVELS.items():
        row = rows[name]
        assert row.status == "filled", name
        assert row.filled, name
        assert row.unit == "x cuff_error_sd_mmhg", name
        assert row.value == value, name
        assert row.distribution is None, name
        assert row.source_type == "design_choice", name


def test_bias_magnitudes_are_increasing_and_non_negative() -> None:
    rows = injection_rows()
    values = [
        rows[f"cuff_silent_bias_magnitude_{level}"].value
        for level in ("low", "medium", "high")
    ]
    assert values == [1.0, 1.5, 2.5]
    assert all(v >= 0 for v in values)
    assert values[0] < values[1] < values[2]


def test_bias_magnitudes_are_proposals_not_reviewed_with_their_arithmetic() -> None:
    rows = injection_rows()
    for name, (_value, mmhg, z_text, p_text) in BIAS_LEVELS.items():
        row = rows[name]
        assert row.verified_by is None, name
        rationale = flat(row.rationale)
        source_ref = flat(row.source_ref)
        assert MARK_PROPOSAL in rationale, name
        assert MARK_DECISION in source_ref, name
        assert "ADR-070 (c)" in source_ref, name
        for doi in (
            "10.1161/HYPERTENSIONAHA.117.10237",
            "10.3389/fcvm.2024.1388313",
            "10.5152/FNJN.2020.19119",
        ):
            assert doi in source_ref, (name, doi)
        assert f"{mmhg} mmHg" in rationale, name
        assert z_text in rationale, name
        assert p_text in rationale, name
        assert "cancels in the RESP drop" in rationale, name
        assert "not a requirement" in rationale, name
        note = flat(row.note)
        assert NOTE_ACCEPTED in note, name
        assert "chosen by an agent" not in note, name
        assert "agent chose" not in note.lower(), name


def test_bias_magnitudes_sub_threshold_by_construction() -> None:
    rows = injection_rows()
    low = flat(rows["cuff_silent_bias_magnitude_low"].rationale)
    medium = flat(rows["cuff_silent_bias_magnitude_medium"].rationale)
    high = flat(rows["cuff_silent_bias_magnitude_high"].rationale)
    assert "sub-threshold by construction for n = 1, 2, 3" in low
    assert "sub-threshold by construction for n = 1 only" in medium
    assert "sub-threshold by construction" not in high
    assert "none of its cells is sub-threshold" in high
