# Containerised environment

Two images, both mounting the repository at `/work` (never copying it) and running as the host
user. Nothing here changes the plan or the contracts; see ADR-031. The ROS 2 image follows ADR-042
(ROS 2 Humble with Gazebo Classic, Python 3.10 floor), which superseded ADR-011.

| Service | Image | Purpose |
|---|---|---|
| `dev` | `ralmon-dev` (python 3.12, numpy, PyYAML, pytest, hypothesis, ruff, mypy) | interactive shell for the ROS-independent core |
| `test` | `ralmon-dev` | `pytest -q` |
| `lint` | `ralmon-dev` | `ruff check`, `ruff format --check`, `mypy src/ralmon` |
| `plan` | `ralmon-dev` | `python3 tools/check_plan.py` |
| `bib` | `ralmon-dev` | `python3 tools/check_bib.py --schema` |
| `ros2` (profile `ros2`) | `ralmon-ros2:humble` (`ros:humble-ros-base`, Ubuntu 22.04, Python 3.10; Gazebo Classic 11 with `gazebo_ros_pkgs`, `ros_gz_bridge` for the Fortress fallback, Nav2, PAL TIAGo and TIAGo Pro simulation, Xvfb, LTTng, CycloneDDS, `tc`; an overlay with `tracetools` built against LTTng and the AWS hospital world; Python dev tools) | WS07 and WS10 work; also the proof that the core runs on Python 3.10 |

## Commands

```bash
docker compose build dev                  # about 25 s
docker compose run --rm test              # same result as `pytest -q` on the host
docker compose run --rm lint
docker compose run --rm plan
docker compose run --rm dev               # shell
docker compose --profile ros2 build ros2  # 4.4 GB; first build downloads ROS packages and, for the
                                          # hospital world, its Gazebo Fuel models (about 6 min)
docker compose --profile ros2 run --rm ros2               # shell in the sourced Humble environment
docker compose --profile ros2 run --rm ros2 pytest -q     # the core suite under Python 3.10
(cd ros2 && colcon build --packages-select ralmon_sim)    # inside the container
docker compose --profile ros2 run --rm -T ros2 pytest ros2/ralmon_sim/test/test_ward_world.py -q -m ros
                                          # the ward world, robot and Nav2 headless (about 5 minutes)
bash ros2/ralmon_sim/scripts/check_sim_env.sh             # inside the container
```

The earlier image `ralmon-ros2:jazzy` is no longer used by the compose file; remove it with
`docker rmi ralmon-ros2:jazzy` once it is not needed.

The compose file reads `UID` and `GID` from the environment and defaults to 1000. If your
host user differs, put `UID=...` and `GID=...` in a `.env` file (listed in `.gitignore`).

## What the image does not contain

- LaTeX (the paper excerpts of the WS01 documents were compiled on the host with `pdflatex`).
- `data/raw/` (never copied, never committed; mount it if a task needs it).
- A display server running. Gazebo Classic needs a display for the laser and camera sensors; the image
  has `Xvfb` with Mesa software rendering (added by WS07-T02) and the fixture `display_env` of
  `ros2/ralmon_sim/test/conftest.py` starts one when `DISPLAY` is not set. The checks of WS07-T01 had
  installed `Xvfb` in a throw-away root container (see `ros2/ralmon_sim/doc/availability.md`,
  Reproduction step 8).
- Options of the ward tests (environment variables, passed with `docker compose run -e NAME=value`):
  `RALMON_SIM_LOG_DIR=/work/<dir>` keeps the log of the simulation there (otherwise it is lost with
  the container), and `RALMON_TEST_SHUFFLE_SEED=<integer>` shuffles the order of the door legs and
  of the bedside legs with a seeded generator. The tests print one line `WARD LEGS ...` with the
  simulation-time duration of every leg, also under `-q`.
- Isolation between simulations. Two containers on the same host share the DDS domain unless
  `ROS_DOMAIN_ID` differs (the compose file defaults to 42): a second simulation next to the first
  (for example the test run of WS07-T02 while another container still runs) mixes `/clock` and the
  Nav2 lifecycle nodes of both. Wait for the first container to exit or run with
  `ROS_DOMAIN_ID=<other number> docker compose --profile ros2 run ...`. On this host
  `docker kill` and `docker rm -f` of a running container failed with "permission denied"
  (`docker stop` was not tried); `docker exec <name> kill <pid>` of the command inside worked, and a
  container ends when its command ends.
- The capability `NET_ADMIN`: `tc netem` works only in a container started with
  `--cap-add NET_ADMIN` as root; the `ros2` service has neither (WS07-T05 decides).
- A user entry for the host uid: Gazebo Classic printed `Error getting username: no matching
  password record` in a run as uid 1000; the hospital-world check as uid 1000 still reached
  `/clock` and the `gazebo_ros` services (a full robot run as uid 1000 was not tried).
- Network access is not restricted by the image; the tests of the plan are written to need none
  (CLAUDE.md, working rules).

## Versions resolved at the time of writing (not pinned: ADR-016)

`ralmon-dev`: Python 3.12, numpy 2.5.3, PyYAML 6.0.3, pytest 9.1.1, hypothesis 6.168.3, ruff 0.16.10,
mypy 2.4.0, types-PyYAML 6.0.12.20260906. The host environment of the earlier tasks used
Python 3.14.4, ruff 0.16.9 and mypy 2.3.1; the suite passes on both.

`ralmon-ros2:humble` (Python 3.10.12, the floor of ADR-042): numpy 1.26.4 (pip, `numpy<2`),
PyYAML 5.4.1 (apt), pytest 6.2.5 (apt), hypothesis 6.168.5, ruff 0.16.10, mypy 2.4.0.

- pytest stays the apt version because pytest 9 breaks the ROS 2 Humble pytest plugins
  (`launch_testing`, `launch_testing_ros`) at start-up; the image links `pytest` to `pytest-3`.
- numpy is limited to 1.x because the apt `pandas` 1.3.5 of `tracetools_analysis` fails to import
  with numpy 2.2.6 (checked). The system numpy 1.21.5 (REP 2000) is too old for the core: on it
  one test fails (`tests/benchmark/test_c1_confounders.py::test_foreign_objects_with_unreadable_fields_are_named_errors`,
  the core does not raise `C1InjectionError`) and `mypy src/ralmon` reports 5 `no-untyped-call`
  errors. Bisection on Python 3.10.12 in throw-away containers (pip `--target` under `/tmp`, 2026-10-08):
  the test fails with numpy 1.21.6, 1.22.4, 1.23.5 and 1.24.4 and passes with 1.25.0, 1.25.1, 1.25.2,
  1.26.4 and 2.2.6; mypy reports the errors with 1.21.5 and 1.21.6 and passes with 1.22.4, 1.25.0 and
  1.25.2. Patch versions between those were not run, so the floor for the test is about 1.25.
  `pyproject.toml` declares no numpy floor (ADR-016) and none was added; a ROS node that imports
  `ralmon` on a machine with only the apt numpy is outside the tested range (open items of
  `ros2/ralmon_sim/doc/availability.md`).
- Python 3.10 results (2026-10-08): `pytest -q` 2357 passed, `ruff check src tests`,
  `ruff format --check src tests` and `mypy src/ralmon` exit 0.
