---
id: WS11-T04
title: Online study implementation
workstream: WS11-vignettes
owner: agent
status: blocked
depends_on: [WS11-T03]
critical_path: false
non_negotiable: false
estimate_pd: 2
sources: ["analisi §5.7"]
interfaces: []
review_items: []
---
## Obiettivo

OPTIONAL: first item in the cut order (`docs/plan/00-master-plan.md` section 7). Implement the online study as a static, dependency-free web app that runs entirely in the participant's browser: counterbalanced presentation of the vignettes, the instruments of `study/protocol.yaml`, timing of decisions, and export of one pseudonymous response file per participant. Concrete outputs: `study/schedule.py` (counterbalancing), `study/responses.py` (response schema validator and loader, reused by WS11-T06), `study/build_app.py` (builds the app) and `study/app/`. The app makes no network request and contains neither the answer key nor any ground-truth field, which keeps third-party data processing out of the ethics dossier.

## Contesto

- `study/` : `design.md` and `protocol.yaml` (conditions, `counterbalancing`, `sample`, `instruments`, `response_schema`, `exclusions`, `trust_scale`), `vignettes/` (participant-facing bundle from WS11-T02), `answer-key.yaml` (read only to check that every scored family has a validated entry; never copied into the app), `ethics-dossier.md` (section `Consent text`, embedded unchanged).
- `docs/plan/workstreams/WS11-vignettes/outputs/WS11-T03.md` (sections `Changes requested to vignettes and instruments`, `Timing and exclusion rule`, `Decision for WS11-T04`).
- `docs/plan/01-conventions.md` sections 2 and 3 (explicit integer seeds, durations in integer milliseconds, deterministic tests, specific exception classes).
- `docs/source/analisi.md` §5.7 (online, within-subject; decision time and other measures).

Unblocked when WS11-T03 is `done` with decision `go` or `go with changes`. If the decision is `go with changes`, an agent first applies the listed changes by rerunning `study/build_vignettes.py`, then starts here. If `trust_scale.items` is empty or unverified, the build must fail (a test below): the app is never built with unverified trust items.

## File toccati

- `study/schedule.py` (create)
- `study/responses.py` (create)
- `study/build_app.py` (create)
- `study/app/` (create; `index.html`, `app.js`, `style.css` written by hand, `bundle.json` generated)
- `tests/study/test_app.py` (create)
- `tests/study/fixtures/` (modify; add `valid_responses/` with synthetic response files written by the tests)

## Test

Written first and run to fail. The YAML library is the one `ralmon.spec` already uses for the registry; do not add another.

- `test_schedule_block_orders_balanced`: for a number of participants that is a multiple of the cycle length in `protocol.yaml` (for the default cyclic Latin square with three conditions, 9 or 12 or 15), each condition appears exactly `n / 3` times at each block position, computed by hand (for n = 9: three participants per condition per position).
- `test_family_condition_rotation_balanced`: over a full cycle each family set is presented in each condition equally often (`n / 3` participants each).
- `test_ranking_block_for_all_after_divergence_block`: when `protocol.yaml` includes the ranking set, every sequence has it exactly once, after the divergence block and before the debrief, and the item order equals the shuffled order of the bundle.
- `test_each_family_seen_once_per_participant`: no participant sees a rotating family twice; the divergence block follows the three condition blocks and is `RSM` only; practice families come first in each block and are flagged `practice`.
- `test_schedule_deterministic_for_seed`: the same explicit integer seed gives the same sequences, the same within-block family order and the same option order per family; the seed is a function argument, no global state.
- `test_bundle_has_no_key_or_ground_truth`: a recursive walk over `bundle.json` and every file in `study/app/` finds none of the keys or values that `study/answer-key.yaml` and the ground-truth fields use (`ground_truth`, `subtype`, `injected`, `confounder_group`, `latent`, `expected_action`, `scoring`, and every expected-action rationale string).
- `test_build_fails_if_trust_items_unverified`: a copy of the protocol with `trust_scale.items: []`, or with `verified_by: null`, makes the builder raise the module's `StudyBuildError`; the real protocol after WS11-T03 builds.
- `test_build_fails_if_a_scored_family_has_no_validated_key`: a key with one entry missing, or with `status: draft`, makes the builder raise `StudyBuildError`.
- `test_app_makes_no_network_requests`: no file in `study/app/` contains `fetch(`, `XMLHttpRequest`, `sendBeacon`, `WebSocket`, or an absolute `http://` or `https://` URL (no CDN, no font service, no analytics).
- `test_every_instrument_item_in_bundle`: every Likert item, cue question, trust item and debrief question id of `protocol.yaml` appears in `bundle.json`, and the consent text equals the `Consent text` section of `study/ethics-dossier.md` byte for byte.
- `test_response_validator_accepts_complete_record`: a hand-written complete record of one vignette passes `study/responses.py`.
- `test_response_validator_rejects_invalid_records`: each of these fails with a specific exception: missing `decision_time_ms`, negative time, non-integer time, unknown `family_id`, an action id not in the family's options, a rating outside the Likert range, a ranking that is not a permutation of the ranks 1 to k, a condition that differs from the one the participant's sequence assigns to that family.
- `test_responses_script_exit_code`: `python3 study/responses.py <directory>` run as a subprocess exits 0 on a directory of valid files and non-zero on a directory with one invalid file, printing one line per file.
- `test_synthetic_session_passes_validator`: a Python simulation that walks one full sequence and answers every vignette produces a response file that passes the validator and contains exactly one record per scored vignette plus the practice records.

Manual browser checks (executed by the agent if a browser is available, otherwise repeated by the human in the dry run of WS11-T05; record which in the completion note): the tab-hidden time is recorded; an answer cannot be changed after submission and there is no back navigation; a page reload resumes at the same vignette without altering recorded answers and marks the resumed vignette; the exported file is named with the participant code only; the page is usable with keyboard only.

## Passi

1. Read the protocol, the T03 artefact and the vignette bundle. Write the tests above (and the synthetic files of `tests/study/fixtures/valid_responses/`, generated by `test_synthetic_session_passes_validator` or written by hand) and watch the tests fail.
2. Implement `study/schedule.py`: sequences from the scheme in `protocol.yaml`, participant code to sequence mapping for up to 15 participants, within-block family order and option order from a seeded generator, practice families first in each block, divergence block last.
3. Implement `study/responses.py`: the `response_schema` of `protocol.yaml` as a validator and a loader for a directory of exported files, with specific exception classes, and runnable as `python3 study/responses.py <directory>` (one line per file, non-zero exit if any file is invalid). Durations are integer milliseconds.
4. Implement `study/build_app.py`: read the participant-facing vignettes, the schedule, the instruments, the consent section; refuse to build if the trust items are unverified or a scored family lacks a validated key entry; write `study/app/bundle.json`.
5. Write the static app: consent page (agreement required, no name field), participant code page, instructions with the practice vignettes, one vignette per page (shared context, the condition-specific panel, the action catalogue in the scheduled option order), then the Likert items, then the cue question in the divergence block, the trust scale after each condition block, the urgency-ranking set (one rank per item, keyboard usable), the debrief, and a button that downloads the response file. Time the decision from display to submission with the browser's monotonic clock and accumulate hidden time from page visibility changes; store integers in milliseconds. Keep progress in the browser's local storage so that a reload resumes. No external resource, no network call.
6. Run `pytest tests/study -q` until green, `ruff check study tests`, and `python3 study/build_app.py`. Refactor. Commit on branch `ws11-t04-study-implementation` with `WS11-T04: implement online vignette study app`; set `status: done`. Record the manual browser checks and the SHA-256 of `study/app/bundle.json` in the completion note (WS11-T05 records the same hash of what participants saw).

## Done when

From the repository root, each exits 0:

- `pytest tests/study -q`
- `ruff check study tests`
- `python3 study/build_app.py`
- `python3 study/responses.py tests/study/fixtures/valid_responses` (a directory of valid synthetic response files created with the tests)
- `test -f study/app/index.html && test -f study/app/bundle.json`
- `! grep -rEq 'fetch\(|XMLHttpRequest|sendBeacon|WebSocket' study/app`
- `! grep -rEq 'ground_truth|expected_action|confounder_group' study/app`
