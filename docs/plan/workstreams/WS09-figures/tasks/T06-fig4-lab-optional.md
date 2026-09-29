---
id: WS09-T06
title: "OPTIONAL: Fig. 4 lab setup photo and ROS graph"
workstream: WS09-figures
owner: agent
status: blocked
depends_on: [WS10-T05]
critical_path: false
non_negotiable: false
estimate_pd: 0.5
sources: ["analisi §7"]
interfaces: []
review_items: []
---
## Obiettivo

OPTIONAL. Produce Fig. 4, a small figure for section V-E (robot deployment): a photograph of the lab setup and the ROS graph of the running system (nodes and topics), as `paper/figures/fig4_lab.pdf` with its `.data.json`. The photo and graph come from the lab demo (WS10-T05); the figure is anonymised for double-blind review. Cut order (`00-master-plan.md` section 7, item 2): if the lab demo is cut and replaced by a simulation video, this task is cut with it, and WS09 plans no replacement figure.

## Contesto

- `docs/source/analisi.md` §7 ("Fig. 4 piccola: foto più grafico ROS (opzionale)") and §5.3 (the lab scenario the photo documents).
- `docs/plan/workstreams/WS10-lab-demo/tasks/T05-demo-runs.md`: the artefact `docs/plan/workstreams/WS10-lab-demo/outputs/WS10-T05.md` (field `outcome` with values `completed`, `partial`, `cut`; field `patient_stand_in`; check 11 on who or what appears in photos and consent) and the optional directory `hardware/lab_demo/lab_plan/photos/` holding photos and the ROS graph export.
- `docs/plan/02-interfaces.md#ros-2-interfaces`: the topic table; graph edges in the `/ralmon/` namespace must match it.
- `docs/plan/00-master-plan.md` section 7 (cut order).
- `docs/plan/workstreams/WS09-figures/README.md`: shared conventions (widths, fonts, provenance, terminology).

Unblocked when WS10-T05 is done with `outcome: completed` or `partial`. If `outcome` is `cut`, this task is cut: mark it `done` with a note "cut with WS10" and write no figure. Undeclared preconditions: WS09-T01 done; WS09-T02 done is recommended so that the tier and topic vocabulary matches Fig. 1.

## File toccati

- `tools/figures/targets/fig4_lab.py` (create): photo preparation, graph reading and drawing, and the `fig4` target.
- `tests/figures/test_fig4_lab.py` (create): tests below.
- `tests/figures/fixtures/fig4/` (create): a small synthetic JPEG carrying EXIF data (orientation and a GPS tag), a sample graph export, and a sample WS10-T05 artefact with `outcome` values.
- `paper/figures/fig4_lab.pdf` (create, generated), with `paper/figures/fig4_lab.data.json`.

## Test

1. `test_fig4_skipped_when_demo_cut`: with an artefact whose `outcome` is `cut`, `python -m tools.figures fig4` exits 0, writes no file and prints a message containing "cut".
2. `test_fig4_missing_photo_names_path`: `outcome: completed` and no photo in `hardware/lab_demo/lab_plan/photos/` exits non-zero and names that directory.
3. `test_fig4_exif_removed`: the raster embedded in the output and the sidecar carry no EXIF (no GPS, no camera serial, no timestamps); orientation is applied to the pixels before stripping.
4. `test_fig4_no_upscaling_and_min_effective_dpi`: the photo panel's effective resolution (pixels divided by printed inches) is at least `MIN_PHOTO_DPI` (300, a project rule to be confirmed against the IEEE author guidelines at WS12-T08); a photo with too few pixels makes the target fail rather than upscale.
5. `test_fig4_person_visible_requires_consent_statement`: if the artefact's statement on photos says that a person is visible and gives no consent, the target fails; with a stand-in manikin or with consent recorded it proceeds; the sidecar records `visible_persons`.
6. `test_fig4_graph_edges_use_contract_topics`: every edge in the `/ralmon/` namespace has a topic in the contract table; other topics are drawn in a distinct style and listed in the sidecar under `non_contract_topics`.
7. `test_fig4_design_time_fallback_is_labelled`: if no graph export exists, the graph is derived from the topic table of `#ros-2-interfaces` and the sidecar says `graph_source: design_time`; with an export it says `graph_source: recorded` and names the format.
8. `test_fig4_single_column_width_and_fonts`: width 3.5 in (252 pt), fonts embedded, text at least 6 pt.
9. `test_fig4_sidecar_hashes_photo_and_graph`: the sidecar has SHA-256 of the photo file and the graph export, the WS10-T05 artefact path and its `outcome`.
10. `test_fig4_render_is_deterministic`: two runs give identical `.data.json`.
11. `test_fig4_sidecar_anonymisation_fields`: the sidecar has `exif_stripped: true`, `logos_or_names_visible` and `inspected_by` fields (filled by the executing agent after viewing the image and confirmed by a human at WS12-T08).

## Passi

1. Read the WS10-T05 artefact and the photos directory. If `outcome` is `cut`, stop as described in Contesto. Note what the artefact says about photos (subject, consent) and the format of the graph export. The artefact has no machine-readable photo field, so parse only what it actually contains and stop with a clear message if the statement about persons in the photo is missing.
2. Create the fixtures and write the tests; run `pytest tests/figures/test_fig4_lab.py -q`, confirm failure; commit `WS09-T06: add failing Fig. 4 tests`.
3. Implement photo preparation with Pillow (already a dependency of matplotlib): apply the EXIF orientation, drop all metadata by rebuilding the image from pixel data, crop to the panel aspect ratio, refuse upscaling.
4. Implement the graph reader for the export format actually present (record the format name in the sidecar; do not invent a format) and the design-time fallback. Draw nodes grouped by ward node and robot with the same vocabulary as Fig. 1, edges labelled with topic names without the `/ralmon/` prefix.
5. Compose the two panels (photo, ROS graph) at single-column width with `style.save_pdf`, look at the PNG conversion of the result, check that the photo shows no faces, logos, institution names or screen contents that identify the authors (double-blind), and record the inspection in the sidecar.
6. Run `ruff format`, `ruff check`, the tests, and `python -m tools.figures fig4 --check`. Commit `WS09-T06: add Fig. 4 lab setup` and set `status` to `done`.

## Done when

- `pytest tests/figures/test_fig4_lab.py -q` exits 0 and `ruff check tools/figures tests/figures` exits 0.
- With `outcome: completed` or `partial`: `python -m tools.figures fig4` exits 0, `test -f paper/figures/fig4_lab.pdf && test -f paper/figures/fig4_lab.data.json`, and `python -m tools.figures fig4 --check` exits 0.
- With `outcome: cut`: the task file `status` is `done` with the note "cut with WS10", and `test ! -f paper/figures/fig4_lab.pdf`.
