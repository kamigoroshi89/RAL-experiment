"""Text helper shared by the modules of ``ralmon.spec``: bounded ``repr`` for error messages."""

from __future__ import annotations

# algorithmic: longest ``repr`` quoted in an error message, so that a hostile 1 MiB value cannot
# flood a log line
_MAX_SHOWN: int = 60


def show(value: object) -> str:
    """A short ``repr`` of ``value`` that never raises."""
    try:
        text = repr(value)
    except Exception:  # noqa: BLE001 - a repr that raises must not hide the real error
        text = f"<{type(value).__name__}>"
    if len(text) > _MAX_SHOWN:
        text = text[:_MAX_SHOWN] + "..."
    return text
