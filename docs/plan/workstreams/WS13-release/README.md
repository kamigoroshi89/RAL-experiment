# WS13-release: Open-source release

## Objective

Turn the repository into a documented, installable and anonymisable open-source release (analisi §9 item 13: "Repository open-source anonimizzabile e documentato"). The benchmark generator is a releasable contribution (analisi §5.1): publishing it together with its seeds, manifest, parameter provenance and non-circularity tests is what lets a reader inspect the circularity objection (analisi §10, objection 1) instead of taking the ground truth on trust. WS13 has four tasks, all owned by an agent and none on the critical path: repository hygiene with a licence proposal (T01), one command per table and figure of the paper (T02), an anonymised snapshot for double-blind review (T03), and a datasheet plus generator documentation for the benchmark (T04). T03 gates the final compile of the paper (WS12-T08 depends on it), so it must be done before milestone M5 of `00-master-plan.md`. Total estimate: 5.0 person-days (analisi §9 item 13 gives 1 person-week).

**Publication rule (binding for every WS13 task).** WS13 prepares artefacts locally and never publishes them. Pushing to any remote requires explicit human approval. The same holds for adding a remote, pushing branches or tags, creating or changing a hosted repository, changing repository visibility, creating a release, and uploading an archive to any hosting, archive or submission service: each of these requires explicit human approval. The approval is given by the human in the session where the action is requested and is quoted in the completion note of the task; without it the agent stops and reports what is ready. Local git operations (branch, commit, merge, local tags) remain allowed as in `01-conventions.md` section 4, which reserves remote operations to this workstream.

**Human decisions.** Agents propose, humans decide. Three decisions are left open and are recorded as ADRs in `03-decisions.md` with status `proposed` and the same confirmation tag as ADR-011 to ADR-017, so that the human can confirm or overturn them:

1. the licence of the code, of the generated benchmark data and of the documentation (T01 states the options and records a provisional proposal);
2. the anonymised hosting procedure for double-blind review (T03 states the options and records no choice until the human names one);
3. the licence of each source dataset and the finding on what the data use agreements of MIMIC-IV and eICU allow to be released (T04 records these as `unverified` until a human verifies them, the same treatment as references in ADR-018).

One further human touchpoint sits inside T03: the list of identifying terms that the anonymisation check searches for is seeded by the agent and reviewed and completed by a human.

**Boundaries.** WS13 does not write the paper's data-availability text (WS12), does not create accounts, and does not de-anonymise anything. The de-anonymised public release after acceptance is a separate step that needs its own human approval under the publication rule above.

## Inputs

- `docs/source/analisi.md`: §9 item 13, §5.1 (generator as a releasable contribution, ground truth, public sources and their access constraints), §10 objection 1, §6 (the implementation contribution: "We release an open-source ROS 2 implementation and a semi-synthetic benchmark").
- `docs/plan/01-conventions.md`: section 1 (layout, `data/raw/` and `outputs/` never committed), section 3 (bit-for-bit reproducibility on the same machine), section 4 (git workflow; remote operations governed here), section 7 (glossary), section 8 (no clinical values outside the registry), section 9 (results layout).
- `docs/plan/02-interfaces.md`: `#package-public-api`, `#experiment-config-and-outputs`, `#trace-schema`.
- `docs/plan/03-decisions.md`: ADR-001 (scope), ADR-002 (C3 threat model), ADR-005 (PriorSource, credentialing), ADR-011, ADR-013, ADR-016 (toolchain), ADR-018 (unverified flag pattern), ADR-020 (unverified clinical parameters).
- From other workstreams: the `run_offline` end-to-end path (WS05-T08); the benchmark builder CLI and manifest (WS04-T01, WS04-T11); the benchmark validation report (WS04-T12); the frozen experiment outputs (WS08-T07); the table and figure generators (WS09-T01 to WS09-T05).
- Human artefacts, read when they exist: `docs/plan/workstreams/WS00-admin/outputs/WS00-T01.md` (section `## Review mode and format`: double-blind rule, anonymisation rules, supplementary material, code release rule) and `docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md` (sections `## Data handling constraints` and `## Open-access datasets`: DUA terms and dataset licences with `Source:` lines).

## Outputs

| Artefact | Task | Consumed by |
|---|---|---|
| `README.md`, `LICENSE`, `docs/install.md` (with dependency and licence inventory), licence metadata in `pyproject.toml` and `ros2/*/package.xml` | T01 | T02, T03, T04, any reader |
| Licence ADR in `docs/plan/03-decisions.md` (status `proposed`, confirmation tag) | T01 | human confirmation, T03 readiness report |
| `tools/reproduce.py`, `experiments/smoke.yaml`, `docs/reproduce.md`, `docs/reproduce-reference.sha256` | T02 | T03, WS12-T05, reviewers |
| `tools/make_anonymous_snapshot.py`, `tools/check_anonymity.py`, `tools/anonymise_allowlist.txt`, `docs/anonymised-release.md` | T03 | WS12-T08 (anonymisation check of the paper source), human hosting step |
| Hosting ADR in `docs/plan/03-decisions.md` (status `proposed`, no choice recorded until the human names one) | T03 | human decision |
| Generated, gitignored: `outputs/anonymised-snapshot/`, `outputs/anonymised-snapshot.tar`, `outputs/anonymised-release-report.md`, private `outputs/anonymity/terms.txt` and `outputs/anonymity/pseudonyms.yaml` | T03 | human hosting step; never committed |
| `docs/benchmark/datasheet.md`, `docs/benchmark/generator.md` | T04 | T03 (allowlisted for the snapshot), WS12-T05 and WS12-T06 (limitations, data availability) |

## Dependencies

- Upstream: WS05-T08 and WS04-T11 (T01); WS08-T07 and WS09-T05 (T02); WS04-T12 (T04). Inside WS13: T03 needs T01 and T02; T04 has no WS13 dependency.
- Downstream: WS12-T08 (final compile, page fit, anonymisation check) needs WS13-T03. Milestone M5 requires the repository anonymised.
- Contract anchors: `02-interfaces.md#package-public-api` (T01), `02-interfaces.md#experiment-config-and-outputs` (T02), `02-interfaces.md#trace-schema` (T04).
- Soft dependencies not listed in `depends_on` (INDEX is binding and unchanged; each task handles the case where the upstream artefact is missing): T02 needs the generators of Table I, Fig. 1 and Fig. 2 (WS09-T04, WS09-T02, WS09-T03), which are not ancestors of WS13-T02; T03 allowlists `docs/benchmark/` written by T04; T04 cites the licence ADR written by T01; T03 reads the double-blind rule from WS00-T01.

## Acceptance criteria

Checked from the repository root once all four tasks are `done`.

1. Structure: `test -f docs/plan/workstreams/WS13-release/README.md` and the four files `tasks/T01-repo-hygiene.md`, `tasks/T02-repro-scripts.md`, `tasks/T03-anonymised-snapshot.md`, `tasks/T04-generator-datasheet.md` exist; `python tools/check_plan.py` exits 0 when the verifier is present.
2. Publication rule: `grep -l 'explicit human approval' docs/plan/workstreams/WS13-release/README.md docs/plan/workstreams/WS13-release/tasks/*.md` lists all five files, and `grep -rn 'push' docs/plan/workstreams/WS13-release | grep -v 'approval'` prints nothing (every mention of pushing carries the approval condition on the same line).
3. No remote action by agents: the completion note of each task shows `git remote -v` unchanged from the start of the task; no task note contains evidence of a remote write.
4. Human decisions are recorded, not silent: `grep -nE '^## ADR-[0-9]+ .*(licen[cs]e|hosting)' docs/plan/03-decisions.md` prints two headings (licence, anonymised hosting); the Status line of each begins with `proposed` (or `accepted` after the human confirms), and the licence ADR lists options, constraints, alternatives and the files to change if overturned.
5. Documented: `README.md`, `docs/install.md`, `docs/reproduce.md`, `docs/benchmark/datasheet.md` and `docs/benchmark/generator.md` exist, and every user-facing file under `docs/` (everything except `docs/plan`, `docs/source`, `docs/superpowers` and the maintainer document `docs/anonymised-release.md`, which is not part of the release) is linked from the `## Documentation` section of `README.md`.
6. Reproducible: `python tools/reproduce.py --list` prints one command for each of Table I, Table II, Table III, Fig. 1, Fig. 2 and Fig. 3 and states that Fig. 4 is not reproducible from the repository; `python tools/reproduce.py all --profile full --check` exits 0 on the machine that produced the frozen results (WS08-T07).
7. Inspectable circularity: `docs/benchmark/datasheet.md` contains the thirteen headings listed in T04 and its section on semi-synthetic nature states the latent versus observed trace definition of analisi §5.1 and cites the non-circularity tests of WS04-T10 by path.
8. Anonymised: `python tools/check_anonymity.py outputs/anonymised-snapshot --terms outputs/anonymity/terms.txt` exits 0; the snapshot contains no `.git` directory, no tooling artefact and no plan or source directory; `outputs/anonymised-release-report.md` states `terms reviewed by human: yes` or lists the snapshot as not to be hosted, and states that publication was not performed.
9. Terminology and claims: the release documents use the glossary of `01-conventions.md` section 7 and the claim wording of analisi §4.8; they contain no clinical numeric value outside quotations of the registry (ADR-020).
10. No forbidden tokens of the authoring brief in any file of this workstream folder.

## Source sections

- analisi §9 item 13 (roadmap row: open-source, anonymisable, documented repository; depends on items 5 and 4).
- analisi §5.1 (the trace generator is a releasable contribution; public sources, licences and access times; ground truth defined on the latent trace; scale).
- analisi §10 objection 1 (circular semi-synthetic evaluation; "rilasciare il generatore, così la circolarità è ispezionabile").
- analisi §6 (implementation contribution: open-source implementation and benchmark).
- analisi §5.5 and §7 (tables, figures and metrics that the reproduction commands regenerate).
- `02-interfaces.md#trace-schema`, `#experiment-config-and-outputs`, `#package-public-api`.

## Tasks

| id | title | owner | status | depends_on |
|---|---|---|---|---|
| WS13-T01 | Repository hygiene: README, install docs, license decision | agent | blocked | WS05-T08, WS04-T11 |
| WS13-T02 | Reproduction scripts: one command per table and figure | agent | blocked | WS08-T07, WS09-T05, WS09-T02, WS09-T03, WS09-T04 |
| WS13-T03 | Anonymised release snapshot for double-blind review | agent | blocked | WS13-T01, WS13-T02, WS13-T04, WS00-T01 |
| WS13-T04 | Benchmark and generator documentation and datasheet | agent | blocked | WS04-T12, WS13-T01 |
