#!/usr/bin/env bash
# Source the ROS 2 environment (Humble, ADR-042), then the overlay with the sources built from
# ros2/sim.repos (tracetools with LTTng, hospital world), then run the command.
set -e
source /opt/ros/humble/setup.bash
if [ -f /opt/ralmon_overlay/install/setup.bash ]; then
  source /opt/ralmon_overlay/install/setup.bash
fi
exec "$@"
