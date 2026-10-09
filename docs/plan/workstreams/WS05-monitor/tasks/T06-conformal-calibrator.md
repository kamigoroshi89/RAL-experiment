---
id: WS05-T06
title: "Split and adaptive conformal calibrator, rho, alpha allocation, recalibration rule"
workstream: WS05-monitor
owner: agent
status: ready
depends_on: ["WS05-T04", "WS01-T06"]
critical_path: true
non_negotiable: false
estimate_pd: 3
sources: ["analisi §4.4", "analisi §5.6 (A1, A6)"]
interfaces: ["02-interfaces.md#conformal-calibrator"]
review_items: ["R2-W3", "R2-W4", "R2-W6"]
---
## Obiettivo

Implement the conformal calibrator of `#conformal-calibrator` in `ralmon.conformal`: `SplitConformal` and `AdaptiveConformal` (adaptive conformal inference after the work cited in analisi §3.2) with a one-sided nonconformity score `R = sigma_true - sigma_hat`, the finite-sample quantile, `PredictedViolation` with `rho = 1 - alpha_star` (a conformal p-value), an alpha allocation per patient-day, and the recalibration rule (a calibrator is tied to the model version it was calibrated for). The calibration unit is the patient episode, never the time step, and the coverage statement is marginal over the population under exchangeability, stated wherever coverage is reported. It closes R2-W3 (rho undefined), R2-W4 (unit of exchangeability, repeated tests) and R2-W6 (recalibration after a model update).

## Contesto

Blocked until WS05-T04 and WS01-T06 are `done`.

- `docs/formal/06-rho-proposition1.md` (rho per verdict type, Proposition 1 with proof and caveats, the definition and quantile of the "possible" variant, disposition of CP4; conformal golden cases).
- `02-interfaces.md#conformal-calibrator` (protocols, rules 1 to 4; `Rho` and `RhoKind` are imported from `ralmon.spec`).
- `docs/source/analisi.md` §4.4 (score, one-sided quantile, alpha star, likely and possible, three caveats).
- `docs/source/review.md` (R2 weaknesses 3, 4 and 6).
- `docs/plan/workstreams/WS05-monitor/README.md` (design decisions D6 and D10: one predictive test per pending instance, model version tokens).

## File toccati

- `src/ralmon/conformal/` (modify: real modules `scores.py`, `split.py`, `adaptive.py`, `allocation.py`; placeholders removed from `_stubs.py`)
- `tests/conformal/` (create: `test_split.py`, `test_predict.py`, `test_coverage.py`, `test_adaptive.py`, `test_allocation.py`)
- `tests/fixtures/conformal/` (create: copies of the golden cases used from `conformal.yaml`, with `id` and `source`)
- `docs/plan/03-decisions.md` (modify: append one ADR, status `proposed`, confirmation tag)
- `docs/plan/02-interfaces.md` (modify: `#conformal-calibrator` additions and version bump)

## Test

Write first; each fails before the implementation. Hand-computed fixture: calibration scores `R = [-0.2, -0.1, 0.0, 0.1, 0.1, 0.2, 0.3, 0.4, 0.6]` (n = 9), built as episodes with `sigma_hat = 0.0` and `sigma_true = R`. With `n = 9` the quantile of level `alpha` is the `k`-th smallest score, `k = ceil((n + 1) * (1 - alpha))`, and it is `+inf` when `k > n`. All values are fixture-only.

Split conformal and prediction (`test_split.py`, `test_predict.py`)

1. `test_score_is_one_sided_true_minus_hat`: `sigma_hat = 0.5`, `sigma_true = 0.3` gives `R = -0.2` (not the absolute value).
2. `test_split_quantile_finite_sample_rank`: on the fixture, `quantile(0.5) == 0.1` (k = 5), `quantile(0.3) == 0.3` (k = 7; `10 * (1 - 0.3)` is a float-boundary case, the ceiling must not give 8), `quantile(0.2) == 0.4` (k = 8), `quantile(0.1) == 0.6` (k = 9), `quantile(0.05) == math.inf` (k = 10 > n).
3. `test_infinite_quantile_never_emits`: with `alpha = 0.05` on the fixture, `predict(-10.0, 0.05)` has `emitted is False` and `rho is None` (too few episodes for that level; reported, not hidden).
4. `test_predict_emits_when_sigma_hat_plus_q_is_negative`: at `alpha = 0.2` (q = 0.4), `sigma_hat = -0.5` is emitted (`-0.5 + 0.4 < 0`) and `sigma_hat = -0.4` is not (`-0.4 + 0.4 = 0.0`, strict inequality).
5. `test_alpha_star_is_the_conformal_p_value`: `sigma_hat = -0.5` at `alpha = 0.2` gives `rho.value == pytest.approx(0.8)` (alpha star 0.2: one score, 0.6, is at least 0.5, so `(1 + 1) / 10`); `sigma_hat = -0.2` at `alpha = 0.5` gives `0.5` (four scores at least 0.2: `(4 + 1) / 10`); `sigma_hat = -0.4` at `alpha = 0.3` gives `0.7` (two scores at least 0.4: `(2 + 1) / 10`).
6. `test_emission_iff_alpha_at_least_alpha_star` (Hypothesis): for random scores and `sigma_hat`, with `alpha_star = (m + 1) / (n + 1)` and `m` the number of scores with `sigma_hat + r >= 0`, emission at level `alpha` holds exactly when `alpha >= alpha_star` (this is `alpha_star = inf{alpha : sigma_hat + q_{1-alpha} < 0}` of the contract).
7. `test_rho_declares_kind_guarantee_and_assumptions`: `rho.kind == RhoKind.PREDICTED`, `rho.alpha` is the level used, `guarantee` contains the words `marginal` and `exchangeab`, `assumptions` names the patient episode as calibration unit (rule 1) and the exchangeability of calibration and test episodes; the class docstring says the calibrator pools all episodes it is given, so coverage is marginal over the population and over the template mix (rule 2).
8. `test_variant_possible_follows_ws01_t06`: every case of `docs/formal/golden/conformal.yaml` for the "possible" variant gives its expected `emitted` and `rho`; the literal reading of analisi §4.4 (`sigma_hat = 0.3`, `alpha = 0.2`, `0.3 - 0.4 < 0` emitted for "possible", not for "likely") is kept only if WS01-T06 keeps that definition; if it defines a lower-tail quantile, the calibrator gains `quantile_lower` per its text and the ADR says so.
9. `test_golden_conformal_cases[<id>]`: all other cases of `conformal.yaml` (quantile, alpha star, coverage bound) reproduce.
10. `test_alpha_and_episode_validation`: `quantile(0.0)`, `quantile(1.0)`, `quantile(-0.1)` raise `ValueError`; `fit([], 0.2)` raises `ValueError`.
11. `test_split_update_is_a_noop`: `quantile` and `predict` are identical before and after `update`.

Coverage (`test_coverage.py`)

12. `test_exhaustive_rank_coverage_bound` (exact, `fractions.Fraction`, no float): for `n` in 1 to 30 and `alpha = j / 20` for `j` in 1 to 19, the calibrator fitted on episodes with `sigma_hat = 0.0` and `sigma_true = 1.0 .. n` returns `quantile(alpha)` equal to the exact `k`-th score or `inf`; and the probability that a new exchangeable score exceeds it, `(n + 1 - k) / (n + 1)` (0 if `k > n`), is at most `alpha` (Proposition 1 of `#conformal-calibrator` rule 3: `P(alert emitted and sigma >= 0) <= alpha`).
13. `test_monte_carlo_upper_bound_miscoverage_matches_nominal`: `rng = default_rng(0)`; 500 independent calibration sets of `n = 99` scores drawn iid standard normal and 500 fresh scores each; the mean over sets of the rate of `R_new > q(alpha)` equals `(n + 1 - k) / (n + 1)` (0.05, 0.1, 0.2 for the three levels) within 4 standard errors, where the standard error is the sample standard deviation of the 500 per-set rates divided by `sqrt(500)` (the per-set rates vary with the calibration set, so the naive binomial error would be too small); the tolerance rule is fixed before the run and never widened to pass.
14. `test_monte_carlo_alert_and_nonviolation_rate_at_most_alpha`: with `sigma_hat` drawn iid uniform on `(-2, 0)` independent of `R`, the mean over sets of the rate of `alert emitted and sigma_hat + R >= 0` is at most `alpha` plus 4 standard errors (same error rule), for the same three levels.

Adaptive (`test_adaptive.py`)

15. `test_adaptive_alpha_recursion_hand_values`: `AdaptiveConformal(gamma=0.1)` (mode `adaptive`) fitted on the fixture at nominal 0.2 starts with `alpha_t == 0.2`; on a fresh instance, an episode with `sigma_hat = 0.0`, `sigma_true = 0.9` (`R = 0.9` above the quantile 0.4, a miss) gives `alpha_t == pytest.approx(0.12)` (`0.2 + 0.1 * (0.2 - 1)`); on another fresh instance, an episode with `sigma_true = 0.0` (covered) gives `0.22` (`0.2 + 0.1 * 0.2`). The recursion is that of the cited work, marked `[ref-needed: WS03]` in the docstring for the human check.
16. `test_adaptive_gamma_is_explicit`: constructing without `gamma` raises `TypeError` (no default step size is invented; WS08-T05 chooses it).
17. `test_adaptive_update_extends_the_score_set`: after one `update`, the number of scores is 10 and later quantiles use it.
18. `test_adaptive_infinite_conventions`: `alpha_t <= 0` gives `quantile == +inf` (no alert) and `alpha_t >= 1` gives `-inf`; `alpha_t` itself is stored unclipped.
19. `test_adaptive_recovers_coverage_under_shift` (A6 hypothesis): `default_rng(0)`; 2000 episodes with `R` standard normal for the first 1000 and normal with mean 1.0 afterwards; both calibrators start from the first 500 scores at `alpha = 0.1`, `gamma = 0.05` (test-only); on the last 500 episodes the adaptive miscoverage is closer to 0.1 than the split miscoverage.
20. `test_fork_states_are_independent`: `fork()` returns a calibrator holding the population scores and the initial `alpha_t`; updating one fork leaves the other and the parent unchanged (per-patient adaptation without leakage across patients).

Allocation, versions, determinism (`test_allocation.py`, `test_split.py`)

21. `test_bonferroni_allocation`: `per_test(0.1, 5) == pytest.approx(0.02)`; `per_test(0.1, 1) == 0.1`; `n_tests < 1` and `alpha_total` outside `(0, 1)` raise `ValueError`; property: `n * per_test(alpha, n) == pytest.approx(alpha)`.
22. `test_fit_records_model_version`: `fit(episodes, 0.2, model_version="v1")` sets `calibrated_for == "v1"`; refitting with `"v2"` sets `"v2"`; `fit` without `model_version` leaves `calibrated_for is None` (calibrated for no particular model, which the monitor refuses in predictive mode, WS05-T08).
23. `test_no_hidden_randomness`: two fits on the same episodes give identical quantiles; constructors take no random generator.
24. `test_ablation_a1_point_forecast_is_a_zero_score_calibrator`: a `SplitConformal` fitted on nine episodes with `sigma_true == sigma_hat` (all scores 0.0) has `quantile(0.2) == 0.0`, emits exactly when `sigma_hat < 0`, and reports `rho.value == pytest.approx(0.9)` for `sigma_hat = -0.1` (`alpha_star = (0 + 1) / 10`): the overconfident, uncalibrated rho that ablation A1 predicts (analisi §5.6); WS08-T03 builds `ours-A1` this way, without new API.

## Passi

1. Verify unblock conditions; branch `ws05-t06-conformal-calibrator`; `status: in_progress`. Read the Contesto documents and analisi §3.2 (adaptive conformal inference and non-exchangeability references; the citation details are verified by a human, ADR-018); write in the completion note the definition of the "possible" variant and any lower quantile from WS01-T06 (CP4), and how WS01-T06 states `Rho.guarantee` (copy its wording).
2. Copy the golden cases used into `tests/fixtures/conformal/`; write the tests; run `pytest tests/conformal -q`; watch them fail. Commit `WS05-T06: add failing conformal tests`.
3. Implement `scores.py` (`CalibrationEpisode` verbatim from the contract, `score(episode)`), `split.py` (`SplitConformal`: sorted scores, `k = ceil(round((n + 1) * (1 - alpha), 9))` so that float representation of `alpha` cannot move the rank, `+inf` when `k > n`; `predict` computing `alpha_star = (m + 1) / (n + 1)` with `m` counted from the sorted scores, `Rho(value=1 - alpha_star, kind=PREDICTED, guarantee=..., alpha=alpha, assumptions=...)`; `PredictedViolation` verbatim), `adaptive.py` (`AdaptiveConformal(gamma, window=None)`: recursion `alpha_next = alpha_t + gamma * (alpha - err_t)` with `err_t = 1` when `R_t` exceeds the quantile at `alpha_t`; `window` limits the retained scores and `None` keeps all; accessors `alpha_t` and `n_scores`, and `fork()`), `allocation.py` (`BonferroniAllocation`; the union bound needs no independence assumption).
4. Docstrings state, in these words: "calibration unit: patient episode"; "coverage is marginal over the population under exchangeability across episodes, not conditional on the patient"; "with many tests per patient-day an alpha allocation is required" (analisi §4.4 caveats). The ADR of step 6 records these as the reporting rule for coverage.
5. Refactor; remove migrated names from `conformal/_stubs.py`; update `conformal/__init__.py`; run `pytest tests/conformal -q`, `ruff format src tests`, `ruff check src tests`, `mypy src/ralmon`.
6. Write the ADR (status `proposed`, confirmation tag) and update the contract in the same commit: `#conformal-calibrator` gains `calibrated_for: str | None` and the keyword-only `model_version: str | None = None` on `fit` (rule 4 says the monitor refuses a calibrator older than the model, and the contract had no token to compare); `AdaptiveConformal` accessors are documented; the additional lower quantile if WS01-T06 defines one. Record that ACI uses the recursion of the cited work, unverified until the human reference check of WS03-T06. Bump the version.
7. Run every command of "Done when". Commit `WS05-T06: implement conformal calibrator`; set `status: done` and `status: ready` in the task files whose `depends_on` are now all `done`.

## Done when

From the repository root, inside `.venv`:

- `pytest tests/conformal -q` exits 0 (all 24 tests; golden case ids from `conformal.yaml` appear in `pytest tests/conformal -q --collect-only`).
- `ruff check src tests` and `ruff format --check src tests` exit 0; `mypy src/ralmon` exits 0.
- `python -c "from ralmon.conformal import ConformalCalibrator, CalibrationEpisode, PredictedViolation, AlphaAllocation, SplitConformal, AdaptiveConformal, BonferroniAllocation"` exits 0 and none has `__ralmon_stub_owner__`.
- `python -c "import ralmon.conformal as c; d = c.SplitConformal.__doc__ or ''; assert 'marginal' in d and 'patient episode' in d"` exits 0.
- `! grep -rn "^from ralmon\.\(attribution\|monitor\)\|^import ralmon\.\(attribution\|monitor\)" src/ralmon/conformal` succeeds (`conformal` imports only `signals` and `spec`).
- `python tools/check_plan.py` exits 0.

## Notes

### Flag from the WS01-T06 review (orchestrator, 2026-10-01)

See `docs/formal/06-rho-proposition1.md` (sections 4, 5, 8 and 10) and ADR-030 (proposed, `[DA-CONFERMARE]`). Test 2 says `10 * (1 - 0.3)` is a float-boundary case with k = 7: it evaluates to exactly 7.0; the boundary level is 0.7 (`(n+1)*(1-alpha)` = 3.0000000000000004, rank 4 instead of 3), so `quantile(0.7)` on this fixture must be 0.0, not 0.1. Test 8 uses the symmetric reading of the "possible" variant: on the fixture `sigma_hat = 0.3` is not emitted by the lower-quantile form (0.3 - 0.1 = 0.2). Step 3 (`ceil(round((n+1)*(1-alpha), 9))`) gave 0 wrong ranks on the two-decimal grid but was not tested on allocated levels `alpha_total / n_tests`: compute ranks with integer or `Fraction` arithmetic on the decimal literal and pass allocated levels as fractions. Golden C-3 gives no `rho` object for the emitted possible-variant row (a MINOR of the review). Kept `blocked` until ADR-030 is decided.
