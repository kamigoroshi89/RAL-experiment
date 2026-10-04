# Containerised environment

Two images, both mounting the repository at `/work` (never copying it) and running as the host
user. Nothing here changes the plan, the contracts or `pyproject.toml`; see ADR-031.

| Service | Image | Purpose |
|---|---|---|
| `dev` | `ralmon-dev` (python 3.12, numpy, PyYAML, pytest, hypothesis, ruff, mypy) | interactive shell for the ROS-independent core |
| `test` | `ralmon-dev` | `pytest -q` |
| `lint` | `ralmon-dev` | `ruff check`, `ruff format --check`, `mypy src/ralmon` |
| `plan` | `ralmon-dev` | `python3 tools/check_plan.py` |
| `bib` | `ralmon-dev` | `python3 tools/check_bib.py --schema` |
| `ros2` (profile `ros2`) | `ralmon-ros2:jazzy` (ROS 2 Jazzy base, `ros_gz_sim`, `ros_gz_bridge`, CycloneDDS, plus the Python dev tools) | WS07 and WS10 work; contains no TIAGo packages (WS07-T01, after WS00-T05) |

## Commands

```bash
docker compose build dev                  # about 25 s
docker compose run --rm test              # same result as `pytest -q` on the host
docker compose run --rm lint
docker compose run --rm plan
docker compose run --rm dev               # shell
docker compose --profile ros2 build ros2  # large image; first build downloads ROS packages
docker compose --profile ros2 run --rm ros2
```

The compose file reads `UID` and `GID` from the environment and defaults to 1000. If your
host user differs, put `UID=...` and `GID=...` in a `.env` file (listed in `.gitignore`).

## What the image does not contain

- LaTeX (the paper excerpts of the WS01 documents were compiled on the host with `pdflatex`).
- `data/raw/` (never copied, never committed; mount it if a task needs it).
- Any TIAGo package, Gazebo world or robot description (WS07-T01).
- Network access is not restricted by the image; the tests of the plan are written to need none
  (CLAUDE.md, working rules).

## Versions resolved at the time of writing (not pinned: ADR-016)

Python 3.12, numpy 2.5.3, PyYAML 6.0.3, pytest 9.1.1, hypothesis 6.168.3, ruff 0.16.10,
mypy 2.4.0, types-PyYAML 6.0.12.20260906. The host environment of the earlier tasks used
Python 3.14.4, ruff 0.16.9 and mypy 2.3.1; the suite passes on both.
