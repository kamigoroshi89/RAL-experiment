"""Tests for tools/check_bib.py (WS03-T01). Fixtures in tests/tools/fixtures are hand-written."""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "check_bib.py"
FIX = Path(__file__).resolve().parent / "fixtures"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_bib", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_bib"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cb() -> ModuleType:
    return _load()


def _run(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "tools/check_bib.py", *map(str, args)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def _findings(out: str) -> list[str]:
    return out.strip().splitlines()[:-1]


def _summary(out: str) -> str:
    return out.strip().splitlines()[-1]


def _kinds_keys(out: str) -> list[tuple[str, str]]:
    return [(line.split()[0], line.split()[1]) for line in _findings(out)]


def test_parse_bib_returns_entries_in_file_order(cb: ModuleType) -> None:
    entries = cb.parse_bib((FIX / "mixed.bib").read_text(encoding="utf-8"))
    assert [e.key for e in entries] == [
        "alpha-verified",
        "beta-unverified",
        "gamma-nofield",
        "delta-uncited",
    ]
    assert "verified" not in entries[2].fields
    assert entries[0].fields["verified"] == "true"
    assert entries[0].line == 2


def test_parse_bib_handles_nested_braces_and_quotes(cb: ModuleType) -> None:
    text = (
        "@Article{k1,\n"
        "  TITLE = {Conformal prediction for {STL} runtime verification},\n"
        "  year = 2023,\n"
        '  Journal = "J. Fixture"\n'
        "}\n"
        '@misc{k2, year = "2023"}\n'
    )
    entries = cb.parse_bib(text)
    assert entries[0].type == "article"
    assert entries[0].fields["title"] == "Conformal prediction for {STL} runtime verification"
    assert entries[0].fields["year"] == "2023"
    assert entries[0].fields["journal"] == "J. Fixture"
    assert entries[1].fields["year"] == "2023"


def test_parse_bib_skips_comment_string_preamble(cb: ModuleType) -> None:
    text = (
        "% a percent line @misc{notanentry, title = {x}}\n"
        "@comment{ignored {nested} text}\n"
        '@string{foo = "bar"}\n'
        '@preamble{"\\newcommand{\\x}{y}"}\n'
        "@misc{real, title = {T}, note = foo # {baz}}\n"
    )
    entries = cb.parse_bib(text)
    assert [e.key for e in entries] == ["real"]
    assert entries[0].fields["note"] == "foo # {baz}"


def test_extract_citations_variants(cb: ModuleType) -> None:
    text = r"\cite{a,b} \citep[see][p.~3]{c} \citet*{d} \autocite{e}"
    assert {key for key, _ in cb.extract_citations(text, latex_comments=True)} == {
        "a",
        "b",
        "c",
        "d",
        "e",
    }


def test_extract_citations_ignores_latex_comments(cb: ModuleType) -> None:
    text = "% \\cite{x}\nText % \\cite{y}\n50\\% of \\cite{z}\n"
    assert {key for key, _ in cb.extract_citations(text, latex_comments=True)} == {"z"}


def test_extract_citations_multiline_key_list(cb: ModuleType) -> None:
    text = "first line\nsee \\cite{a,\n  b}\n"
    found = cb.extract_citations(text, latex_comments=True)
    assert sorted(found) == [("a", 2), ("b", 2)]


def test_scan_directory_reads_tex_and_md_only(cb: ModuleType, tmp_path: Path) -> None:
    (tmp_path / "x.tex").write_text("\\cite{from-tex}\n", encoding="utf-8")
    (tmp_path / "y.md").write_text("50% and \\cite{k}\n", encoding="utf-8")
    (tmp_path / "z.bib").write_text("\\cite{from-bib}\n", encoding="utf-8")
    (tmp_path / "w.txt").write_text("\\cite{from-txt}\n", encoding="utf-8")
    keys = {c[0] for c in cb.scan_sources([tmp_path])}
    assert keys == {"from-tex", "k"}


def test_cli_fails_on_unverified_cited_entry() -> None:
    r = _run("--bib", FIX / "mixed.bib", "--src", FIX / "mixed.tex")
    assert r.returncode == 1
    assert _kinds_keys(r.stdout) == [
        ("MISSING", "missing-key"),
        ("UNVERIFIED", "beta-unverified"),
        ("UNVERIFIED", "gamma-nofield"),
    ]
    assert _summary(r.stdout) == (
        "entries=4 cited=4 unverified=2 missing=1 incomplete=0 duplicate=0 invalid=0 status=FAIL"
    )


def test_cli_passes_when_all_cited_entries_verified() -> None:
    r = _run("--bib", FIX / "ok.bib", "--src", FIX / "ok.tex")
    assert r.returncode == 0
    assert _findings(r.stdout) == []
    assert _summary(r.stdout) == (
        "entries=2 cited=2 unverified=0 missing=0 incomplete=0 duplicate=0 invalid=0 status=OK"
    )


def test_uncited_unverified_entry_is_ignored(tmp_path: Path) -> None:
    tex = tmp_path / "only-alpha.tex"
    tex.write_text("\\cite{alpha-verified}\n", encoding="utf-8")
    r = _run("--bib", FIX / "mixed.bib", "--src", tex)
    assert r.returncode == 0
    assert _findings(r.stdout) == []


def test_missing_verified_field_counts_as_unverified(tmp_path: Path) -> None:
    bib = tmp_path / "gamma.bib"
    bib.write_text(
        "@misc{gamma-nofield, author = {F}, title = {G}, howpublished = {x}}\n",
        encoding="utf-8",
    )
    tex = tmp_path / "g.tex"
    tex.write_text("\\cite{gamma-nofield}\n", encoding="utf-8")
    r = _run("--bib", bib, "--src", tex)
    assert r.returncode == 1
    assert _kinds_keys(r.stdout) == [("UNVERIFIED", "gamma-nofield")]


def test_verified_true_requires_audit_fields(tmp_path: Path) -> None:
    tex = tmp_path / "inc.tex"
    tex.write_text("\\cite{inc}\n", encoding="utf-8")
    r = _run("--bib", FIX / "incomplete.bib", "--src", tex)
    assert r.returncode == 1
    assert _kinds_keys(r.stdout) == [("INCOMPLETE", "inc")]


def test_duplicate_key_is_reported(tmp_path: Path) -> None:
    r = _run("--bib", FIX / "dup.bib", "--src", tmp_path)
    assert r.returncode == 1
    assert ("DUPLICATE", "same") in _kinds_keys(r.stdout)
    assert "duplicate=1" in _summary(r.stdout)


def test_invalid_verified_value_is_reported(tmp_path: Path) -> None:
    r = _run("--bib", FIX / "badvalue.bib", "--src", tmp_path)
    assert r.returncode == 1
    assert _kinds_keys(r.stdout) == [("INVALID", "bad")]


def test_nocite_star_cites_every_entry() -> None:
    r = _run("--bib", FIX / "mixed.bib", "--src", FIX / "nocite.tex")
    assert r.returncode == 1
    assert _kinds_keys(r.stdout) == [
        ("UNVERIFIED", "beta-unverified"),
        ("UNVERIFIED", "delta-uncited"),
        ("UNVERIFIED", "gamma-nofield"),
    ]
    assert "cited=4 " in _summary(r.stdout)


def test_all_flag_gates_every_entry() -> None:
    r = _run("--bib", FIX / "mixed.bib", "--all")
    assert r.returncode == 1
    assert {k for kind, k in _kinds_keys(r.stdout) if kind == "UNVERIFIED"} == {
        "beta-unverified",
        "gamma-nofield",
        "delta-uncited",
    }


def test_schema_mode_accepts_unverified_entries_and_requires_custom_fields() -> None:
    ok = _run("--bib", FIX / "schema_ok.bib", "--schema")
    assert ok.returncode == 0
    assert _summary(ok.stdout).endswith("status=OK")
    bad = _run("--bib", FIX / "schema_bad.bib", "--schema")
    assert bad.returncode == 1
    assert _kinds_keys(bad.stdout) == [("INVALID", "schema-bad")]


def test_multiple_bib_files_merge_and_cross_file_duplicates_fail() -> None:
    merged = _run("--bib", FIX / "ok.bib", "--bib", FIX / "mixed.bib", "--all")
    assert "entries=6 " in _summary(merged.stdout)
    dup = _run("--bib", FIX / "ok.bib", "--bib", FIX / "ok.bib", "--schema")
    assert dup.returncode == 1
    kinds = _kinds_keys(dup.stdout)
    assert ("DUPLICATE", "one") in kinds
    assert ("DUPLICATE", "two") in kinds


def test_exit_code_2_on_missing_paths_and_bad_flags(tmp_path: Path) -> None:
    assert _run("--bib", tmp_path / "nope.bib", "--schema").returncode == 2
    assert _run("--bib", FIX / "ok.bib", "--src", tmp_path / "nope").returncode == 2
    assert _run("--bib", FIX / "ok.bib", "--all", "--schema").returncode == 2


def test_no_citations_in_src_is_not_an_error(tmp_path: Path) -> None:
    (tmp_path / "empty.tex").write_text("no citations here\n", encoding="utf-8")
    r = _run("--bib", FIX / "mixed.bib", "--src", tmp_path)
    assert r.returncode == 0
    assert "cited=0 " in _summary(r.stdout)


def test_output_is_sorted_and_deterministic() -> None:
    args = ("--bib", FIX / "mixed.bib", "--src", FIX / "mixed.tex")
    first, second = _run(*args), _run(*args)
    assert first.stdout == second.stdout
    keys = _kinds_keys(first.stdout)
    assert keys == sorted(keys)


def test_tool_imports_only_stdlib() -> None:
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    assert names
    assert names <= set(sys.stdlib_module_names)


def test_repo_bib_entries_all_have_explicit_verified_field(cb: ModuleType) -> None:
    bib = REPO / "paper" / "refs" / "references.bib"
    for entry in cb.parse_bib(bib.read_text(encoding="utf-8")):
        assert entry.fields.get("verified") in {"true", "false"}, entry.key
