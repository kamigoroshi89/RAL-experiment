#!/usr/bin/env python3
"""Message-count probe for `tc netem` on a same-host DDS stream (WS07-T01, doc/availability.md).

Run a subscriber and a publisher as two processes of the same host, with and without a netem
qdisc on an interface, and compare the number of received messages with the number sent:

    netem_probe.py sub --seconds 16 &
    netem_probe.py pub --seconds 10 --rate 100

The topic uses the sensor-data QoS (best effort), so a dropped packet is a lost message and is
not retransmitted. It needs a sourced ROS 2 environment and no `ralmon` import.
"""

from __future__ import annotations

import argparse
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import Int64

TOPIC = "/netem_probe"


def run_pub(seconds: float, rate: float) -> None:
    rclpy.init()
    node = rclpy.create_node("netem_probe_pub")
    publisher = node.create_publisher(Int64, TOPIC, qos_profile_sensor_data)
    give_up = time.monotonic() + 30.0
    while publisher.get_subscription_count() == 0 and time.monotonic() < give_up:
        time.sleep(0.1)
    matched = publisher.get_subscription_count()
    total = int(seconds * rate)
    start = time.monotonic()
    for sent in range(total):
        message = Int64()
        message.data = sent
        publisher.publish(message)
        time.sleep(max(0.0, start + (sent + 1) / rate - time.monotonic()))
    print(f"pub matched_subscribers={matched} sent={total}", flush=True)
    node.destroy_node()
    rclpy.shutdown()


def run_sub(seconds: float) -> None:
    rclpy.init()
    node = rclpy.create_node("netem_probe_sub")
    seen: set[int] = set()
    node.create_subscription(
        Int64, TOPIC, lambda message: seen.add(message.data), qos_profile_sensor_data
    )
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        rclpy.spin_once(node, timeout_sec=0.1)
    print(f"sub received={len(seen)}", flush=True)
    node.destroy_node()
    rclpy.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["pub", "sub"])
    parser.add_argument("--seconds", type=float, required=True)
    parser.add_argument("--rate", type=float, default=100.0)
    args = parser.parse_args()
    if args.mode == "pub":
        run_pub(args.seconds, args.rate)
    else:
        run_sub(args.seconds)


if __name__ == "__main__":
    main()
