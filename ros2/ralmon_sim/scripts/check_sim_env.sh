#!/usr/bin/env bash
# Observe, on this machine, the components recorded in config/package_availability.yaml.
#
# Output (stdout): one line per component, "<id> <recorded status> <observed>", where observed is
#   yes   the component is present in the sourced environment,
#   no    it is not,
#   n/a   nothing to observe on a machine (the onboard computer and Isaac Sim are documentary).
# Diagnostics go to stderr and start with "#".
#
# Exit codes:
#   0  every component recorded as `available` is observed
#   1  at least one component recorded as `available` is not observed
#   2  no sourced ROS 2 environment (nothing is checked)
#   3  the record cannot be read (python3 with PyYAML is needed)
#
# The script does not need the ralmon core; it only prints whether `import ralmon` works.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECORD="$HERE/../config/package_availability.yaml"

if [ -z "${ROS_DISTRO:-}" ] || ! command -v ros2 >/dev/null 2>&1; then
  echo "ROS 2 environment not sourced"
  exit 2
fi

record_lines="$(python3 - "$RECORD" <<'PY'
import sys

import yaml

record = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
components = record["components"]
print("TARGET", record["target"]["ros_distro"], record["target"]["gazebo"])
print("VARIANT", components["robot_sim_pal"]["variant"])
print("WORLD", components["hospital_world"]["decision"])
for name, component in components.items():
    print("COMPONENT", name, component["status"])
PY
)" || { echo "cannot read $RECORD" >&2; exit 3; }

target_distro="" target_gazebo="" variant="" world_decision=""
while read -r kind a b; do
  case "$kind" in
    TARGET) target_distro="$a"; target_gazebo="$b" ;;
    VARIANT) variant="$a" ;;
    WORLD) world_decision="$a" ;;
  esac
done <<<"$record_lines"

has_pkg() { ros2 pkg prefix "$1" >/dev/null 2>&1; }

observe() {
  case "$1" in
    ros2_distro)
      [ "$ROS_DISTRO" = "$target_distro" ] ;;
    gazebo)
      case "$target_gazebo" in
        classic) command -v gazebo >/dev/null 2>&1 && gazebo --version 2>/dev/null | grep -q "version 11" ;;
        fortress) command -v ign >/dev/null 2>&1 && ign gazebo --versions 2>/dev/null | grep -q "^6" ;;
        *) command -v gz >/dev/null 2>&1 && gz sim --versions >/dev/null 2>&1 ;;
      esac ;;
    ros_gz_bridge)
      # gazebo_ros_pkgs serves Gazebo Classic (target); ros_gz_bridge serves the Fortress fallback.
      has_pkg gazebo_ros && has_pkg ros_gz_bridge ;;
    nav2)
      has_pkg nav2_bringup ;;
    robot_sim_pal)
      case "$variant" in
        tiago_pro) has_pkg tiago_pro_gazebo ;;
        tiago) has_pkg tiago_gazebo ;;
        *) return 1 ;;
      esac ;;
    hospital_world)
      case "$world_decision" in
        procedural) has_pkg ralmon_sim ;;
        *) has_pkg aws_robomaker_hospital_world ;;
      esac ;;
    human_sim)
      has_pkg hunav_agent_manager ;;
    ros2_tracing)
      # tracetools built with LTTng reports "Tracing enabled"; the binary package does not.
      command -v lttng >/dev/null 2>&1 && has_pkg tracetools \
        && ros2 run tracetools status 2>/dev/null | grep -qi "tracing enabled" ;;
    tc_netem)
      command -v tc >/dev/null 2>&1 ;;
    onboard_computer | isaac_sim)
      return 2 ;;
    *)
      return 1 ;;
  esac
}

missing=0
while read -r kind name status; do
  [ "$kind" = "COMPONENT" ] || continue
  observe "$name"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    seen="yes"
  elif [ "$rc" -eq 2 ]; then
    seen="n/a"
  else
    seen="no"
  fi
  echo "$name $status $seen"
  if [ "$status" = "available" ] && [ "$seen" = "no" ]; then
    missing=$((missing + 1))
  fi
done <<<"$record_lines"

if python3 -c "import ralmon" >/dev/null 2>&1; then
  echo "# info: import ralmon works (informational only)" >&2
else
  echo "# info: import ralmon does not work here (informational only)" >&2
fi
echo "# info: ROS_DISTRO=$ROS_DISTRO python=$(python3 --version 2>&1)" >&2

if [ "$missing" -gt 0 ]; then
  echo "# $missing component(s) recorded as available are not observed" >&2
  exit 1
fi
exit 0
