"""Bibliography gate of ADR-018 (WS03-T01).

Standard library only, no network. Run from the repository root:

    python3 tools/check_bib.py [--bib PATH ...] [--src PATH ...] [--all | --schema]

Default mode: every entry cited by a LaTeX or Markdown source must have ``verified = {true}``
together with the audit fields. ``--all`` gates every entry, ``--schema`` checks structure only.

Output: one finding per line (``KIND key [file:line]``, sorted by kind then key) and a final
summary line. Exit code 0 without findings, 1 with findings, 2 for usage or I/O errors.
See docs/related-work/bib-conventions.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

DEFAULT_BIB = "paper/refs/references.bib"
DEFAULT_SRC = "paper"
SOURCE_SUFFIXES = (".tex", ".md")

CITE_COMMANDS = (
    "citeyearpar",
    "citeauthor",
    "parencite",
    "autocite",
    "citealp",
    "citealt",
    "citeyear",
    "textcite",
    "nocite",
    "citep",
    "citet",
    "cite",
)
CITE_RE = re.compile(
    r"\\(?:" + "|".join(CITE_COMMANDS) + r")\*?(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]*)\}"
)
ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

AUDIT_FIELDS = ("verified_by", "verified_via", "author", "title", "year")
VENUE_FIELDS = (
    "booktitle",
    "journal",
    "publisher",
    "series",
    "howpublished",
    "institution",
    "organization",
)
SCHEMA_FIELDS = ("uncertain", "ref_status", "analisi", "task", "topic", "verified")
REF_STATUS_VALUES = ("recalled", "partial")
SKIPPED_TYPES = ("comment", "string", "preamble")

KINDS = ("MISSING", "UNVERIFIED", "INCOMPLETE", "DUPLICATE", "INVALID")


@dataclass(frozen=True, slots=True)
class Entry:
    """One bibliography entry; field names are lower case, values verbatim."""

    key: str
    type: str
    fields: dict[str, str] = field(hash=False)
    line: int
    source: str = ""


@dataclass(frozen=True, slots=True)
class Finding:
    kind: str
    key: str
    location: str

    def render(self) -> str:
        return f"{self.kind} {self.key} [{self.location}]"


class UsageError(Exception):
    """Usage or I/O error; the command line exits with code 2."""


# --------------------------------------------------------------------------- .bib scanner


def _match_close(text: str, start: int) -> int:
    """Index of the delimiter closing the one at ``start``; brace counting, ``-1`` if none."""
    opener = text[start]
    closer = "}" if opener == "{" else ")"
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i
    return -1


def _is_single_piece(raw: str) -> bool:
    """True when ``raw`` is one ``{...}`` or one ``"..."`` piece (no ``#``, no macro)."""
    if raw.startswith("{"):
        return _match_close(raw, 0) == len(raw) - 1
    if raw.startswith('"') and len(raw) >= 2 and raw.endswith('"'):
        depth = 0
        for i in range(1, len(raw) - 1):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
            elif raw[i] == '"' and depth == 0:
                return False
        return True
    return False


def _split_top_level_commas(body: str) -> list[str]:
    """Split ``body`` on commas outside braces and double quotes."""
    parts: list[str] = []
    depth = 0
    in_quotes = False
    current: list[str] = []
    for ch in body:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == '"' and depth == 0:
            in_quotes = not in_quotes
        if ch == "," and depth == 0 and not in_quotes:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


def _parse_value(raw: str) -> str:
    raw = raw.strip()
    if _is_single_piece(raw):
        return raw[1:-1].strip()
    return raw


def _parse_body(body: str) -> tuple[str, dict[str, str]]:
    key_part, *field_parts = _split_top_level_commas(body)
    fields: dict[str, str] = {}
    for part in field_parts:
        name, sep, raw = part.partition("=")
        if sep and name.strip():
            fields[name.strip().lower()] = _parse_value(raw)
    return key_part.strip(), fields


def parse_bib(text: str, source: str = "") -> list[Entry]:
    """Parse ``.bib`` text into entries in file order (no third-party library).

    ``@comment``, ``@string``, ``@preamble`` and ``%`` lines outside entries are skipped.
    """
    entries: list[Entry] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "%":
            newline = text.find("\n", i)
            i = n if newline == -1 else newline + 1
            continue
        if ch != "@":
            i += 1
            continue
        m = re.compile(r"@\s*([A-Za-z]+)\s*").match(text, i)
        if m is None:
            i += 1
            continue
        entry_type = m.group(1).lower()
        open_at = m.end()
        if open_at >= n or text[open_at] not in "{(":
            # e.g. "@comment free text": skip to the end of the line
            newline = text.find("\n", open_at)
            i = n if newline == -1 else newline + 1
            continue
        close_at = _match_close(text, open_at)
        if close_at == -1:
            close_at = n - 1
        if entry_type not in SKIPPED_TYPES:
            key, fields = _parse_body(text[open_at + 1 : close_at])
            entries.append(
                Entry(key, entry_type, fields, text.count("\n", 0, i) + 1, source)
            )
        i = close_at + 1
    return entries


# --------------------------------------------------------------------------- citations


def _strip_latex_comments(text: str) -> str:
    """Remove text after an unescaped ``%`` on every line; newlines are kept."""
    lines: list[str] = []
    for line in text.split("\n"):
        i = 0
        while i < len(line):
            if line[i] == "\\":
                i += 2
                continue
            if line[i] == "%":
                line = line[:i]
                break
            i += 1
        lines.append(line)
    return "\n".join(lines)


def extract_citations(text: str, latex_comments: bool) -> list[tuple[str, int]]:
    """Return ``(key, line)`` for every cited key; ``line`` is the start of the command."""
    if latex_comments:
        text = _strip_latex_comments(text)
    found: list[tuple[str, int]] = []
    for m in CITE_RE.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        for raw_key in m.group(1).split(","):
            key = raw_key.strip()
            if key:
                found.append((key, line))
    return found


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise UsageError(f"cannot read {path}: {exc}") from exc


def scan_sources(paths: list[Path]) -> list[tuple[str, str, int]]:
    """Citations ``(key, file, line)`` from files and directories (``*.tex`` and ``*.md``)."""
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(
                sorted(
                    p
                    for p in path.rglob("*")
                    if p.is_file() and p.suffix in SOURCE_SUFFIXES
                )
            )
        else:
            files.append(path)
    found: list[tuple[str, str, int]] = []
    for file in files:
        for key, line in extract_citations(
            _read(file), latex_comments=file.suffix == ".tex"
        ):
            found.append((key, str(file), line))
    return found


# --------------------------------------------------------------------------- checks


def _has(entry: Entry, name: str) -> bool:
    return bool(entry.fields.get(name, "").strip())


def _location(entry: Entry) -> str:
    return f"{entry.source}:{entry.line}"


def _incomplete(entry: Entry) -> bool:
    if entry.fields.get("verified") != "true":
        return False
    on = entry.fields.get("verified_on", "")
    if not ISO_DATE_RE.fullmatch(on):
        return True
    try:
        date.fromisoformat(on)
    except ValueError:
        return True
    return not all(_has(entry, f) for f in AUDIT_FIELDS) or not any(
        _has(entry, f) for f in VENUE_FIELDS
    )


def _schema_invalid(entry: Entry) -> bool:
    fields = entry.fields
    if not all(_has(entry, f) for f in SCHEMA_FIELDS):
        return True
    return (
        fields["uncertain"] not in ("true", "false")
        or fields["ref_status"] not in REF_STATUS_VALUES
    )


def check(
    entries: list[Entry],
    cited: dict[str, str],
    *,
    gate_all: bool = False,
    schema: bool = False,
) -> list[Finding]:
    """Findings for ``entries``; ``cited`` maps each cited key to its first ``file:line``."""
    found: dict[tuple[str, str], str] = {}

    def add(kind: str, key: str, location: str) -> None:
        found.setdefault((kind, key), location)

    seen: set[str] = set()
    for entry in entries:
        if entry.key in seen:
            add("DUPLICATE", entry.key, _location(entry))
        seen.add(entry.key)
        verified = entry.fields.get("verified")
        if verified is not None and verified not in ("true", "false"):
            add("INVALID", entry.key, _location(entry))
        if schema and _schema_invalid(entry):
            add("INVALID", entry.key, _location(entry))
        if _incomplete(entry):
            add("INCOMPLETE", entry.key, _location(entry))
        if not schema and (gate_all or entry.key in cited) and verified != "true":
            add("UNVERIFIED", entry.key, _location(entry))
    if not schema:
        for key, location in cited.items():
            if key not in seen:
                add("MISSING", key, location)
    return sorted(
        (Finding(kind, key, loc) for (kind, key), loc in found.items()),
        key=lambda f: (f.kind, f.key),
    )


def summary_line(entries: int, cited: int, findings: list[Finding]) -> str:
    counts = {kind: sum(1 for f in findings if f.kind == kind) for kind in KINDS}
    status = "FAIL" if findings else "OK"
    return (
        f"entries={entries} cited={cited} unverified={counts['UNVERIFIED']} "
        f"missing={counts['MISSING']} incomplete={counts['INCOMPLETE']} "
        f"duplicate={counts['DUPLICATE']} invalid={counts['INVALID']} status={status}"
    )


# --------------------------------------------------------------------------- command line


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # argparse default is already exit code 2
        self.print_usage(sys.stderr)
        raise UsageError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        description="Bibliography gate: fail when a cited entry is unverified."
    )
    parser.add_argument(
        "--bib",
        action="append",
        type=Path,
        help=f"bib file, repeatable (default {DEFAULT_BIB})",
    )
    parser.add_argument(
        "--src",
        action="append",
        type=Path,
        help=f"file or directory with citations, repeatable (default {DEFAULT_SRC})",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--all", action="store_true", help="treat every entry as cited")
    mode.add_argument(
        "--schema",
        action="store_true",
        help="structural checks on all entries; ignore --src",
    )
    return parser


def _run(args: argparse.Namespace) -> bool:
    """Run the checks and print the report; True when there is at least one finding."""
    bib_paths: list[Path] = args.bib or [Path(DEFAULT_BIB)]
    src_paths: list[Path] = args.src or (
        [] if args.all or args.schema else [Path(DEFAULT_SRC)]
    )
    for path in [*bib_paths, *src_paths]:
        if not path.exists():
            raise UsageError(f"path does not exist: {path}")

    entries: list[Entry] = []
    for path in bib_paths:
        entries.extend(parse_bib(_read(path), str(path)))

    cited: dict[str, str] = {}
    if not args.schema:
        for key, file, line in scan_sources(src_paths):
            cited.setdefault(key, f"{file}:{line}")
        if "*" in cited or args.all:
            star_location = cited.get("*", "all")
            for entry in entries:
                cited.setdefault(entry.key, star_location)
        cited.pop("*", None)

    findings = check(entries, cited, gate_all=args.all, schema=args.schema)
    lines = [f.render() for f in findings]
    lines.append(summary_line(len(entries), len(cited), findings))
    print("\n".join(lines))
    return bool(findings)


def main(argv: list[str]) -> int:
    """Entry point; returns the process exit code (0 no findings, 1 findings, 2 usage or I/O)."""
    try:
        args = _build_parser().parse_args(argv)
        return 1 if _run(args) else 0
    except UsageError as exc:
        print(f"check_bib.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
