---
id: WS00-T05
title: "Check real TIAGo or TIAGo Pro availability and ROS 2 simulation packages"
workstream: WS00-admin
owner: human
status: done
depends_on: []
critical_path: false
non_negotiable: false
estimate_pd: 1
sources: ["analisi §9 (0.7)", "analisi §5.2", "analisi §5.3"]
interfaces: ["02-interfaces.md#ros-2-interfaces"]
review_items: []
---
## Obiettivo

Establish, by desk research and by asking the lab, which robot the group can use and which ROS 2 simulation packages exist for it, and decide ADR-011 (ROS 2 distribution and Gazebo generation). The task covers: the ROS 2 distribution and the Gazebo generation with which the simulation packages are compatible; whether a TIAGo Pro simulation model exists for ROS 2 or only a TIAGo model; the onboard computer specifications, needed to measure CPU and memory on equivalent hardware (analisi §5.2); and the availability of a real TIAGo or TIAGo Pro for the lab demo. Concrete output: `docs/plan/workstreams/WS00-admin/outputs/WS00-T05.md` and an accepted or superseded ADR-011 in `docs/plan/03-decisions.md`. Nothing is installed here: the installation and package check belongs to WS07-T01, which starts from this artefact.

## Contesto

- `docs/source/analisi.md` §5.2 (Humble or Jazzy depending on the TIAGo packages; hospital world for Gazebo; PAL simulation packages; onboard computer specifications; measurements with ros2_tracing) and §9 row 0.7.
- `docs/plan/03-decisions.md` ADR-011 (proposed: Jazzy with Gazebo Harmonic, to be superseded by Humble if the packages need it) and ADR-016 (Python 3.11 or newer).
- `docs/plan/02-interfaces.md#ros-2-interfaces` (ward node plus robot, lifecycle nodes, liveliness and deadline QoS on `/ralmon/heartbeat` and `/ralmon/samples`).
- `docs/source/analisi.md` §5.3 (real robot in the lab: needed to plan WS10).
- The vendor documentation and package repositories for TIAGo and TIAGo Pro, and the hospital-world package named in analisi §5.2, which the human consults for current information.

No dependency: this task is `ready` and starts on day one (`00-master-plan.md` section 6).

## File toccati

- `docs/plan/workstreams/WS00-admin/outputs/WS00-T05.md` (create)
- `docs/plan/03-decisions.md` (modify: ADR-011 status and heading tag; a new superseding ADR only if Humble or another stack is chosen)

## Test

Verification checks:

1. The artefact starts with `completed_by:` and `completed_on:` lines and contains the six H2 fields of Done when, each non-empty and each with `Source:` lines (vendor page, repository address, message from the vendor or the lab, with the date consulted).
2. `## Real robot availability` states whether a TIAGo or TIAGo Pro exists in reach of the group, which model, where, who books it, the ROS distribution its software stack uses today, and the time window in which WS10 could use it. If none exists, it says so and states the consequence: WS10 falls back to simulation video (`00-master-plan.md` section 7).
3. `## ROS 2 distribution and Gazebo compatibility` has, for Humble and for Jazzy, the vendor simulation packages (repository and branch or release), the Gazebo generations they support (Gazebo Classic or the newer Gazebo lines, with the ROS 2 bridge), and the availability of Nav2 and ros2_tracing. It also gives the ROS 2 support status of the hospital world named in analisi §5.2 and whether it needs porting from Gazebo Classic.
4. `## TIAGo Pro simulation model` answers yes or no to "does a simulation model of TIAGo Pro exist for ROS 2", names the package if yes, and if the answer is TIAGo only, states how the paper will describe the simulated robot ("TIAGo-class") and what differs from TIAGo Pro.
5. `## Onboard computer specs` gives, for TIAGo and for TIAGo Pro as documented by the vendor: CPU, memory, storage, GPU if present, operating system. It names the equivalent hardware available for the WS07-T07 measurement of CPU and memory (analisi §5.2), or states that none is available.
6. `## ADR-011 decision` states: keep Jazzy with Gazebo Harmonic, or choose another distribution and Gazebo generation; the evidence from checks 3 and 4 in two or three lines; the Python version delivered by the chosen distribution's target operating system and whether it satisfies ADR-016 (Python 3.11 or newer, since the ROS 2 wrappers under `ros2/` import `ralmon`); and whether the lifecycle and QoS features named in `#ros-2-interfaces` exist in the chosen distribution.
7. In `docs/plan/03-decisions.md` the heading of ADR-011 no longer ends with the confirmation tag and its status is `accepted (confirmed (WS00-T05, YYYY-MM-DD))` or `superseded by ADR-0NN (WS00-T05, YYYY-MM-DD)`. A superseding ADR has context, decision, alternatives, consequences and status, and states that the `ralmon` core is unaffected because it is ROS-independent.
8. If the Python check in item 6 fails, the artefact states that ADR-016 must be reopened and names the owner (the decision-makers of WS00-T02).

## Passi

1. Real robot: ask the lab or the vendor whether a TIAGo or TIAGo Pro is available, which one, and in which periods. Fill `## Real robot availability` and note the answer for WS10-T01.
2. Simulation packages: read the vendor documentation and repositories for both ROS 2 distributions named in ADR-011 and fill `## ROS 2 distribution and Gazebo compatibility`. Record versions and branches exactly as found, with the date.
3. TIAGo Pro: determine whether a ROS 2 simulation model of TIAGo Pro exists, as analisi §5.2 asks, and fill `## TIAGo Pro simulation model`.
4. Onboard computer: read the vendor specification of the TIAGo and TIAGo Pro computers and fill `## Onboard computer specs`; then identify the equivalent lab hardware for WS07-T07.
5. Hospital world: check the ROS 2 support status of the hospital world (analisi §5.2) and record it in `## ROS 2 distribution and Gazebo compatibility`. The optional HuNavSim and Isaac Sim mentioned in analisi §5.2 are not needed for this decision.
6. Decide ADR-011: keep Jazzy with Gazebo Harmonic if the packages needed for the TIAGo model, the hospital world, Nav2 and ros2_tracing exist for it; otherwise choose the distribution and Gazebo generation for which they do, and add the superseding ADR with the next free number. Write `## ADR-011 decision`.
7. Edit `docs/plan/03-decisions.md`: remove the confirmation tag from the heading of ADR-011 and set the status as in check 7. Do not edit `02-interfaces.md`: the contract does not name a distribution.
8. Write `## Open points` (anything unanswered, with the question sent, the recipient and the date), then set `status: done` in this task file and tell the owner of WS07-T01 that it is unblocked.

## Done when

From the repository root:

- `test -f docs/plan/workstreams/WS00-admin/outputs/WS00-T05.md` exits 0.
- `grep -cE '^## (Real robot availability|ROS 2 distribution and Gazebo compatibility|TIAGo Pro simulation model|Onboard computer specs|ADR-011 decision|Open points)$' docs/plan/workstreams/WS00-admin/outputs/WS00-T05.md` prints `6`.
- `grep -cE '^## ADR-011 .*\[DA-' docs/plan/03-decisions.md` prints `0`.
- `grep -cE '\(WS00-T05, [0-9]{4}-[0-9]{2}-[0-9]{2}\)' docs/plan/03-decisions.md` prints at least `1`.
- Inspection: checks 3 to 6 hold; every value has a `Source:` line or the text `not stated in <source>` with the date the question was sent.

## Notes

### Status update (user attestation)

Marked `done` on 2026-09-30 at the user's explicit instruction ("le task umane iniziali sono tutte eseguite"). The artefact named in "Done when" (`docs/plan/workstreams/WS00-admin/outputs/WS00-T05.md`) was not present in the repository at that time; the agent did not create or reconstruct it. Anything downstream that needs its content will stop and report.
