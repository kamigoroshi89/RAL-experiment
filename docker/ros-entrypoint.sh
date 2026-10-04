#!/usr/bin/env bash
# Source the ROS 2 environment, then run the command.
set -e
source /opt/ros/jazzy/setup.bash
exec "$@"
