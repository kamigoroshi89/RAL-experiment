"""Placeholders for public names whose owner task is not done (decision D1 of WS05).

Each placeholder imports, carries ``__ralmon_stub_owner__`` and fails loudly when used.
The owner task moves its names to a real module and deletes them from this file.

``ralmon.benchmark`` has no placeholder left: WS04-T11 moved ``generate_benchmark`` and ``load_benchmark`` to
``ralmon.benchmark.builder``.
"""

from __future__ import annotations
