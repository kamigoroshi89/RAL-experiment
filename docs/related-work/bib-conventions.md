# Bibliography conventions

Binding for WS03 and for every later task that adds a reference. The bibliography lives in `paper/refs/references.bib`; the build gate is `tools/check_bib.py` (ADR-018, WS03-T01).

## Entry schema

Binding for T01 to T05.

| Field | Required | Value | Set by |
|---|---|---|---|
| `verified` | yes | `{false}` or `{true}`; absent counts as false for the tool | agents: `{false}`; human (T06): `{true}` |
| `uncertain` | yes | `{true}` if analisi marks the item with a dagger, else `{false}`. If the dagger covers a conference and an extended version (Bortolussi; Gombolay), both entries are `{true}` | agent; human may set `{false}` after confirming |
| `ref_status` | yes | `{recalled}`: analisi gives an author or organisation and at least one of year and venue. `{partial}`: otherwise (only a name, a number, or authors without year and venue) | agent |
| `analisi` | yes | analisi section, for example `{3.2}`; for items taken from the reviewer text `{2 (R1 weakness 10)}` | agent |
| `task` | yes | producing task, for example `{WS03-T02}` | agent |
| `topic` | yes | one-line English description of what the work is and why analisi cites it; never printed by bibliography styles | agent |
| `author` | at least one of `author`, `title` | Surnames only, as in analisi, joined by `and`; `and others` for "et al."; corporate author in double braces, for example `{{Royal College of Physicians}}`. Non-ASCII letters as LaTeX accents (`Donz{\'e}`, `Ni{\v c}kovi{\'c}`, `Co{\c s}ar`) | agent; human completes first names |
| `title` | only if analisi quotes a title, or the only identity of the item is a name written in analisi (tools without a paper, standards) | as written in analisi | agent; human completes |
| `year` | only if analisi gives it | four digits | agent |
| venue field | only if analisi gives it | `booktitle` (conference), `journal` (article), `booktitle` plus `series` plus `volume` (book chapter), `series` or `publisher` (book); abbreviations kept as in analisi (`ICCPS`, `CAV`) | agent; human expands |
| `verified_by`, `verified_on`, `verified_via` | when `verified = {true}` | name; ISO date `YYYY-MM-DD`; source consulted (DBLP, Google Scholar, publisher page) | human |
| `verify_notes` | optional | corrections made | human |

Entry types: `@inproceedings` for a conference, `@article` for a journal, `@incollection` for a book chapter, `@book` for a book or a SpringerBriefs volume, `@misc` when the venue is not given, and for standards, guidance and tools. The human may change the type during T06.

Nothing is added that analisi does not state. A field that analisi does not give is omitted, not filled from memory.
## Key naming

`<first-author-surname>-<short-topic>`, lower case ASCII, hyphens, no year and no venue (T06 may correct both, so keys never encode them). Where analisi names a conference version and an extended version of one work, two entries are created with suffixes `-conf` and `-ext`; T05 cites one of them and records the choice.

## Verification workflow (ADR-018)

1. Agents (WS03-T02 to T04) write entries from analisi only, with `verified = {false}`; nothing is added from memory.
2. WS03-T05 merges the fragments into `paper/refs/references.bib`; no entry is verified at that point.
3. A human (WS03-T06) checks each cited entry on DBLP, Google Scholar or the publisher page, corrects fields, and only then sets `verified = {true}` with `verified_by`, `verified_on` (`YYYY-MM-DD`) and `verified_via`.
4. `tools/check_bib.py` fails while any cited entry is unverified or incomplete; WS12 runs it as the paper build gate, so agents cannot bypass the human step.
5. Citations added later by WS12 go through the same verification before the paper build (WS12-T07 audits the claims). No network access is assumed for agents.

## check_bib.py usage and exit codes

```
python3 tools/check_bib.py [--bib PATH ...] [--src PATH ...] [--all | --schema]
```

- `--bib` (repeatable, default `paper/refs/references.bib`): bibliography files, merged in order.
- `--src` (repeatable, default `paper`): files or directories; directories are scanned recursively for `*.tex` and `*.md`. In `.tex` files text after an unescaped `%` is ignored; in `.md` files nothing is a comment. Cite commands: `\cite`, `\citep`, `\citet`, `\citealp`, `\citealt`, `\citeauthor`, `\citeyear`, `\citeyearpar`, `\parencite`, `\textcite`, `\autocite`, `\nocite` (optional star and optional arguments); `\nocite{*}` cites every entry.

Modes (`--all` and `--schema` are mutually exclusive):

- Default gate: only cited entries must be verified. Sources are read from `--src`.
- `--all`: every entry is treated as cited (sources are scanned only if `--src` is given).
- `--schema`: structural checks on all entries, `--src` is ignored; unverified entries are accepted. Use it on the repository bibliography after every merge.

Findings, one per line as `KIND key [file:line]`, sorted by kind then key:

| Kind | Meaning |
|---|---|
| `MISSING` | cited key defined in no bib file |
| `UNVERIFIED` | cited entry (every entry with `--all`) whose `verified` is not `true`; an absent field counts as false |
| `INCOMPLETE` | entry with `verified = {true}` lacking `verified_by`, `verified_on` (`YYYY-MM-DD`), `verified_via`, `author`, `title`, `year`, or a venue field (`booktitle`, `journal`, `publisher`, `series`, `howpublished`, `institution`, `organization`) |
| `DUPLICATE` | key defined twice, also across `--bib` files, cited or not |
| `INVALID` | `verified` not `true` or `false` (all modes); with `--schema` also a missing `uncertain`, `ref_status`, `analisi`, `task`, `topic` or `verified`, `uncertain` not `true` or `false`, `ref_status` not `recalled` or `partial` |

Last line: `entries=E cited=C unverified=U missing=M incomplete=I duplicate=D invalid=V status=OK` (or `status=FAIL`). `cited` counts distinct cited keys, missing ones included, and is 0 with `--schema`.

Exit codes: 0 no findings; 1 at least one finding; 2 usage or I/O error (nonexistent `--bib` or `--src`, unreadable file, `--all` with `--schema`). A `--src` without citations is not an error.
