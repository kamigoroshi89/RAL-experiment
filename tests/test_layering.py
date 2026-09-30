"""Package graph of src/ralmon follows 01-conventions.md section 1 (WS05-T01)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PKG_DIR = SRC / "ralmon"

# Allowed dependency edges (importer -> imported). `benchmark` is wider than the
# text of 01-conventions.md section 1 (WS04-T02 reads the registry, WS04-T10 runs
# the monitor); the API reconciliation ADR of WS05-T01 records the amendment.
ALLOWED_EDGES: dict[str, set[str]] = {
    "signals": set(),
    "spec": {"signals"},
    "conformal": {"signals", "spec"},
    "monitor": {"signals", "spec", "conformal"},
    "attribution": {"signals", "spec", "monitor"},
    "benchmark": {"signals", "spec", "monitor"},
    "baselines": {
        "signals",
        "spec",
        "monitor",
        "conformal",
        "attribution",
        "benchmark",
    },
    "eval": {
        "signals",
        "spec",
        "monitor",
        "conformal",
        "attribution",
        "benchmark",
        "baselines",
    },
}


def _sources() -> list[Path]:
    assert PKG_DIR.is_dir(), "src/ralmon does not exist"
    return sorted(PKG_DIR.rglob("*.py"))


def _module_of(path: Path) -> list[str]:
    """Dotted module parts of a file under src/, e.g. ['ralmon', 'spec', 'x']."""
    return list(path.relative_to(SRC).with_suffix("").parts)


def _imports(path: Path) -> list[list[str]]:
    """Absolute dotted targets (as part lists) of every import in a file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    module = _module_of(path)
    package = module[:-1]
    targets: list[list[str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.extend(alias.name.split(".") for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = (node.module or "").split(".")
            else:
                base = package[: len(package) - (node.level - 1)]
                if node.module:
                    base = base + node.module.split(".")
            if base == ["ralmon"]:
                targets.extend(base + [alias.name] for alias in node.names)
            else:
                targets.append(base)
    return targets


def _package_of(path: Path) -> str | None:
    parts = _module_of(path)
    return parts[1] if len(parts) > 2 else None


def _edges() -> list[tuple[str, str, list[str], Path]]:
    found = []
    for path in _sources():
        source_pkg = _package_of(path)
        for target in _imports(path):
            if target[0] != "ralmon" or len(target) < 2:
                continue
            found.append((source_pkg or "", target[1], target, path))
    return found


def test_layering_edges_follow_conventions() -> None:
    bad = []
    for source, dest, _target, path in _edges():
        if source == "" or source == dest:
            continue
        if dest not in ALLOWED_EDGES:  # root-level private helper (ralmon._stub)
            continue
        if dest not in ALLOWED_EDGES.get(source, set()):
            bad.append(f"{path.relative_to(ROOT)}: {source} -> {dest}")
    assert bad == []


def test_cross_package_imports_use_package_root_only() -> None:
    bad = []
    for source, dest, target, path in _edges():
        if source == dest or dest not in ALLOWED_EDGES:
            continue
        if len(target) > 2:
            bad.append(f"{path.relative_to(ROOT)}: {'.'.join(target)}")
    assert bad == []


def test_package_graph_is_acyclic() -> None:
    graph: dict[str, set[str]] = {p: set() for p in ALLOWED_EDGES}
    for source, dest, _target, _path in _edges():
        if source in graph and dest in graph and source != dest:
            graph[source].add(dest)
    state: dict[str, int] = {}

    def visit(node: str, stack: list[str]) -> None:
        if state.get(node) == 2:
            return
        assert state.get(node) != 1, f"cycle: {' -> '.join([*stack, node])}"
        state[node] = 1
        for nxt in sorted(graph[node]):
            visit(nxt, [*stack, node])
        state[node] = 2

    for pkg in graph:
        visit(pkg, [])


def test_core_never_imports_ros() -> None:
    bad = []
    for path in _sources():
        for target in _imports(path):
            if target[0] in {"rclpy", "rclcpp"}:
                bad.append(str(path.relative_to(ROOT)))
    assert bad == []
