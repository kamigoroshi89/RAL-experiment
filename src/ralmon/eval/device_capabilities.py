"""The extractor's device capabilities from the manifest of a benchmark (WS04-T18, I3 of the review).

A benchmark records its device profile in ``manifest.settings["device_profile"]`` (``ralmon.benchmark.device_profile``).
The run that reads the benchmark must declare the SAME facts to the evidence extractor: the display resolution the
generator rounded the cuff readings to (``DeviceCapabilities.cuff_resolution``; ``None`` for a benchmark built without
rounding, never a default), whether the dispenser senses its content, the nodes whose driver reports ``diagnostics``,
and which devices authenticate. ``device_capabilities_from_manifest`` builds exactly that part of the profile; every
other capability (sequence numbers, clocks, error codes, status reports, the robot's) is not a fact of the manifest
and comes from the run's own declaration, passed as ``base``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

from ralmon.attribution import DeviceCapabilities, DeviceProfile

__all__ = ["device_capabilities_from_manifest"]

_CUFF = "cuff"
_DISPENSER = "dispenser"


def _section(source: Any) -> Mapping[str, Any]:
    """The ``device_profile`` mapping of a manifest, of its settings, or the mapping itself."""
    settings = getattr(source, "settings", source)
    if isinstance(settings, Mapping) and isinstance(
        settings.get("device_profile"), Mapping
    ):
        return settings["device_profile"]  # type: ignore[no-any-return]
    if isinstance(settings, Mapping) and "dispenser_content_sensing" in settings:
        return settings
    raise ValueError(
        "no device_profile section: pass a manifest, its settings or the device_profile mapping"
    )


def device_capabilities_from_manifest(
    source: Any, base: DeviceProfile | None = None
) -> DeviceProfile:
    """The extractor's ``DeviceProfile`` for a benchmark: what its manifest determines, completed over ``base``.

    ``source`` is a ``Manifest``, its ``settings`` or its ``device_profile`` section. The cuff gets
    ``cuff_resolution`` (the manifest's ``cuff_resolution_mmhg``, ``None`` when the benchmark is not rounded), the
    dispenser ``content_sensing``, every device of ``authenticating_devices`` ``authenticates``, and every device of
    ``driver.devices`` ``diagnostics`` (only for the profile ``driver_with_diagnostics``). A capability of ``base``
    that the manifest does not determine is kept.
    """
    section = _section(source)
    driver = section.get("driver")
    driven = set(driver.get("devices", ())) if isinstance(driver, Mapping) else set()
    authenticating = set(section.get("authenticating_devices", ()))
    resolution = section.get("cuff_resolution_mmhg")
    nodes = dict(base.nodes) if base is not None else {}
    declared: dict[str, dict[str, Any]] = {}
    for node in {_CUFF, _DISPENSER} | driven | authenticating:
        facts: dict[str, Any] = {
            "diagnostics": node in driven,
            "authenticates": node in authenticating,
        }
        if node == _CUFF:
            facts["cuff_resolution"] = None if resolution is None else float(resolution)
        if node == _DISPENSER:
            facts["content_sensing"] = bool(
                section.get("dispenser_content_sensing", False)
            )
        declared[node] = facts
    for node, facts in declared.items():
        current = nodes.get(node, DeviceCapabilities())
        nodes[node] = dataclasses.replace(current, **facts)
    return DeviceProfile(nodes)
