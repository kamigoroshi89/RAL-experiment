---
id: WS09-T02
title: Fig. 1 redesigned architecture
workstream: WS09-figures
owner: agent
status: blocked
depends_on: ["WS01-T08", "WS02-T04", "WS09-T01"]
critical_path: false
non_negotiable: false
estimate_pd: 1.5
sources: ["analisi §4.9 (6)", "analisi §7"]
interfaces: ["02-interfaces.md#ros-2-interfaces"]
review_items: ["R3-W7", "AE-5"]
---
## Obiettivo

Produce Fig. 1, the redesigned architecture, as a **single-column** IEEE figure (3.5 in wide) generated from a machine-readable diagram specification, so that every fix of analisi §4.9 item 6 is a testable property. The figure shows the corrected pipeline (signal abstraction, measured and predictive monitor, attribution, event manager), the humans (patient, nurse, clinician), the robot, the ward node, the sensing tier including ambient sensors, and the back-end, with on-path components visibly distinct from off-path ones. Output: `paper/figures/fig1_architecture.pdf` and `fig1_architecture.data.json` (the specification dump, also the table view of the figure).

## Contesto

- `docs/source/analisi.md` §4.9 item 6 (the six defects of the workshop Fig. 1), items 1, 3, 4 (distributed architecture, cascades, clinician in the loop), §7 ("Fig. 1" definition) and §2 R3 weakness 7 (dispenser is not worn, ambulatory blood-pressure monitor, ambient sensors missing).
- `docs/plan/02-interfaces.md#ros-2-interfaces`: topics and placement (ward node and robot); the same file's `#verdict` fixes that conformal prediction acts only in PENDING.
- `docs/plan/03-decisions.md` ADR-003 (ward node plus robot, heartbeat, fallback to the nurse), read together with ADR-004, ADR-008 and ADR-010.
- `docs/plan/01-conventions.md` section 7: the binding glossary; "on-path" and "off-path" are defined once and then reused.
- The workshop paper `Clinical_Pathways_Physical_AI_IJCAI-ECAI_2026.pdf` (repository root): its Fig. 1 and its sentence on privacy-aware storage of feature representations; reuse only labels that remain correct.

Unblocked when WS01-T08 and WS02-T04 are done (template decomposition, verdict semantics and the evidence flow into attribution are frozen). Undeclared precondition: WS09-T01 (`tools/figures/style.py`, `provenance.py`, CLI) must be done; if it is not, stop and report, do not create a second scaffold. If the WS05-T09 or WS07 task files exist and refine placement, follow them.

## File toccati

- `tools/figures/targets/fig1_spec.py` (create): dataclasses `Node`, `Edge`, `Tier` and the specification instance (label, tier, kind `module|human|device_group|robot|backend`, `on_path`, geometry in figure units; edge source, target, label, `topic` or `None`, style).
- `tools/figures/targets/fig1_architecture.py` (create): renderer (matplotlib patches and arrows at 3.5 in) and the `fig1` target.
- `tests/figures/test_fig1_architecture.py` (create): tests below.
- `paper/figures/fig1_architecture.pdf` (create, generated).
- `paper/figures/fig1_architecture.data.json` (create, generated).

## Test

Specification tests (pure Python, no rendering), in `tests/figures/test_fig1_architecture.py`:

1. `test_fig1_pipeline_order`: the module chain in the specification is signal abstraction, monitor, attribution, event manager, in this topological order (fix 6a, analisi §7).
2. `test_fig1_monitor_has_measured_and_predictive_paths`: the monitor node has a measured path emitting definitive verdicts and a predictive path; the forecaster and the conformal calibrator have edges only into the predictive path, and no edge leads from them to the measured path (ADR-008: conformal prediction acts only in PENDING; this prevents the contradiction the meta-review lists, AE-5).
3. `test_fig1_has_signal_abstraction_block`: a module node whose label contains "signal abstraction" exists (fix 6b; it was missing).
4. `test_fig1_humans_present`: nodes of kind `human` for patient, nurse and clinician exist (fix 6c).
5. `test_fig1_ambient_sensors_present`: the text of some node contains "ambient sensors" (fix 6c and R3-W7).
6. `test_fig1_dispenser_not_worn_and_no_wearable_sphygmomanometer`: no label contains "wearable sphygmomanometer" or "patient-worn" together with "dispenser"; a label containing "ambulatory blood-pressure monitor" exists (R3-W7).
7. `test_fig1_event_manager_has_outgoing_edges`: the event manager has at least one outgoing edge to the nurse and one to the robot, and the labels of those edges do not authorise clinical actions without the nurse (fix 6d "Safety Actions had no outgoing arrows"; analisi §4.9 item 4: autonomy limited to robot actions such as stop, retry, call; clinical actions clinician-in-the-loop).
8. `test_fig1_backend_edge_is_feature_representations`: the edge from the ward node to the back-end has a label containing "feature" and none containing "patient data" (fix 6e: the arrow "Patient data and Events" contradicted privacy-aware storage of feature representations).
9. `test_fig1_on_path_flags`: every node has `on_path` set; ward-node modules and the robot are on-path; the back-end nodes are off-path; the nurse and clinician (humans) are drawn in a human style that is neither.
10. `test_fig1_heartbeat_watchdog_and_fallback`: a heartbeat edge links robot and ward node in both directions, and a fallback edge from the watchdog or event manager to the nurse exists (ADR-003).
11. `test_fig1_draws_every_contract_topic`: the topic names parsed from `02-interfaces.md` (regular expression `/ralmon/(\w+)` in the ROS 2 table) are each used by at least one edge, and every edge `topic` that is not `None` is in that set.
12. `test_fig1_pipeline_count_matches_sidecar`: `len(pipeline_modules)` in the generated `.data.json` equals the number of pipeline module nodes drawn (fix 6f: the workshop text said "three pipeline stages" for five blocks; WS12 takes the count from the sidecar field `pipeline_modules`).
13. `test_fig1_labels_avoid_glossary_violations`: no label contains any of `subsystem`, `Time-Series Learner`, `Conformal Uncertainty`, `edge cloud`, `PILL`, `middleware-agnostic`, `Physical AI`, or `Clinical Pathway` used for a single patient's prescription; DISPENSE and INTAKE, if drawn, are upper case and separate.

Rendering tests:

14. `test_fig1_single_column_width`: the `/MediaBox` width of the PDF is 252 pt (3.5 in) within 0.5 pt; the height does not exceed `FIG1_MAX_HEIGHT_IN` (a provisional constant, to be confirmed against the page budget of WS12-T02).
15. `test_fig1_text_fits_boxes`: with the Agg renderer, the extent of every node text lies inside its box (no overflow).
16. `test_fig1_min_font_size`: every text object has size at least `MIN_FONT_PT` (6 pt) at the final size.
17. `test_fig1_on_path_encoding_not_colour_only`: on-path and off-path nodes differ in line style and line width as well as fill (solid heavy versus dashed light), so the distinction survives grayscale.
18. `test_fig1_render_is_deterministic`: two runs give identical `.data.json` and identical PDF bytes.

## Passi

1. Confirm the precondition (WS09-T01 done) and read the six defects in analisi §4.9 item 6. Open the workshop PDF, list the blocks and labels of its Fig. 1 and mark each as keep, rename or remove. Write the list in the module docstring of `fig1_spec.py`.
2. Write the tests (specification tests first), run `pytest tests/figures/test_fig1_architecture.py -q` and watch them fail.
3. Implement the specification dataclasses and the specification instance. Layout guidance (geometry is yours, verified in step 6): sensing tier as one grouped box (ambulatory blood-pressure monitor, worn sensors for ECG and SpO2, smart dispenser at the bedside, ambient sensors); ward node as a vertical stack of the pipeline modules with the forecaster and conformal calibrator beside the predictive path; robot with its embodied specification monitor (task deadlines, presence, INTAKE witness) and its actions (stop, retry, call); back-end in a dashed off-path band (signed care plan authoring, model update and recalibration, retrospective checking, feature storage); a human row with patient, nurse, clinician. Only use device names that appear in `02-interfaces.md#signals` or in the workshop paper; do not add devices.
4. Define "on-path" and "off-path" in one sentence in the docstring (on-path: components whose unavailability stops an alert from being produced; off-path: the back-end, which only updates plans and models) and hand it to WS12 through the sidecar field `onpath_definition`. WS12 owns the final wording.
5. Implement the renderer with `style.apply_rcparams()` and `style.save_pdf()`; edge labels use the topic names of the ROS 2 table without the `/ralmon/` prefix plus the non-topic labels listed in the specification; no dual encoding by colour alone (dataviz: recessive lines, direct labels, at most a small legend for solid versus dashed).
6. Render, convert the PDF to PNG at 200 dpi (for example with `pdftoppm -png -r 200`) and inspect it as an image for overlaps, crossing arrows and legibility at 3.5 in. Iterate on geometry until tests 14 to 17 pass and the render is readable.
7. Write the sidecar through `write_generated` (nodes, edges, tiers, `pipeline_modules`, `onpath_definition`).
8. Run `ruff format` and `ruff check`, then the tests until green. Commit `WS09-T02: add Fig. 1 architecture` and set `status` to `done`.

## Done when

- `pytest tests/figures/test_fig1_architecture.py -q` exits 0 and `ruff check tools/figures tests/figures` exits 0.
- `python -m tools.figures fig1` exits 0; `test -f paper/figures/fig1_architecture.pdf && test -f paper/figures/fig1_architecture.data.json`.
- `grep -a -o '/MediaBox \[[^]]*\]' paper/figures/fig1_architecture.pdf` shows a width of 252.
- `python -m tools.figures fig1 --check` exits 0.
