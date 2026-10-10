"""Tests for the minors of the independent review of WS08-T01 (items 1 to 15 of the coordinator's message).

ILLUSTRATIVE, UNVERIFIED, FIXTURE-ONLY. Expected values are derived by hand in the comments.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from ralmon.eval import MatchConfig, match_events
from ralmon.eval import runner as runner_module
from ralmon.eval.metrics import (
    COLUMNS,
    BootstrapError,
    bin_index,
    bootstrap_ci,
    bootstrap_weights,
    ci_from_weights,
    ci_with_report,
    min_bootstrap_resamples,
    reliability_bins,
    table_prf,
)
from ralmon.eval.ours import PipelineComponents
from ralmon.eval.runner import (
    GUARD_DECISIONS,
    MAX_HISTORY_DAYS,
    ConfigError,
    HookResult,
    RunFacts,
    RunOptions,
    adr_statuses,
    evaluate_guards,
    load_experiment,
    required_tail_ms,
    run_experiment,
)
from ralmon.monitor import VerdictState, run_offline
from tests.eval.helpers import (
    C1,
    C2,
    MINI,
    SMOKE,
    UND,
    T,
    alert,
    det,
    gt,
    ms,
    smoke_document,
    write_config,
)
from tests.eval.test_runner import (
    SCRIPT,
    factory_for,
    facts,
    hand_document,
    ids,
    options,
    read_metrics,
    run_doc,
)

REPO = Path(__file__).resolve().parents[2]


# ---- (1) matching in the order of the reference instant ---------------------------------------------------------------


def test_matching_takes_the_events_in_the_order_of_their_reference_instant() -> None:
    # g1: onset 0, end 2000 (reference 2000); g2: onset 1000, end 1500 (reference 1500); detections at 1000 and 2800,
    # tolerance 1000. In reference order g2 (window [500, 2500]) takes 1000 and g1 (window [1000, 3000]) takes 2800:
    # two pairs. In onset order g1 would take 1000 and g2 would find nothing: one pair.
    events = [gt("C1", 0, 2000, template="resp"), gt("C1", 1000, 1500, template="resp")]
    m = match_events(
        events,
        [det(1000, C1), det(2800, C1)],
        MatchConfig(1000, "first_decidable"),
    )
    assert len(m.pairs) == 2 and m.missed == ()
    assert sorted((p.gt.onset_ms, p.det.t_ms) for p in m.pairs) == [
        (0, 2800),
        (1000, 1000),
    ]


def test_the_tolerance_window_is_closed_at_both_ends() -> None:
    cfg = MatchConfig(1_000, "onset")
    late_edge = match_events([gt("C1", 10_000)], [det(11_000, C1)], cfg)
    assert [p.delay_ms for p in late_edge.pairs] == [1_000.0]
    beyond = match_events([gt("C1", 10_000)], [det(11_001, C1)], cfg)
    assert beyond.pairs == () and len(beyond.false_alarms) == 1
    early_edge = match_events([gt("C1", 10_000)], [det(9_000, C1)], cfg)
    assert [p.delay_ms for p in early_edge.pairs] == [-1_000.0]
    assert match_events([gt("C1", 10_000)], [det(8_999, C1)], cfg).pairs == ()


# ---- (2) the bootstrap: a minimum, degenerate samples, NaN replicates reported ---------------------------------------


def test_the_bootstrap_needs_a_minimum_number_of_resamples() -> None:
    # each tail of the percentile interval must hold at least one replicate: 2 / (1 - level), 40 at level 0.95
    assert min_bootstrap_resamples(0.95) == 40
    assert min_bootstrap_resamples(0.9) == 20
    with pytest.raises(BootstrapError):
        bootstrap_ci([0.0, 1.0], n_resamples=39, level=0.95, seed=0)
    assert bootstrap_ci([0.0, 1.0], n_resamples=40, level=0.95, seed=0) is not None
    assert issubclass(BootstrapError, ValueError)


def test_a_degenerate_sample_has_no_interval() -> None:
    lo, hi = bootstrap_ci([0.5], n_resamples=100, level=0.95, seed=0)
    assert math.isnan(lo) and math.isnan(hi)
    lo, hi = bootstrap_ci(
        [0.1, 0.9, 0.5], n_resamples=100, level=0.95, seed=0, clusters=[7, 7, 7]
    )
    assert math.isnan(lo) and math.isnan(
        hi
    )  # one cluster: the cluster bootstrap has nothing to resample


def test_nan_replicates_are_counted() -> None:
    # unit 0 has a ratio 1 / 1, unit 1 has 0 / 0: a replicate that holds only unit 1 has an undefined ratio
    table = np.array([[1.0, 1.0], [0.0, 0.0]])
    weights = bootstrap_weights(2, 200, 3)

    def ratio(row: np.ndarray) -> float:
        return float(row[0] / row[1]) if row[1] > 0 else math.nan

    lo, hi, n_nan = ci_with_report(table, ratio, weights, 0.95)
    assert n_nan == int((weights[:, 0] == 0).sum()) > 0
    assert (lo, hi) == ci_from_weights(table, ratio, weights, 0.95)
    assert lo == hi == 1.0  # the defined replicates are all 1.0


def test_n_bootstrap_below_the_minimum_is_a_config_error(tmp_path: Path) -> None:
    doc = smoke_document()
    doc["run_options"]["n_bootstrap"] = 39
    with pytest.raises(ConfigError, match="n_bootstrap"):
        load_experiment(write_config(tmp_path / "c.yaml", doc))
    doc["run_options"]["n_bootstrap"] = 40
    load_experiment(write_config(tmp_path / "c.yaml", doc))


def test_the_run_reports_its_replicates_and_the_degenerate_cluster_sample(
    tmp_path: Path,
) -> None:
    doc = hand_document()
    doc["split"] = {
        "train": 0.5,
        "calibration": 0.33,
        "test": 0.17,
    }  # 6 patients: 3, 2, 1
    m = read_metrics(run_doc(tmp_path, doc, factory_for({}))[0])
    b = m["analysis"]["run"]["bootstrap"]
    assert b["n_replicates"] == 100 and b["n_units"] == 2 and b["n_clusters"] == 1
    assert b["degenerate_clusters"] is True
    leaf = m["false_alarms_per_patient_day"]["ours-s1"]
    assert (
        leaf["ci_cluster_lo"] is None and leaf["ci_cluster_hi"] is None
    )  # one patient: no cluster interval
    assert "nan_replicates" in b


# ---- (3) the bin of rho is exact on decimal literals ------------------------------------------------------------------


def test_rho_at_a_decimal_edge_falls_in_the_bin_that_starts_there() -> None:
    assert (
        0.29 * 100 < 29 and 0.57 * 100 < 57
    )  # the floating-point product is below the edge
    assert bin_index(0.29, 100) == 29 and bin_index(0.57, 100) == 57
    assert reliability_bins([0.29], [True], 100)[29].n == 1
    assert reliability_bins([0.57], [False], 100)[57].n == 1
    assert bin_index(1.0, 100) == 99 and bin_index(0.0, 100) == 0


@pytest.mark.parametrize("bins", [5, 10, 20, 100])
def test_every_decimal_edge_is_in_the_bin_it_opens(bins: int) -> None:
    for k in range(bins + 1):
        edge = float(f"{k / bins:.12g}")
        assert bin_index(edge, bins) == min(k, bins - 1)


def test_the_runner_bins_rho_with_the_same_rule() -> None:
    table = runner_module._ece_table([[(0.29, True)]], 100)
    assert table[0, 3 * 29] == 1 and table[0].sum() == pytest.approx(2.29)


# ---- (4) mutants: the cluster wiring and the unresolved count ----------------------------------------------------------


def test_the_cluster_interval_is_a_bootstrap_over_patients(tmp_path: Path) -> None:
    captured: list[Any] = []

    def hook(ctx: Any) -> HookResult:
        captured.append(ctx)
        return HookResult()

    module = types.ModuleType("ralmon.eval.analysis")
    module.hooks_for = lambda experiment_id: [hook]  # type: ignore[attr-defined]
    sys.modules["ralmon.eval.analysis"] = module
    try:
        m = read_metrics(run_doc(tmp_path, hand_document(), factory_for(SCRIPT))[0])
    finally:
        del sys.modules["ralmon.eval.analysis"]
    ctx = captured[0]
    table = ctx.tables["ours-s1"]
    patients = [p for p, _ in ctx.units]

    def stat(row: np.ndarray) -> float:
        return table_prf(row)["any"]["recall"]

    leaf = m["per_class_prf"]["ours-s1"]["any"]["recall"]
    by_patient = ci_from_weights(
        table, stat, bootstrap_weights(len(patients), 100, 0, clusters=patients), 0.95
    )
    by_day = ci_from_weights(
        table, stat, bootstrap_weights(len(patients), 100, 0), 0.95
    )
    assert (leaf["ci_cluster_lo"], leaf["ci_cluster_hi"]) == pytest.approx(by_patient)
    assert (leaf["ci_lo"], leaf["ci_hi"]) == pytest.approx(by_day)
    assert (
        by_patient != by_day
    )  # the two intervals are not the same object on this case


def test_a_pair_matched_by_an_unresolved_predicted_alert_is_counted(
    tmp_path: Path,
) -> None:
    from ralmon.eval.metrics import MatchConfig as MC

    predicted = alert(ms(14), UND, key="u", verdict=VerdictState.PREDICTED_VIOLATION)
    m = match_events([gt("C1", ms(14))], [predicted], MC(60_000, "onset"))
    assert m.table().sum(axis=0)[COLUMNS.index("unresolved")] == 1
    script = {
        ("p01", 0): [predicted]
    }  # matches the 14:00 range event of p01 and nothing supersedes it
    out = read_metrics(run_doc(tmp_path, hand_document(), factory_for(script))[0])
    block = out["attribution_confusion"]["ours-s1"]
    assert block["n_unresolved"] == 1
    assert sum(sum(row.values()) for row in block["matrix"].values()) == 0


# ---- (5), (6) metadata ------------------------------------------------------------------------------------------------


def test_the_metadata_says_which_interval_is_the_headline_one_and_what_the_band_is(
    tmp_path: Path,
) -> None:
    m = read_metrics(run_doc(tmp_path, hand_document(), factory_for(SCRIPT))[0])
    b = m["meta"]["bootstrap"]
    assert b["headline_interval"] == "cluster"
    assert "reference only" in b["day_level_interval"]
    note = m["meta"]["interval_width_note"]
    assert "1 - 2" in note and "not the nominal" in note


# ---- (7) the artefact of the shared step ------------------------------------------------------------------------------


def test_detections_at_a_shared_step_are_counted_and_repeats_are_visible(
    tmp_path: Path,
) -> None:
    # the run of day 0 emits at its closing step T and the run of day 1 emits the same thing at its first step T
    script = {
        ("p06", 0): [det(T, C1), det(ms(5), C1)],
        ("p06", 1): [det(T, C1), det(T + ms(5), C2), det(2 * T, C1)],
    }
    m = read_metrics(run_doc(tmp_path, hand_document(), factory_for(script))[0])
    shared = m["analysis"]["run"]["shared_step_detections"]["ours-s1"]
    # at a shared step: T (twice) and 2T (the final closing step); one of the two at T repeats the other
    assert shared == {"n_at_shared_step": 3, "n_repeating_previous_day": 1}


def test_a_repeat_of_an_alert_is_an_alert_of_the_same_instance_at_the_same_instant(
    tmp_path: Path,
) -> None:
    script = {
        ("p06", 0): [alert(T, C1, key="count-day-end@86400000")],
        ("p06", 1): [
            alert(T, C1, key="count-day-end@86400000"),
            alert(T, C1, key="other"),
        ],
    }
    m = read_metrics(run_doc(tmp_path, hand_document(), factory_for(script))[0])
    shared = m["analysis"]["run"]["shared_step_detections"]["ours-s1"]
    assert shared == {"n_at_shared_step": 3, "n_repeating_previous_day": 1}


# ---- (8) an unknown INT gate -------------------------------------------------------------------------------------------


def test_a_verdict_runner_without_counters_leaves_the_int_gate_unknown() -> None:
    from ralmon.spec import load_registry, load_templates
    from tests.eval.helpers import REGISTRY
    from tests.eval.test_ours import (
        device_profile,
        make_ours,
        out_of_band_day,
        range_plan,
    )

    registry = load_registry(REGISTRY, step_ms=60_000, allow_fixture_only=True)
    templates = load_templates(registry=registry)
    components = PipelineComponents(
        use_forecaster=False, verdict_runner=lambda *a, **k: run_offline(*a, **k)
    )
    ours = make_ours(registry, templates, components=components)
    ours.fit([], [])
    ours.run(out_of_band_day(), range_plan(registry), None)
    assert ours.last_run is not None
    assert ours.last_run.presence_samples_without_availability_marks is None
    assert device_profile() is not None


def test_an_unknown_int_gate_is_a_hard_failure_of_a_headline_run_and_a_flag_otherwise() -> (
    None
):
    hard = evaluate_guards(facts(int_gate_unknown=("ours-A7",)), options(headline=True))
    assert "INT_GATE_UNKNOWN" in ids(hard.hard)
    soft = evaluate_guards(
        facts(int_gate_unknown=("ours-A7",)), options(headline=False)
    )
    assert soft.hard == () and "INT_GATE_UNKNOWN" in ids(soft.flags)


def test_a_run_of_a_variant_without_counters_flags_the_gate_as_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = types.ModuleType("stub")
    module.variant_components = lambda name: (  # type: ignore[attr-defined]
        PipelineComponents(verdict_runner=lambda *a, **k: run_offline(*a, **k))
        if name == "ours-A7"
        else None
    )
    monkeypatch.setitem(sys.modules, "ralmon.eval.ablations", module)
    doc = smoke_document()
    doc["detectors"] = ["ours-A7"]
    m = read_metrics(run_doc(tmp_path, doc, None)[0])
    flags = {f["id"] for f in m["meta"]["guards"]["flags"]}
    assert "INT_GATE_UNKNOWN" in flags
    assert m["meta"]["guards"]["facts"]["int_gate_unknown"] == ["ours-A7"]


# ---- (9) accepted decisions are checked against the decisions file -----------------------------------------------------


def test_the_statuses_are_read_from_the_decisions_file() -> None:
    statuses = adr_statuses()
    assert statuses["ADR-066"].startswith("accepted")
    assert statuses["ADR-061"].startswith("proposed")
    assert statuses["ADR-042"].startswith("accepted")
    assert set(GUARD_DECISIONS) >= {"ADR063_INT_SYS_COMPARISON", "HISTORY_ASYMMETRY"}


def test_the_guard_to_decision_table_is_explicit() -> None:
    assert GUARD_DECISIONS["ADR063_INT_SYS_COMPARISON"] == "ADR-063"
    assert GUARD_DECISIONS["HISTORY_ASYMMETRY"] == "ADR-061"
    # the decisions D2, F19 and F20 have no ADR yet: their flags cannot be lifted
    for guard in (
        "B5_NOT_PAPER_COMPARISON",
        "CONTAMINATION_POLICY_OPEN",
        "LATENCY_CONVENTION_OPEN",
    ):
        assert GUARD_DECISIONS[guard] is None


def test_a_proposed_adr_does_not_lift_a_guard() -> None:
    # ADR-063 and ADR-061 are proposed [DA-CONFERMARE] in docs/plan/03-decisions.md
    with pytest.raises(
        ConfigError, match="record the decision as an accepted ADR first"
    ):
        evaluate_guards(
            facts(detectors=("B3", "ours")), options(accepted_decisions=("ADR-063",))
        )


@pytest.mark.parametrize(
    "name", ["ADR-63", "ADR-9999", "adr-063", "D2", "F19", "F20", ""]
)
def test_an_unknown_or_malformed_decision_name_is_refused(name: str) -> None:
    with pytest.raises(
        ConfigError, match="record the decision as an accepted ADR first"
    ):
        evaluate_guards(facts(), options(accepted_decisions=(name,)))


def test_the_loader_refuses_such_names_at_load_time(tmp_path: Path) -> None:
    doc = smoke_document()
    doc["run_options"]["accepted_decisions"] = ["D2"]
    with pytest.raises(ConfigError, match="accepted ADR"):
        load_experiment(write_config(tmp_path / "c.yaml", doc))
    doc["run_options"]["accepted_decisions"] = [
        "ADR-066"
    ]  # accepted, and in no guard: recorded, lifts nothing
    config, opts = load_experiment(write_config(tmp_path / "c.yaml", doc))
    assert opts.accepted_decisions == ("ADR-066",)


def test_a_missing_decisions_file_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="03-decisions.md"):
        adr_statuses(tmp_path / "nope.md")


def test_the_status_is_taken_from_the_status_line_of_the_section(
    tmp_path: Path,
) -> None:
    f = tmp_path / "d.md"
    f.write_text(
        "## ADR-001 a\n\n- **Status.** accepted (x)\n\n## ADR-002 b\n\n- **Status.** partly accepted (x)\n\n"
        "## ADR-003 c\n\ntext without a status\n",
        encoding="utf-8",
    )
    assert adr_statuses(f) == {
        "ADR-001": "accepted (x)",
        "ADR-002": "partly accepted (x)",
        "ADR-003": "",
    }


# ---- (10) the tail of the baselines ------------------------------------------------------------------------------------


def test_the_required_tail_follows_the_audit_conclusion() -> None:
    day_end = 90_000_000  # the 25 h of the audit configuration: the day and one hour
    assert (
        required_tail_ms(10_800_000, 120_000) == day_end
    )  # delta2 + D is shorter than that
    assert required_tail_ms(100_000_000, 120_000) == 100_120_000


def test_a_short_tail_is_a_hard_failure_of_a_headline_run_and_a_flag_otherwise() -> (
    None
):
    kw = {"timing_tail_ms": 0}
    hard = evaluate_guards(facts(**kw), options(headline=True))
    assert "TIMING_TAIL_TOO_SHORT" in ids(hard.hard)
    soft = evaluate_guards(facts(**kw), options(headline=False))
    assert soft.hard == () and "TIMING_TAIL_TOO_SHORT" in ids(soft.flags)
    assert "TIMING_TAIL_TOO_SHORT" not in ids(evaluate_guards(facts(), options()).hard)


def test_a_run_with_tail_zero_is_flagged(tmp_path: Path) -> None:
    doc = smoke_document()
    doc["run_options"]["detector_params"]["timing_tail_ms"] = 0
    m = read_metrics(run_doc(tmp_path, doc, None)[0])
    assert "TIMING_TAIL_TOO_SHORT" in {f["id"] for f in m["meta"]["guards"]["flags"]}
    assert m["meta"]["guards"]["facts"]["required_tail_ms"] == 90_000_000


# ---- (11) the resolution of the calibration set ------------------------------------------------------------------------


def test_an_alpha_below_the_calibration_resolution_is_a_guard() -> None:
    kw = {
        "min_alpha": 0.01,
        "calibration_episodes": {"ours": 4},
    }  # 1 / (4 + 1) = 0.2 > 0.01
    hard = evaluate_guards(facts(**kw), options(headline=True))
    assert "ALPHA_BELOW_CALIBRATION_RESOLUTION" in ids(hard.hard)
    soft = evaluate_guards(facts(**kw), options(headline=False))
    assert soft.hard == () and "ALPHA_BELOW_CALIBRATION_RESOLUTION" in ids(soft.flags)
    ok = {
        "min_alpha": 0.2,
        "calibration_episodes": {"ours": 4},
    }  # alpha = 1 / (n + 1) is the smallest level
    assert "ALPHA_BELOW_CALIBRATION_RESOLUTION" not in ids(
        evaluate_guards(facts(**ok), options()).hard
    )


def test_the_run_flags_a_vacuous_alpha(tmp_path: Path) -> None:
    doc = smoke_document()
    doc["detectors"] = ["ours"]
    doc["alpha"] = 0.01
    doc["monitor"]["alpha"] = 0.01
    doc["run_options"]["alpha_grid"] = [0.01]
    m = read_metrics(run_doc(tmp_path, doc, None)[0])
    assert "ALPHA_BELOW_CALIBRATION_RESOLUTION" in {
        f["id"] for f in m["meta"]["guards"]["flags"]
    }


# ---- (12) the device profile --------------------------------------------------------------------------------------------


def test_no_device_profile_is_a_guard_when_the_proposed_method_runs() -> None:
    hard = evaluate_guards(facts(has_device_profile=False), options(headline=True))
    assert "NO_DEVICE_PROFILE" in ids(hard.hard)
    soft = evaluate_guards(facts(has_device_profile=False), options(headline=False))
    assert soft.hard == () and "NO_DEVICE_PROFILE" in ids(soft.flags)
    no_ours = evaluate_guards(
        facts(detectors=("B1",), has_device_profile=False), options(headline=True)
    )
    assert "NO_DEVICE_PROFILE" not in ids(no_ours.hard) | ids(no_ours.flags)


def test_the_smoke_run_flags_the_missing_profile_and_a_configured_one_lifts_it(
    tmp_path: Path,
) -> None:
    m = read_metrics(run_doc(tmp_path, smoke_document(), None)[0])
    assert "NO_DEVICE_PROFILE" in {f["id"] for f in m["meta"]["guards"]["flags"]}
    doc = smoke_document()
    doc["run_options"]["detector_params"]["ours"] = {
        "device_profile": {"cuff": {"seq": True}}
    }
    m = read_metrics(run_doc(tmp_path, doc, None, out="b")[0])
    assert "NO_DEVICE_PROFILE" not in {f["id"] for f in m["meta"]["guards"]["flags"]}


# ---- (13) no absolute path in an output ---------------------------------------------------------------------------------


def test_config_yaml_and_metrics_hold_no_absolute_path(tmp_path: Path) -> None:
    config, opts = load_experiment(SMOKE)
    d = run_experiment(config, opts, tmp_path / "o", git_rev=lambda: "r")[0]
    text = (d / "config.yaml").read_text(encoding="utf-8")
    recorded = yaml.safe_load(text)
    assert recorded["benchmark_manifest"] == "tests/fixtures/eval/mini_benchmark"
    assert recorded["run_options"]["registry"] == "tests/fixtures/eval/registry.yaml"
    for output in (text, (d / "metrics.json").read_text(encoding="utf-8")):
        assert (
            str(REPO) not in output
            and "/home" not in output
            and str(tmp_path) not in output
        )
    again, again_opts = load_experiment(
        d / "config.yaml"
    )  # the copy loads again, to the same objects
    assert (again.benchmark_manifest, again_opts.registry) == (
        config.benchmark_manifest,
        opts.registry,
    )


def test_a_benchmark_outside_the_repository_is_recorded_relative_to_the_seed_directory(
    tmp_path: Path,
) -> None:
    bench = tmp_path / "bench"
    shutil.copytree(MINI, bench)
    doc = hand_document()
    doc["benchmark_manifest"] = str(bench)
    d = run_doc(tmp_path, doc, factory_for(SCRIPT))[0]
    recorded = yaml.safe_load((d / "config.yaml").read_text(encoding="utf-8"))
    assert not os.path.isabs(recorded["benchmark_manifest"])
    assert (d / recorded["benchmark_manifest"]).resolve() == bench.resolve()
    assert load_experiment(d / "config.yaml")[0].benchmark_manifest == str(
        bench.resolve()
    )


# ---- (14) the history bound ---------------------------------------------------------------------------------------------


def test_the_history_bound_is_the_one_of_the_monitor() -> None:
    from ralmon.monitor.offline import MAX_HISTORY_DAYS as MONITOR_BOUND

    assert MAX_HISTORY_DAYS == MONITOR_BOUND


# ---- the cases above must not have changed the earlier conventions --------------------------------------------------------


def test_the_json_of_a_run_is_still_canonical(tmp_path: Path) -> None:
    d = run_doc(tmp_path, hand_document(), factory_for(SCRIPT))[0]
    text = (d / "metrics.json").read_text(encoding="utf-8")
    assert (
        text
        == json.dumps(json.loads(text), sort_keys=True, indent=2, ensure_ascii=False)
        + "\n"
    )


_unused: tuple[Callable[..., Any], ...] = (RunFacts, RunOptions, C2)
