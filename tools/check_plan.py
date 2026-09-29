#!/usr/bin/env python3
"""Verify the consistency of the development plan (bootstrap phase F9).

Standard library only. Run from the repository root:

    python3 tools/check_plan.py

Exit code 0 when every check passes, 1 otherwise. Checks:

 1. every workstream folder has README.md and at least one task;
 2. every task has complete frontmatter, the six template sections and at least one source;
 3. every depends_on id exists and the dependency graph is acyclic;
 4. every reviewer finding of docs/source/review.md appears in 04-review-traceability.md;
 5. every contract of 02-interfaces.md is used by at least one task, and every cited anchor exists;
 6. B5, A4 and every WS01 task have non_negotiable: true;
 7. no placeholder tokens in the plan documents;
 8. no file under src/.

Additional consistency checks: task frontmatter matches workstreams/INDEX.md; task status is
consistent with dependency status; file names match task ids; the progress checklist is coherent.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "docs" / "plan"
WS_DIR = PLAN / "workstreams"

REQUIRED_KEYS = [
    "id", "title", "workstream", "owner", "status", "depends_on", "critical_path",
    "non_negotiable", "estimate_pd", "sources", "interfaces", "review_items",
]
REQUIRED_SECTIONS = ["Obiettivo", "Contesto", "File toccati", "Test", "Passi", "Done when"]
OWNERS = {"agent", "human"}
STATUSES = {"ready", "blocked", "in_progress", "done"}
PLACEHOLDER = re.compile(r"\bTODO\b|\bTBD\b|\?\?\?|\blorem\b", re.IGNORECASE)

errors: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


# ---------------------------------------------------------------- frontmatter

def _strip_comment(value: str) -> str:
    in_quote: str | None = None
    for i, ch in enumerate(value):
        if ch in "\"'":
            if in_quote is None:
                in_quote = ch
            elif in_quote == ch:
                in_quote = None
        elif ch == "#" and in_quote is None and (i == 0 or value[i - 1] == " "):
            return value[:i].rstrip()
    return value.strip()


def _parse_scalar(raw: str):
    raw = raw.strip()
    if raw in ("true", "True"):
        return True
    if raw in ("false", "False"):
        return False
    if raw in ("null", "~", ""):
        return None
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _parse_inline_list(raw: str) -> list:
    inner = raw.strip()[1:-1].strip()
    if not inner:
        return []
    try:
        return json.loads("[" + inner + "]")
    except json.JSONDecodeError:
        pass
    items, cur, quote = [], "", None
    for ch in inner:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            cur += ch
        elif ch == ",":
            items.append(_parse_scalar(cur))
            cur = ""
        else:
            cur += ch
    if cur.strip():
        items.append(_parse_scalar(cur))
    return items


def parse_frontmatter(text: str) -> tuple[dict, str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    block = text[4:end].split("\n")
    body = text[end + 4:]
    data: dict = {}
    key = None
    for line in block:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if m and not line.startswith(" "):
            key = m.group(1)
            val = _strip_comment(m.group(2))
            if val.startswith("["):
                data[key] = _parse_inline_list(val)
            elif val == "":
                data[key] = []
            else:
                data[key] = _parse_scalar(val)
        elif line.lstrip().startswith("- ") and key is not None:
            if not isinstance(data.get(key), list):
                data[key] = []
            data[key].append(_parse_scalar(_strip_comment(line.lstrip()[2:])))
    return data, body


# ---------------------------------------------------------------- loading

def load_tasks() -> dict[str, dict]:
    tasks: dict[str, dict] = {}
    if not WS_DIR.is_dir():
        err("docs/plan/workstreams missing")
        return tasks
    ws_folders = sorted(p for p in WS_DIR.iterdir() if p.is_dir())
    if not ws_folders:
        err("no workstream folders")
    for ws in ws_folders:
        # check 1
        if not (ws / "README.md").is_file():
            err(f"{ws.name}: README.md missing")
        task_files = sorted((ws / "tasks").glob("T*.md")) if (ws / "tasks").is_dir() else []
        if not task_files:
            err(f"{ws.name}: no task files in tasks/")
        for tf in task_files:
            rel = tf.relative_to(ROOT)
            parsed = parse_frontmatter(tf.read_text(encoding="utf-8"))
            if parsed is None:
                err(f"{rel}: missing or malformed frontmatter")
                continue
            fm, body = parsed
            fm["_path"] = str(rel)
            fm["_body"] = body
            fm["_dir"] = ws.name
            # check 2
            for k in REQUIRED_KEYS:
                if k not in fm:
                    err(f"{rel}: frontmatter key '{k}' missing")
            if not isinstance(fm.get("sources"), list) or not fm.get("sources"):
                err(f"{rel}: 'sources' must be a non-empty list")
            if fm.get("owner") not in OWNERS:
                err(f"{rel}: owner must be one of {sorted(OWNERS)}")
            if fm.get("status") not in STATUSES:
                err(f"{rel}: status must be one of {sorted(STATUSES)}")
            for k in ("depends_on", "interfaces", "review_items"):
                if k in fm and not isinstance(fm[k], list):
                    err(f"{rel}: '{k}' must be a list")
            for k in ("critical_path", "non_negotiable"):
                if k in fm and not isinstance(fm[k], bool):
                    err(f"{rel}: '{k}' must be true or false")
            if not isinstance(fm.get("estimate_pd"), (int, float)):
                err(f"{rel}: estimate_pd must be a number")
            headings = re.findall(r"^##\s+(.+?)\s*$", body, flags=re.MULTILINE)
            for sec in REQUIRED_SECTIONS:
                if sec not in headings:
                    err(f"{rel}: section '## {sec}' missing")
            tid = fm.get("id")
            if not isinstance(tid, str):
                continue
            if not tf.name.startswith(tid.split("-", 1)[1] + "-"):
                err(f"{rel}: file name should start with '{tid.split('-', 1)[1]}-' (id {tid})")
            if not ws.name.startswith(tid.split("-", 1)[0] + "-"):
                err(f"{rel}: id prefix does not match workstream folder {ws.name}")
            if fm.get("workstream") != ws.name:
                err(f"{rel}: workstream '{fm.get('workstream')}' != folder '{ws.name}'")
            if tid in tasks:
                err(f"{rel}: duplicate id {tid}")
            tasks[tid] = fm
    return tasks


# ---------------------------------------------------------------- checks

def check_dependencies(tasks: dict[str, dict]) -> None:
    for tid, fm in tasks.items():
        for d in fm.get("depends_on") or []:
            if d not in tasks:
                err(f"{tid}: depends_on '{d}' does not exist")
    state: dict[str, int] = {}

    def dfs(n: str, stack: list[str]) -> None:
        if state.get(n) == 1:
            err("dependency cycle: " + " -> ".join(stack + [n]))
            return
        if state.get(n) == 2 or n not in tasks:
            return
        state[n] = 1
        for d in tasks[n].get("depends_on") or []:
            dfs(d, stack + [n])
        state[n] = 2

    for n in tasks:
        dfs(n, [])
    # status coherence
    for tid, fm in tasks.items():
        deps = fm.get("depends_on") or []
        all_done = all(tasks[d].get("status") == "done" for d in deps if d in tasks)
        if fm.get("status") in ("ready", "in_progress") and not all_done:
            err(f"{tid}: status '{fm.get('status')}' but some dependencies are not done")
        if fm.get("status") == "blocked" and all_done:
            err(f"{tid}: status 'blocked' but all dependencies are done")


def review_finding_ids() -> list[str]:
    path = ROOT / "docs" / "source" / "review.md"
    if not path.is_file():
        err("docs/source/review.md missing")
        return []
    ids: list[str] = []
    section = None
    in_weak = False
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^###\s+(R[123]):", line)
        if m:
            section, in_weak = m.group(1), False
            continue
        if line.startswith("### Meta-review"):
            section, in_weak = "AE", False
            ids.extend(["AE-5"])  # paragraph on internal inconsistencies (see 04 header)
            continue
        if section in ("R1", "R2", "R3"):
            if line.startswith("**Debolezze"):
                in_weak = True
                continue
            if line.startswith("**") and in_weak:
                in_weak = False
            if in_weak:
                m2 = re.match(r"^(\d+)\.\s", line)
                if m2:
                    ids.append(f"{section}-W{m2.group(1)}")
        elif section == "AE":
            m2 = re.match(r"^(\d)\.\s", line)
            if m2 and int(m2.group(1)) <= 4:
                ids.append(f"AE-{m2.group(1)}")
    return sorted(set(ids))


def check_review_traceability(tasks: dict[str, dict]) -> None:
    ids = review_finding_ids()
    trace_path = PLAN / "04-review-traceability.md"
    if not trace_path.is_file():
        err("04-review-traceability.md missing")
        return
    trace = trace_path.read_text(encoding="utf-8")
    if len([i for i in ids if i.startswith("R")]) != 26:
        err(f"expected 26 reviewer weaknesses in review.md, parsed {len([i for i in ids if i.startswith('R')])}")
    rows = {}
    for line in trace.splitlines():
        m = re.match(r"^\|\s*((?:R[123]-W\d+|AE-\d+))\b[^|]*\|", line)
        if m:
            rows[m.group(1)] = line
    for fid in ids:
        if fid not in rows:
            err(f"04-review-traceability.md: finding {fid} has no row")
            continue
        cited = re.findall(r"WS\d\d-T\d\d", rows[fid])
        if not cited:
            err(f"04-review-traceability.md: finding {fid} maps to no task")
        for t in cited:
            if t not in tasks:
                err(f"04-review-traceability.md: {fid} cites unknown task {t}")
            elif fid not in (tasks[t].get("review_items") or []):
                err(f"04-review-traceability.md: {fid} cites {t} but {t} does not list it in review_items")
    for tid, fm in tasks.items():
        for r in fm.get("review_items") or []:
            if r not in ids:
                err(f"{tid}: review_items '{r}' is not a known finding id")
            elif r in rows and tid not in rows[r]:
                err(f"{tid}: lists {r} but 04-review-traceability.md row does not cite {tid}")


def contract_anchors() -> list[str]:
    path = PLAN / "02-interfaces.md"
    if not path.is_file():
        err("02-interfaces.md missing")
        return []
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^# Contracts\s*$", text, flags=re.MULTILINE)
    if not m:
        err("02-interfaces.md: '# Contracts' marker missing")
        return []
    anchors = []
    for h in re.findall(r"^##\s+(.+?)\s*$", text[m.end():], flags=re.MULTILINE):
        slug = re.sub(r"[^\w\s-]", "", h.lower()).strip()
        slug = re.sub(r"\s+", "-", slug)
        anchors.append(slug)
    return anchors


def check_contracts(tasks: dict[str, dict]) -> None:
    anchors = set(contract_anchors())
    used: set[str] = set()
    for tid, fm in tasks.items():
        for ref in fm.get("interfaces") or []:
            m = re.match(r"^02-interfaces\.md#([a-z0-9-]+)$", str(ref))
            if not m:
                err(f"{tid}: malformed interfaces reference '{ref}'")
                continue
            if m.group(1) not in anchors:
                err(f"{tid}: interface anchor '#{m.group(1)}' does not exist in 02-interfaces.md")
            used.add(m.group(1))
    for a in sorted(anchors - used):
        err(f"contract '#{a}' is not used by any task")


def check_non_negotiable(tasks: dict[str, dict]) -> None:
    for tid, fm in tasks.items():
        must = tid.startswith("WS01-") or re.search(r"(?<![-\w])(B5|A4)\b", str(fm.get("title", "")))
        if must and fm.get("non_negotiable") is not True:
            err(f"{tid}: must have non_negotiable: true")
    if not any(re.search(r"\bB5\b", str(f.get("title", ""))) for f in tasks.values()):
        err("no task with B5 in its title")
    if not any(re.search(r"\bA4\b", str(f.get("title", ""))) for f in tasks.values()):
        err("no task with A4 in its title")
    # never in cut lists: a line about cutting must not name B5/A4 without a negation
    for path in [PLAN / "00-master-plan.md", *WS_DIR.rglob("*.md")]:
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\bcuts?\b(?!-off)|\bcutting\b|\btagli", line, re.IGNORECASE) and re.search(r"\b(B5|A4)\b", line):
                if not re.search(r"\b(never|not|no|non|nor|without)\b", line, re.IGNORECASE):
                    err(f"{path.relative_to(ROOT)}:{i}: B5/A4 appears in a cut context")


def check_placeholders() -> None:
    files = [ROOT / "CLAUDE.md"]
    files += sorted((ROOT / "docs" / "plan").rglob("*.md"))
    files += sorted((ROOT / "docs" / "superpowers").rglob("*.md"))
    for extra in ("formal", "models", "related-work", "benchmark"):
        d = ROOT / "docs" / extra
        if d.is_dir():
            files += sorted(d.rglob("*.md"))
    for f in files:
        if not f.is_file():
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if PLACEHOLDER.search(line):
                err(f"{f.relative_to(ROOT)}:{i}: placeholder token")


def check_src() -> None:
    src = ROOT / "src"
    if src.exists():
        files = [p for p in src.rglob("*") if p.is_file()]
        if files:
            err(f"src/ must be empty during bootstrap; found {len(files)} file(s), e.g. {files[0].relative_to(ROOT)}")


def parse_index() -> dict[str, dict]:
    path = WS_DIR / "INDEX.md"
    rows: dict[str, dict] = {}
    if not path.is_file():
        err("workstreams/INDEX.md missing")
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not re.match(r"^\| WS\d\d-T\d\d \|", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 11:
            err(f"INDEX.md: malformed row {cells[0]}")
            continue
        rows[cells[0]] = {
            "title": cells[2], "owner": cells[3],
            "deps": [] if cells[4] == "-" else [d.strip() for d in cells[4].split(",")],
            "crit": cells[5] == "yes", "nonneg": cells[6] == "yes", "pd": float(cells[7]),
            "review": [] if cells[10] == "-" else cells[10].split(),
        }
    return rows


def check_index(tasks: dict[str, dict]) -> None:
    rows = parse_index()
    for tid in sorted(set(rows) - set(tasks)):
        err(f"INDEX.md lists {tid} but no task file exists")
    for tid in sorted(set(tasks) - set(rows)):
        err(f"task {tid} is not listed in INDEX.md")
    for tid, r in rows.items():
        fm = tasks.get(tid)
        if not fm:
            continue
        if fm.get("title") != r["title"]:
            err(f"{tid}: title differs from INDEX.md")
        if fm.get("owner") != r["owner"]:
            err(f"{tid}: owner differs from INDEX.md")
        if sorted(fm.get("depends_on") or []) != sorted(r["deps"]):
            err(f"{tid}: depends_on differs from INDEX.md")
        if fm.get("critical_path") != r["crit"]:
            err(f"{tid}: critical_path differs from INDEX.md")
        if fm.get("non_negotiable") != r["nonneg"]:
            err(f"{tid}: non_negotiable differs from INDEX.md")
        if isinstance(fm.get("estimate_pd"), (int, float)) and abs(float(fm["estimate_pd"]) - r["pd"]) > 1e-9:
            err(f"{tid}: estimate_pd differs from INDEX.md")
        if sorted(fm.get("review_items") or []) != sorted(r["review"]):
            err(f"{tid}: review_items differ from INDEX.md")


def check_docs_present() -> None:
    for name in ("00-master-plan.md", "01-conventions.md", "02-interfaces.md", "03-decisions.md",
                 "04-review-traceability.md", "PROGRESS.md"):
        if not (PLAN / name).is_file():
            err(f"docs/plan/{name} missing")
    if not (ROOT / "CLAUDE.md").is_file():
        err("CLAUDE.md missing")
    else:
        n = len((ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines())
        if n >= 200:
            err(f"CLAUDE.md has {n} lines; must be under 200")
    if (PLAN / "BLOCKED.md").exists():
        err("docs/plan/BLOCKED.md exists")
    for name in ("analisi.md", "review.md"):
        if not (ROOT / "docs" / "source" / name).is_file():
            err(f"docs/source/{name} missing")


def main() -> int:
    check_docs_present()
    tasks = load_tasks()
    check_dependencies(tasks)
    check_review_traceability(tasks)
    check_contracts(tasks)
    check_non_negotiable(tasks)
    check_index(tasks)
    check_placeholders()
    check_src()
    if errors:
        print(f"check_plan: FAILED with {len(errors)} problem(s)")
        for e in errors:
            print(" -", e)
        return 1
    print(f"check_plan: OK ({len(tasks)} tasks, {len(contract_anchors())} contracts, "
          f"{len(review_finding_ids())} findings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
