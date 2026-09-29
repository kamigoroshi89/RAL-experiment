---
id: WS03-T01
title: Bibliography infrastructure with verified flag and check tool
workstream: WS03-related-work
owner: agent
status: ready
depends_on: []
critical_path: false
non_negotiable: false
estimate_pd: 1
sources: ["analisi §3 (note)", "analisi §7"]
interfaces: []
review_items: ["AE-3"]
---
## Obiettivo

Create the bibliography infrastructure of ADR-018: an empty `paper/refs/references.bib` with a documented entry schema whose `verified` flag defaults to false, and the stdlib-only tool `tools/check_bib.py` that exits non-zero when a cited entry is unverified (and in the other failure cases listed below). The concrete outputs are the tool, its pytest suite with hand-computed fixtures, the header-only bibliography file and `docs/related-work/bib-conventions.md`. The tool is the build gate that WS12 later runs; it never touches the network.

## Contesto

- `docs/plan/03-decisions.md`, ADR-018 (reference verification is a human step; the paper build fails if a cited entry is unverified).
- `docs/plan/workstreams/WS03-related-work/README.md`, sections "Bibliography entry schema" and "Key naming" (binding schema, copied by this task into `bib-conventions.md`).
- `docs/source/analisi.md` §3 (note on references and daggers) and §7 (30 to 35 references in the paper).
- `docs/plan/01-conventions.md` sections 2 and 3 (Python 3.11 or newer, ruff, pytest, deterministic tests, no network).

## File toccati

1. `tools/check_bib.py` (create)
2. `tests/tools/test_check_bib.py` (create)
3. `tests/tools/fixtures/` (create; small hand-written `.bib` and `.tex` fixtures, one directory counts as one path)
4. `paper/refs/references.bib` (create; header comment only, zero entries)
5. `docs/related-work/bib-conventions.md` (create)

## Test

Behaviour under test (this is the specification of the tool).

- Command line: `python3 tools/check_bib.py [--bib PATH ...] [--src PATH ...] [--all | --schema]`. `--bib` is repeatable (default `paper/refs/references.bib`); several files are merged. `--src` is repeatable, each a file or a directory (directories are scanned recursively for `*.tex` and `*.md`; default `paper`). `--all` treats every entry as cited. `--schema` performs structural checks on all entries and ignores `--src`. `--all` and `--schema` are mutually exclusive.
- Parsing (regex or a small scanner, no third-party library): `@type{key, field = {value} | "value" | bare, ...}`, nested braces inside values, field names and entry types case-insensitive, `@comment`, `@string`, `@preamble` and `%` lines skipped, line number of each entry recorded. Values that use `#` concatenation or string macros are kept verbatim.
- Citation extraction from source files: commands `\cite`, `\citep`, `\citet`, `\citealp`, `\citealt`, `\citeauthor`, `\citeyear`, `\citeyearpar`, `\parencite`, `\textcite`, `\autocite`, `\nocite`, optional star, zero to two optional arguments in brackets, comma-separated keys (possibly spread over several lines). In `.tex` files, text after an unescaped `%` is ignored; in `.md` files nothing is treated as a comment. `\nocite{*}` cites every entry.
- Findings, one line each, `KIND key [file:line]`, sorted by kind then key: `MISSING` (cited key not in any bib), `UNVERIFIED` (cited entry whose `verified` is not `true`; an absent field counts as false; with `--all`, every entry), `INCOMPLETE` (entry with `verified = {true}` that lacks any of: `verified_by`; `verified_on` in `YYYY-MM-DD` form; `verified_via`; `author`; `title`; `year`; at least one venue field among `booktitle`, `journal`, `publisher`, `series`, `howpublished`, `institution`, `organization`), `DUPLICATE` (same key twice, also across `--bib` files, cited or not), `INVALID` (all modes: `verified` not `true` or `false`; `--schema` only: missing `uncertain`, `ref_status`, `analisi`, `task`, `topic` or `verified`, `uncertain` not `true` or `false`, `ref_status` not `recalled` or `partial`).
- Last line: `entries=E cited=C unverified=U missing=M incomplete=I duplicate=D invalid=V status=OK` or `status=FAIL`. `cited` is the number of distinct cited keys (missing ones included; in `--schema` mode 0).
- Exit codes: 0 when there are no findings, 1 when there is at least one, 2 for usage or I/O errors (a `--bib` or `--src` path that does not exist, unreadable file, both `--all` and `--schema`). A `--src` that exists but contains no citations is not an error.

Fixtures (hand-written, in `tests/tools/fixtures/`), expected values computed by hand:

- `mixed.bib`: four entries in this order: `alpha-verified` (`verified = {true}`, with `verified_by`, `verified_on = {2026-01-01}`, `verified_via`, `author`, `title`, `year`, `booktitle`), `beta-unverified` (`verified = {false}`), `gamma-nofield` (no `verified` field), `delta-uncited` (`verified = {false}`).
- `mixed.tex`: line 1 `Text \cite{alpha-verified,beta-unverified}.`; line 2 `% \cite{delta-uncited}`; line 3 `See \citep[p.~3]{gamma-nofield} and \citet*{missing-key}.` Cited set: `alpha-verified`, `beta-unverified`, `gamma-nofield`, `missing-key` (4 keys). Expected findings: `UNVERIFIED beta-unverified`, `UNVERIFIED gamma-nofield`, `MISSING missing-key`; summary `entries=4 cited=4 unverified=2 missing=1 incomplete=0 duplicate=0 invalid=0 status=FAIL`; exit 1.
- `ok.bib` (two verified, complete entries `one` and `two`) and `ok.tex` (`\cite{one} and \parencite{two}`): summary `entries=2 cited=2 unverified=0 missing=0 incomplete=0 duplicate=0 invalid=0 status=OK`; exit 0.
- `dup.bib` (two entries with key `same`), `badvalue.bib` (one entry with `verified = {yes}`), `incomplete.bib` (one entry `inc` with `verified = {true}` and no `verified_by`), `schema_ok.bib` (one entry with all seven required custom fields and `verified = {false}`), `schema_bad.bib` (same entry without `ref_status`), `nocite.tex` (`\nocite{*}`).

Pytest tests in `tests/tools/test_check_bib.py` (CLI tests call `subprocess.run([sys.executable, "tools/check_bib.py", ...])` from the repository root; unit tests load the module with `importlib.util.spec_from_file_location`). Write all of them first; they must fail because the tool does not exist yet.

1. `test_parse_bib_returns_entries_in_file_order`: `mixed.bib` yields keys `[alpha-verified, beta-unverified, gamma-nofield, delta-uncited]`; `gamma-nofield` has no `verified` field.
2. `test_parse_bib_handles_nested_braces_and_quotes`: `title = {Conformal prediction for {STL} runtime verification}` is returned without the outer braces and with the inner braces kept; `year = 2023` (bare) and `year = "2023"` both give `2023`.
3. `test_parse_bib_skips_comment_string_preamble`: `@comment{...}`, `@string{...}`, `@preamble{...}` and `%` lines produce no entries.
4. `test_extract_citations_variants`: text with `\cite{a,b}`, `\citep[see][p.~3]{c}`, `\citet*{d}`, `\autocite{e}` gives `{a,b,c,d,e}`.
5. `test_extract_citations_ignores_latex_comments`: a fully commented `\cite{x}` and a trailing `% \cite{y}` are ignored; `50\% of \cite{z}` still yields `z` (escaped percent).
6. `test_extract_citations_multiline_key_list`: `\cite{a,\n  b}` yields `{a,b}` and reports the line of the command start.
7. `test_scan_directory_reads_tex_and_md_only`: a temporary directory with `x.tex`, `y.md`, `z.bib`, `w.txt` scans only `x.tex` and `y.md`; in `y.md` a `%` does not hide a later `\cite{k}` on the same line.
8. `test_cli_fails_on_unverified_cited_entry`: `mixed.bib` with `mixed.tex` exits 1, prints the three findings above and the exact summary line above.
9. `test_cli_passes_when_all_cited_entries_verified`: `ok.bib` with `ok.tex` exits 0 with the exact summary above.
10. `test_uncited_unverified_entry_is_ignored`: `mixed.bib` with a temporary tex citing only `alpha-verified` exits 0.
11. `test_missing_verified_field_counts_as_unverified`: `gamma-nofield` alone, cited, gives `UNVERIFIED gamma-nofield`, exit 1.
12. `test_verified_true_requires_audit_fields`: `incomplete.bib` with a tex citing `inc` prints `INCOMPLETE inc`, exit 1.
13. `test_duplicate_key_is_reported`: `dup.bib` prints `DUPLICATE same`, exit 1, even when nothing is cited.
14. `test_invalid_verified_value_is_reported`: `badvalue.bib` prints `INVALID` for its key, exit 1, even when uncited.
15. `test_nocite_star_cites_every_entry`: `mixed.bib` with `nocite.tex` reports `cited=4` and `UNVERIFIED` for the three unverified or missing-field entries that exist (`beta-unverified`, `gamma-nofield`, `delta-uncited`), exit 1.
16. `test_all_flag_gates_every_entry`: `--all` on `mixed.bib` reports `UNVERIFIED` for exactly `beta-unverified`, `gamma-nofield`, `delta-uncited`, and not for `alpha-verified`.
17. `test_schema_mode_accepts_unverified_entries_and_requires_custom_fields`: `--schema` on `schema_ok.bib` exits 0 with `status=OK`; on `schema_bad.bib` prints `INVALID` and exits 1; no `--src` is required.
18. `test_multiple_bib_files_merge_and_cross_file_duplicates_fail`: `--bib ok.bib --bib mixed.bib` merges (6 entries); `--bib ok.bib --bib ok.bib` reports `DUPLICATE one` and `DUPLICATE two`.
19. `test_exit_code_2_on_missing_paths_and_bad_flags`: nonexistent `--bib`, nonexistent `--src`, and `--all --schema` together each exit 2.
20. `test_output_is_sorted_and_deterministic`: two runs on `mixed` give byte-identical stdout, and finding lines are sorted by kind then key.
21. `test_tool_imports_only_stdlib`: parse `tools/check_bib.py` with `ast`; every imported top-level module name is in `sys.stdlib_module_names`.
22. `test_repo_bib_entries_all_have_explicit_verified_field`: every entry of `paper/refs/references.bib` has `verified` equal to `true` or `false` (passes vacuously while the file has no entries; it protects the T05 merge).

## Passi

1. Create `tests/tools/fixtures/` with the fixtures above, then `tests/tools/test_check_bib.py` with the 22 tests. Run `python3 -m pytest tests/tools -q` and confirm it fails (import or file-not-found errors). If `pytest` is not installed in the environment, report that in the completion note instead of changing dependency lists; WS05-T01 owns the toolchain.
2. Implement the `.bib` scanner in `tools/check_bib.py` (functions for parsing, citation extraction, checking, and `main(argv) -> int`). Make tests 1 to 3 pass.
3. Implement citation extraction and directory scanning. Make tests 4 to 7 pass.
4. Implement the checks, the summary line, sorting and exit codes, then the `--all` and `--schema` modes. Make tests 8 to 20 pass.
5. Add `if __name__ == "__main__": raise SystemExit(main(sys.argv[1:]))`. Make tests 21 and 22 pass. Refactor for readability without changing behaviour.
6. Create `paper/refs/references.bib` containing only a comment header: purpose, the pointer to `docs/related-work/bib-conventions.md`, the rule that `verified` defaults to false and only a human sets it to true, and the statement that T05 merges the fragments from `paper/refs/fragments/`. No entries.
7. Write `docs/related-work/bib-conventions.md` with the headings `## Entry schema`, `## Key naming`, `## Verification workflow (ADR-018)`, `## check_bib.py usage and exit codes`. The first two sections are copied from the WS03 README; the third describes T06 in five lines; the fourth lists the command line, finding kinds, summary line and exit codes above and the three modes (default gate on cited entries, `--all`, `--schema`).
8. Run the commands under "Done when". Commit with message `WS03-T01: add bibliography infrastructure and check_bib gate`, set `status: done` in this file and paste the outputs into the completion note.

## Done when

- `python3 -m pytest tests/tools -q` exits 0 (22 tests pass).
- `python3 tools/check_bib.py --schema` exits 0 and prints `entries=0 ... status=OK`.
- `python3 tools/check_bib.py` exits 0 (no citations under `paper` yet).
- `ruff check tools/check_bib.py tests/tools` exits 0 when ruff is installed (state in the completion note if it is not).
- `test -f paper/refs/references.bib && test -f docs/related-work/bib-conventions.md && grep -c '^## ' docs/related-work/bib-conventions.md` prints 4.
