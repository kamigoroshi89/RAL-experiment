"""Placeholders for public names whose owner task is not done (decision D1 of WS05).

Each placeholder imports, carries ``__ralmon_stub_owner__`` and fails loudly when used.
The owner task moves its names to a real module and deletes them from this file. WS05-T04 moved the names of
the monitor core and WS05-T05 the forecasters; WS05-T08 moved ``build_calibration_episodes`` (to
``offline.py``) and ``StaleCalibratorError`` (to ``predictive.py``). No placeholder of ``ralmon.monitor`` remains.
"""

from __future__ import annotations
