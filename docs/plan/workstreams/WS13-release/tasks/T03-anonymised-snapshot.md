---
id: WS13-T03
title: Anonymised release snapshot for double-blind review
workstream: WS13-release
owner: agent
status: blocked
depends_on: ["WS13-T01", "WS13-T02", "WS13-T04", "WS00-T01"]
critical_path: false
non_negotiable: false
estimate_pd: 1
sources: ["analisi §9 (13)"]
interfaces: []
review_items: []
---
## Obiettivo

Produce, locally and repeatably, an anonymised copy of the repository that can be given to reviewers of a double-blind submission, and a check that proves no author name, affiliation, institution-specific path or identifier is left in it. Concrete output: `tools/make_anonymous_snapshot.py` (allowlist-based, deterministic, optional tar archive, readiness report), `tools/check_anonymity.py` (usable on the snapshot and on the paper source, WS12-T08 reuses it), `tools/anonymise_allowlist.txt`, `docs/anonymised-release.md` (procedure) and an ADR that states the options for anonymised hosting and records no choice until a human names one. Whether and how the venue requires double blind is stated in WS00-T01; the snapshot is safe to build either way. Two human touchpoints are built in: the list of identifying terms is seeded by the agent and reviewed by a human, and the hosting procedure is chosen by a human. Nothing is hosted or published by this task; pushing to any remote requires explicit human approval.

## Contesto

- `docs/plan/01-conventions.md` section 1 (layout; `outputs/` and `data/raw/` are gitignored) and section 4 (local git operations only; no history rewriting on `main`; remote operations reserved to WS13).
- `docs/plan/03-decisions.md`: ADR format, the confirmation-tag pattern of ADR-011 to ADR-017, ADR-005 (credentialed data) and ADR-018 (unverified flag pattern).
- `docs/source/analisi.md` §9 item 13 (open-source, anonymisable, documented repository).
- `docs/plan/workstreams/WS00-admin/outputs/WS00-T01.md`, section `## Review mode and format` (single or double blind, anonymisation rules, supplementary material, code release rule), if the file exists; if it does not, write `venue policy not established` in the completion note and continue.
- Outputs of WS13-T01 and WS13-T02 (`README.md`, `LICENSE`, `docs/install.md`, `docs/reproduce.md`, the licence ADR) and, if present, of WS13-T04 (`docs/benchmark/`).

Blocked until WS13-T01 and WS13-T02 are `done`. The snapshot is meant to be built again after WS13-T04 is done, because `docs/benchmark/` belongs to the release; a snapshot built earlier is reported as incomplete.

## File toccati

- `tools/make_anonymous_snapshot.py` (create)
- `tools/check_anonymity.py` (create)
- `tools/anonymise_allowlist.txt` (create)
- `tests/tools/test_anonymise.py` (create)
- `docs/anonymised-release.md` (create)
- `docs/plan/03-decisions.md` (modify: append the hosting ADR and update the index line)

## Test

Pytest names, written before the steps. All fixtures are built in `tmp_path` with fictitious identities (`Alice Example`, `Bob Example`, `Aaron Example`, `Example University`, `alice@example.org`, `labhost-07`); no real name appears in the repository. Both tools are loaded by path with `importlib.util.spec_from_file_location`. Interfaces used by the tests: `python tools/make_anonymous_snapshot.py --root ROOT --files-from FILE --allowlist FILE --terms FILE --pseudonyms FILE --out DIR [--archive FILE] [--report FILE] [--adr-file FILE] [--terms-reviewed]` (exit 0 success, 1 residual identifiers, 2 usage error) and `python tools/check_anonymity.py DIR --terms FILE [--allowlist FILE]` (exit 0 clean, 1 findings, 2 usage error; findings print as `path:line: kind: text`, sorted). The terms file has one entry per line, `#` starts a comment, `term` means detect only and `term => replacement` means replace in text files then detect; matching is case-insensitive. The allowlist file has lines `include: <glob>` and `domain: <host>`. A built-in denylist in the script always wins over the allowlist.

1. `test_builder_refuses_missing_or_empty_terms_file`: a missing terms file and an empty one (only comments) both exit 2 and the message names the file; an anonymity check without terms would be vacuous.
2. `test_only_allowlisted_files_are_copied`: file list `a.py`, `b.bin` with allowlist `include: a.py` copies only `a.py`.
3. `test_denylist_wins_over_allowlist`: with allowlist `include: **`, the entries `.git/config`, `.claude/settings.json`, `prompt/PROMPT.md`, `CLAUDE.md`, `docs/plan/x.md`, `docs/source/y.md`, `docs/superpowers/z.md`, `paper/main.tex`, `ruvector.db`, `agentdb.rvf`, `pkg/__pycache__/m.pyc`, `pkg.egg-info/PKG-INFO` and `Clinical_Pathways_Physical_AI_IJCAI-ECAI_2026.pdf` are all absent from the output, and `a.py` is present.
4. `test_files_absent_from_file_list_are_ignored`: a file that exists in the tree but is not in the `--files-from` list (an untracked file) is not copied.
5. `test_pyproject_authors_and_urls_replaced`: for an input with `authors = [{name = "Alice Example", email = "alice@example.org"}]`, `maintainers` and a `[project.urls]` table, `tomllib.loads(output)["project"]["authors"] == [{"name": "Anonymous Authors"}]`, the same for `maintainers`, and `"urls"` is not a key of `project`.
6. `test_license_copyright_holder_replaced`: the line `Copyright (c) 2026 Alice Example` becomes `Copyright (c) 2026 Anonymous Authors` (year kept).
7. `test_package_xml_maintainers_authors_and_urls_anonymised`: `<maintainer email="alice@example.org">Alice Example</maintainer>` becomes `<maintainer email="anonymous@example.invalid">Anonymous</maintainer>`, `<author>Bob Example</author>` becomes `<author>Anonymous</author>`, a `<url type="website">https://example.org/x</url>` element is removed, and the output still parses with `xml.etree.ElementTree`.
8. `test_setup_py_maintainer_fields_anonymised`: `maintainer='Alice Example',` becomes `maintainer='Anonymous',` and `maintainer_email='alice@example.org',` becomes `maintainer_email='anonymous@example.invalid',` (same for `author` and `author_email`).
9. `test_reviewer_fields_pseudonymised_alphabetically`: in a YAML file with `reviewed_by: Bob Example`, `reviewed_by: Alice Example`, `reviewed_by: null` and a JSON file with `"verified_by": "Alice Example"` and `"verified_by": null`, Alice becomes `person-1` in both files, Bob becomes `person-2`, the nulls stay null, and both files still load with `yaml.safe_load` and `json.loads` (a pseudonym is non-null, so "verified" or "reviewed" keeps its meaning, ADR-020).
10. `test_pseudonym_map_is_stable_when_new_name_added`: with an existing map `{"Alice Example": "person-1"}` and a new name `Aaron Example`, Aaron receives `person-2`, Alice keeps `person-1`, and the rewritten map holds both.
11. `test_home_paths_replaced`: `/home/alice/x/y.py` becomes `<HOME>/x/y.py`, `/Users/alice/z` becomes `<HOME>/z`, and `C:\Users\alice\w` becomes `<HOME>\w`.
12. `test_substitution_rule_applied_and_detect_only_rule_fails_build`: with terms `Example University => Anonymous Institution` and `labhost-07`, a file containing `example university` (lower case) is rewritten to `Anonymous Institution`; a file containing `labhost-07` makes the build exit 1 and the message gives its `path:line`.
13. `test_check_flags_file_and_directory_names_containing_terms`: with the term `alice`, a tree holding `alice/notes.py` and `alice_notes.py` yields findings for the directory name and the file name.
14. `test_check_flags_email_ipv4_mac_and_unlisted_url`: a file containing `alice@example.org`, `192.168.1.10`, `00:11:22:33:44:55` and `https://intranet.example.org/x` yields exactly four findings; `127.0.0.1`, `anonymous@example.invalid` and `https://physionet.org/content/x` (with `domain: physionet.org` in the allowlist) yield none.
15. `test_check_scans_binary_bytes_for_terms`: a file with bytes `b"\x89PNG\r\n\x1a\n" + b"Example University" + bytes(range(200, 256))` (not valid UTF-8) with the term `Example University` yields one finding.
16. `test_check_flags_pdf_author_and_image_metadata_markers`: `b"%PDF-1.4 /Author (Alice Example)"` is flagged as `pdf-author`; `b"%PDF-1.4 /Author ()"` is not; a byte string containing `Exif\x00\x00` and one containing `<x:xmpmeta` are flagged as `image-metadata`.
17. `test_check_exit_zero_on_clean_tree`: a tree with none of the above exits 0 and prints `0 findings`.
18. `test_snapshot_is_deterministic`: two builds from the same inputs give the same sorted file list, the same bytes for every file, and every mtime equal to the module constant `SNAPSHOT_MTIME`.
19. `test_archive_is_deterministic_and_has_no_owner_names`: two archives are byte-identical; members are sorted by name; every member has uid 0, gid 0, empty uname and gname, and mtime `SNAPSHOT_MTIME`.
20. `test_report_lists_proposed_adrs_and_states_publication_not_performed`: for an ADR file with `ADR-001` (Status accepted), `ADR-021 Code licence` (Status proposed), `ADR-022 Anonymised hosting` (Status proposed) and `ADR-023 Other` (Status proposed), the report lists ADR-021, ADR-022 and ADR-023 as awaiting confirmation, marks ADR-021 and ADR-022 `release-blocking` (title contains licence or hosting), does not list ADR-001, and contains the line `Publication: not performed; requires explicit human approval`.
21. `test_report_marks_unreviewed_terms_as_not_to_host`: without `--terms-reviewed` the report contains `terms reviewed by human: no` and `do not host`; with the flag it contains `terms reviewed by human: yes`.
22. `test_tools_have_no_network_or_remote_git_calls`: parsing both tool files with `ast`, none of `socket`, `urllib`, `http`, `requests`, `ftplib`, `smtplib`, `subprocess` is imported (the builder reads the file list from a file and never runs git).

## Passi

1. Create the branch `ws13-t03-anonymised-snapshot` from `main` and record `git remote -v`. Do not run any command that writes to a remote: pushing to any remote requires explicit human approval, which this task does not have; if a step seems to need it, stop and report. Read the venue rule in WS00-T01 `## Review mode and format` if the file exists.
2. Write `tests/tools/test_anonymise.py` with the 22 tests. Run `pytest tests/tools/test_anonymise.py -q` and watch every test fail because the tools do not exist.
3. Implement `tools/check_anonymity.py` one behaviour at a time (tests 13 to 17): text and binary scan for terms (case-insensitive, over contents, file names and directory names), the generic patterns (email, IPv4 except `127.0.0.1` and `0.0.0.0`, MAC address, remaining home paths, URLs whose host is not listed as `domain:` in the allowlist), the metadata markers, exit codes.
4. Implement `tools/make_anonymous_snapshot.py` (tests 1 to 12 and 18 to 21): read the file list, apply the allowlist and then the built-in denylist (`.git/`, `.claude/`, `prompt/`, `CLAUDE.md`, `docs/plan/`, `docs/source/`, `docs/superpowers/`, `paper/`, `outputs/`, `data/`, `__pycache__/`, `*.egg-info/`, virtual environments, `*.db`, `*.rvf`, `*.rvf.lock`, the workshop paper PDF and `analisi_RAL_clinical_pathways.md` at the repository root), apply the transformations (pyproject authors, maintainers and urls; `LICENSE` holder; `package.xml` and `setup.py` maintainer, author and url fields; pseudonyms for `reviewed_by` and `verified_by` in YAML and JSON; home paths; term substitutions), write files in sorted order with normalised mtime and mode, optionally write the tar archive, run the checker on the output, and write the report. The builder never runs git. The pseudonym map lives outside the snapshot (`outputs/anonymity/pseudonyms.yaml`).
5. Write `tools/anonymise_allowlist.txt`: `include:` lines for `README.md`, `LICENSE`, `pyproject.toml`, `src/ralmon/**`, `tests/**`, `ros2/**`, `experiments/**`, `configs/**`, `docs/install.md`, `docs/reproduce.md`, `docs/reproduce-reference.sha256`, `docs/benchmark/**` and `tools/reproduce.py`; comment lines explain each. `hardware/` and `study/` are not listed: lab and vignette material carries institution, partner and participant identifiers and a human adds them only after review. Add `domain:` lines only for public sites that the snapshot legitimately links (dataset and documentation sites), found by running the checker once, each with a comment naming why it is public.
6. Seed the private terms file `outputs/anonymity/terms.txt` (gitignored, never committed): author and committer names and emails from `git log --format='%an%n%ae%n%cn%n%ce' | sort -u`, `git config user.name` and `git config user.email`, author and maintainer strings found in `pyproject.toml`, `ros2/*/package.xml` and `LICENSE`, the login name and home directory name of the machine, and add `term => replacement` rules for institution names once known. Then ask the human to review and complete it with: institutions, laboratories and hospitals, collaborators, robot host names and serial numbers, network names, project and funding acronyms. Do not derive identities from memory. Pass `--terms-reviewed` only when the human confirms the review; otherwise the report says so.
7. Build and check, from the repository root with a clean working tree (`git status --porcelain` prints nothing): `git ls-files > outputs/anonymity/files.txt`, then `python tools/make_anonymous_snapshot.py --root . --files-from outputs/anonymity/files.txt --allowlist tools/anonymise_allowlist.txt --terms outputs/anonymity/terms.txt --pseudonyms outputs/anonymity/pseudonyms.yaml --out outputs/anonymised-snapshot --archive outputs/anonymised-snapshot.tar --report outputs/anonymised-release-report.md --adr-file docs/plan/03-decisions.md`, then `python tools/check_anonymity.py outputs/anonymised-snapshot --terms outputs/anonymity/terms.txt --allowlist tools/anonymise_allowlist.txt`. Fix each finding at its source in the repository (local commit) or add an explicit `term => replacement` rule; never edit the snapshot by hand.
8. Licence consistency (WS13-T01 could not check `ros2/` if it did not exist yet): compare the `license` field of `pyproject.toml`, the first line of `LICENSE` and `grep -h '<license>' ros2/*/package.xml | sort -u`; they must name the same licence. Re-read the `## Distribution and licence` section of `docs/benchmark/datasheet.md` if it exists and confirm that it cites an ADR that exists; otherwise the report and the completion note say that WS13-T04 is not done.
9. Write the hosting ADR (next free number after the licence ADR; check with `grep -n '^## ADR-' docs/plan/03-decisions.md | tail -3`), in the ADR format, with the confirmation tag and Status `proposed`:
   - Options: A, an anonymising proxy in front of a repository that lives under a pseudonymous account; B, an archive service that issues an anonymised or view-only link to the uploaded snapshot; C, the archive attached as supplementary material to the submission, only if the venue rules of WS00-T01 allow it; D, no external hosting during review, the paper announcing release on acceptance and the snapshot held ready (weakest for the inspection of circularity that motivates releasing the generator, analisi §10 objection 1).
   - Constraints: H1 the venue rule; H2 account hygiene (no institutional email, profile, avatar or name on a pseudonymous account); H3 what the service records (access logs, reviewer IP addresses, uploader identity) and for how long; H4 the link stays valid through review and rebuttal; H5 the wording of the link in the paper does not identify (WS12-T08 checks the paper source with `tools/check_anonymity.py`); H6 the de-anonymised release after acceptance is a separate human-approved action.
   - Decision: open. The human names the option and the service in this ADR before any hosting action; the agent takes no hosting action and records no default. Update the index line at the top of `03-decisions.md`.
10. Write `docs/anonymised-release.md` (maintainer documentation: it is not linked from the README and not allowlisted, so it stays out of the snapshot) with the H2 headings `## Purpose`, `## Approvals and the publication rule`, `## Procedure` (steps 6 to 8 above as numbered commands, plus the hosting step done by the human and the insertion of the link in the paper by WS12), `## What is removed or replaced` (a table: item, action; covering author names, affiliations, emails, pyproject authors and urls, copyright holder, package maintainers, reviewer names in registry and manifests, home paths, host names and MAC or IP addresses, git history and metadata, tooling artefacts, the workshop paper PDF, plan and source documents, image and PDF metadata), `## Hosting options (human decision)` (the ADR options; examples the human may check, listed without endorsement and unverified: an anonymising proxy for GitHub repositories, anonymised view-only links of an open-science archive, restricted or embargoed records of a research data archive), `## Residual risks` (writing style, the combination of robot model, dataset and locale, self-citations in the paper bibliography, identifiers inside binary files that the checker cannot read, service logs) and `## After acceptance` (the snapshot is derived and never the source of truth; the de-anonymised release needs the licence ADR confirmed, the copyright holder stated, and explicit human approval for any push or upload).
11. Run `ruff check src tests tools`, then `pytest tests/tools/test_anonymise.py -q`. Commit on the branch with messages `WS13-T03: <summary>`; the last commit sets `status: done` in this task file. Merge to `main` locally. Do not push (pushing to any remote requires explicit human approval).
12. Write the completion note: the report of step 7, the checker output, whether the human reviewed the terms file, the venue policy, and the open human actions (confirm the licence ADR, choose the hosting procedure in its ADR, verify unverified licences in the datasheet, approve any publication).

## Done when

From the repository root, each command exits 0:

- `pytest tests/tools/test_anonymise.py -q`
- `ruff check src tests tools`
- `python tools/check_anonymity.py outputs/anonymised-snapshot --terms outputs/anonymity/terms.txt --allowlist tools/anonymise_allowlist.txt`
- `test -f outputs/anonymised-snapshot.tar && test -f outputs/anonymised-release-report.md`
- `test ! -e outputs/anonymised-snapshot/.git && test ! -e outputs/anonymised-snapshot/docs/plan && test ! -e outputs/anonymised-snapshot/CLAUDE.md`

Also:

- `grep -c 'Publication: not performed; requires explicit human approval' outputs/anonymised-release-report.md` prints 1, and `grep -E 'terms reviewed by human: (yes|no)' outputs/anonymised-release-report.md` prints one line; if it says `no`, the completion note states that the snapshot must not be hosted.
- `grep -cE '^## (Purpose|Approvals and the publication rule|Procedure|What is removed or replaced|Hosting options \(human decision\)|Residual risks|After acceptance)$' docs/anonymised-release.md` prints `7`.
- `grep -nE '^## ADR-[0-9]+ .*hosting' docs/plan/03-decisions.md` prints one heading whose Status line begins with `proposed` and whose Decision states that the human names the option.
- `git remote -v` is identical at the start and at the end of the task (shown in the completion note).
